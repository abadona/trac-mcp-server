"""Entry point for trac-convert when run as `python -m trac_mcp_server.cli`."""

from trac_mcp_server.cli.convert import run

if __name__ == "__main__":
    run()
