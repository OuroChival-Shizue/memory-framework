"""Utilities for turning tool-heavy query results into readable prompt text."""

from __future__ import annotations

from typing import Any


class PromptCleaner:
    def __init__(self, llm_function=None):
        self.llm_function = llm_function

    def clean_character_states(self, conversation: list, tool_results: dict) -> str:
        """Render tool results into human-readable character state notes."""
        lines: list[str] = []

        for char_name, char_data in tool_results.items():
            if char_name == "_character_list":
                continue
            if not isinstance(char_data, dict) or "error" in char_data:
                continue

            lines.append(f"- {char_name}：")
            fields = char_data.get("fields", {})
            if not fields:
                lines.append("  - 暂无可用字段")
                continue

            for field_name, field_value in fields.items():
                value = field_value
                if isinstance(field_value, list) and field_value:
                    latest = field_value[-1]
                    if isinstance(latest, dict):
                        value = latest.get("value", latest)
                    else:
                        value = latest
                lines.append(f"  - {field_name}：{value}")

        return "\n".join(lines) if lines else "暂无已查询到的角色状态。"

    def extract_task_description(self, conversation: list, history_context: str) -> str:
        """Generate a concise current-task description from existing context."""
        lines = [line.strip() for line in history_context.splitlines() if line.strip()]
        focus_line = ""
        for line in reversed(lines):
            if line.startswith("【") and line.endswith("】"):
                continue
            if line.startswith("第") and "章" in line:
                continue
            if len(line) >= 12:
                focus_line = line[:120]
                break

        description = "延续已有剧情，保持角色状态一致，推进当前章节的核心事件与冲突。"
        if focus_line:
            description += f" 重点承接：{focus_line}"
        return description
