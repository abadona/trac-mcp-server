"""Subprocess-level end-to-end tests for the trac-convert CLI (Phase 18-03).

These tests spawn the CLI as a real subprocess to exercise:
- The run() wrapper in cli/convert.py (sys.exit propagation)
- The [project.scripts] entry-point binding in pyproject.toml
- Real OS pipe behavior and fd separation of stdout/stderr

In-process main(argv) tests in test_cli_convert.py cover behavior; these
tests cover WIRING. Do not duplicate behavioral coverage here.
"""

import subprocess
import sys

from trac_mcp_server import __version__

# Invoke via the cli package __main__.py, which calls run() -> sys.exit(main()).
# Using python -m trac_mcp_server.cli (not trac_mcp_server.cli.convert) because
# the __main__.py lives at the cli package level, not inside convert.py.
# This exercises the full run() -> sys.exit() wiring and real OS pipe behaviour.
CLI_MODULE = "trac_mcp_server.cli"


def _run_cli(
    *args: str, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Invoke `python -m trac_mcp_server.cli ...` with optional stdin."""
    return subprocess.run(
        [sys.executable, "-m", CLI_MODULE, *args],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Task 1: Smoke tests (version, help, exit codes, real pipe)
# ---------------------------------------------------------------------------


def test_subprocess_version_flag_exits_0_and_prints_version() -> None:
    """--version exits 0, prints version and program name, no stderr."""
    result = _run_cli("--version")
    assert result.returncode == 0
    assert __version__ in result.stdout
    assert "trac-convert" in result.stdout
    assert result.stderr == ""


def test_subprocess_help_flag_exits_0_and_prints_usage() -> None:
    """--help exits 0 and includes usage text and program name."""
    result = _run_cli("--help")
    assert result.returncode == 0
    assert "usage:" in result.stdout
    assert "trac-convert" in result.stdout


def test_subprocess_missing_required_to_exits_2() -> None:
    """Omitting --to exits 2 (argparse error) with diagnostic on stderr."""
    result = _run_cli()
    assert result.returncode == 2
    assert "--to" in result.stderr
    assert "required" in result.stderr.lower()
    assert result.stdout == ""


def test_subprocess_invalid_to_choice_exits_2() -> None:
    """Passing an invalid --to value exits 2 with argparse error on stderr."""
    result = _run_cli("--to", "wat")
    assert result.returncode == 2
    assert result.stdout == ""
    # argparse emits "invalid choice: 'wat'" or similar
    assert "wat" in result.stderr or "invalid choice" in result.stderr


def test_subprocess_stdin_to_stdout_pipe_roundtrips_content() -> None:
    """Stdin→stdout pipe: real OS pipe, run() wrapper, and convert wiring."""
    result = _run_cli(
        "--from", "md", "--to", "tracwiki", input_text="# Hello\n"
    )
    assert result.returncode == 0
    assert result.stdout.startswith("= Hello =")
    assert result.stderr == ""


# ---------------------------------------------------------------------------
# Task 2: fd separation, file I/O, missing file, pipe roundtrip, UTF-8
# ---------------------------------------------------------------------------


def test_subprocess_stdout_and_stderr_are_separate_fds() -> None:
    """Verbose info: lines go only to stderr; stdout carries converted text."""
    result = _run_cli(
        "--from", "md", "--to", "tracwiki", "-v", input_text="# H\n"
    )
    assert result.returncode == 0
    assert result.stdout.startswith("= H =")
    assert "info:" in result.stderr
    assert "info:" not in result.stdout


def test_subprocess_file_input_and_output_flags(tmp_path) -> None:
    """Positional FILE + -o FILE flags work end-to-end via real subprocess."""
    in_file = tmp_path / "in.md"
    out_file = tmp_path / "out.tw"
    in_file.write_text("# Title\n", encoding="utf-8")

    result = _run_cli(
        str(in_file),
        "--from",
        "md",
        "--to",
        "tracwiki",
        "-o",
        str(out_file),
    )
    assert result.returncode == 0
    assert out_file.read_text(encoding="utf-8").startswith("= Title =")
    assert result.stdout == ""
    assert result.stderr == ""


def test_subprocess_missing_input_file_exits_1(tmp_path) -> None:
    """Referencing a non-existent input file exits 1 with diagnostic on stderr."""
    missing = tmp_path / "does_not_exist.md"
    result = _run_cli(str(missing), "--from", "md", "--to", "md")
    assert result.returncode == 1
    assert "cannot read input file" in result.stderr
    assert result.stdout == ""


def test_subprocess_real_pipe_roundtrip_md_tw_md() -> None:
    """Two-stage pipe: md→tracwiki→md via two real subprocesses."""
    p1 = subprocess.run(
        [
            sys.executable,
            "-m",
            CLI_MODULE,
            "--from",
            "md",
            "--to",
            "tracwiki",
        ],
        input="# Hello\n\nBody.\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert p1.returncode == 0

    p2 = subprocess.run(
        [
            sys.executable,
            "-m",
            CLI_MODULE,
            "--from",
            "tracwiki",
            "--to",
            "md",
        ],
        input=p1.stdout,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert p2.returncode == 0
    assert "# Hello" in p2.stdout
    assert "Body." in p2.stdout


def test_subprocess_non_ascii_stdin_stdout_pipe() -> None:
    """Non-ASCII (UTF-8) input flows cleanly through the subprocess boundary."""
    result = _run_cli(
        "--from", "md", "--to", "md", input_text="# Café\n"
    )
    assert result.returncode == 0
    assert "Café" in result.stdout
