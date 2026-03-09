"""Dual-agent architecture for state management and content generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from agent_tools import TOOLS, execute_tool
from core.llm_utils import (
    assistant_message_from_response,
    extract_message_content,
    normalize_tool_calls,
)


class StateAgent:
    """State agent responsible for querying and updating character states."""

    def __init__(
        self,
        llm_function: Callable,
        schema_path: str = "state_schema.yaml",
        progress_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.llm_function = llm_function
        self.tools = TOOLS
        self.schema = self._load_schema(schema_path)
        self.progress_callback = progress_callback

    def _load_schema(self, path: str) -> dict:
        schema_path = Path(path)
        if not schema_path.is_absolute():
            schema_path = Path(__file__).resolve().parent / schema_path
        with open(schema_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _emit_progress(self, event_type: str, **payload: Any) -> None:
        if callable(self.progress_callback):
            self.progress_callback({"type": event_type, **payload})

    def _normalize_fields_payload(self, fields: Any) -> dict[str, Any]:
        if isinstance(fields, dict):
            return fields
        if isinstance(fields, str):
            try:
                parsed = json.loads(fields)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def build_update_prompt(self, content: str, chapter: int) -> str:
        return (
            "根据以下章节内容，更新所有相关角色的状态。\n\n"
            "状态规则：\n"
            f"{yaml.dump(self.schema, allow_unicode=True, sort_keys=False)}\n"
            "章节内容：\n"
            f"{content}\n\n"
            "要求：\n"
            "1. 仅通过工具调用写入状态\n"
            "2. 所有写入都必须包含 `chapter` 和 `reason`\n"
            "3. 如果出现新角色，先创建角色再写入字段\n"
            "4. 不确定时保守处理，不要虚构明确状态"
        )

    def build_update_messages(self, content: str, chapter: int) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": "你是状态管理 Agent，负责根据章节正文更新角色状态。",
            },
            {"role": "user", "content": self.build_update_prompt(content, chapter)},
        ]

    def prepare_context(self, chapter: int) -> str:
        """Prepare a simple state summary for backward compatibility."""
        from dynamic_state import DynamicStateManager

        manager = DynamicStateManager()
        characters = sorted(manager.list_characters())

        if not characters:
            return f"第{chapter}章暂无可用角色状态。"

        lines = [f"第{chapter}章生成前的角色当前状态："]
        for name in characters:
            data = manager.get_character_latest(name)
            if "error" in data:
                continue
            lines.append(f"- {name}")
            for field_name, value in data.get("fields", {}).items():
                lines.append(f"  - {field_name}: {value}")

        return "\n".join(lines)

    def query_states_actively(self, chapter: int, history_context: str) -> dict:
        """
        Let the model decide which character states should be queried.

        Returns a dict with the full conversation and collected tool results.
        """
        prompt = f"""你是状态查询 Agent。

请基于下面的历史上下文，为第{chapter}章生成做准备。你需要自主决定应该查询哪些角色的状态。

历史上下文：
{history_context}

请使用这些工具完成查询：
- `list_characters()`：列出所有角色
- `get_character_latest(name)`：获取角色当前状态
- `get_character(name)`：在确有必要时查看完整历史

