"""Smoke tests for the trac-convert CLI scaffold (Phase 11 + 12)."""

import argparse

import pytest

from trac_mcp_server import __version__
from trac_mcp_server.cli.convert import (
    build_parser,
    convert_text,
    main,
)


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


def test_no_args_missing_required_to_exits_2(capsys):
    """No args now fails argparse required-arg check (--to)."""
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "--to" in captured.err
    assert "required" in captured.err.lower()


# ---------- Parser flag tests ----------


def test_from_flag_defaults_to_auto():
    args = build_parser().parse_args(["--to", "md"])
    assert args.source_format == "auto"
    assert args.target_format == "md"


def test_from_flag_accepts_md_tracwiki_auto():
    parser = build_parser()
    for choice in ("md", "tracwiki", "auto"):
        args = parser.parse_args(["--from", choice, "--to", "md"])
        assert args.source_format == choice


def test_to_flag_accepts_md_and_tracwiki():
    parser = build_parser()
    for choice in ("md", "tracwiki"):
        args = parser.parse_args(["--to", choice])
        assert args.target_format == choice


def test_from_flag_rejects_invalid_choice(capsys):
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--from", "bogus", "--to", "md"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice" in err
    assert "bogus" in err


def test_to_flag_rejects_invalid_choice(capsys):
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--to", "bogus"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice" in err


def test_to_flag_is_required(capsys):
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--from", "md"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "--to" in err


# ---------- convert_text dispatch tests ----------


def test_convert_text_auto_detects_markdown_source():
    result = convert_text("# Hello world", "auto", "tracwiki")
    assert result.source_format == "markdown"
    assert result.target_format == "tracwiki"
    assert result.converted is True


def test_convert_text_auto_detects_tracwiki_source():
    result = convert_text("= Hello world =", "auto", "md")
    assert result.source_format == "tracwiki"
    assert result.target_format == "markdown"
    assert result.converted is True


def test_convert_text_honors_explicit_md_source():
    # A doc whose content leans tracwiki but user says --from md:
    # explicit flag must win over the heuristic.
    result = convert_text("= Hello =", "md", "tracwiki")
    assert result.source_format == "markdown"
    assert result.target_format == "tracwiki"


def test_convert_text_honors_explicit_tracwiki_source():
    result = convert_text("# Hello", "tracwiki", "md")
    assert result.source_format == "tracwiki"
    assert result.target_format == "markdown"


def test_convert_text_same_format_is_passthrough():
    text = "# Hello\n\nParagraph text."
    result = convert_text(text, "md", "md")
    assert result.source_format == "markdown"
    assert result.target_format == "markdown"
    assert result.converted is False
    assert result.text == text
    assert result.warnings == []


def test_convert_text_same_format_tracwiki_passthrough():
    text = "= Hello =\n\nParagraph text."
    result = convert_text(text, "tracwiki", "tracwiki")
    assert result.converted is False
    assert result.text == text


def test_convert_text_md_to_tracwiki_produces_tracwiki_heading():
    result = convert_text("# Hello", "md", "tracwiki")
    # TracWiki H1 uses `= Hello =` style; we don't over-specify the
    # exact output (that's the converter's contract), just confirm
    # the tracwiki heading marker is present.
    assert "= Hello" in result.text


def test_convert_text_tracwiki_to_md_produces_md_heading():
    result = convert_text("= Hello =", "tracwiki", "md")
    # Markdown H1 uses `# Hello`.
    assert result.text.lstrip().startswith("# Hello")
