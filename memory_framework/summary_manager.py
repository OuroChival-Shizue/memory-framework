"""Summary generation and retrieval for layered chapter context."""

from __future__ import annotations

import re
from pathlib import Path

from core.llm_utils import extract_message_content


class SummaryManager:
    def __init__(
        self,
        llm_function,
        data_dir: str = "data",
        summary_length: tuple[int, int] = (200, 500),
        compressed_summary_length: tuple[int, int] = (500, 1000),
    ):
        self.llm_function = llm_function
        self.data_dir = Path(data_dir)
        self.summaries_dir = self.data_dir / "summaries"
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        self.summary_length = summary_length
        self.compressed_summary_length = compressed_summary_length

    def _summary_path(self, chapter_num: int) -> Path:
        return self.summaries_dir / f"chapter_{chapter_num}.txt"

    def _fallback_summary(self, chapter_num: int, content: str, limit: int = 320) -> str:
        normalized = re.sub(r"\s+", " ", content).strip()
        clipped = normalized[:limit]
        suffix = "..." if len(normalized) > limit else ""
        return f"第{chapter_num}章摘要：{clipped}{suffix}" if clipped else ""

    def list_summary_chapters(self) -> list[int]:
        chapters = []
        for path in self.summaries_dir.glob("chapter_*.txt"):
            try:
                chapters.append(int(path.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue
        return sorted(chapters)

    def generate_summary(self, chapter_num: int, content: str) -> str:
        """Generate and persist a chapter summary."""
        min_len, max_len = self.summary_length
        prompt = f"""请为以下章节生成摘要，要求：
1. 长度控制在 {min_len}-{max_len} 字
2. 包含核心事件、关键角色动作、剧情推进、伏笔或悬念
3. 用自然语言写成一段或两段，便于后续章节检索

章节内容：
{content}
"""

        summary = ""
        if self.llm_function:
            messages = [
                {
                    "role": "system",
                    "content": "你是小说摘要助手，负责提炼章节关键信息。",
                },
                {"role": "user", "content": prompt},
            ]
            response = self.llm_function(messages, tools=None)
            summary = extract_message_content(response).strip()

        if not summary:
            summary = self._fallback_summary(chapter_num, content)

        self._summary_path(chapter_num).write_text(summary, encoding="utf-8")
        return summary

    def get_summary(self, chapter_num: int) -> str:
        """Read a summary file if present."""
        path = self._summary_path(chapter_num)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def get_recent_summaries(self, current_chapter: int, count: int = 5) -> list[dict]:
        """Get the most recent chapter summaries before the current chapter."""
        summaries: list[dict] = []
        for chapter_num in range(current_chapter - 1, 0, -1):
            summary = self.get_summary(chapter_num)
            if summary:
                summaries.append({"chapter": chapter_num, "summary": summary})
            if len(summaries) >= count:
                break
        return summaries

    def get_summary_range(self, start_chapter: int, end_chapter: int) -> list[dict]:
        """Return summaries for a chapter range, skipping missing files."""
        items: list[dict] = []
        for chapter_num in range(start_chapter, end_chapter + 1):
            summary = self.get_summary(chapter_num)
            if summary:
                items.append({"chapter": chapter_num, "summary": summary})
        return items

    def compress_summaries(self, chapter_range: tuple[int, int]) -> str:
        """Compress a chapter range into a higher-level summary."""
        start_chapter, end_chapter = chapter_range
        segments = self.get_summary_range(start_chapter, end_chapter)
        if not segments:
            return ""

        joined = "\n\n".join(
            f"第{item['chapter']}章：{item['summary']}" for item in segments
        )

        if self.llm_function:
            min_len, max_len = self.compressed_summary_length
            messages = [
                {
                    "role": "system",
                    "content": "你是小说摘要助手，负责压缩多章剧情脉络。",
                },
                {
                    "role": "user",
                    "content": f"""请将以下多章摘要压缩成 {min_len}-{max_len} 字的总摘要。
要求保留关键剧情线、角色发展和伏笔。

{joined}
""",
                },
            ]
            response = self.llm_function(messages, tools=None)
            summary = extract_message_content(response).strip()
            if summary:
                return summary

        return joined[:1200]
