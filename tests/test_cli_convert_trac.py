"""Tests for Phase 20 CLI additions: --trac-* flags, --check-trac diagnostic,
EXIT_TRAC, and regression guards against premature --from-wiki/--to-wiki
scaffolding."""

import xmlrpc.client
from unittest.mock import MagicMock

import pytest
import requests.exceptions  # noqa: F401

from trac_mcp_server.cli.convert import (
    EXIT_OK,
    EXIT_TRAC,
    EXIT_USAGE_ERROR,
    main,
)
from trac_mcp_server.core.client import TracClient

# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

_TEST_URL = "https://trac.example.com"
_TEST_USER = "testuser"
_TEST_PASS = "testpass"


def _mock_valid_env(monkeypatch):
    """Set valid Trac env vars to safe test values."""
    monkeypatch.setenv("TRAC_URL", _TEST_URL)
    monkeypatch.setenv("TRAC_USERNAME", _TEST_USER)
    monkeypatch.setenv("TRAC_PASSWORD", _TEST_PASS)


def _mock_tracclient(
    validate_return="1.2.0",
    validate_side_effect=None,
    get_wiki_page_return=None,
    get_wiki_page_side_effect=None,
):
    """Return a MagicMock(spec=TracClient) with configurable validate_connection.

    Args:
        validate_return: The value validate_connection() should return on success.
        validate_side_effect: If set, validate_connection() raises this instead.
        get_wiki_page_return: The value get_wiki_page() should return.
        get_wiki_page_side_effect: If set, get_wiki_page() raises this instead.
    """
    mock_client_instance = MagicMock(spec=TracClient)
    if validate_side_effect is not None:
        mock_client_instance.validate_connection.side_effect = (
            validate_side_effect
        )
    else:
        mock_client_instance.validate_connection.return_value = (
            validate_return
        )
    if get_wiki_page_side_effect is not None:
        mock_client_instance.get_wiki_page.side_effect = (
            get_wiki_page_side_effect
        )
    elif get_wiki_page_return is not None:
        mock_client_instance.get_wiki_page.return_value = (
            get_wiki_page_return
        )
    return mock_client_instance


# ---------------------------------------------------------------------------
# 1. Help output & parser structure
# ---------------------------------------------------------------------------


def test_help_shows_all_five_trac_flags(capsys):
    """--help output includes all five --trac-* / --check-trac flags."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--trac-url" in out
    assert "--trac-username" in out
    assert "--trac-password" in out
    assert "--trac-password-file" in out
    assert "--check-trac" in out


def test_help_shows_from_wiki_but_not_to_wiki(capsys):
    """REGRESSION GUARD: --from-wiki must appear in --help; --to-wiki must NOT.

    This test protects against accidentally shipping Phase 22 (--to-wiki)
    scaffolding before that phase lands. Update (do not delete) this test
    when Phase 22 ships.
    """
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "--from-wiki" in out
    assert "--to-wiki" not in out


def test_exit_trac_constant_is_4():
    """EXIT_TRAC must equal 4."""
    assert EXIT_TRAC == 4


# ---------------------------------------------------------------------------
# 4-6. --check-trac happy path (mocked TracClient)
# ---------------------------------------------------------------------------


def test_check_trac_success_prints_url_user_sources_and_exits_ok(
    monkeypatch, capsys
):
    """Happy path: prints URL/username/sources/OK and returns EXIT_OK."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(validate_return="1.2.0")
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--check-trac"])

    assert result == EXIT_OK
    out = capsys.readouterr().out
    assert "URL:" in out
    assert _TEST_URL in out
    assert "Username:" in out
    assert _TEST_USER in out
    assert "Sources:" in out
    assert "environment variables" in out
    assert "OK (Trac API version 1.2.0)" in out


