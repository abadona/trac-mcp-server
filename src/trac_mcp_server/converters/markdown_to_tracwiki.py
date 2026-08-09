"""Markdown to TracWiki conversion using mistune AST rendering."""

import re
from typing import Any

import mistune

from .common import ConversionResult, markdown_to_tracwiki_lang

# GitHub-style heading slug, mirrored from auto-pm's docs_linkcheck rule
# (lowercase, whitespace runs → single dash, drop everything that isn't
# alphanumeric / dash / underscore). Inline TracWiki markers produced by
# the renderer pipeline (`backticks`, `'''bold'''`, `''italic''`) are
# stripped before the rule runs so the slug derives from the *visible*
# heading text, not its render-side decoration.
_SLUG_DROP_RE = re.compile(r"[^\w\- ]+")
_SLUG_WS_RE = re.compile(r"\s+")

# TracLink resolvers that Trac understands natively as the target of
# `[target text]`.  Deliberately an explicit allowlist rather than
# "anything scheme-shaped": non-URL sentinels such as ``auto-pm:`` or
# ``foo:bar`` must stay literal (ticket #8), while real TracLinks that
# `tracwiki_to_markdown` emits as ``[text](wiki:Page)`` must survive a
# push back through this converter unchanged (ticket #17).
_TRACLINK_SCHEMES = frozenset(
    {
        "attachment",
        "browser",
        "changeset",
        "comment",
        "diff",
        "export",
        "htdocs",
        "log",
        "milestone",
        "query",
        "raw-attachment",
        "report",
        "repos",
        "search",
        "source",
        "ticket",
        "timeline",
        "wiki",
    }
)
# scheme:target — target must be non-empty, so a bare ``auto-pm:``
# sentinel never matches even if its scheme were listed above.
_TRACLINK_RE = re.compile(
    r"(?P<scheme>[A-Za-z][\w+.-]*):(?P<target>\S.*)\Z"
)


def _heading_slug(rendered_text: str) -> str:
    """Return the GitHub-style anchor slug for a rendered heading text.

    Used by :meth:`TracWikiRenderer.heading` to emit an explicit Trac
    heading anchor (``== Heading == #heading``) so cross-page links
    written as Markdown ``[text](#heading)`` resolve after conversion.
    Without this, Trac auto-generates a heading id by stripping
    whitespace + non-alphanumerics WITHOUT lowercasing — ``#Heading``
    or ``#WikiTaskIndexPageSchema`` — which never matches the
    Markdown source's ``#heading`` / ``#wiki-task-index-page-schema``.
    """
    cleaned = rendered_text
    # Strip TracWiki inline markers our own renderer emits before us.
    cleaned = (
        cleaned.replace("'''", "").replace("''", "").replace("`", "")
    )
    cleaned = _SLUG_DROP_RE.sub("", cleaned)
    cleaned = cleaned.strip().lower()
    cleaned = _SLUG_WS_RE.sub("-", cleaned)
    return cleaned


