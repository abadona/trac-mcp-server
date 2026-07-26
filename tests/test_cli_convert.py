"""Smoke tests for trac-convert CLI (Phase 11 + 12 + 13 + 14 + 15 + 16 + 17)."""

import argparse
import io

import pyperclip
import pytest

from trac_mcp_server import __version__
from trac_mcp_server.cli.convert import (
    EXIT_CONVERSION_ERROR,
    EXIT_OK,
    EXIT_RUNTIME_ERROR,
    EXIT_USAGE_ERROR,
    build_parser,
    convert_text,
    main,
)
from trac_mcp_server.converters.common import ConversionResult


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


# ---------- stdin/stdout integration tests ----------


def test_main_reads_stdin_and_writes_converted_output_to_stdout(
    monkeypatch, capsys
):
    monkeypatch.setattr("sys.stdin", io.StringIO("# Hello"))
    exit_code = main(["--from", "md", "--to", "tracwiki"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "= Hello" in captured.out
    assert captured.err == ""


def test_main_pass_through_when_source_equals_target(
    monkeypatch, capsys
):
    input_text = "# Hello\n\nBody.\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(input_text))
    exit_code = main(["--from", "md", "--to", "md"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == input_text


def test_main_writes_verbatim_no_trailing_newline_added(
    monkeypatch, capsys
):
    monkeypatch.setattr("sys.stdin", io.StringIO("# Hi"))
    exit_code = main(["--from", "md", "--to", "md"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == "# Hi"


def test_main_auto_detects_when_no_from_flag(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("= Hello ="))
    exit_code = main(["--to", "md"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("# Hello")


def test_main_empty_stdin_is_valid_no_op(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    exit_code = main(["--to", "md"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_writes_warnings_to_stderr_not_stdout(monkeypatch, capsys):
    fake_result = ConversionResult(
        text="output text",
        source_format="markdown",
        target_format="tracwiki",
        converted=True,
        warnings=["lossy: table dropped"],
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.convert_text",
        lambda *_, **__: fake_result,
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("anything"))
    exit_code = main(["--to", "tracwiki"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "warning: lossy: table dropped" in captured.err
    assert "warning:" not in captured.out


# ---------- file I/O integration tests ----------


def test_input_file_positional_defaults_to_none():
    """Positional FILE is optional — defaults to None when omitted."""
    assert build_parser().parse_args(["--to", "md"]).input_file is None


def test_input_file_positional_accepts_a_path():
    """Positional FILE captures the path string."""
    assert (
        build_parser()
        .parse_args(["some/file.md", "--to", "md"])
        .input_file
        == "some/file.md"
    )


def test_output_flag_short_and_long_forms_equivalent():
    """-o and --output set output_file to the same value."""
    short = (
        build_parser()
        .parse_args(["--to", "md", "-o", "out.md"])
        .output_file
    )
    long = (
        build_parser()
        .parse_args(["--to", "md", "--output", "out.md"])
        .output_file
    )
    assert short == "out.md"
    assert long == "out.md"


def test_main_reads_from_positional_file_and_writes_to_stdout(
    tmp_path, capsys
):
    """main() reads the positional FILE and prints conversion to stdout."""
    in_file = tmp_path / "in.md"
    in_file.write_text("# Hello", encoding="utf-8")
    exit_code = main([str(in_file), "--from", "md", "--to", "tracwiki"])
    assert exit_code == 0
    assert "= Hello" in capsys.readouterr().out


def test_main_file_input_takes_precedence_when_stdin_also_available(
    monkeypatch, tmp_path, capsys
):
    """When both a positional FILE and stdin are present, FILE wins."""
    in_file = tmp_path / "in.tracwiki"
    in_file.write_text("= FromFile =", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO("# FromStdin"))
    exit_code = main([str(in_file), "--to", "md"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.startswith("# FromFile")


def test_main_missing_input_file_returns_1_with_stderr_message(
    tmp_path, capsys
):
    """A non-existent positional FILE exits 1 with a clear stderr message."""
    missing = tmp_path / "does_not_exist.md"
    exit_code = main([str(missing), "--to", "md"])
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "trac-convert: cannot read input file" in err
    assert str(missing) in err


def test_main_writes_to_output_file_and_leaves_stdout_empty(
    monkeypatch, tmp_path, capsys
):
    """main() writes to -o FILE and emits nothing to stdout."""
    monkeypatch.setattr("sys.stdin", io.StringIO("# Hello"))
    out = tmp_path / "out.tracwiki"
    exit_code = main(
        ["--from", "md", "--to", "tracwiki", "-o", str(out)]
    )
    assert exit_code == 0
    assert out.exists()
    assert "= Hello" in out.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""


def test_main_output_write_error_returns_1_with_stderr_message(
    monkeypatch, tmp_path, capsys
):
    """An unwritable output path exits 1 with a clear stderr message."""
    monkeypatch.setattr("sys.stdin", io.StringIO("# Hello"))
    bad_out = str(tmp_path / "no_such_dir" / "out.md")
    exit_code = main(["--from", "md", "--to", "md", "-o", bad_out])
    assert exit_code == 1
    assert (
        "trac-convert: cannot write output file"
        in capsys.readouterr().err
    )


def test_main_file_to_file_roundtrip(tmp_path, capsys):
    """File-to-file pass-through produces a byte-identical copy on disk."""
    content = "# Hello\n\nBody.\n"
    in_file = tmp_path / "in.md"
    in_file.write_text(content, encoding="utf-8")
    out = tmp_path / "out.md"
    exit_code = main(
        [str(in_file), "--from", "md", "--to", "md", "-o", str(out)]
    )
    assert exit_code == 0
    assert out.read_text(encoding="utf-8") == content
    assert capsys.readouterr().out == ""


def test_main_output_file_written_as_utf8(monkeypatch, tmp_path):
    """Non-ASCII content roundtrips correctly through UTF-8 file write."""
    monkeypatch.setattr("sys.stdin", io.StringIO("# Café ☕"))
    out = tmp_path / "out.md"
    exit_code = main(["--from", "md", "--to", "md", "-o", str(out)])
    assert exit_code == 0
    raw = out.read_bytes()
    assert raw.decode("utf-8") == "# Café ☕"


# ---------- clipboard I/O integration tests ----------


def test_from_clipboard_flag_defaults_to_false():
    """--from-clipboard defaults to False when not provided."""
    args = build_parser().parse_args(["--to", "md"])
    assert args.from_clipboard is False


def test_to_clipboard_flag_defaults_to_false():
    """--to-clipboard defaults to False when not provided."""
    args = build_parser().parse_args(["--to", "md"])
    assert args.to_clipboard is False


def test_from_clipboard_flag_parsed_as_true():
    """--from-clipboard sets from_clipboard to True."""
    args = build_parser().parse_args(["--from-clipboard", "--to", "md"])
    assert args.from_clipboard is True


def test_to_clipboard_flag_parsed_as_true():
    """--to-clipboard sets to_clipboard to True."""
    args = build_parser().parse_args(["--to", "md", "--to-clipboard"])
    assert args.to_clipboard is True


def test_from_clipboard_and_file_mutually_exclusive(tmp_path, capsys):
    """--from-clipboard and positional FILE are mutually exclusive."""
    in_file = tmp_path / "in.md"
    in_file.write_text("# Hello", encoding="utf-8")
    exit_code = main(["--from-clipboard", str(in_file), "--to", "md"])
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "--from-clipboard" in err
    assert "FILE" in err
    assert "mutually exclusive" in err


def test_to_clipboard_and_output_mutually_exclusive(tmp_path, capsys):
    """--to-clipboard and --output are mutually exclusive."""
    exit_code = main(
        [
            "--to",
            "md",
            "--to-clipboard",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "--to-clipboard" in err
    assert "--output" in err
    assert "mutually exclusive" in err


def test_main_reads_from_clipboard(monkeypatch, capsys):
    """--from-clipboard reads from pyperclip.paste() and converts."""
    monkeypatch.setattr(pyperclip, "paste", lambda: "= Hello =")
    exit_code = main(["--from-clipboard", "--to", "md"])
    assert exit_code == 0
    assert capsys.readouterr().out.startswith("# Hello")


def test_clipboard_read_error_returns_1(monkeypatch, capsys):
    """PyperclipException on paste() → exit 1 with 'clipboard read failed'."""

    def raise_paste():
        raise pyperclip.PyperclipException("no mechanism")

    monkeypatch.setattr(pyperclip, "paste", raise_paste)
    exit_code = main(["--from-clipboard", "--to", "md"])
    assert exit_code == 1
    assert "clipboard read failed" in capsys.readouterr().err


def test_main_writes_to_clipboard(monkeypatch, capsys):
    """--to-clipboard passes converted text to pyperclip.copy(); stdout empty."""
    copied = []
    monkeypatch.setattr(pyperclip, "copy", lambda t: copied.append(t))
    monkeypatch.setattr("sys.stdin", io.StringIO("# Hello"))
    exit_code = main(
        ["--from", "md", "--to", "tracwiki", "--to-clipboard"]
    )
    assert exit_code == 0
    assert len(copied) == 1
    assert "= Hello" in copied[0]
    assert capsys.readouterr().out == ""


def test_clipboard_write_error_returns_1(monkeypatch, capsys):
    """PyperclipException on copy() → exit 1 with 'clipboard write failed'."""

    def raise_copy(_):
        raise pyperclip.PyperclipException("no mechanism")

    monkeypatch.setattr(pyperclip, "copy", raise_copy)
    monkeypatch.setattr("sys.stdin", io.StringIO("# Hello"))
    exit_code = main(
        ["--from", "md", "--to", "tracwiki", "--to-clipboard"]
    )
    assert exit_code == 1


# ---------------------------------------------------------------------------
# Phase 16: --heading-anchors and --unknown-macros CLI flags
# ---------------------------------------------------------------------------


def test_heading_anchors_on_by_default(monkeypatch, capsys):
    """--heading-anchors defaults to on; stdout includes the #slug suffix."""
    monkeypatch.setattr("sys.stdin", io.StringIO("# H"))
    exit_code = main(["--from", "md", "--to", "tracwiki"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.startswith("= H = #h")


def test_heading_anchors_off_omits_slug(monkeypatch, capsys):
    """--heading-anchors off: heading emitted without #slug suffix."""
    monkeypatch.setattr("sys.stdin", io.StringIO("# H"))
    exit_code = main(
        ["--from", "md", "--to", "tracwiki", "--heading-anchors", "off"]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.startswith("= H =")
    assert "#h" not in out


def test_heading_anchors_ignored_on_tw_to_md(monkeypatch, capsys):
    """--heading-anchors off on the wrong direction exits 0 (silently ignored)."""
    monkeypatch.setattr("sys.stdin", io.StringIO("= H = #h"))
    exit_code = main(
        [
            "--from",
            "tracwiki",
            "--to",
            "md",
            "--heading-anchors",
            "off",
        ]
    )
    assert exit_code == 0


def test_unknown_macros_bracket_default(monkeypatch, capsys):
    """--unknown-macros defaults to bracket; stdout contains [MACRO: PageOutline]."""
    monkeypatch.setattr("sys.stdin", io.StringIO("[[PageOutline]]"))
    exit_code = main(["--from", "tracwiki", "--to", "md"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "[MACRO: PageOutline]" in out


def test_unknown_macros_preserve(monkeypatch, capsys):
    """--unknown-macros preserve: stdout contains [[PageOutline]] literal."""
    monkeypatch.setattr("sys.stdin", io.StringIO("[[PageOutline]]"))
    exit_code = main(
        [
            "--from",
            "tracwiki",
            "--to",
            "md",
            "--unknown-macros",
            "preserve",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "[[PageOutline]]" in out


def test_unknown_macros_drop(monkeypatch, capsys):
    """--unknown-macros drop: stdout does NOT contain PageOutline."""
    monkeypatch.setattr("sys.stdin", io.StringIO("[[PageOutline]]"))
    exit_code = main(
        ["--from", "tracwiki", "--to", "md", "--unknown-macros", "drop"]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PageOutline" not in out


def test_help_lists_new_flags(capsys):
    """--help output includes both new flags."""
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "--heading-anchors" in out
    assert "--unknown-macros" in out


# ---------------------------------------------------------------------------
# Phase 17: exit-code constants + conversion-error guard
# ---------------------------------------------------------------------------


def test_exit_code_constants_have_expected_values():
    """EXIT_* constants have values (0, 1, 2, 3) in order."""
    assert (
        EXIT_OK,
        EXIT_RUNTIME_ERROR,
        EXIT_USAGE_ERROR,
        EXIT_CONVERSION_ERROR,
    ) == (
        0,
        1,
        2,
        3,
    )


def test_convert_text_exception_returns_exit_3_with_stderr_message(
    monkeypatch, capsys
):
    """convert_text() raising an exception → EXIT_CONVERSION_ERROR with stderr message."""
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.convert_text",
        lambda *_, **__: (_ for _ in ()).throw(ValueError("bad input")),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("anything"))
    exit_code = main(["--to", "tracwiki"])
    assert exit_code == EXIT_CONVERSION_ERROR
    err = capsys.readouterr().err
    assert "trac-convert: conversion failed: bad input" in err


def test_convert_text_exception_does_not_leak_traceback(
    monkeypatch, capsys
):
    """On converter exception, stderr must not contain traceback markers."""
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.convert_text",
        lambda *_, **__: (_ for _ in ()).throw(ValueError("bad input")),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("anything"))
    main(["--to", "tracwiki"])
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert 'File "' not in err


def test_convert_text_exception_writes_no_stdout(monkeypatch, capsys):
    """On converter exception, stdout must be empty (no partial output)."""
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.convert_text",
        lambda *_, **__: (_ for _ in ()).throw(ValueError("bad input")),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("anything"))
    main(["--to", "tracwiki"])
    assert capsys.readouterr().out == ""


def test_usage_error_still_exits_2_via_argparse(capsys):
    """Invalid --to choice → SystemExit with code EXIT_USAGE_ERROR (2)."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--to", "bogus"])
    assert excinfo.value.code == EXIT_USAGE_ERROR


def test_runtime_error_missing_file_uses_exit_1_constant(
    tmp_path, capsys
):
    """Missing positional FILE → EXIT_RUNTIME_ERROR (not literal 1)."""
    missing = tmp_path / "does_not_exist.md"
    exit_code = main([str(missing), "--to", "md"])
    assert exit_code == EXIT_RUNTIME_ERROR
