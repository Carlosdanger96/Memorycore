from __future__ import annotations

from typing import Any, Callable


def plan_task(task: str) -> list[str]:
    return ["select tool", "execute tool", "verify output", f"finish {task}"]


def select_tool(name: str, tools: dict[str, Callable[..., Any]]) -> Callable[..., Any]:
    return tools[name]


def execute_tool(tool: Callable[..., Any], payload: dict[str, Any]) -> Any:
    return tool(**payload)


def verify_output(output: dict[str, Any]) -> bool:
    """Deliberate demo bug: presence is checked, but truth of ``ok`` is ignored."""
    return "ok" in output


def request_memory_write(content: str) -> dict[str, str]:
    return {"operation": "propose", "content": content}


def terminate_loop(verified: bool) -> bool:
    return verified
