"""Batch ticket tool handlers for MCP server.

This module implements batch ticket operations: batch create, batch update,
and batch delete. All operations use best-effort processing -- every item
is attempted, and per-item success/failure is reported in the response.
Parallelism is bounded by the existing gather_limited/run_sync_limited
infrastructure.
"""

import logging
from typing import Any

import mcp.types as types

from ...converters import markdown_to_tracwiki
from ...core.async_utils import gather_limited, run_sync_limited
from ...core.client import TracClient
from .constants import DEFAULT_TICKET_TYPE
from .errors import build_error_response
from .registry import ToolSpec
from .ticket_write import merge_extra_fields

logger = logging.getLogger(__name__)

# Per-item accepted keys, mirroring the JSON-Schema `properties` on each
# batch tool. Unknown per-item keys are rejected as a per-item failure so
# one malformed item does not silently no-op while the batch as a whole
# reports success. Distinct from the single-tool sets because the batch
# schemas do not currently expose ``severity``, ``summary``, ``description``,
# ``type``, or ``action`` in the update variant.
_BATCH_CREATE_ITEM_ACCEPTED_KEYS = frozenset(
    {
        "summary",
        "description",
        "ticket_type",
        "priority",
        "component",
        "milestone",
        "owner",
        "cc",
        "keywords",
        "extra_fields",
    }
)

_BATCH_UPDATE_ITEM_ACCEPTED_KEYS = frozenset(
    {
        "ticket_id",
        "comment",
        "status",
        "resolution",
        "priority",
        "component",
        "milestone",
        "owner",
        "cc",
        "keywords",
        "extra_fields",
    }
)


def _find_unknown_keys(
    item: dict, accepted: frozenset[str]
) -> list[str]:
    """Return sorted list of ``item`` keys that are not in ``accepted``."""
    return sorted(k for k in item if k not in accepted)


def _format_unknown_keys_error(unknown: list[str]) -> str:
    """Format a per-item error message naming the offending keys."""
    joined = ", ".join(repr(k) for k in unknown)
    return (
        f"Unknown parameter(s): {joined}. Use `extra_fields` for custom "
        "Trac fields."
    )


# Tool definitions for list_tools()
TICKET_BATCH_TOOLS = [
    types.Tool(
        name="ticket_batch_create",
        description="Create multiple tickets in a single batch operation. Best-effort: all items attempted, per-item results reported. Bounded by TRAC_MAX_PARALLEL_REQUESTS semaphore.",
        inputSchema={
            "type": "object",
            "properties": {
                "tickets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "description": {"type": "string"},
                            "ticket_type": {"type": "string"},
                            "priority": {"type": "string"},
                            "component": {"type": "string"},
                            "milestone": {"type": "string"},
                            "owner": {"type": "string"},
                            "keywords": {"type": "string"},
                            "cc": {"type": "string"},
                            "extra_fields": {
                                "type": "object",
                                "description": "Optional map of custom Trac field name to string value, forwarded verbatim to the ticket. Use for fields defined in the instance's [ticket-custom] section that are not exposed as top-level parameters. Standard fields specified at the top level take precedence on collision.",
                                "additionalProperties": {
                                    "type": "string"
                                },
                            },
                        },
                        "required": ["summary", "description"],
                    },
                    "description": "List of ticket objects to create",
                }
            },
            "required": ["tickets"],
        },
    ),
    types.Tool(
        name="ticket_batch_delete",
        description="Delete multiple tickets in a single batch operation. Best-effort: all items attempted, per-item results reported. Requires TICKET_ADMIN permission.",
        inputSchema={
            "type": "object",
            "properties": {
                "ticket_ids": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "description": "List of ticket IDs to delete",
                }
            },
            "required": ["ticket_ids"],
        },
    ),
    types.Tool(
        name="ticket_batch_update",
        description="Update multiple tickets in a single batch operation. Best-effort: all items attempted, per-item results reported.",
        inputSchema={
            "type": "object",
            "properties": {
                "updates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticket_id": {
                                "type": "integer",
                                "minimum": 1,
                            },
                            "comment": {"type": "string"},
                            "status": {"type": "string"},
                            "resolution": {"type": "string"},
                            "priority": {"type": "string"},
                            "component": {"type": "string"},
                            "milestone": {"type": "string"},
                            "owner": {"type": "string"},
                            "keywords": {"type": "string"},
                            "cc": {"type": "string"},
                            "extra_fields": {
                                "type": "object",
                                "description": "Optional map of custom Trac field name to string value, forwarded verbatim to the ticket. Use for fields defined in the instance's [ticket-custom] section (e.g. 'parent' for TracChildTickets) that are not exposed as top-level parameters. An empty string clears a text-typed custom field. Standard fields specified at the top level take precedence on collision.",
                                "additionalProperties": {
                                    "type": "string"
                                },
                            },
                        },
                        "required": ["ticket_id"],
                    },
                    "description": "List of update objects with ticket_id and fields to change",
                }
            },
            "required": ["updates"],
        },
    ),
]


