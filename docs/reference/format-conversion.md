# Format Conversion

## Overview

The Trac MCP Server automatically converts between Markdown and TracWiki formats:

- **Markdown -> TracWiki:** When creating/updating wiki pages and ticket descriptions
- **TracWiki -> Markdown:** When reading wiki pages and ticket content

## Conversion Direction by Operation

| Operation | Input Format | Output Format | Conversion |
|-----------|--------------|---------------|------------|
| `wiki_create` | Markdown | TracWiki | Auto-converts content |
| `wiki_update` | Markdown | TracWiki | Auto-converts content |
| `wiki_get` | TracWiki | Markdown | Auto-converts (unless `raw=true`) |
| `ticket_create` | Markdown | TracWiki | Auto-converts description |
| `ticket_get` | TracWiki | Markdown | Auto-converts (unless `raw=true`) |
| `ticket_update` | Markdown | TracWiki | Auto-converts comment |

## The `raw` Parameter

Use `raw=true` to skip format conversion and get/send content in original TracWiki format:

```json
{
  "name": "wiki_get",
  "arguments": {
    "page_name": "WikiStart",
    "raw": true
  }
}
```

## ConversionResult Structure

```python
@dataclass
class ConversionResult:
    text: str           # Converted text output
    source_format: str  # 'markdown', 'tracwiki', or 'unknown'
    target_format: str  # 'markdown' or 'tracwiki'
    converted: bool     # True if conversion performed
    warnings: list[str] # Warnings about lossy conversions
```

## Language Mappings for Code Blocks

Code block languages are mapped between formats:

| Markdown | TracWiki | Notes |
|----------|----------|-------|
| `bash`, `shell`, `zsh` | `sh` | Shell variants normalize to `sh` |
| `js` | `javascript` | Short form expanded |
| `ts` | `typescript` | Short form expanded |
| `c++` | `cpp` | Normalized name |
| `text`, `plaintext`, `plain` | `text` | Text variants normalized |

**Identity languages (unchanged):** `python`, `java`, `c`, `ruby`, `go`, `rust`, `sql`, `html`, `css`, `xml`, `json`, `yaml`, `diff`, etc.

## Conversion Warnings

The converter detects potentially lossy conversions and returns warnings:

**Markdown to TracWiki:**
- HTML tags (may not render correctly)
- TOC macros (use `[[PageOutline]]` instead)

**TracWiki to Markdown:**
- Unknown macros (preserved as `[MACRO: Name]` notation) -- only genuine
  macro names (a fixed allowlist of Trac's built-ins, e.g. `TOC`,
  `PageOutline`, `RecentChanges`) or `[[Name(args)]]` forms carrying explicit
  arguments are treated as macros. A bare `[[PageName]]` or
  `[[PageName|Label]]` is a WikiLink and converts to a real Markdown link
  instead (see Links below) -- unrecognized macro names from third-party
  plugins that take no arguments will be misread as links, since the
  converter has no access to the live Trac instance's macro registry.
- Definition lists (converted to bold text)
- Table cell spanning (merged into single cell)
- Multi-line table rows (joined into single line)
- Processor-based table cells (converted to plain text)
- TracLinks (preserved but not clickable)

## Markup Conversion Examples

**Headings:**
```
Markdown:  # Heading 1
TracWiki:  = Heading 1 =

Markdown:  ## Heading 2
TracWiki:  == Heading 2 ==
```

**Bold/Italic:**
```
Markdown:  **bold** and *italic*
TracWiki:  '''bold''' and ''italic''
```

**Code Blocks:**
```
Markdown:  ```python
           print("hello")
           ```

TracWiki:  {{{#!python
           print("hello")
           }}}
```

**Links:**
```
Markdown:  [Link Text](https://example.com)
TracWiki:  [https://example.com Link Text]

Markdown:  [Wiki Link](WikiPage)
TracWiki:  [wiki:WikiPage Wiki Link]

Markdown:  [Wiki Link](wiki:WikiPage)
TracWiki:  [wiki:WikiPage Wiki Link]

TracWiki:  [[WikiPage]]
Markdown:  [WikiPage](wiki:WikiPage)

TracWiki:  [[WikiPage|Wiki Link]]
Markdown:  [Wiki Link](wiki:WikiPage)
```

> **Note:** Double-bracket `[[WikiPage]]` / `[[WikiPage|Label]]` links only
> ever appear on the TracWiki-to-Markdown side; `markdown_to_tracwiki`
> always emits the single-bracket `[wiki:WikiPage ...]` form shown above, so
> a `wiki_get` -> edit -> `wiki_update` round-trip normalizes double-bracket
> links to single-bracket ones rather than preserving the original syntax.

> **Note:** Link targets that already carry a TracLink resolver prefix -- `wiki:`, `ticket:`, `milestone:`, `source:`, `attachment:`, `changeset:`, and the rest of Trac's built-in resolvers -- are emitted verbatim, not prefixed a second time. This is the form `tracwiki_to_markdown` produces, so a `wiki_get` -> edit -> `wiki_update` round-trip that leaves existing links untouched preserves them exactly. Targets without a prefix (`WikiPage`, `Planning/Phases/Phase01`) get `wiki:` added.

> **Note:** Non-URL-shaped "links" (URL portion contains a `:` that is not a known TracLink resolver, e.g. sentinel tokens like `[auto-pm: state NEEDS_CODE]` or `[label](foo:bar)`) are emitted verbatim as Markdown rather than wrapped as TracWiki wiki links. This preserves machine-readable state markers through round-trip conversion.

**Images:**
```
Markdown:  ![alt](image.png)
TracWiki:  [[Image(image.png)]]
```

**Lists:**
```
Markdown:  - Item 1
           - Item 2
             - Nested

TracWiki:   * Item 1
            * Item 2
              * Nested
```

---

[Back to Reference Overview](overview.md)
