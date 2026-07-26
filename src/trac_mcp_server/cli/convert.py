"""trac-convert CLI entry point.

This module is the Phase 11 scaffold for the ``trac-convert`` binary.
Phases 12-17 layer format flags, I/O modes, stdin/stdout wiring,
file I/O, clipboard support, converter options, and error handling
on top of this skeleton.
"""

import argparse
import sys

from .. import __version__
from ..converters import auto_convert  # noqa: F401 — Phase 12 consumer


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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the CLI.

    Returns an integer exit code for ``sys.exit``.
    """
    build_parser().parse_args(argv)
    print(
        "trac-convert: conversion not yet implemented"
        " (Phase 11 scaffold)",
        file=sys.stderr,
    )
    return 2


def run() -> None:
    """Console scripts entry point — delegates to main()."""
    sys.exit(main())