async def _handle_batch_create(
    client: TracClient, args: dict
) -> types.CallToolResult:
    """Handle ticket_batch_create."""
    tickets = args.get("tickets")
    if not tickets:
        return build_error_response(
            "validation_error",
            "tickets list is required and cannot be empty",
            "Provide a non-empty tickets array.",
        )

    max_size = client.config.max_batch_size
    if len(tickets) > max_size:
        return build_error_response(
            "validation_error",
            f"Batch size {len(tickets)} exceeds maximum {max_size}. Split into smaller batches.",
            "Reduce the number of tickets per request.",
        )

    async def _create_one(
        index: int, ticket_data: dict
    ) -> dict[str, Any]:
        # Reject unknown per-item keys before any work so a mistaken
        # top-level custom-field write does not silently no-op the item.
        unknown = _find_unknown_keys(
            ticket_data, _BATCH_CREATE_ITEM_ACCEPTED_KEYS
        )
        if unknown:
            return {
                "index": index,
                "summary": ticket_data.get("summary", ""),
                "error": _format_unknown_keys_error(unknown),
            }

        summary = ticket_data.get("summary")
        description = ticket_data.get("description")

        if not summary:
            return {
                "index": index,
                "summary": "",
                "error": "summary is required",
            }
        if not description:
            return {
                "index": index,
                "summary": summary,
                "error": "description is required",
            }

        try:
            description_tracwiki = markdown_to_tracwiki(description)
            ticket_type = ticket_data.get(
                "ticket_type", DEFAULT_TICKET_TYPE
            )
            attributes: dict[str, Any] = {}

            for field in (
                "priority",
                "component",
                "milestone",
                "owner",
                "cc",
                "keywords",
            ):
                if field in ticket_data:
                    attributes[field] = ticket_data[field]

            # Merge per-item custom fields; a malformed extra_fields for
            # this ticket raises ValueError which the enclosing except
            # translates into a per-item failure record without aborting
            # the batch.
            merge_extra_fields(ticket_data, attributes)

            ticket_id = await run_sync_limited(
                client.create_ticket,
                summary,
                description_tracwiki,
                ticket_type,
                attributes,
            )
            return {"id": ticket_id, "summary": summary}
        except Exception as e:
            return {
                "index": index,
                "summary": ticket_data.get("summary", ""),
                "error": str(e),
            }

    results = await gather_limited(
        [_create_one(i, t) for i, t in enumerate(tickets)]
    )

    created = [r for r in results if "id" in r]
    failed = [r for r in results if "error" in r]
    total = len(tickets)

    # Build text response
    lines = [
        f"Batch create: {len(created)}/{total} succeeded, {len(failed)} failed."
    ]
    if created:
        lines.append("")
        lines.append("Created:")
        for item in created:
            lines.append(f"  - #{item['id']}: {item['summary']}")
    if failed:
        lines.append("")
        lines.append("Failed:")
        for item in failed:
            lines.append(
                f"  - [index {item.get('index', '?')}] {item.get('summary', '')}: {item['error']}"
            )

    return types.CallToolResult(
        content=[types.TextContent(type="text", text="\n".join(lines))],
        structuredContent={
            "created": created,
            "failed": failed,
            "total": total,
            "succeeded": len(created),
            "failed_count": len(failed),
        },
    )


