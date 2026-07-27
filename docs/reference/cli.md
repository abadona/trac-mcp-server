# CLI Reference

## trac-mcp-server

The `trac-mcp-server` command starts the MCP server. It communicates via stdin/stdout using JSON-RPC 2.0 over the Model Context Protocol. It is designed to be launched by MCP clients (Claude Desktop, Claude Code, etc.), not used interactively.

### Usage

```bash
trac-mcp-server
trac-mcp-server --version
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--url URL` | -- | Override Trac URL (takes precedence over `TRAC_URL` env var) |
| `--username USER` | -- | Override Trac username (takes precedence over `TRAC_USERNAME` env var) |
| `--password PASS` | -- | Override Trac password (takes precedence over `TRAC_PASSWORD` env var) |
| `--insecure` | `false` | Skip SSL certificate verification (development only) |
| `--log-file PATH` | `/tmp/trac-mcp-server.log` | Log file location |
| `--permissions-file PATH` | -- | Restrict available tools by Trac permissions (see [Tool Architecture](tool-architecture.md#permission-filtering)) |
| `--version` | -- | Show version and exit |

### Configuration

Configuration can come from YAML config files, environment variables, or CLI flags. CLI flags take highest precedence. See [Configuration](configuration.md) for details.

### How It Works

The server runs over stdio transport: it reads JSON-RPC requests from stdin and writes responses to stdout. All log output goes to a file (never stdout), so the stdio channel stays clean for MCP protocol messages.

Typical lifecycle:

1. MCP client launches `trac-mcp-server` as a subprocess
2. Server validates Trac connection on startup
3. Server handles MCP tool calls (tickets, wiki, milestones, etc.) until the client disconnects

### Installation

```bash
pip install .          # installs trac-mcp-server command
pipx install .         # alternative: isolated environment
```

The `trac-mcp-server` command is registered as an entry point in `pyproject.toml`.

---

## trac-convert

The `trac-convert` command is a standalone binary that converts between TracWiki and Markdown formats. Unlike `trac-mcp-server`, it is designed for interactive shell use and Unix pipe composition — no Trac connection required.

### Usage

```bash
trac-convert --from md --to tracwiki < input.md > output.tw     # stdin → stdout
trac-convert --to tracwiki input.md -o output.tw                 # file → file
trac-convert --from-clipboard --to md                            # clipboard → stdout
trac-convert --to-clipboard input.md                             # file → clipboard
trac-convert --version
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--from {md,tracwiki,auto}` | `auto` | Source format; `auto` sniffs the input via heuristics |
| `--to {md,tracwiki}` | *(required unless --check-trac or --to-wiki)* | Destination format |
| `FILE` (positional) | stdin | Input file path; omit or use `-` for stdin |
| `-o, --output FILE` | stdout | Output file path; omit for stdout |
| `--from-clipboard` | -- | Read input from system clipboard instead of stdin/file (requires pyperclip) |
| `--to-clipboard` | -- | Write output to system clipboard instead of stdout/file |
| `--heading-anchors {on,off}` | `on` | md→tracwiki only: emit explicit `#slug` anchors on TracWiki headings (silently ignored in tw→md direction) |
| `--unknown-macros {bracket,preserve,drop}` | `bracket` | tw→md only: how to render unknown TracWiki macros — `bracket` = `[MACRO: Name]`, `preserve` = leave `[[Name]]` literal, `drop` = omit (silently ignored in md→tw direction) |
| `-v, --verbose` | -- | Emit `info:` diagnostics to stderr (mutually exclusive with `-q`) |
| `-q, --quiet` | -- | Suppress `warning:` lines to stderr (mutually exclusive with `-v`; does NOT suppress `error:` lines) |
| `--from-wiki PAGE` | -- | Fetch input from a Trac wiki page (source format is TracWiki). Mutually exclusive with `FILE` positional and `--from-clipboard`. |
| `--to-wiki PAGE` | -- | Write output to a Trac wiki page (target format is TracWiki). Mutually exclusive with `-o/--output` and `--to-clipboard`. Bypasses the `--to` requirement. |
| `--wiki-comment MSG` | `Updated via trac-convert` | Change comment recorded on the wiki page when using `--to-wiki`. Ignored without `--to-wiki`. |
| `--check-trac` | -- | Print resolved Trac config source per field, ping the server, and exit (no conversion performed). |
| `--trac-url URL` | -- | Override Trac URL (default: `TRAC_URL` env var or YAML config). |
| `--trac-username USER` | -- | Override Trac username (default: `TRAC_USERNAME` env var or YAML config). |
| `--trac-password PASS` | -- | Override Trac password (default: `TRAC_PASSWORD` env var or YAML config). Prefer `--trac-password-file` for secrets. |
| `--trac-password-file PATH` | -- | Read Trac password from file (single line, trimmed). Takes precedence over `--trac-password`. |
| `--version` | -- | Show version and exit |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Runtime error (I/O failure, clipboard unavailable, mutually-exclusive flag conflict) |
| `2` | Usage error (argparse-emitted: missing required flag, bad choice) |
| `3` | Conversion error (exception raised inside the converter) |
| `4` | Trac error (auth failure, network/timeout, permission denied, page not found, XML-RPC fault, SSL error) — emitted by `--check-trac`, `--from-wiki`, and `--to-wiki`. |

### Auto-detection

When `--from auto` is used (the default when omitted), the format is detected via `converters.common.detect_format`: TracWiki markers (`{{{`, `[[`, `= Heading =`) win, otherwise Markdown is assumed. On ambiguous input, prefer the explicit `--from` flag.

### Trac Wiki I/O

`--from-wiki` and `--to-wiki` read and write Trac wiki pages directly via the same `TracClient` and config precedence as `trac-mcp-server` (CLI `--trac-*` > env `TRAC_*` > `.trac_mcp/config.yml`).

```bash
# Verify connectivity: prints resolved config source per field and pings the server
trac-convert --check-trac

# Fetch a Trac wiki page, convert to Markdown, save locally
trac-convert --from-wiki MyPage --to md -o my-page.md

# Push a Markdown file back to Trac
trac-convert notes.md --to-wiki MyPage --wiki-comment "Edited via CLI"

# Round-trip: fetch, edit locally, then push back
trac-convert --from-wiki MyPage --to md -o my-page.md
# (edit my-page.md)
trac-convert my-page.md --to-wiki MyPage
```

On failure, `trac-convert` exits with code `4` and writes a classified error message (page-not-found, permission-denied, timeout, SSL, connection, generic) to stderr. See [Configuration](configuration.md) for the full auth and config precedence rules.

### Installation

```bash
pip install .          # installs BOTH trac-mcp-server and trac-convert
pipx install .         # alternative: isolated environment, both binaries available
```

Both entry points are registered in `pyproject.toml` under `[project.scripts]`.

---

[Back to Reference Overview](overview.md)
