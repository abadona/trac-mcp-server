"""Ticket attachment tool handlers for MCP server.

This module exposes file-based MCP tools that wrap Trac's
``ticket.putAttachment`` / ``getAttachment`` / ``listAttachments`` /
``deleteAttachment`` XML-RPC methods.

The tool I/O is intentionally path-based (not inline base64): MCP clients
serialize tool arguments and results into the conversation transcript, so
inlining binary payloads would re-tokenize each attachment into the
model's context. Tools accept/return absolute filesystem paths, the file
content never enters the model context — only the Trac server, the MCP
server process, and the local filesystem ever touch it.

This mirrors the ``wiki_file.py`` precedent (``wiki_file_push`` /
``wiki_file_pull`` also use ``file_path``).
"""

import logging
import xmlrpc.client
from typing import Any

import mcp.types as types

from ...core.async_utils import run_sync
from ...core.client import TracClient
from ...file_handler import validate_file_path, validate_output_path
from .errors import build_error_response, translate_xmlrpc_error

logger = logging.getLogger(__name__)


# Tool definitions for list_tools()
TICKET_ATTACHMENT_TOOLS = [
    types.Tool(
        name="ticket_attachment_put",
        description=(
            "Upload a local file as an attachment to a Trac ticket. The "
            "file is read from the server's filesystem and sent as raw "
            "bytes via XML-RPC; its contents are NOT inlined into the "
            "tool arguments or the conversation transcript."
        ),
        annotations=types.ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "Ticket number to attach to",
                    "minimum": 1,
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to local file to upload",
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Attachment filename stored on the ticket. "
                        "Defaults to the basename of file_path."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Attachment description",
                    "default": "",
                },
                "replace": {
                    "type": "boolean",
                    "description": (
                        "If true, overwrite an existing attachment with "
                        "the same filename. Default false."
                    ),
                    "default": False,
                },
            },
            "required": ["ticket_id", "file_path"],
        },
    ),
    types.Tool(
        name="ticket_attachment_get",
        description=(
            "Download a ticket attachment to a local file. Bytes are "
            "written directly to output_path; the attachment content is "
            "NOT inlined into the tool result or the conversation "
            "transcript."
        ),
        annotations=types.ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=True,
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "Ticket number the attachment belongs to",
                    "minimum": 1,
                },
                "filename": {
                    "type": "string",
                    "description": "Attachment filename to download",
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Absolute path for the downloaded file. The "
                        "parent directory must already exist."
                    ),
                },
            },
            "required": ["ticket_id", "filename", "output_path"],
        },
    ),
    types.Tool(
        name="ticket_attachment_list",
        description="List attachments on a Trac ticket.",
        annotations=types.ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "Ticket number to list attachments for",
                    "minimum": 1,
                },
            },
            "required": ["ticket_id"],
        },
    ),
    types.Tool(
        name="ticket_attachment_delete",
        description=(
            "Delete a ticket attachment permanently. Requires "
            "TICKET_ADMIN permission."
        ),
        annotations=types.ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "Ticket number the attachment belongs to",
                    "minimum": 1,
                },
                "filename": {
                    "type": "string",
                    "description": "Attachment filename to delete",
                },
            },
            "required": ["ticket_id", "filename"],
        },
    ),
]


async def handle_ticket_attachment_tool(
    name: str,
    arguments: dict | None,
    client: TracClient,
) -> types.CallToolResult:
    """Handle ticket attachment tool execution.

    Args:
        name: Tool name (ticket_attachment_put, ticket_attachment_get,
            ticket_attachment_list, ticket_attachment_delete)
        arguments: Tool arguments (dict or None)
        client: Pre-configured TracClient instance

    Returns:
        CallToolResult with text content and optional structured content,
        or CallToolResult with isError=True for errors.
    """
    args = arguments or {}

    try:
        if name == "ticket_attachment_put":
            return await _handle_put(args, client)
        elif name == "ticket_attachment_get":
            return await _handle_get(args, client)
        elif name == "ticket_attachment_list":
            return await _handle_list(args, client)
        elif name == "ticket_attachment_delete":
            return await _handle_delete(args, client)
        else:
            raise ValueError(
                f"Unknown ticket_attachment tool: {name}"
            )

    except xmlrpc.client.Fault as e:
        return translate_xmlrpc_error(e, "ticket")
    except ValueError as e:
        return build_error_response(
            "validation_error",
            str(e),
            "Check parameter values and retry.",
        )
    except Exception as e:
        return build_error_response(
            "server_error",
            str(e),
            "Contact Trac administrator or retry later.",
        )


async def _handle_put(
    args: dict[str, Any], client: TracClient
) -> types.CallToolResult:
    """Handle ticket_attachment_put.

    Reads the file from disk, wraps the raw bytes in
    ``xmlrpc.client.Binary``, and uploads via ``ticket.putAttachment``.
    """
    ticket_id = args.get("ticket_id")
    file_path = args.get("file_path")

    if not ticket_id:
        return build_error_response(
            "validation_error",
            "ticket_id is required",
            "Provide ticket_id parameter.",
        )
    if not file_path:
        return build_error_response(
            "validation_error",
            "file_path is required",
            "Provide file_path parameter.",
        )

    description = args.get("description", "")
    replace = bool(args.get("replace", False))

    # Validate path and read raw bytes
    resolved = await run_sync(validate_file_path, file_path)
    data = await run_sync(resolved.read_bytes)
    binary = xmlrpc.client.Binary(data)

    filename = args.get("filename") or resolved.name

    stored = await run_sync(
        client.put_ticket_attachment,
        ticket_id,
        filename,
        description,
        binary,
        replace,
    )

    # Trac's putAttachment typically returns the stored filename string;
    # surface whatever the server returns alongside the bytes uploaded.
    stored_name = stored if isinstance(stored, str) else filename
    bytes_uploaded = len(data)

    renamed_on_collision = stored_name != filename

    text = (
        f"Uploaded attachment '{stored_name}' to ticket #{ticket_id} "
        f"({bytes_uploaded} bytes, replace={replace})"
    )

    structured = {
        "ticket_id": ticket_id,
        "requested_filename": filename,
        "attached_filename": stored_name,
        "renamed_on_collision": renamed_on_collision,
        "file_path": str(file_path),
        "bytes_uploaded": bytes_uploaded,
        "replace": replace,
        "description": description,
    }

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=structured,
    )


