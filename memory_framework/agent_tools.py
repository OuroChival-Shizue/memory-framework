"""Tool definitions and execution helpers for state-related agents."""

from __future__ import annotations

import json

from dynamic_state import DynamicStateManager

state_manager = DynamicStateManager()


def _normalize_fields_payload(fields):
    if isinstance(fields, dict):
        return fields
    if isinstance(fields, str):
        try:
            parsed = json.loads(fields)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_characters",
            "description": "列出当前所有角色名称。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_character_latest",
            "description": "获取某个角色的最新状态，不返回历史记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "角色名称"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_character",
            "description": "获取某个角色的完整状态历史。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "角色名称"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_character",
            "description": "创建新角色，并写入初始字段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "角色名称"},
                    "chapter": {
                        "type": "integer",
                        "description": "当前章节号",
                        "default": 1,
                    },
                    "reason": {
                        "type": "string",
                        "description": "创建原因",
                        "default": "初始创建",
                    },
                    "is_foreshadowing": {
                        "type": "boolean",
                        "description": "是否为伏笔标记",
                        "default": False,
                    },
                    "fields": {
                        "type": "object",
                        "description": "角色字段，例如 {\"location\": \"东城\"}",
                    },
                },
                "required": ["name", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_character",
            "description": "更新角色字段，按追加历史的方式写入。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "角色名称"},
                    "chapter": {"type": "integer", "description": "当前章节号"},
                    "reason": {"type": "string", "description": "修改原因"},
                    "is_foreshadowing": {
                        "type": "boolean",
                        "description": "是否为伏笔标记",
                        "default": False,
                    },
                    "fields": {
                        "type": "object",
                        "description": "需要更新的字段",
                    },
                },
                "required": ["name", "chapter", "reason", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_character",
            "description": "删除角色。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "角色名称"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_character_at_chapter",
            "description": "获取角色在指定章节时的状态，用于回顾历史伏笔。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "角色名称"},
                    "chapter": {"type": "integer", "description": "章节号"}
                },
                "required": ["name", "chapter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_field_history",
            "description": "查询某个字段在章节范围内的变化历史，用于追踪状态演变。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "角色名称"},
                    "field": {"type": "string", "description": "字段名"},
                    "start_chapter": {"type": "integer", "description": "起始章节（可选）"},
                    "end_chapter": {"type": "integer", "description": "结束章节（可选）"}
                },
                "required": ["name", "field"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_chapter",
            "description": "读取指定章节的完整文本内容，用于了解历史章节中发生的具体事件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter": {"type": "integer", "description": "章节号"}
                },
                "required": ["chapter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_unresolved_foreshadowing",
            "description": "列出所有未回收的伏笔，帮助在生成新章节时主动回收伏笔。",
            "parameters": {
                "type": "object",
                "properties": {
                    "current_chapter": {"type": "integer", "description": "当前章节号"}
                },
                "required": ["current_chapter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_characters_at_chapter",
            "description": "获取所有角色在指定章节的状态快照，用于了解某个时间点的整体局势。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter": {"type": "integer", "description": "章节号"}
                },
                "required": ["chapter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chapter_state_changes",
            "description": "获取指定章节中所有角色的状态变化，快速了解该章节发生的关键事件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter": {"type": "integer", "description": "章节号"}
                },
                "required": ["chapter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_chapter",
            "description": "在指定章节中搜索关键词，返回匹配的行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter": {"type": "integer", "description": "章节号"},
                    "keyword": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["chapter", "keyword"],
            },
        },
    },
]


def execute_tool(tool_name: str, arguments: dict) -> dict:
    """Execute a tool call against the append-only state store."""
    if tool_name == "list_characters":
        return {"characters": sorted(state_manager.list_characters())}

    if tool_name == "get_character_latest":
        return state_manager.get_character_latest(arguments["name"])

    if tool_name == "get_character":
        return state_manager.get_character(arguments["name"])

    if tool_name == "create_character":
        chapter = arguments.get("chapter", 1)
        reason = arguments.get("reason", "初始创建")
        is_foreshadowing = arguments.get("is_foreshadowing", False)
        fields = _normalize_fields_payload(arguments.get("fields"))
        return state_manager.create_character(
            arguments["name"],
            chapter,
            reason,
            is_foreshadowing,
            **fields,
        )

    if tool_name == "update_character":
        is_foreshadowing = arguments.get("is_foreshadowing", False)
        fields = _normalize_fields_payload(arguments.get("fields"))
        return state_manager.update_character(
            arguments["name"],
            arguments["chapter"],
            arguments["reason"],
            is_foreshadowing,
            **fields,
        )

    if tool_name == "delete_character":
        return state_manager.delete_character(arguments["name"])

    if tool_name == "get_character_at_chapter":
        return state_manager.get_character_at_chapter(
            arguments["name"],
            arguments["chapter"]
        )

    if tool_name == "query_field_history":
        return state_manager.query_field_history(
            arguments["name"],
            arguments["field"],
            arguments.get("start_chapter"),
            arguments.get("end_chapter")
        )

    if tool_name == "read_chapter":
        return state_manager.read_chapter(arguments["chapter"])

    if tool_name == "list_unresolved_foreshadowing":
        return state_manager.list_unresolved_foreshadowing(arguments["current_chapter"])

    if tool_name == "get_all_characters_at_chapter":
        return state_manager.get_all_characters_at_chapter(arguments["chapter"])

    if tool_name == "get_chapter_state_changes":
        return state_manager.get_chapter_state_changes(arguments["chapter"])

    if tool_name == "search_in_chapter":
        return state_manager.search_in_chapter(
            arguments["chapter"],
            arguments["keyword"]
        )

    return {"error": f"未知工具: {tool_name}"}