class TracWikiRenderer(mistune.BaseRenderer):
    """Renderer that converts Markdown AST to TracWiki syntax."""

    NAME = "tracwiki"

    def __init__(self, heading_anchors: bool = False):
        """Initialize renderer with state tracking for table rendering.

        Args:
            heading_anchors: When True, emit an explicit ``#slug`` anchor on
                each heading so Markdown-source cross-references resolve after
                conversion.  Default is False: plain ``= Heading =`` syntax,
                because Trac auto-generates heading anchors and explicit slugs
                like ``#4-non-goals`` cause ``#4`` to be misread as a ticket
                reference.
        """
        super().__init__()
        self._heading_anchors = heading_anchors
        # Track column alignments for current table
        self._table_alignments: list[str | None] = []

    def text(self, text: str) -> str:
        """Render plain text."""
        return text

    def emphasis(self, text: str) -> str:
        """Render italic text (single emphasis)."""
        return f"''{text}''"

    def strong(self, text: str) -> str:
        """Render bold text (double emphasis)."""
        return f"'''{text}'''"

    def codespan(self, text: str) -> str:
        """Render inline code."""
        return f"`{text}`"

    def linebreak(self) -> str:
        """Render line break."""
        return "[[BR]]\n"

    def softbreak(self) -> str:
        """Render soft break."""
        return "\n"

    def blank_line(self) -> str:
        """Render blank line."""
        return ""

    def heading(self, text: str, level: int, **attrs) -> str:
        """Render heading.

        TracWiki heading syntax uses leading = markers (trailing = optional).
        We produce the canonical form with trailing markers AND an explicit
        anchor (``#slug``) so Markdown-source cross-references like
        ``[text](#some-heading)`` resolve after conversion. Trac's default
        heading id (whitespace + punctuation stripped, case preserved) does
        NOT match the Markdown slug rule (lowercase + whitespace→dash);
        emitting an explicit anchor makes the Markdown slug authoritative.

            = H1 = #h1
            == H2 == #h2

        If the heading text slugifies to empty (e.g. punctuation-only),
        the explicit anchor is omitted and Trac's default id applies.

        When ``self._heading_anchors`` is False (set via ``--heading-anchors
        off`` on the CLI), the slug computation is skipped entirely and plain
        ``= Heading =`` syntax is emitted — useful when the caller does not
        need Markdown cross-reference compatibility.
        """
        marker = "=" * level
        # --heading-anchors off: skip slug computation, emit plain heading.
        if not self._heading_anchors:
            return f"{marker} {text} {marker}\n"
        slug = _heading_slug(text)
        if slug:
            return f"{marker} {text} {marker} #{slug}\n"
        return f"{marker} {text} {marker}\n"

    def paragraph(self, text: str) -> str:
        """Render paragraph."""
        return f"{text}\n\n"

    def block_text(self, text: str) -> str:
        """Render block text."""
        return text

    def block_code(self, code: str, info: str | None = None) -> str:
        """Render code block.

        TracWiki syntax:
        {{{#!language
        code
        }}}

        Language identifiers are mapped from Markdown to TracWiki equivalents
        (e.g., 'bash' -> 'sh').
        """
        code = code.rstrip("\n")
        if info:
            # Map Markdown language to TracWiki processor directive
            tracwiki_lang = markdown_to_tracwiki_lang(info)
            return f"{{{{{{#!{tracwiki_lang}\n{code}\n}}}}}}\n"
        else:
            return f"{{{{{{\n{code}\n}}}}}}\n"

    def block_quote(self, text: str) -> str:
        """Render blockquote.

        TracWiki uses two-space indent for quotes.
        """
        lines = text.rstrip("\n").split("\n")
        quoted = "\n".join(f"  {line}" for line in lines)
        return f"{quoted}\n"

    def block_html(self, html: str) -> str:
        """Render block HTML (pass through)."""
        return html + "\n"

    def block_error(self, text: str) -> str:
        """Render block error."""
        return text

    def thematic_break(self) -> str:
        """Render horizontal rule."""
        return "----\n"

    def list(self, text: str, ordered: bool, **attrs) -> str:
        """Render list."""
        return text

    def list_item(self, text: str) -> str:
        """Render list item.

        TracWiki uses space prefix:
        Unordered: ' * item'
        Ordered: ' 1. item'
        Nested: ' * * nested'

        The nesting is handled by tracking depth in the render_token override.
        """
        # Clean up extra newlines from nested content
        text = text.rstrip("\n")
        return text + "\n"

    def link(self, text: str, url: str, title=None) -> str:
        """Render link.

        Markdown: [text](url)
        TracWiki: [url text] for external URLs
                  [url text] for already-resolved TracLinks (wiki:, ticket:, ...)
                  [wiki:page text] for internal wiki pages

        Refuses non-URL-shaped "links" (e.g., sentinels like ``auto-pm:``)
        so state-marker syntax such as ``[auto-pm: state NEEDS_CODE]``
        survives round-tripping instead of getting mangled into a broken
        TracWiki link.
        """
        # External URLs - no prefix needed
        if url.startswith(("http://", "https://", "ftp://", "mailto:")):
            return f"[{url} {text}]"

        # Anchor-only links - keep as-is
        if url.startswith("#"):
            return f"[{url} {text}]"

        # Already-resolved TracLinks (`wiki:Page`, `ticket:42`,
        # `source:trunk/f.py`, ...) are valid TracWiki targets as they
        # stand — emit them verbatim. This is what `tracwiki_to_markdown`
        # produces, so a wiki_get -> wiki_update round-trip that leaves
        # existing links untouched no longer corrupts them (ticket #17).
        traclink = _TRACLINK_RE.match(url)
        if (
            traclink
            and traclink.group("scheme").lower() in _TRACLINK_SCHEMES
        ):
            # `<wiki:Page>` autolinks arrive with text == url; `[target]`
            # is the tidier equivalent of `[target target]`.
            if text == url:
                return f"[{url}]"
            return f"[{url} {text}]"

        # Refuse non-URL-shaped "links". A real URL or wiki link either
        # starts with a known scheme (handled above), is an anchor
        # (handled above), or is a wiki-page-shaped path. Wiki page names
        # never contain ":" — Trac reserves it for the resolvers listed in
        # _TRACLINK_SCHEMES — so any ":" still present here means the url
        # is a sentinel like "auto-pm:" or "foo:bar", not a page path.
        # Emit the original Markdown link syntax verbatim so the text is
        # preserved downstream rather than wrapped as a broken wiki link.
        if ":" in url:
            return f"[{text}]({url})"

        # Internal wiki links - add wiki: prefix
        return f"[wiki:{url} {text}]"

    def image(self, text: str, url: str, title=None) -> str:
        """Render image.

        Markdown: ![alt](url)
        TracWiki: [[Image(url)]]
        """
        return f"[[Image({url})]]"

    def newline(self) -> str:
        """Render newline."""
        return ""

    def inline_html(self, html: str) -> str:
        """Render inline HTML (pass through)."""
        return html

    # Table rendering methods for GFM tables
    def table(self, text: str) -> str:
        """Render complete table.

        TracWiki tables use ||cell|| syntax.
        Tables are block elements and should be separated from other content.
        """
        # Reset alignments after table is complete
        self._table_alignments = []
        # Table is a block element, add trailing newlines for paragraph separation
        return text.rstrip("\n") + "\n\n"

    def table_head(self, text: str) -> str:
        """Render table header section.

        Header cells are concatenated by mistune with || between them.
        We strip the trailing || from cells and wrap the whole row.
        """
        # Cells are concatenated with || between them (each cell adds trailing ||)
        # Remove the trailing || and wrap with || on both ends
        text = text.rstrip("|")
        return f"||{text}||\n"

    def table_body(self, text: str) -> str:
        """Render table body section."""
        return text

    def table_row(self, text: str) -> str:
        """Render table row.

        Body cells are concatenated by mistune with || between them.
        We strip the trailing || from cells and wrap the whole row.
        """
        # Cells are concatenated with || between them (each cell adds trailing ||)
        # Remove the trailing || and wrap with || on both ends
        text = text.rstrip("|")
        return f"||{text}||\n"

    def table_cell(
        self, text: str, align: str | None = None, head: bool = False
    ) -> str:
        """Render table cell.

        Args:
            text: Cell content
            align: Alignment ('left', 'center', 'right', or None)
            head: True if this is a header cell

        TracWiki alignment is determined by whitespace:
        - Left aligned: ||text || (text flush left, space right)
        - Right aligned: || text|| (space left, text flush right)
        - Centered: || text || (space both sides)

        TracWiki header cells use ||= Header =|| syntax.

        Note: Cells are concatenated by mistune. We add || after each cell,
        and table_row/table_head will strip the trailing || and wrap properly.
        """
        # For header cells, wrap with = markers and apply alignment
        if head:
            # Handle empty cells
            if not text:
                cell_content = ""
            else:
                match align:
                    case "left":
                        cell_content = f"={text} ="
                    case "right":
                        cell_content = f"= {text}="
                    case "center":
                        cell_content = f"= {text} ="
                    case _:
                        # No alignment: minimal spacing
                        cell_content = f"={text}="
        else:
            # Apply TracWiki alignment via whitespace for body cells
            match align:
                case "left":
                    # Left aligned: text flush left, space on right
                    cell_content = f"{text} "
                case "right":
                    # Right aligned: space on left, text flush right
                    cell_content = f" {text}"
                case "center":
                    # Centered: space on both sides
                    cell_content = f" {text} "
                case _:
                    # No alignment: just the text
                    cell_content = text

        # Add || separator after cell (will be concatenated with next cell)
        return cell_content + "||"

    def render_token(self, token: dict[str, Any], state) -> str:
        """Override token rendering to handle list depth tracking and extract text/attrs."""
        # Get the token type
        token_type: str = token.get("type") or ""
        func = self._get_method(token_type)
        attrs = token.get("attrs")

        match token_type:
            # For lists, track ordered state and reset item counter
            case "list":
                ordered = token.get("attrs", {}).get("ordered", False)
                depth = getattr(
                    state, "list_depth", -1
                )  # Start at -1 so first level is 0

                # Save current state
                old_ordered = getattr(state, "list_ordered", False)
                old_depth = depth
                old_item_num = getattr(state, "list_item_num", 0)

                # Set new state
                state.list_ordered = ordered  # type: ignore[attr-defined]  # mistune BlockState dynamic attr
                state.list_depth = depth + 1  # type: ignore[attr-defined]  # mistune BlockState dynamic attr
                state.list_item_num = 0  # type: ignore[attr-defined]  # mistune BlockState dynamic attr

                # Render children
                if "children" in token:
                    text = self.render_tokens(token["children"], state)
                else:
                    text = ""

                # Restore state
                state.list_ordered = old_ordered  # type: ignore[attr-defined]  # mistune BlockState dynamic attr
                state.list_depth = old_depth  # type: ignore[attr-defined]  # mistune BlockState dynamic attr
                state.list_item_num = old_item_num  # type: ignore[attr-defined]  # mistune BlockState dynamic attr

                # Call list renderer with text and ordered flag
                if attrs:
                    return func(text, **attrs)
                else:
                    return func(text, False)

            # For list items, we need to determine depth and type
            case "list_item":
                # Track list depth from state
                depth = getattr(state, "list_depth", 0)

                # Check if parent list is ordered
                ordered = getattr(state, "list_ordered", False)

                # Increment and get item number
                item_num = getattr(state, "list_item_num", 0) + 1
                state.list_item_num = item_num  # type: ignore[attr-defined]  # mistune BlockState dynamic attr

                # Determine marker
                if ordered:
                    marker = f"{item_num}."
                else:
                    marker = "*"

                # Render children - check if there's a nested list
                if "children" in token:
                    children = token["children"]
                    # Separate inline content from nested lists
                    inline_parts = []
                    nested_lists = []

                    for child in children:
                        if child.get("type") == "list":
                            nested_lists.append(child)
                        else:
                            inline_parts.append(child)

                    # Render inline content
                    if inline_parts:
                        text = self.render_tokens(inline_parts, state)
                    else:
                        text = ""

                    # Render nested lists (they handle their own newlines)
                    if nested_lists:
                        nested_text = self.render_tokens(
                            nested_lists, state
                        )
                        # The nested list adds its items directly, don't add to text
                        nested_text = nested_text.rstrip("\n")
                    else:
                        nested_text = ""
                else:
                    text = token.get("raw", "")
                    nested_text = ""

                # Build TracWiki list item with proper depth
                # TracWiki uses indentation for nesting: 1 space for level 0, +2 spaces per level
                # Depth 0: " * item" (1 space + marker)
                # Depth 1: "   * item" (3 spaces + marker)
                # Depth 2: "     * item" (5 spaces + marker)
                indent = " " * (depth * 2 + 1)
                prefix = f"{indent}{marker}"

                text = text.rstrip("\n")

                # Combine text and nested list
                if nested_text:
                    return f"{prefix} {text}\n{nested_text}\n"
                else:
                    return f"{prefix} {text}\n"

            # Default rendering: extract text from raw, text, or children, pass attrs
            case _:
                if "raw" in token:
                    text = token["raw"]
                elif "text" in token:
                    # Used by table_cell tokens
                    text = token["text"]
                elif "children" in token:
                    text = self.render_tokens(token["children"], state)
                else:
                    # No text content, just call with attrs
                    if attrs:
                        return func(**attrs)
                    else:
                        return func()

                # Call function with text and attrs
                if attrs:
                    return func(text, **attrs)
                else:
                    return func(text)


