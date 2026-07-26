"""Shared config-bootstrap helper. Returns (Config, sources) with no side
effects on stderr/stdout. Callers own their own logging and error translation.

This module contains the single public function ``bootstrap_config()`` which
encapsulates the six-step configuration-loading sequence previously inlined in
``mcp/lifespan.py``. Both the MCP server lifespan and the ``trac-convert`` CLI
call this helper to resolve the layered config precedence without duplicating
logic.
"""

from typing import Any

from dotenv import load_dotenv

from .config import Config, load_config
from .config_loader import (
    discover_config_files,
    load_hierarchical_config,
)
from .config_schema import build_config


def bootstrap_config(
    cli_overrides: dict[str, Any] | None = None,
) -> tuple[Config, list[str]]:
    """Load configuration with CLI > env > YAML > defaults precedence.

    Performs the six-step bootstrap sequence:

    1. ``load_dotenv()`` — loads ``.env`` file so env vars are available
       before any reads (idempotent; safe to call multiple times).
    2. ``discover_config_files()`` — finds YAML config files in precedence
       order; if any exist, loads and merges them via
       ``load_hierarchical_config()`` / ``build_config()``, then extracts
       non-None trac-section values as ``yaml_fallbacks``.
    3. ``load_config(...)`` — resolves final values with precedence:
       CLI > env var / .env > YAML fallbacks > built-in defaults.
    4. Builds a ``sources`` list describing which layers contributed.

    Accepted ``cli_overrides`` keys:
        - ``url`` (str | None): Trac URL override.
        - ``username`` (str | None): Trac username override.
        - ``password`` (str | None): Trac password override.
        - ``insecure`` (bool): Skip SSL verification (default: False).
        - ``debug`` (bool): Enable debug logging (default: False).

    Args:
        cli_overrides: Optional dict with CLI-sourced values. Keys missing
            from the dict fall through to env vars / YAML / defaults.
            Pass ``None`` or ``{}`` when no CLI overrides are present;
            both are treated identically (no "CLI arguments" source label).

    Returns:
        A two-tuple ``(config, sources)`` where:
        - ``config``: A validated :class:`~trac_mcp_server.config.Config`
          instance ready for use with :class:`TracClient`.
        - ``sources``: A list of human-readable source labels in the order
          they contributed (e.g. ``["config file: /path/to/config.yaml",
          "CLI arguments", "environment variables"]``).

    Raises:
        ValueError: If required fields (``url``, ``username``, ``password``)
            are missing after checking all sources. Callers must translate:
            ``RuntimeError`` for the MCP server lifespan, ``EXIT_TRAC`` (exit
            code 4) for the CLI. Do NOT catch this error here.
    """
    # Step 1: Load .env early so ${VAR} interpolation in YAML can use them
    load_dotenv()

    # Step 2: Load YAML config if present, extract trac section as fallbacks
    yaml_fallbacks: dict[str, Any] | None = None
    sources: list[str] = []
    config_files = discover_config_files()

    if config_files:
        raw = load_hierarchical_config()
        unified = build_config(raw)
        yaml_fallbacks = {
            k: v
            for k, v in unified.trac.model_dump().items()
            if v is not None
        }
        sources.append(f"config file: {config_files[0]}")

    # Step 3: Single call to load_config with all sources merged
    overrides = cli_overrides or {}
    config = load_config(
        url=overrides.get("url"),
        username=overrides.get("username"),
        password=overrides.get("password"),
        insecure=overrides.get("insecure", False),
        debug=overrides.get("debug", False),
        yaml_fallbacks=yaml_fallbacks,
    )

    # Step 4-6: Build source labels
    if overrides:
        sources.append("CLI arguments")
    sources.append("environment variables")

    return config, sources
