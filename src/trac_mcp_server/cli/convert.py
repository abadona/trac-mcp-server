"""trac-convert CLI entry point.

This module is the Phase 11 scaffold for the ``trac-convert`` binary.
Phases 12-17 layer format flags, I/O modes, stdin/stdout wiring,
file I/O, clipboard I/O, converter options, and error handling
on top of this skeleton.
"""

import argparse
import sys
from pathlib import Path

import pyperclip

from .. import __version__
from ..converters import (
    detect_format_heuristic,
    tracwiki_to_markdown,
)
from ..converters.common import ConversionResult
from ..converters.markdown_to_tracwiki import convert_with_warnings

# ---------------------------------------------------------------------------
# Exit-code constants
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1     # I/O, clipboard, mutual-exclusion
EXIT_USAGE_ERROR = 2       # argparse default (not raised by us directly)
EXIT_CONVERSION_ERROR = 3  # exception raised inside convert_text()


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
    parser.add_argument(
        "input_file",
        nargs="?",
        default=None,
        metavar="FILE",
        help="Input file. Reads from stdin if omitted.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_file",
        default=None,
        metavar="FILE",
        help="Output file. Writes to stdout if omitted.",
    )
    parser.add_argument(
        "--from-clipboard",
        dest="from_clipboard",
        action="store_true",
        default=False,
        help=(
            "Read input from the system clipboard instead of"
            " stdin or FILE."
        ),
    )
    parser.add_argument(
        "--to-clipboard",
        dest="to_clipboard",
        action="store_true",
        default=False,
        help=(
            "Write output to the system clipboard instead of"
            " stdout or --output FILE."
        ),
    )
    parser.add_argument(
        "--heading-anchors",
        dest="heading_anchors",
        choices=("on", "off"),
        default="on",
        help=(
            "Emit explicit #slug anchors on TracWiki headings"
            " (md → tracwiki only). Default: on."
        ),
    )
    parser.add_argument(
        "--unknown-macros",
        dest="unknown_macros",
        choices=("bracket", "preserve", "drop"),
        default="bracket",
        help=(
            "How to render unknown TracWiki macros"
            " (tracwiki → md only). bracket = [MACRO: Name],"
            " preserve = leave [[Name]] literal, drop = omit."
            " Default: bracket."
        ),
    )
    parser.add_argument(
        "-q",
        "--quiet",
        dest="quiet",
        action="store_true",
        default=False,
        help="Suppress warning: lines on stderr. Errors still shown.",
    )
    return parser


def convert_text(
    text: str,
    source_format: str,
    target_format: str,
    *,
    heading_anchors: bool = True,
    unknown_macros: str = "bracket",
) -> ConversionResult:
    """Convert text between Markdown and TracWiki.

    source_format: "md", "tracwiki", or "auto".
    target_format: "md" or "tracwiki".
    heading_anchors: forwarded to convert_with_warnings() for md→tracwiki.
        Ignored on the tracwiki→md direction.
    unknown_macros: forwarded to tracwiki_to_markdown() for tracwiki→md.
        Ignored on the md→tracwiki direction.

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
        return convert_with_warnings(
            text, heading_anchors=heading_anchors
        )
    return tracwiki_to_markdown(text, unknown_macros=unknown_macros)  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the CLI.

    Reads from --from-clipboard, positional FILE, or stdin (in that
    order of precedence), dispatches via convert_text(), writes
    result.text verbatim to --to-clipboard, --output FILE, or stdout
    (in that order of precedence), emits result.warnings to stderr one
    line each prefixed with ``warning: ``, and returns an integer exit
    code for ``sys.exit``.

    Exit codes:
    - 0 (EXIT_OK): success (including pass-through with no conversion).
    - 1 (EXIT_RUNTIME_ERROR): I/O error, clipboard failure, or
      mutual-exclusion violation; a ``trac-convert: <what>: <reason>``
      message is written to stderr.
    - 2 (EXIT_USAGE_ERROR): invalid flags or missing required argument;
      raised internally by argparse (not by this function directly).
    - 3 (EXIT_CONVERSION_ERROR): the converter raised an unexpected
      exception; a ``trac-convert: conversion failed: <reason>`` message
      is written to stderr (no traceback).

    Note on direction-scoped flags: --heading-anchors only affects the
    md→tracwiki direction and is silently ignored for tracwiki→md (and
    vice-versa for --unknown-macros).  This is intentional — --from auto
    may resolve either way at runtime, so mutual-exclusion checks are not
    applied.
    """
    args = build_parser().parse_args(argv)

    # --- mutual exclusion validation ---
    if args.from_clipboard and args.input_file is not None:
        sys.stderr.write(
            "trac-convert: --from-clipboard and FILE are"
            " mutually exclusive\n"
        )
        return EXIT_RUNTIME_ERROR
    if args.to_clipboard and args.output_file is not None:
        sys.stderr.write(
            "trac-convert: --to-clipboard and --output are"
            " mutually exclusive\n"
        )
        return EXIT_RUNTIME_ERROR

    # --- read input ---
    if args.from_clipboard:
        try:
            text = pyperclip.paste()
        except pyperclip.PyperclipException as e:
            sys.stderr.write(
                f"trac-convert: clipboard read failed: {e}\n"
            )
            return EXIT_RUNTIME_ERROR
    elif args.input_file is not None:
        try:
            text = Path(args.input_file).read_text(encoding="utf-8")
        except OSError as e:
            sys.stderr.write(
                f"trac-convert: cannot read input file:"
                f" {args.input_file}: {e.strerror or e}\n"
            )
            return EXIT_RUNTIME_ERROR
    else:
        text = sys.stdin.read()

    # --- convert ---
    # Translate --heading-anchors on|off to bool before forwarding.
    heading_anchors_bool = args.heading_anchors == "on"
    try:
        result = convert_text(
            text,
            args.source_format,
            args.target_format,
            heading_anchors=heading_anchors_bool,
            unknown_macros=args.unknown_macros,
        )
    except Exception as e:
        sys.stderr.write(f"trac-convert: conversion failed: {e}\n")
        return EXIT_CONVERSION_ERROR

    # --- write output ---
    if args.to_clipboard:
        try:
            pyperclip.copy(result.text)
        except pyperclip.PyperclipException as e:
            sys.stderr.write(
                f"trac-convert: clipboard write failed: {e}\n"
            )
            return EXIT_RUNTIME_ERROR
    elif args.output_file is not None:
        try:
            Path(args.output_file).write_text(
                result.text, encoding="utf-8"
            )
        except OSError as e:
            sys.stderr.write(
                f"trac-convert: cannot write output file:"
                f" {args.output_file}: {e.strerror or e}\n"
            )
            return EXIT_RUNTIME_ERROR
    else:
        sys.stdout.write(result.text)

    # --- warnings (emitted after write, preserving Phase 13 ordering) ---
    if not args.quiet:
        for warning in result.warnings:
            sys.stderr.write(f"warning: {warning}\n")

    return EXIT_OK


def run() -> None:
    """Console scripts entry point — delegates to main()."""
    sys.exit(main())