目标：
1. 找出第{chapter}章高概率会出场或被提及的角色
2. 查询这些角色的最新状态
3. 如果有必要，再补充查看完整历史
4. 当你认为信息足够时，直接给出一句简短结论，不要继续调用工具
"""

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": "你是状态查询 Agent，只负责查询，不负责编造状态。",
            },
            {"role": "user", "content": prompt},
        ]
        tool_results: dict[str, Any] = {}
        self._emit_progress(
            "status",
            stage="query",
            message=f"开始为第 {chapter} 章主动查询角色状态。",
        )

        for round_num in range(1, 9):
            self._emit_progress(
                "status",
                stage="query",
                message=f"第 {round_num} 轮角色状态查询。",
            )
            response = self.llm_function(messages, self.tools)
            assistant_message = assistant_message_from_response(response)
            messages.append(assistant_message)
            assistant_content = extract_message_content(response).strip()
            if assistant_content:
                self._emit_progress(
                    "agent_note",
                    stage="query",
                    message=assistant_content[:300],
                )

            tool_calls = normalize_tool_calls(response)
            if not tool_calls:
                self._emit_progress(
                    "query_decision",
                    stage="query",
                    message=assistant_content or "查询 Agent 认为当前信息已经足够。",
                )
                break

            for tool_call in tool_calls:
                self._emit_progress(
                    "tool_call",
                    stage="query",
                    action="查询",
                    tool_name=tool_call["name"],
                    character=tool_call["arguments"].get("name", ""),
                    field_names=[],
                    arguments=tool_call["arguments"],
                )
                result = execute_tool(tool_call["name"], tool_call["arguments"])

                if tool_call["name"] in {"get_character_latest", "get_character"}:
                    character_name = result.get("name") or tool_call["arguments"].get("name")
                    if character_name and "error" not in result:
                        tool_results[character_name] = result
                elif tool_call["name"] == "list_characters":
                    tool_results["_character_list"] = result

                if "error" in result:
                    self._emit_progress(
                        "tool_error",
                        stage="query",
                        tool_name=tool_call["name"],
                        character=tool_call["arguments"].get("name", ""),
                        message=result["error"],
                    )
                else:
                    payload: dict[str, Any] = {
                        "stage": "query",
                        "tool_name": tool_call["name"],
                    }
                    if tool_call["name"] == "list_characters":
                        characters = result.get("characters", [])
                        payload.update(
                            {
                                "character_count": len(characters),
                                "characters": characters,
                            }
                        )
                    else:
                        fields = result.get("fields", {})
                        payload.update(
                            {
                                "character": result.get("name")
                                or tool_call["arguments"].get("name", ""),
                                "field_names": list(fields.keys()),
                            }
                        )
                    self._emit_progress("tool_result", **payload)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        if not any(name != "_character_list" for name in tool_results):
            from dynamic_state import DynamicStateManager

            manager = DynamicStateManager()
            for name in sorted(manager.list_characters()):
                result = manager.get_character_latest(name)
                if "error" not in result:
                    tool_results[name] = result
            self._emit_progress(
                "status",
                stage="query",
                message="查询阶段未命中明确角色，已回退为读取全部角色最新状态。",
            )

        queried_characters = sorted(
            name for name in tool_results.keys() if name != "_character_list"
        )
        self._emit_progress(
            "query_summary",
            stage="query",
            message=f"查询完成，共整理出 {len(queried_characters)} 个角色状态。",
            characters=queried_characters,
        )

        return {
            "conversation": messages,
            "tool_results": tool_results,
        }

    def update_states(self, content: str, chapter: int) -> None:
        """Update character states based on chapter content."""
        messages = self.build_update_messages(content, chapter)

        self._emit_progress("status", message="开始分析章节内容。")

        for round_num in range(1, 11):
            self._emit_progress("status", message=f"第 {round_num} 轮状态分析。")
            response = self.llm_function(messages, self.tools)

            assistant_content = extract_message_content(response).strip()
            if assistant_content:
                self._emit_progress("agent_note", message=assistant_content[:300])

            assistant_message = assistant_message_from_response(response)
            tool_calls = normalize_tool_calls(response)
            if not tool_calls:
                messages.append(assistant_message)
                self._emit_progress("status", message="状态更新分析完成。")
                break

            messages.append(assistant_message)
            self._emit_progress(
                "status",
                message=f"本轮发现 {len(tool_calls)} 个状态操作。",
            )

            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                arguments = tool_call["arguments"]
                character = arguments.get("name", "")
                fields = self._normalize_fields_payload(arguments.get("fields"))
                action = (
                    "创建"
                    if tool_name == "create_character"
                    else "更新"
                    if tool_name == "update_character"
                    else "处理"
                )

                self._emit_progress(
                    "tool_call",
                    tool_name=tool_name,
                    action=action,
                    character=character,
                    field_names=list(fields.keys()),
                    reason=arguments.get("reason", ""),
                    chapter=arguments.get("chapter", chapter),
                )

                result = execute_tool(tool_name, arguments)
                if "error" in result:
                    self._emit_progress(
                        "tool_error",
                        tool_name=tool_name,
                        character=character,
                        message=result["error"],
                    )
                else:
                    if tool_name in {"create_character", "update_character"}:
                        for field_name, field_value in fields.items():
                            self._emit_progress(
                                "field_update",
                                tool_name=tool_name,
                                action=action,
                                character=character,
                                field=field_name,
                                value=field_value,
                                reason=arguments.get("reason", ""),
                                chapter=arguments.get("chapter", chapter),
                            )

                    self._emit_progress(
                        "tool_result",
                        tool_name=tool_name,
                        character=result.get("character", character),
                        updated_fields=result.get(
                            "updated_fields", list(fields.keys())
                        ),
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )


class ContentAgent:
    """Content agent responsible for chapter prose generation."""

    def __init__(self, llm_function: Callable):
        self.llm_function = llm_function

    def build_messages(
        self,
        chapter: int,
        context: str,
        previous_summary: str = "",
    ) -> list[dict[str, str]]:
        prompt = context
        if previous_summary.strip():
            prompt = f"{context}\n\n【额外补充】\n{previous_summary.strip()}"

        return [
            {
                "role": "system",
                "content": "你是小说创作 Agent，只输出章节正文，不解释写作过程。",
            },
            {"role": "user", "content": prompt},
        ]

    def generate(self, chapter: int, context: str, previous_summary: str = "") -> str:
        messages = self.build_messages(chapter, context, previous_summary)
        response = self.llm_function(messages, tools=None)
        return extract_message_content(response)
