"""Smoke tests for the Phase 11 trac-convert CLI scaffold."""

import argparse

import pytest

from trac_mcp_server import __version__
from trac_mcp_server.cli.convert import build_parser, main


def test_build_parser_returns_parser():
    """build_parser() returns an ArgumentParser with prog=trac-convert."""
    parser = build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    assert parser.prog == "trac-convert"


def test_version_flag_prints_package_version(capsys):
    """--version exits 0 and prints the package version."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out
    assert "trac-convert" in captured.out


def test_help_flag_exits_zero_with_usage(capsys):
    """--help exits 0 and includes usage and program name."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out
    assert "trac-convert" in captured.out


def test_no_args_returns_not_implemented_exit_code(capsys):
    """Invocation with no args returns exit code 2 with not-yet-implemented message."""
    result = main([])
    assert result == 2
    captured = capsys.readouterr()
    assert "not yet implemented" in captured.err