def markdown_to_tracwiki(
    markdown_text: str, *, heading_anchors: bool = False
) -> str:
    """
    Convert Markdown text to TracWiki format.

    Args:
        markdown_text: Markdown formatted text
        heading_anchors: When True, each heading includes an explicit
            ``#slug`` anchor for Markdown cross-reference compatibility.
            Default is False: Trac auto-generates anchors and explicit slugs
            can be misread as ticket references (e.g. ``#4-non-goals`` → #4).

    Returns:
        TracWiki formatted text
    """
    # Create renderer and parser with table plugin enabled
    renderer = TracWikiRenderer(heading_anchors=heading_anchors)
    markdown = mistune.create_markdown(
        renderer=renderer, plugins=["table"]
    )

    # Parse and render
    result: str = markdown(markdown_text)  # type: ignore[assignment]

    # Clean up extra newlines (but preserve double newlines for paragraph separation)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = result.rstrip("\n")

    return result


def convert_with_warnings(
    markdown_text: str, *, heading_anchors: bool = False
) -> ConversionResult:
    """
    Convert Markdown to TracWiki and detect unsupported features.

    Args:
        markdown_text: Markdown formatted text
        heading_anchors: Forwarded to :func:`markdown_to_tracwiki`.  When
            True, headings include an explicit ``#slug`` anchor for
            Markdown cross-reference compatibility.  Default is False.

    Returns:
        ConversionResult with TracWiki text and any warnings
    """
    warnings = []

    # Tables are now fully supported via mistune table plugin

    # Check for HTML tags
    if re.search(r"<[a-zA-Z][^>]*>", markdown_text):
        warnings.append(
            "HTML tags detected - these may not render correctly in TracWiki."
        )

    # Check for TOC macros
    if re.search(r"\[TOC\]|\[\[TOC\]\]", markdown_text, re.IGNORECASE):
        warnings.append(
            "TOC macro detected - use [[PageOutline]] in TracWiki instead."
        )

    # Convert the markdown
    tracwiki = markdown_to_tracwiki(
        markdown_text, heading_anchors=heading_anchors
    )

    return ConversionResult(
        text=tracwiki,
        source_format="markdown",
        target_format="tracwiki",
        converted=True,
        warnings=warnings,
    )
