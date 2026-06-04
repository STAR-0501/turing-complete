"""Permission system for TC's AI Agent.

Defines tool-level permission levels and a permission checker
that gates every command dispatched through execute_circuit_command.
"""

from __future__ import annotations

from enum import IntEnum


class Permission(IntEnum):
    """Permission levels (higher = more authority)."""
    READ = 0    # Read circuit state, sample outputs
    EXEC = 1    # Simulate, toggle/set inputs (no modification)
    WRITE = 2   # Add/wire/move/comment elements
    ADMIN = 3   # Delete/clear circuit, define modules


# Minimum permission required for each tool
TOOL_PERMISSIONS: dict[str, Permission] = {
    # READ
    "get_state": Permission.READ,
    "sample_outputs": Permission.READ,

    # EXEC
    "simulate": Permission.EXEC,
    "toggle_input": Permission.EXEC,
    "set_input": Permission.EXEC,

    # WRITE
    "add_element": Permission.WRITE,
    "add_wire": Permission.WRITE,
    "move_element": Permission.WRITE,
    "set_element_comment": Permission.WRITE,

    # ADMIN
    "remove_element": Permission.ADMIN,
    "remove_wire": Permission.ADMIN,
    "clear_circuit": Permission.ADMIN,
    "define_module": Permission.ADMIN,
}


class PermissionChecker:
    """Gates tool execution against the current permission level.

    Usage:
        checker = PermissionChecker(level=Permission.WRITE)
        checker.check("remove_element")  # → False (needs ADMIN)
    """

    def __init__(self, level: Permission = Permission.WRITE):
        self.level = level

    def check(self, tool_name: str) -> tuple[bool, str | None]:
        """Return (allowed, error_message).

        If allowed is True, error_message is None.
        If allowed is False, error_message describes what level is needed.
        """
        required = TOOL_PERMISSIONS.get(tool_name)
        if required is None:
            # Unknown tool → ADMIN required (safe default)
            if self.level >= Permission.ADMIN:
                return True, None
            return False, (
                f"Permission denied: '{tool_name}' is not in the tool registry "
                f"and requires ADMIN level (current: {self.level.name})"
            )
        if self.level >= required:
            return True, None
        return False, (
            f"Permission denied: '{tool_name}' requires {required.name} "
            f"(current: {self.level.name})"
        )