async def _handle_get(
    args: dict[str, Any], client: TracClient
) -> types.CallToolResult:
    """Handle ticket_attachment_get.

    Fetches the attachment via ``ticket.getAttachment`` and writes the
    raw bytes to ``output_path``. The bytes never enter the tool result
    payload.
    """
    ticket_id = args.get("ticket_id")
    filename = args.get("filename")
    output_path = args.get("output_path")

    if not ticket_id:
        return build_error_response(
            "validation_error",
            "ticket_id is required",
            "Provide ticket_id parameter.",
        )
    if not filename:
        return build_error_response(
            "validation_error",
            "filename is required",
            "Provide filename parameter.",
        )
    if not output_path:
        return build_error_response(
            "validation_error",
            "output_path is required",
            "Provide output_path parameter.",
        )

    # Validate output path (absolute, parent dir exists)
    resolved = await run_sync(validate_output_path, output_path)

    data = await run_sync(
        client.get_ticket_attachment, ticket_id, filename
    )

    # _parse_xmlrpc_value's base64 arm returns bytes; defensively coerce
    # so callers always get a file written to disk even if a future
    # parser change hands back something else.
    if isinstance(data, str):
        # Treat as already-decoded text payload (rare); encode to utf-8
        payload = data.encode("utf-8")
    elif isinstance(data, (bytes, bytearray)):
        payload = bytes(data)
    elif isinstance(data, xmlrpc.client.Binary):
        payload = data.data
    else:
        raise ValueError(
            f"Unexpected attachment payload type: {type(data).__name__}"
        )

    await run_sync(resolved.write_bytes, payload)
    bytes_written = len(payload)

    text = (
        f"Downloaded attachment '{filename}' from ticket #{ticket_id} "
        f"to {output_path} ({bytes_written} bytes)"
    )

    structured = {
        "ticket_id": ticket_id,
        "filename": filename,
        "output_path": str(output_path),
        "bytes_written": bytes_written,
    }

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=structured,
    )


async def _handle_list(
    args: dict[str, Any], client: TracClient
) -> types.CallToolResult:
    """Handle ticket_attachment_list.

    Returns the raw attachment tuples plus a summary text rendering.
    Each tuple is ``[filename, description, size, time, author]``.
    """
    ticket_id = args.get("ticket_id")
    if not ticket_id:
        return build_error_response(
            "validation_error",
            "ticket_id is required",
            "Provide ticket_id parameter.",
        )

    raw = await run_sync(
        client.list_ticket_attachments, ticket_id
    )

    attachments: list[dict[str, Any]] = []
    for entry in raw or []:
        # Trac returns 5-tuples: (filename, description, size, time, author).
        # Defensively handle short/long tuples without crashing.
        if not isinstance(entry, (list, tuple)):
            continue
        filename = entry[0] if len(entry) > 0 else None
        description = entry[1] if len(entry) > 1 else ""
        size = entry[2] if len(entry) > 2 else None
        time_val = entry[3] if len(entry) > 3 else None
        author = entry[4] if len(entry) > 4 else None
        attachments.append(
            {
                "filename": filename,
                "description": description,
                "size": size,
                "time": str(time_val) if time_val is not None else None,
                "author": author,
            }
        )

    if attachments:
        lines = [
            f"Ticket #{ticket_id} has {len(attachments)} attachment(s):"
        ]
        for a in attachments:
            size_str = (
                f"{a['size']} bytes" if a["size"] is not None else "?"
            )
            lines.append(
                f"- {a['filename']} ({size_str}) by {a['author'] or '?'}"
            )
        text = "\n".join(lines)
    else:
        text = f"Ticket #{ticket_id} has no attachments."

    structured = {
        "ticket_id": ticket_id,
        "count": len(attachments),
        "attachments": attachments,
    }

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=structured,
    )


async def _handle_delete(
    args: dict[str, Any], client: TracClient
) -> types.CallToolResult:
    """Handle ticket_attachment_delete."""
    ticket_id = args.get("ticket_id")
    filename = args.get("filename")

    if not ticket_id:
        return build_error_response(
            "validation_error",
            "ticket_id is required",
            "Provide ticket_id parameter.",
        )
    if not filename:
        return build_error_response(
            "validation_error",
            "filename is required",
            "Provide filename parameter.",
        )

    try:
        await run_sync(
            client.delete_ticket_attachment, ticket_id, filename
        )
    except xmlrpc.client.Fault as e:
        if (
            "permission" in e.faultString.lower()
            or "denied" in e.faultString.lower()
        ):
            return build_error_response(
                "permission_denied",
                e.faultString,
                "Deleting ticket attachments requires TICKET_ADMIN. "
                "Contact Trac administrator.",
            )
        raise

    text = (
        f"Deleted attachment '{filename}' from ticket #{ticket_id}."
    )
    structured = {
        "ticket_id": ticket_id,
        "filename": filename,
    }

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=structured,
    )


__all__ = [
    "TICKET_ATTACHMENT_TOOLS",
    "handle_ticket_attachment_tool",
]