def test_check_trac_success_never_prints_password(monkeypatch, capsys):
    """CRITICAL (Pitfall 3): the password must never appear in stdout or stderr."""
    secret = "s3cret_XY!zz"
    monkeypatch.setenv("TRAC_URL", _TEST_URL)
    monkeypatch.setenv("TRAC_USERNAME", _TEST_USER)
    monkeypatch.setenv("TRAC_PASSWORD", secret)
    mock_instance = _mock_tracclient(validate_return="1.2.0")
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    main(["--check-trac"])

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_check_trac_shows_insecure_warning_when_config_insecure(
    monkeypatch, capsys
):
    """When config.insecure is True, --check-trac prints 'verification DISABLED'."""
    _mock_valid_env(monkeypatch)
    monkeypatch.setenv("TRAC_INSECURE", "true")
    mock_instance = _mock_tracclient(validate_return="1.2.0")
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--check-trac"])

    assert result == EXIT_OK
    out = capsys.readouterr().out
    assert "verification DISABLED" in out


# ---------------------------------------------------------------------------
# 7-10. --check-trac failure paths
# ---------------------------------------------------------------------------


def test_check_trac_auth_missing_prints_friendly_error_and_exits_4(
    monkeypatch, tmp_path, capsys
):
    """No credentials: friendly two-line error to stderr, exit 4, no Traceback."""
    for var in (
        "TRAC_URL",
        "TRAC_USERNAME",
        "TRAC_PASSWORD",
        "TRAC_MCP_CONFIG",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # avoid picking up a real YAML

    # Suppress load_dotenv() so a real .env file in the repo root cannot
    # re-inject credentials that monkeypatch.delenv() just removed.
    monkeypatch.setattr(
        "trac_mcp_server.config_bootstrap.load_dotenv",
        lambda: None,
    )

    result = main(["--check-trac"])

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert err.startswith("trac-convert: no Trac credentials found.")
    assert "TRAC_URL" in err
    assert "TRAC_USERNAME" in err
    assert "TRAC_PASSWORD" in err
    assert ".trac_mcp/config.yaml" in err
    assert "Traceback" not in err


def test_check_trac_ping_auth_fault_classified(monkeypatch, capsys):
    """XML-RPC auth fault is classified as 'authentication failed'."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        validate_side_effect=xmlrpc.client.Fault(403, "Forbidden")
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--check-trac"])

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert "authentication failed" in err
    assert "Forbidden" in err


def test_check_trac_ping_ssl_error_classified(monkeypatch, capsys):
    """SSL error is classified and mentions 'SSL'."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        validate_side_effect=requests.exceptions.SSLError("bad cert")
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--check-trac"])

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert "SSL" in err


def test_check_trac_ping_connection_error_classified(
    monkeypatch, capsys
):
    """Connection error is classified and mentions 'cannot reach' and the URL."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        validate_side_effect=requests.exceptions.ConnectionError(
            "refused"
        )
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--check-trac"])

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert "cannot reach" in err
    assert _TEST_URL in err


# ---------------------------------------------------------------------------
# 11-12. Password-file precedence
# ---------------------------------------------------------------------------


def test_password_file_precedes_password_flag(monkeypatch, tmp_path):
    """--trac-password-file takes precedence over --trac-password."""
    pw_file = tmp_path / "pw.txt"
    pw_file.write_text("filepass\n", encoding="utf-8")

    monkeypatch.setenv("TRAC_URL", _TEST_URL)
    monkeypatch.setenv("TRAC_USERNAME", _TEST_USER)
    # No TRAC_PASSWORD env - password comes from file or flag

    captured_config = []

    def mock_client_factory(cfg):
        captured_config.append(cfg)
        return _mock_tracclient(validate_return="1.2.0")

    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        mock_client_factory,
    )

    result = main(
        [
            "--check-trac",
            "--trac-password",
            "flagpass",
            "--trac-password-file",
            str(pw_file),
        ]
    )

    assert result == EXIT_OK
    assert len(captured_config) == 1
    assert captured_config[0].password == "filepass"


def test_password_file_read_failure_exits_4(monkeypatch, capsys):
    """Non-existent password file exits 4 with a diagnostic on stderr."""
    _mock_valid_env(monkeypatch)

    result = main(
        ["--check-trac", "--trac-password-file", "/nonexistent/path"]
    )

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert "cannot read --trac-password-file" in err


# ---------------------------------------------------------------------------
# 13-14. Dispatch and regression guards
# ---------------------------------------------------------------------------


def test_check_trac_does_not_require_to_flag(monkeypatch):
    """--check-trac works without --to (dispatch happens before --to check)."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(validate_return="1.2.0")
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--check-trac"])  # no --to

    assert result == EXIT_OK


def test_normal_conversion_still_requires_to_flag(capsys):
    """REGRESSION GUARD: normal conversion without --to exits EXIT_USAGE_ERROR."""
    result = main(["--from", "md"])  # no --to, no --check-trac

    assert result == EXIT_USAGE_ERROR
    err = capsys.readouterr().err
    assert "--to" in err


# ---------------------------------------------------------------------------
# --- Phase 21: --from-wiki tests ---
# ---------------------------------------------------------------------------


def test_help_shows_from_wiki_page_metavar(capsys):
    """--from-wiki entry in --help shows PAGE as the metavar."""
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "PAGE" in out


def test_from_wiki_mutex_with_positional_file_exits_1_runtime_error(
    capsys,
):
    """--from-wiki and FILE positional are mutually exclusive (exit 1)."""
    from trac_mcp_server.cli.convert import EXIT_RUNTIME_ERROR

    result = main(["--from-wiki", "Foo", "somefile.md", "--to", "md"])

    assert result == EXIT_RUNTIME_ERROR
    err = capsys.readouterr().err
    assert "--from-wiki and FILE are mutually exclusive" in err


def test_from_wiki_mutex_with_from_clipboard_exits_1_runtime_error(
    capsys,
):
    """--from-wiki and --from-clipboard are mutually exclusive (exit 1)."""
    from trac_mcp_server.cli.convert import EXIT_RUNTIME_ERROR

    result = main(
        ["--from-wiki", "Foo", "--from-clipboard", "--to", "md"]
    )

    assert result == EXIT_RUNTIME_ERROR
    err = capsys.readouterr().err
    assert (
        "--from-wiki and --from-clipboard are mutually exclusive" in err
    )


def test_from_wiki_happy_path_prints_converted_markdown_to_stdout(
    monkeypatch, capsys
):
    """--from-wiki fetches TracWiki, converts to Markdown, prints to stdout."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        get_wiki_page_return="= Heading =\n\nsome tracwiki body"
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--from-wiki", "MyPage", "--to", "md"])

    assert result == EXIT_OK
    out = capsys.readouterr().out
    assert out.startswith("# Heading")


def test_from_wiki_to_tracwiki_is_passthrough_no_conversion(
    monkeypatch, capsys
):
    """--from-wiki + --to tracwiki is a pass-through (source == target)."""
    raw_page = "= Heading =\n\nsome tracwiki body"
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(get_wiki_page_return=raw_page)
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--from-wiki", "MyPage", "--to", "tracwiki"])

    assert result == EXIT_OK
    out = capsys.readouterr().out
    assert out == raw_page


def test_from_wiki_silently_overrides_explicit_from_md(
    monkeypatch, capsys
):
    """--from-wiki forces source_format=tracwiki, silently ignoring --from md."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        get_wiki_page_return="= Heading =\n\nbody"
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    # --from md is explicitly set but should be silently overridden
    result = main(
        ["--from-wiki", "MyPage", "--from", "md", "--to", "md"]
    )

    assert result == EXIT_OK
    out = capsys.readouterr().out
    # If --from md were honoured, tracwiki "= Heading =" would be treated
    # as markdown and output "= Heading =" verbatim (passthrough or literal).
    # With override to tracwiki→md, it must become "# Heading".
    assert "# Heading" in out


def test_from_wiki_auth_missing_prints_friendly_error_and_exits_4(
    monkeypatch, tmp_path, capsys
):
    """No Trac credentials: friendly error, exit 4, no Traceback."""
    for var in (
        "TRAC_URL",
        "TRAC_USERNAME",
        "TRAC_PASSWORD",
        "TRAC_MCP_CONFIG",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "trac_mcp_server.config_bootstrap.load_dotenv",
        lambda: None,
    )

    result = main(["--from-wiki", "MyPage", "--to", "md"])

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert "no Trac credentials found" in err
    assert "docs/reference/cli.md" in err
    assert "Traceback" not in err


def test_from_wiki_page_not_found_prints_friendly_error_and_exits_4(
    monkeypatch, capsys
):
    """Fault(1) -> 'wiki page not found: <page name>'."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        get_wiki_page_side_effect=xmlrpc.client.Fault(
            1, "page not found"
        )
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--from-wiki", "NoSuchPage", "--to", "md"])

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert "wiki page not found: NoSuchPage" in err


def test_from_wiki_other_fault_reports_fault_string_and_exits_4(
    monkeypatch, capsys
):
    """Fault(403) -> 'Trac fault' message with the faultString."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        get_wiki_page_side_effect=xmlrpc.client.Fault(
            403, "permission denied"
        )
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--from-wiki", "SomePage", "--to", "md"])

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert "Trac fault" in err
    assert "permission denied" in err
    assert "wiki page not found" not in err