async def _handle_batch_delete(
    client: TracClient, args: dict
) -> types.CallToolResult:
    """Handle ticket_batch_delete."""
    ticket_ids = args.get("ticket_ids")
    if not ticket_ids:
        return build_error_response(
            "validation_error",
            "ticket_ids list is required and cannot be empty",
            "Provide a non-empty ticket_ids array.",
        )

    max_size = client.config.max_batch_size
    if len(ticket_ids) > max_size:
        return build_error_response(
            "validation_error",
            f"Batch size {len(ticket_ids)} exceeds maximum {max_size}. Split into smaller batches.",
            "Reduce the number of ticket IDs per request.",
        )

    async def _delete_one(ticket_id: int) -> dict[str, Any]:
        try:
            await run_sync_limited(client.delete_ticket, ticket_id)
            return {"id": ticket_id}
        except Exception as e:
            return {"id": ticket_id, "error": str(e)}

    results = await gather_limited(
        [_delete_one(tid) for tid in ticket_ids]
    )

    deleted = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    total = len(ticket_ids)

    # Build text response
    lines = [
        f"Batch delete: {len(deleted)}/{total} succeeded, {len(failed)} failed."
    ]
    if deleted:
        lines.append("")
        lines.append("Deleted:")
        for item in deleted:
            lines.append(f"  - #{item['id']}")
    if failed:
        lines.append("")
        lines.append("Failed:")
        for item in failed:
            lines.append(f"  - #{item['id']}: {item['error']}")

    return types.CallToolResult(
        content=[types.TextContent(type="text", text="\n".join(lines))],
        structuredContent={
            "deleted": [r["id"] for r in deleted],
            "failed": failed,
            "total": total,
            "succeeded": len(deleted),
            "failed_count": len(failed),
        },
    )


async def _handle_batch_update(
    client: TracClient, args: dict
) -> types.CallToolResult:
    """Handle ticket_batch_update."""
    updates = args.get("updates")
    if not updates:
        return build_error_response(
            "validation_error",
            "updates list is required and cannot be empty",
            "Provide a non-empty updates array.",
        )

    max_size = client.config.max_batch_size
    if len(updates) > max_size:
        return build_error_response(
            "validation_error",
            f"Batch size {len(updates)} exceeds maximum {max_size}. Split into smaller batches.",
            "Reduce the number of updates per request.",
        )

    async def _update_one(update_data: dict) -> dict[str, Any]:
        # Reject unknown per-item keys before any work; same rationale as
        # ticket_batch_create (silent no-op is the failure mode #1163
        # closes).
        unknown = _find_unknown_keys(
            update_data, _BATCH_UPDATE_ITEM_ACCEPTED_KEYS
        )
        if unknown:
            return {
                "id": update_data.get("ticket_id", 0),
                "error": _format_unknown_keys_error(unknown),
            }

        ticket_id = update_data.get("ticket_id")
        if not ticket_id:
            return {
                "id": update_data.get("ticket_id", 0),
                "error": "ticket_id is required",
            }

        try:
            comment = update_data.get("comment", "")
            if comment:
                comment = markdown_to_tracwiki(comment)

            attributes: dict[str, Any] = {}
            for field in (
                "status",
                "resolution",
                "priority",
                "component",
                "milestone",
                "owner",
                "cc",
                "keywords",
            ):
                if field in update_data:
                    attributes[field] = update_data[field]

            # Merge per-item custom fields; a malformed extra_fields for
            # this ticket raises ValueError which the enclosing except
            # translates into a per-item failure record without aborting
            # the batch.
            merge_extra_fields(update_data, attributes)

            await run_sync_limited(
                client.update_ticket, ticket_id, comment, attributes
            )
            return {"id": ticket_id}
        except Exception as e:
            return {
                "id": update_data.get("ticket_id", 0),
                "error": str(e),
            }

    results = await gather_limited([_update_one(u) for u in updates])

    updated = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    total = len(updates)

    # Build text response
    lines = [
        f"Batch update: {len(updated)}/{total} succeeded, {len(failed)} failed."
    ]
    if updated:
        lines.append("")
        lines.append("Updated:")
        for item in updated:
            lines.append(f"  - #{item['id']}")
    if failed:
        lines.append("")
        lines.append("Failed:")
        for item in failed:
            lines.append(f"  - #{item['id']}: {item['error']}")

    return types.CallToolResult(
        content=[types.TextContent(type="text", text="\n".join(lines))],
        structuredContent={
            "updated": [r["id"] for r in updated],
            "failed": failed,
            "total": total,
            "succeeded": len(updated),
            "failed_count": len(failed),
        },
    )


# ToolSpec list for registry-based dispatch
TICKET_BATCH_SPECS: list[ToolSpec] = [
    ToolSpec(
        tool=TICKET_BATCH_TOOLS[0],
        permissions=frozenset({"TICKET_CREATE", "TICKET_BATCH_MODIFY"}),
        handler=_handle_batch_create,
    ),
    ToolSpec(
        tool=TICKET_BATCH_TOOLS[1],
        permissions=frozenset({"TICKET_ADMIN", "TICKET_BATCH_MODIFY"}),
        handler=_handle_batch_delete,
    ),
    ToolSpec(
        tool=TICKET_BATCH_TOOLS[2],
        permissions=frozenset({"TICKET_MODIFY", "TICKET_BATCH_MODIFY"}),
        handler=_handle_batch_update,
    ),
]
