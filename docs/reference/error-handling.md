# Error Handling

## Error Response Format

All errors are returned as structured text content with consistent formatting:

```
Error ({error_type}): {message}

Action: {corrective_action}
```

## Error Types

| Error Type | Meaning | Common Causes |
|------------|---------|---------------|
| `not_found` | Resource does not exist | Invalid ticket ID, missing wiki page, unknown milestone |
| `permission_denied` | Insufficient permissions | Missing TICKET_VIEW, WIKI_CREATE, TICKET_ADMIN, etc. |
| `version_conflict` | Concurrent modification | Another user modified resource since you loaded it |
| `validation_error` | Invalid input parameters | Missing required fields, invalid values, format errors |
| `already_exists` | Resource already exists | Creating wiki page or milestone that exists |
| `timeout_ticket_created` | `ticket_create` timed out, but the ticket was created anyway | Slow Trac response; the write landed after the client gave up |
| `timeout_not_created` | `ticket_create` timed out and no matching ticket was found | Slow Trac response; the write most likely did not land |
| `server_error` | Server-side error | XML-RPC failure, network issues, Trac bugs |

## Corrective Actions by Error Type

### not_found

```
Error (not_found): Ticket #999 not found

Action: Use ticket_search to verify ticket exists.
```

**Resolution:** Search for valid resources before operating on them.

### permission_denied

```
Error (permission_denied): TICKET_CREATE permission required

Action: Try adding a comment instead, or contact ticket owner.
```

**Resolution:** Check user permissions, request elevated access, or use alternative actions.

### version_conflict

```
Error (version_conflict): Page has been modified. Current version is 7, you tried to update version 5.

Action: Fetch current content with wiki_get(page_name='Page'), then retry update with version=7.
```

**Resolution:** Re-fetch the resource, merge changes if needed, retry with correct version.

### validation_error

```
Error (validation_error): summary is required

Action: Provide summary parameter.
```

**Resolution:** Provide all required parameters with valid values.

### already_exists

```
Error (already_exists): Page 'WikiStart' already exists

Action: Use wiki_update to modify existing page, or choose a different name.
```

**Resolution:** Use update operation instead of create, or choose unique name.

### timeout_ticket_created

```
Error (timeout_ticket_created): ticket.create timed out after 60s, but the
ticket was created anyway as #77. Do not retry; read #77 to confirm its contents.

Action: Do NOT retry -- that would create a duplicate. Use
ticket_get(ticket_id=77) to confirm the ticket, and ticket_update to correct
it if needed.
```

**Resolution:** Treat the ticket as created. `ticket_create` is not idempotent,
so retrying produces a duplicate.

### timeout_not_created

```
Error (timeout_not_created): ticket.create timed out after 60s and no ticket
matching this summary was found afterwards, so it most likely was not created.

Action: Retrying ticket_create is most likely safe. To be certain first, use
ticket_search to check whether a ticket with this summary already exists.
```

**Resolution:** Retry the create. The check is a heuristic (recent tickets by
the same reporter, matched on summary), so confirm with `ticket_search` first
if many tickets share this summary or were created concurrently. Raising
`TRAC_RPC_TIMEOUT` reduces how often this occurs.

### server_error

```
Error (server_error): Connection refused

Action: Contact Trac administrator or retry later.
```

**Resolution:** Check server status, network connectivity, or contact administrator.
A bare `Timeout` reaching this handler for `ticket_create` means the
created/not-created check could not be completed, so the outcome is unknown --
verify with `ticket_search` before retrying.

---

[Back to Reference Overview](overview.md)