def test_from_wiki_connection_error_reports_reach_and_exits_4(
    monkeypatch, capsys
):
    """ConnectionError -> 'cannot reach Trac at <url>' message."""
    import requests.exceptions

    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        get_wiki_page_side_effect=requests.exceptions.ConnectionError(
            "connection refused"
        )
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--from-wiki", "SomePage", "--to", "md"])

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert "cannot reach Trac at" in err
    assert _TEST_URL in err


def test_from_wiki_ssl_error_reports_ssl_and_exits_4(
    monkeypatch, capsys
):
    """SSLError -> 'SSL error' message."""
    import requests.exceptions

    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        get_wiki_page_side_effect=requests.exceptions.SSLError(
            "bad cert"
        )
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    result = main(["--from-wiki", "SomePage", "--to", "md"])

    assert result == EXIT_TRAC
    err = capsys.readouterr().err
    assert "SSL error" in err


def test_from_wiki_password_never_printed(monkeypatch, capsys):
    """CRITICAL: password must never appear in stdout or stderr."""
    secret = "s3cret_XY!zz"
    monkeypatch.setenv("TRAC_URL", _TEST_URL)
    monkeypatch.setenv("TRAC_USERNAME", _TEST_USER)
    monkeypatch.setenv("TRAC_PASSWORD", secret)
    mock_instance = _mock_tracclient(
        get_wiki_page_return="= Heading =\n\nbody"
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    main(["--from-wiki", "MyPage", "--to", "md"])

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_from_wiki_output_to_clipboard_writes_converted_text(
    monkeypatch, capsys
):
    """--from-wiki + --to-clipboard writes converted markdown to clipboard."""
    _mock_valid_env(monkeypatch)
    mock_instance = _mock_tracclient(
        get_wiki_page_return="= Heading =\n\nbody"
    )
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.TracClient",
        lambda _: mock_instance,
    )

    clipboard_calls = []
    monkeypatch.setattr(
        "trac_mcp_server.cli.convert.pyperclip.copy",
        lambda text: clipboard_calls.append(text),
    )

    result = main(
        ["--from-wiki", "MyPage", "--to", "md", "--to-clipboard"]
    )

    assert result == EXIT_OK
    assert len(clipboard_calls) == 1
    assert clipboard_calls[0].startswith("# Heading")
