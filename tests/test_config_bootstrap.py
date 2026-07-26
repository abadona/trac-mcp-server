# Unit tests for the extracted bootstrap_config() helper.
# Behavior parity for the lifespan integration is covered by tests/test_lifespan.py.

from unittest.mock import patch

import pytest

from trac_mcp_server.config_bootstrap import bootstrap_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TRAC_URL = "https://trac.example.com/trac"
_VALID_USERNAME = "testuser"
_VALID_PASSWORD = "testpass"


def _set_valid_env(monkeypatch):
    """Set required Trac env vars to valid values."""
    monkeypatch.setenv("TRAC_URL", _VALID_TRAC_URL)
    monkeypatch.setenv("TRAC_USERNAME", _VALID_USERNAME)
    monkeypatch.setenv("TRAC_PASSWORD", _VALID_PASSWORD)


def _clear_trac_env(monkeypatch):
    """Remove all Trac credential env vars so no fallback is available."""
    for var in (
        "TRAC_URL",
        "TRAC_USERNAME",
        "TRAC_PASSWORD",
        "TRAC_INSECURE",
        "TRAC_DEBUG",
        "TRAC_MCP_CONFIG",
        "TRAC_ASSIST_CONFIG",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# 1. env-only path
# ---------------------------------------------------------------------------


def test_env_only_returns_config_and_sources(monkeypatch):
    """bootstrap_config(None) with env vars set returns Config + correct sources."""
    _set_valid_env(monkeypatch)

    with (
        patch("trac_mcp_server.config_bootstrap.load_dotenv"),
        patch(
            "trac_mcp_server.config_bootstrap.discover_config_files",
            return_value=[],
        ),
    ):
        config, sources = bootstrap_config(None)

    assert config.trac_url == _VALID_TRAC_URL
    assert config.username == _VALID_USERNAME
    assert config.password == _VALID_PASSWORD
    assert sources == ["environment variables"]


# ---------------------------------------------------------------------------
# 2. YAML config file path
# ---------------------------------------------------------------------------


def test_yaml_only_returns_yaml_source_label(monkeypatch, tmp_path):
    """When a YAML config file is found, its path appears first in sources."""
    # Write a minimal YAML config under tmp_path
    config_dir = tmp_path / ".trac_mcp"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(
        "trac:\n"
        f"  url: {_VALID_TRAC_URL}\n"
        f"  username: {_VALID_USERNAME}\n"
        # password must come from env — YAML-only can't provide it in isolation
        # because load_config still requires it
    )

    # Provide password via env only (env-only for password)
    monkeypatch.setenv("TRAC_PASSWORD", _VALID_PASSWORD)
    # Clear URL/USERNAME from env so they come from YAML only
    monkeypatch.delenv("TRAC_URL", raising=False)
    monkeypatch.delenv("TRAC_USERNAME", raising=False)

    with (
        patch("trac_mcp_server.config_bootstrap.load_dotenv"),
        patch(
            "trac_mcp_server.config_bootstrap.discover_config_files",
            return_value=[config_file],
        ),
        patch(
            "trac_mcp_server.config_bootstrap.load_hierarchical_config",
            return_value={
                "trac": {
                    "url": _VALID_TRAC_URL,
                    "username": _VALID_USERNAME,
                }
            },
        ),
    ):
        config, sources = bootstrap_config(None)

    assert sources[0] == f"config file: {config_file}"
    assert "environment variables" in sources
    assert config.trac_url == _VALID_TRAC_URL


# ---------------------------------------------------------------------------
# 3. CLI overrides win over env
# ---------------------------------------------------------------------------


def test_cli_overrides_win_over_env(monkeypatch):
    """CLI overrides take precedence over env vars; 'CLI arguments' in sources."""
    # Set env vars to different values
    monkeypatch.setenv("TRAC_URL", "https://env.example.com")
    monkeypatch.setenv("TRAC_USERNAME", "env_user")
    monkeypatch.setenv("TRAC_PASSWORD", "env_pass")

    cli_overrides = {
        "url": "https://override.example.com",
        "username": "cli_user",
        "password": "cli_pass",
    }

    with (
        patch("trac_mcp_server.config_bootstrap.load_dotenv"),
        patch(
            "trac_mcp_server.config_bootstrap.discover_config_files",
            return_value=[],
        ),
    ):
        config, sources = bootstrap_config(cli_overrides)

    assert config.trac_url == "https://override.example.com"
    assert config.username == "cli_user"
    assert "CLI arguments" in sources


# ---------------------------------------------------------------------------
# 4. Missing credentials → ValueError
# ---------------------------------------------------------------------------


def test_missing_credentials_raises_valueerror(monkeypatch, tmp_path):
    """bootstrap_config raises ValueError when required fields are absent."""
    _clear_trac_env(monkeypatch)
    # Change CWD to tmp_path so no real config file is found
    monkeypatch.chdir(tmp_path)

    with (
        patch("trac_mcp_server.config_bootstrap.load_dotenv"),
        patch(
            "trac_mcp_server.config_bootstrap.discover_config_files",
            return_value=[],
        ),
    ):
        with pytest.raises(ValueError):
            bootstrap_config(None)


# ---------------------------------------------------------------------------
# 5. Empty dict is treated the same as None (no 'CLI arguments' label)
# ---------------------------------------------------------------------------


def test_empty_cli_overrides_dict_does_not_add_source_label(
    monkeypatch,
):
    """Passing {} is identical to None — 'CLI arguments' must NOT appear in sources."""
    _set_valid_env(monkeypatch)

    with (
        patch("trac_mcp_server.config_bootstrap.load_dotenv"),
        patch(
            "trac_mcp_server.config_bootstrap.discover_config_files",
            return_value=[],
        ),
    ):
        _, sources = bootstrap_config({})

    assert "CLI arguments" not in sources
    assert "environment variables" in sources


# ---------------------------------------------------------------------------
# 6. Source list ordering: YAML file first, env vars last
# ---------------------------------------------------------------------------


def test_sources_list_ordering(monkeypatch, tmp_path):
    """With YAML + env (no CLI), sources order must be [config file, env vars]."""
    _set_valid_env(monkeypatch)
    fake_config_path = tmp_path / "config.yaml"

    with (
        patch("trac_mcp_server.config_bootstrap.load_dotenv"),
        patch(
            "trac_mcp_server.config_bootstrap.discover_config_files",
            return_value=[fake_config_path],
        ),
        patch(
            "trac_mcp_server.config_bootstrap.load_hierarchical_config",
            return_value={
                "trac": {
                    "url": _VALID_TRAC_URL,
                    "username": _VALID_USERNAME,
                    "password": _VALID_PASSWORD,
                }
            },
        ),
    ):
        _, sources = bootstrap_config(None)

    assert sources == [
        f"config file: {fake_config_path}",
        "environment variables",
    ]


# ---------------------------------------------------------------------------
# 7. Helper does not write to stdout or stderr
# ---------------------------------------------------------------------------


def test_helper_does_not_write_to_stderr_or_stdout(monkeypatch, capsys):
    """bootstrap_config() must produce no stdout/stderr output (data only)."""
    _set_valid_env(monkeypatch)

    with (
        patch("trac_mcp_server.config_bootstrap.load_dotenv"),
        patch(
            "trac_mcp_server.config_bootstrap.discover_config_files",
            return_value=[],
        ),
    ):
        bootstrap_config(None)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
