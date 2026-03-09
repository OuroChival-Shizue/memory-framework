"""Build layered history context and final clean prompts for V2 generation."""

from __future__ import annotations

from pathlib import Path


class ContextBuilder:
    def __init__(
        self,
        llm_function,
        state_agent,
        summary_manager,
        prompt_cleaner,
        data_dir: str = "data",
        recent_summary_count: int = 5,
        compress_threshold: int = 10,
    ):
        self.llm_function = llm_function
        self.state_agent = state_agent
        self.summary_manager = summary_manager
        self.prompt_cleaner = prompt_cleaner
        self.data_dir = Path(data_dir)
        self.chapters_dir = self.data_dir / "chapters"
        self.recent_summary_count = recent_summary_count
        self.compress_threshold = compress_threshold
        self._cache: dict = {}

    def _chapter_path(self, chapter: int) -> Path:
        return self.chapters_dir / f"chapter_{chapter}.txt"

    def _strip_state_appendix(self, content: str) -> str:
        text = content or ""
        markers = (
            "【角色状态更新】",
            "**【角色状态更新】**",
            "【状态更新】",
            "**【状态更新】**",
        )
        positions = [text.find(marker) for marker in markers if marker in text]
        if positions:
            text = text[: min(positions)]
        return text.rstrip()

    def build_history_context(self, chapter: int) -> str:
        """Build layered context from full text, recent summaries, and compressed history."""
        sections: list[str] = []
        previous_chapter = chapter - 1

        if previous_chapter >= 1:
            previous_path = self._chapter_path(previous_chapter)
            if previous_path.exists():
                previous_content = self._strip_state_appendix(
                    previous_path.read_text(encoding="utf-8").strip()
                )
                if previous_content:
                    sections.append(
                        f"【上一章完整内容】\n第{previous_chapter}章：\n{previous_content}"
                    )

        recent_start = max(1, chapter - self.recent_summary_count - 1)
        recent_end = chapter - 2
        if recent_start <= recent_end:
            recent_items = self.summary_manager.get_summary_range(recent_start, recent_end)
            recent_items = sorted(recent_items, key=lambda item: item["chapter"], reverse=True)
            if recent_items:
                lines = ["【前几章摘要】"]
                for item in recent_items:
                    lines.append(f"第{item['chapter']}章：{item['summary']}")
                sections.append("\n".join(lines))

        older_end = recent_start - 1
        if older_end >= 1:
            older_count = older_end
            if older_count >= self.compress_threshold:
                compressed = self.summary_manager.compress_summaries((1, older_end))
                if compressed:
                    sections.append(f"【更早章节总览】\n第1章-第{older_end}章：{compressed}")
            else:
                older_items = self.summary_manager.get_summary_range(1, older_end)
                if older_items:
                    lines = ["【更早章节摘要】"]
                    for item in older_items:
                        lines.append(f"第{item['chapter']}章：{item['summary']}")
                    sections.append("\n".join(lines))

        if not sections:
            sections.append("【历史上下文】\n这是第一章，或当前还没有可用的历史章节与摘要。")

        history_context = "\n\n".join(sections)
        self._cache["chapter"] = chapter
        self._cache["history_context"] = history_context
        return history_context

    def build_character_context(self, chapter: int, history_context: str) -> str:
        """Build readable character context through active state querying."""
        query_result = self.state_agent.query_states_actively(chapter, history_context)
        character_context = self.prompt_cleaner.clean_character_states(
            query_result.get("conversation", []),
            query_result.get("tool_results", {}),
        )

        self._cache["chapter"] = chapter
        self._cache["history_context"] = history_context
        self._cache["query_result"] = query_result
        self._cache["character_context"] = character_context
        return character_context

    def cache_query_context(
        self,
        chapter: int,
        history_context: str,
        query_result: dict,
        character_context: str,
    ) -> None:
        """Cache externally prepared query results for final prompt assembly."""
        self._cache["chapter"] = chapter
        self._cache["history_context"] = history_context
        self._cache["query_result"] = query_result
        self._cache["character_context"] = character_context

    def build_final_prompt(
        self,
        chapter: int,
        extra_context: str = "",
        outline_text: str = "",
    ) -> str:
        """Build the final clean prompt for content generation."""
        history_context = self._cache.get("history_context")
        if self._cache.get("chapter") != chapter or not history_context:
            history_context = self.build_history_context(chapter)

        character_context = self._cache.get("character_context")
        query_result = self._cache.get("query_result")
        if not character_context or self._cache.get("chapter") != chapter:
            character_context = self.build_character_context(chapter, history_context)
            query_result = self._cache.get("query_result")

        task_description = self.prompt_cleaner.extract_task_description(
            (query_result or {}).get("conversation", []),
            history_context,
        )

        parts = [
            f"你现在要续写一部小说，写第{chapter}章。",
            f"【当前任务】\n{task_description}",
            "【创作约束】\n- 保持人物设定、时间线与地理逻辑一致。\n- 只输出章节正文，不要附加角色状态更新、摘要或解释。",
        ]

        if outline_text.strip():
            parts.append(f"【项目大纲】\n{outline_text.strip()}")

        parts.extend(
            [
                f"【最近上下文摘要】\n{history_context}",
                f"【角色当前状态】\n{character_context}",
            ]
        )

        if extra_context.strip():
            parts.append(f"【用户补充说明】\n{extra_context.strip()}")

        parts.append(
            f"""【输出要求】
请直接输出第{chapter}章正文，不要解释。
文风保持连贯，优先承接上一章的事件、情绪和目标。
"""
        )

        final_prompt = "\n\n".join(parts)
        self._cache["final_prompt"] = final_prompt
        return final_prompt
