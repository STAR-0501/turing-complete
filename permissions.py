"""TC AI Agent 的权限系统。

定义工具级别的权限等级和权限检查器，
对通过 execute_circuit_command 分发的每条命令进行权限门控。
"""

from __future__ import annotations

from enum import IntEnum


class Permission(IntEnum):
    """权限级别（值越大权限越高）。"""
    READ = 0    # 读取电路状态、采样输出
    EXEC = 1    # 仿真、切换/设置输入（不修改电路）
    WRITE = 2   # 添加/连线/移动/注释元件
    ADMIN = 3   # 删除/清空电路、定义模块


# 每个工具所需的最低权限
TOOL_PERMISSIONS: dict[str, Permission] = {
    # 读取
    "get_state": Permission.READ,
    "sample_outputs": Permission.READ,

    # 执行
    "simulate": Permission.EXEC,
    "toggle_input": Permission.EXEC,
    "set_input": Permission.EXEC,

    # 写入
    "add_element": Permission.WRITE,
    "add_wire": Permission.WRITE,
    "move_element": Permission.WRITE,
    "set_element_comment": Permission.WRITE,

    # 管理
    "remove_element": Permission.ADMIN,
    "remove_wire": Permission.ADMIN,
    "clear_circuit": Permission.ADMIN,
    "define_module": Permission.ADMIN,
}


class PermissionChecker:
    """根据当前权限等级门控工具执行。

    用法:
        checker = PermissionChecker(level=Permission.WRITE)
        checker.check("remove_element")  # → False (需要 ADMIN)
    """

    def __init__(self, level: Permission = Permission.WRITE):
        self.level = level

    def check(self, tool_name: str) -> tuple[bool, str | None]:
        """返回 (是否允许, 错误信息)。

        如果 allowed 为 True，error_message 为 None。
        如果 allowed 为 False，error_message 描述需要什么级别。
        """
        required = TOOL_PERMISSIONS.get(tool_name)
        if required is None:
            # 未知工具 → 需要 ADMIN（安全默认）
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
