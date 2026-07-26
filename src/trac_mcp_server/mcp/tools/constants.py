"""Shared constants for MCP tool handlers."""

# Default ticket type when none is specified by the user.
# This value is used by both ticket_write and ticket_batch modules.
# 'defect' is chosen because it is part of Trac's out-of-the-box ticket type
# set and matches Trac's own default for new tickets. The other standard
# values shipped with Trac are 'enhancement' and 'task' (see TICKET_TYPE_LIST
# below).
DEFAULT_TICKET_TYPE = "defect"

# Human-readable list of common ticket types for tool descriptions.
TICKET_TYPE_LIST = "defect, enhancement, task"
