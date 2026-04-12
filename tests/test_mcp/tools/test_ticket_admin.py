"""Tests for ticket_admin MCP tool handlers.

These tests verify the handler functions and spec definitions for the
four admin tools: ticket_component_create, ticket_component_list,
ticket_enum_create, ticket_enum_list.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import CallToolResult

from trac_mcp_server.mcp.tools.ticket_admin import (
    TICKET_ADMIN_SPECS,
    TICKET_ADMIN_TOOLS,
    _handle_component_create,
    _handle_component_list,
    _handle_enum_create,
    _handle_enum_list,
)


@pytest.fixture
def mock_client():
    """Create a MagicMock TracClient for handler tests."""
    return MagicMock()


# -- ticket_component_create ------------------------------------------------


@patch("trac_mcp_server.mcp.tools.ticket_admin.run_sync")
@pytest.mark.asyncio
async def test_component_create_calls_client(mock_run_sync, mock_client):
    """Test _handle_component_create forwards args to client.create_component."""
    mock_run_sync.return_value = None

    result = await _handle_component_create(
        mock_client, {"name": "foo", "description": "bar", "owner": "alice"}
    )

    mock_run_sync.assert_called_once_with(
        mock_client.create_component, "foo", "bar", "alice"
    )
    assert isinstance(result, CallToolResult)
    assert not result.isError
    assert "foo" in result.content[0].text
    assert "created" in result.content[0].text.lower()


@patch("trac_mcp_server.mcp.tools.ticket_admin.run_sync")
@pytest.mark.asyncio
async def test_component_create_rejects_empty_name(mock_run_sync, mock_client):
    """Test _handle_component_create returns validation error for empty name."""
    result = await _handle_component_create(mock_client, {"name": ""})

    mock_run_sync.assert_not_called()
    assert isinstance(result, CallToolResult)
    assert result.isError
    assert "validation_error" in result.content[0].text.lower()


# -- ticket_component_list --------------------------------------------------


@patch("trac_mcp_server.mcp.tools.ticket_admin.run_sync")
@pytest.mark.asyncio
async def test_component_list_returns_json_text(mock_run_sync, mock_client):
    """Test _handle_component_list returns JSON-serialized component data."""
    mock_run_sync.return_value = [
        {"name": "a", "owner": "alice", "description": "one"}
    ]

    result = await _handle_component_list(mock_client, {})

    mock_run_sync.assert_called_once_with(mock_client.list_components)
    assert isinstance(result, CallToolResult)
    assert not result.isError
    parsed = json.loads(result.content[0].text)
    assert parsed == [{"name": "a", "owner": "alice", "description": "one"}]


# -- ticket_enum_create -----------------------------------------------------


@patch("trac_mcp_server.mcp.tools.ticket_admin.run_sync")
@pytest.mark.asyncio
async def test_enum_create_priority(mock_run_sync, mock_client):
    """Test _handle_enum_create forwards priority/name to client.create_enum."""
    mock_run_sync.return_value = None

    result = await _handle_enum_create(
        mock_client, {"enum_type": "priority", "name": "urgent"}
    )

    mock_run_sync.assert_called_once_with(
        mock_client.create_enum, "priority", "urgent"
    )
    assert isinstance(result, CallToolResult)
    assert not result.isError
    assert "priority" in result.content[0].text
    assert "urgent" in result.content[0].text
    assert "created" in result.content[0].text.lower()


@patch("trac_mcp_server.mcp.tools.ticket_admin.run_sync")
@pytest.mark.asyncio
async def test_enum_create_rejects_invalid_type(mock_run_sync, mock_client):
    """Test _handle_enum_create returns validation error for bad enum_type."""
    result = await _handle_enum_create(
        mock_client, {"enum_type": "bogus", "name": "foo"}
    )

    mock_run_sync.assert_not_called()
    assert isinstance(result, CallToolResult)
    assert result.isError
    assert "validation_error" in result.content[0].text.lower()


@patch("trac_mcp_server.mcp.tools.ticket_admin.run_sync")
@pytest.mark.asyncio
async def test_enum_create_rejects_empty_name(mock_run_sync, mock_client):
    """Test _handle_enum_create returns validation error for empty name."""
    result = await _handle_enum_create(
        mock_client, {"enum_type": "priority", "name": ""}
    )

    mock_run_sync.assert_not_called()
    assert isinstance(result, CallToolResult)
    assert result.isError
    assert "validation_error" in result.content[0].text.lower()


# -- ticket_enum_list -------------------------------------------------------


@patch("trac_mcp_server.mcp.tools.ticket_admin.run_sync")
@pytest.mark.asyncio
async def test_enum_list_returns_json_text(mock_run_sync, mock_client):
    """Test _handle_enum_list returns JSON-serialized enum values."""
    mock_run_sync.return_value = ["blocker", "critical"]

    result = await _handle_enum_list(
        mock_client, {"enum_type": "priority"}
    )

    mock_run_sync.assert_called_once_with(mock_client.list_enum, "priority")
    assert isinstance(result, CallToolResult)
    assert not result.isError
    parsed = json.loads(result.content[0].text)
    assert parsed == ["blocker", "critical"]


@patch("trac_mcp_server.mcp.tools.ticket_admin.run_sync")
@pytest.mark.asyncio
async def test_enum_list_rejects_invalid_type(mock_run_sync, mock_client):
    """Test _handle_enum_list returns validation error for bad enum_type."""
    result = await _handle_enum_list(
        mock_client, {"enum_type": "bogus"}
    )

    mock_run_sync.assert_not_called()
    assert isinstance(result, CallToolResult)
    assert result.isError
    assert "validation_error" in result.content[0].text.lower()


# -- Spec verification ------------------------------------------------------


def test_specs_require_ticket_admin_for_writes():
    """Test write specs require TICKET_ADMIN, read specs require TICKET_VIEW."""
    specs_by_name = {s.tool.name: s for s in TICKET_ADMIN_SPECS}

    # Write tools require TICKET_ADMIN
    assert specs_by_name["ticket_component_create"].permissions == frozenset(
        {"TICKET_ADMIN"}
    )
    assert specs_by_name["ticket_enum_create"].permissions == frozenset(
        {"TICKET_ADMIN"}
    )

    # Read tools require only TICKET_VIEW
    assert specs_by_name["ticket_component_list"].permissions == frozenset(
        {"TICKET_VIEW"}
    )
    assert specs_by_name["ticket_enum_list"].permissions == frozenset(
        {"TICKET_VIEW"}
    )


def test_tool_count():
    """Belt-and-suspenders pin: exactly 4 tools and 4 specs."""
    assert len(TICKET_ADMIN_TOOLS) == 4
    assert len(TICKET_ADMIN_SPECS) == 4
