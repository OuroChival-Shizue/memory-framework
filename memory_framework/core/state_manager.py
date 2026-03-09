"""角色状态管理器"""
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


class StateManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.characters_dir = self.data_dir / "characters"
        self.characters_dir.mkdir(parents=True, exist_ok=True)

    def create_character(self, name: str, initial_state: Dict[str, Any], chapter: int = 1) -> None:
        """创建新角色"""
        character_data = {
            "name": name,
            "created_at": chapter,
            "current_state": initial_state,
            "state_history": [
                {
                    "chapter": chapter,
                    "state": initial_state,
                    "timestamp": datetime.now().isoformat()
                }
            ]
        }

        file_path = self.characters_dir / f"{name}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(character_data, f, ensure_ascii=False, indent=2)

    def get_character_state(self, name: str, chapter: int = None) -> Dict[str, Any]:
        """获取角色状态（可指定章节）"""
        file_path = self.characters_dir / f"{name}.json"
        if not file_path.exists():
            raise ValueError(f"角色 {name} 不存在")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if chapter is None:
            return data["current_state"]

        # 查找指定章节的状态
        for record in reversed(data["state_history"]):
            if record["chapter"] <= chapter:
                return record["state"]

        return data["state_history"][0]["state"]

    def update_character_state(self, name: str, chapter: int, new_state: Dict[str, Any],
                               changes: List[str] = None) -> None:
        """更新角色状态"""
        file_path = self.characters_dir / f"{name}.json"
        if not file_path.exists():
            raise ValueError(f"角色 {name} 不存在")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 更新当前状态
        data["current_state"] = new_state

        # 添加到历史记录
        data["state_history"].append({
            "chapter": chapter,
            "state": new_state,
            "changes": changes or [],
            "timestamp": datetime.now().isoformat()
        })

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list_all_characters(self) -> List[str]:
        """列出所有角色"""
        return [f.stem for f in self.characters_dir.glob("*.json")]

    def get_all_current_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有角色的当前状态"""
        states = {}
        for name in self.list_all_characters():
            states[name] = self.get_character_state(name)
        return states
