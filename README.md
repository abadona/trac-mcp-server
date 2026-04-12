<p align="center">
  <img src="img/trac_mcp_server_banner_dark_1280.png" alt="trac-mcp-server banner" />
</p>

# trac-mcp-server

Standalone MCP server that gives AI agents full access to Trac project management -- tickets, wiki, milestones, and search -- via the Model Context Protocol.

## Quick Start

Requires Python 3.10 or later.

```bash
pip install .
```

Set your Trac connection:

```bash
export TRAC_URL="https://trac.example.com"
export TRAC_USERNAME="your-username"
export TRAC_PASSWORD="your-password"
```

Run the server:

```bash
trac-mcp-server
```

## Configuration

Configuration via environment variables, `.env` file, or YAML config file (`.trac_mcp/config.yaml`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRAC_URL` | Yes | -- | Trac instance URL |
| `TRAC_USERNAME` | Yes | -- | Trac username |
| `TRAC_PASSWORD` | Yes | -- | Trac password |
| `TRAC_INSECURE` | No | `false` | Skip SSL verification (development only) |
| `TRAC_DEBUG` | No | `false` | Enable debug logging |
| `TRAC_MAX_PARALLEL_REQUESTS` | No | `5` | Max parallel XML-RPC requests |
| `TRAC_MAX_BATCH_SIZE` | No | `500` | Max items per batch operation (1-10000) |

For YAML config file format and advanced options, see [Configuration Reference](docs/reference/configuration.md).

## MCP Client Integration

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "trac": {
      "command": "trac-mcp-server",
      "env": {
        "TRAC_URL": "https://trac.example.com",
        "TRAC_USERNAME": "your-username",
        "TRAC_PASSWORD": "your-password"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add trac -e TRAC_URL=https://trac.example.com \
  -e TRAC_USERNAME=your-username \
  -e TRAC_PASSWORD=your-password \
  -- trac-mcp-server
```

### Other MCP Clients

Any MCP client that supports stdio transport can launch `trac-mcp-server` as a subprocess. Pass Trac credentials via environment variables.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Project Structure

```
src/trac_mcp_server/
  config.py       # Environment variable configuration
  core/           # Trac XML-RPC client, async utilities
  mcp/            # MCP server, tools, resources
  converters/     # Markdown <-> TracWiki conversion
  detection/      # Content format detection
```

## Documentation

See [docs/reference/overview.md](docs/reference/overview.md) for detailed tool reference, configuration, and troubleshooting.
