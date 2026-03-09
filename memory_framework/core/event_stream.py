"""事件流管理器"""
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


class EventStream:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.events_dir = self.data_dir / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.events_dir / "stream.jsonl"

    def add_event(self, chapter: int, event_type: str, data: Dict[str, Any]) -> None:
        """添加事件到流"""
        event = {
            "chapter": chapter,
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

        with open(self.events_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')

    def get_events(self, chapter_start: int = None, chapter_end: int = None,
                   event_type: str = None, character: str = None) -> List[Dict[str, Any]]:
        """查询事件（支持过滤）"""
        if not self.events_file.exists():
            return []

        events = []
        with open(self.events_file, 'r', encoding='utf-8') as f:
            for line in f:
                event = json.loads(line)

                # 过滤条件
                if chapter_start and event["chapter"] < chapter_start:
                    continue
                if chapter_end and event["chapter"] > chapter_end:
                    continue
                if event_type and event["type"] != event_type:
                    continue
                if character and event["data"].get("character") != character:
                    continue

                events.append(event)

        return events

    def get_character_events(self, character: str, chapter_start: int = None,
                            chapter_end: int = None) -> List[Dict[str, Any]]:
        """获取特定角色的所有事件"""
        return self.get_events(chapter_start, chapter_end, character=character)
