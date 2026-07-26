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
| `--to {md,tracwiki}` | *(required)* | Destination format |
| `FILE` (positional) | stdin | Input file path; omit or use `-` for stdin |
| `-o, --output FILE` | stdout | Output file path; omit for stdout |
| `--from-clipboard` | -- | Read input from system clipboard instead of stdin/file (requires pyperclip) |
| `--to-clipboard` | -- | Write output to system clipboard instead of stdout/file |
| `--heading-anchors {on,off}` | `on` | md→tracwiki only: emit explicit `#slug` anchors on TracWiki headings (silently ignored in tw→md direction) |
| `--unknown-macros {bracket,preserve,drop}` | `bracket` | tw→md only: how to render unknown TracWiki macros — `bracket` = `[MACRO: Name]`, `preserve` = leave `[[Name]]` literal, `drop` = omit (silently ignored in md→tw direction) |
| `-v, --verbose` | -- | Emit `info:` diagnostics to stderr (mutually exclusive with `-q`) |
| `-q, --quiet` | -- | Suppress `warning:` lines to stderr (mutually exclusive with `-v`; does NOT suppress `error:` lines) |
| `--version` | -- | Show version and exit |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Runtime error (I/O failure, clipboard unavailable, mutually-exclusive flag conflict) |
| `2` | Usage error (argparse-emitted: missing required flag, bad choice) |
| `3` | Conversion error (exception raised inside the converter) |

### Auto-detection

When `--from auto` is used (the default when omitted), the format is detected via `converters.common.detect_format`: TracWiki markers (`{{{`, `[[`, `= Heading =`) win, otherwise Markdown is assumed. On ambiguous input, prefer the explicit `--from` flag.

### Installation

```bash
pip install .          # installs BOTH trac-mcp-server and trac-convert
pipx install .         # alternative: isolated environment, both binaries available
```

Both entry points are registered in `pyproject.toml` under `[project.scripts]`.

---

[Back to Reference Overview](overview.md)
