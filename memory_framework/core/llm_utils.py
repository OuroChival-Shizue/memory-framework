"""Utilities for normalizing LLM responses across providers."""

from __future__ import annotations

import json
from typing import Any


def extract_message_content(response: Any) -> str:
    """Return the text content from a chat message-like object."""
    if response is None:
        return ""

    if isinstance(response, dict):
        content = response.get("content", "")
    else:
        content = getattr(response, "content", "")

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            else:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)

    return str(content or "")


def _raw_tool_calls(response: Any) -> list[Any]:
    if response is None:
        return []
    if isinstance(response, dict):
        return response.get("tool_calls") or []
    return getattr(response, "tool_calls", None) or []


def normalize_tool_calls(response: Any) -> list[dict[str, Any]]:
    """Normalize tool calls to a plain dict structure."""
    normalized: list[dict[str, Any]] = []

    for index, tool_call in enumerate(_raw_tool_calls(response), start=1):
        if isinstance(tool_call, dict):
            tool_id = tool_call.get("id", f"tool_call_{index}")
            fn = tool_call.get("function") or {}
            name = fn.get("name", "")
            arguments_json = fn.get("arguments", "{}")
        else:
            tool_id = getattr(tool_call, "id", f"tool_call_{index}")
            function = getattr(tool_call, "function", None)
            name = getattr(function, "name", "")
            arguments_json = getattr(function, "arguments", "{}")

        try:
            arguments = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError:
            arguments = {}

        normalized.append(
            {
                "id": tool_id,
                "name": name,
                "arguments_json": arguments_json or "{}",
                "arguments": arguments,
            }
        )

    return normalized


def assistant_message_from_response(response: Any) -> dict[str, Any]:
    """Convert a provider response to an assistant message dict."""
    message: dict[str, Any] = {
        "role": "assistant",
        "content": extract_message_content(response),
    }

    tool_calls = normalize_tool_calls(response)
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": item["id"],
                "type": "function",
                "function": {
                    "name": item["name"],
                    "arguments": item["arguments_json"],
                },
            }
            for item in tool_calls
        ]

    return message
