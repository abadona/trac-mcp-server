"""trac-convert CLI entry point.

This module is the Phase 11 scaffold for the ``trac-convert`` binary.
Phases 12-17 layer format flags, I/O modes, stdin/stdout wiring,
file I/O, clipboard support, converter options, and error handling
on top of this skeleton.
"""

import argparse
import sys

from .. import __version__
from ..converters import (
    detect_format_heuristic,
    tracwiki_to_markdown,
)
from ..converters.common import ConversionResult
from ..converters.markdown_to_tracwiki import convert_with_warnings


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser.

    Kept pure (no side effects) so tests can inspect it directly.
    """
    parser = argparse.ArgumentParser(
        prog="trac-convert",
        description="Convert between Markdown and TracWiki formats.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"trac-convert {__version__}",
    )
    parser.add_argument(
        "--from",
        dest="source_format",
        choices=("md", "tracwiki", "auto"),
        default="auto",
        help=(
            "Source format. 'auto' (default) detects from content "
            "using heuristics."
        ),
    )
    parser.add_argument(
        "--to",
        dest="target_format",
        choices=("md", "tracwiki"),
        required=True,
        help="Target format. Required.",
    )
    return parser


def convert_text(
    text: str,
    source_format: str,
    target_format: str,
) -> ConversionResult:
    """Convert text between Markdown and TracWiki.

    source_format: "md", "tracwiki", or "auto".
    target_format: "md" or "tracwiki".
    Returns a ConversionResult (may be a pass-through with
    converted=False when source and target resolve to the same
    format).
    """
    _ALIAS = {"md": "markdown", "tracwiki": "tracwiki"}

    if source_format == "auto":
        source = detect_format_heuristic(text)
    else:
        source = _ALIAS[source_format]

    target = _ALIAS[target_format]

    if source == target:
        return ConversionResult(
            text=text,
            source_format=source,
            target_format=target,
            converted=False,
            warnings=[],
        )
    if source == "markdown" and target == "tracwiki":
        return convert_with_warnings(text)
    return tracwiki_to_markdown(text)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the CLI.

    Reads all of stdin, dispatches via convert_text(), writes
    result.text verbatim to stdout (no added newline), emits
    result.warnings to stderr one line each prefixed with
    ``warning: ``, and returns 0 on success (including pass-through).

    Returns an integer exit code for ``sys.exit``.
    """
    args = build_parser().parse_args(argv)
    text = sys.stdin.read()
    result = convert_text(text, args.source_format, args.target_format)
    sys.stdout.write(result.text)
    for warning in result.warnings:
        sys.stderr.write(f"warning: {warning}\n")
    return 0


def run() -> None:
    """Console scripts entry point — delegates to main()."""
    sys.exit(main())
