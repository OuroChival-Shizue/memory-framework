"""动态字段的状态管理器 - Agent版本"""
import json
from pathlib import Path
from datetime import datetime


class DynamicStateManager:
    def __init__(self, data_dir: str = "data", project_id: str = None):
        """
        初始化状态管理器

        Args:
            data_dir: 数据目录路径（绝对路径或相对路径）
            project_id: 项目ID（可选），如果提供则使用项目管理器获取数据目录
        """
        if project_id:
            # 使用项目管理器获取项目数据目录
            from project_manager import ProjectManager
            pm = ProjectManager()
            self.data_dir = pm.get_project_data_dir(project_id)
        else:
            # 使用传统的数据目录
            base_dir = Path(__file__).resolve().parent
            raw_data_dir = Path(data_dir)
            self.data_dir = raw_data_dir if raw_data_dir.is_absolute() else base_dir / raw_data_dir

        self.characters_dir = self.data_dir / "characters"
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.chapters_dir = self.data_dir / "chapters"
        self.chapters_dir.mkdir(parents=True, exist_ok=True)

    def create_character(self, name: str, chapter: int = 1, reason: str = "初始创建", is_foreshadowing: bool = False, **fields) -> dict:
        """创建角色，支持任意字段（历史链表模式）"""
        if (self.characters_dir / f"{name}.json").exists():
            return {"error": f"角色 {name} 已存在"}

        timestamp = datetime.now().isoformat()

        # 将每个字段值包装成历史节点列表
        history_fields = {}
        for key, value in fields.items():
            history_fields[key] = [{
                "value": value,
                "chapter": chapter,
                "reason": reason,
                "timestamp": timestamp,
                "is_foreshadowing": is_foreshadowing
            }]

        data = {
            "name": name,
            "fields": history_fields,
            "created_at": timestamp,
            "updated_at": timestamp
        }

        with open(self.characters_dir / f"{name}.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {"success": True, "character": name}

    def get_character(self, name: str) -> dict:
        """获取角色状态"""
        file_path = self.characters_dir / f"{name}.json"
        if not file_path.exists():
            return {"error": f"角色 {name} 不存在"}

        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def update_character(self, name: str, chapter: int, reason: str, is_foreshadowing: bool = False, **fields) -> dict:
        """更新角色字段（追加历史节点）"""
        file_path = self.characters_dir / f"{name}.json"
        if not file_path.exists():
            return {"error": f"角色 {name} 不存在"}

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        timestamp = datetime.now().isoformat()

        # 为每个字段追加新的历史节点
        for key, value in fields.items():
            if key not in data["fields"]:
                data["fields"][key] = []
            data["fields"][key].append({
                "value": value,
                "chapter": chapter,
                "reason": reason,
                "timestamp": timestamp,
                "is_foreshadowing": is_foreshadowing
            })

        data["updated_at"] = timestamp

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {"success": True, "character": name, "updated_fields": list(fields.keys())}

    def delete_character(self, name: str) -> dict:
        """删除角色"""
        file_path = self.characters_dir / f"{name}.json"
        if not file_path.exists():
            return {"error": f"角色 {name} 不存在"}

        file_path.unlink()
        return {"success": True, "character": name}

    def list_characters(self) -> list:
        """列出所有角色"""
        return [f.stem for f in self.characters_dir.glob("*.json")]

    def get_character_latest(self, name: str) -> dict:
        """获取角色最新状态（只返回最新值）"""
        data = self.get_character(name)
        if "error" in data:
            return data

        # 提取每个字段的最新值
        latest_fields = {}
        for key, history in data["fields"].items():
            if history:
                latest_fields[key] = history[-1]["value"]

        return {
            "name": data["name"],
            "fields": latest_fields,
            "created_at": data["created_at"],
            "updated_at": data["updated_at"]
        }

    def get_character_at_chapter(self, name: str, chapter: int) -> dict:
        """获取角色在指定章节时的状态"""
        data = self.get_character(name)
        if "error" in data:
            return data

        fields_at_chapter = {}
        for key, history in data["fields"].items():
            # 找到该章节或之前最近的状态
            value_at_chapter = None
            for entry in history:
                if entry["chapter"] <= chapter:
                    value_at_chapter = entry
                else:
                    break
            if value_at_chapter:
                fields_at_chapter[key] = value_at_chapter

        return {
            "name": data["name"],
            "chapter": chapter,
            "fields": fields_at_chapter
        }

    def query_field_history(self, name: str, field: str, start_chapter: int = None, end_chapter: int = None) -> dict:
        """查询某个字段在章节范围内的变化历史"""
        data = self.get_character(name)
        if "error" in data:
            return data

        if field not in data["fields"]:
            return {"error": f"字段 {field} 不存在"}

        history = data["fields"][field]
        filtered = []
        for entry in history:
            ch = entry["chapter"]
            if (start_chapter is None or ch >= start_chapter) and (end_chapter is None or ch <= end_chapter):
                filtered.append(entry)

        return {
            "name": name,
            "field": field,
            "history": filtered
        }

    def read_chapter(self, chapter: int) -> dict:
        """读取指定章节的完整文本内容"""
        file_path = self.chapters_dir / f"chapter_{chapter}.txt"
        if not file_path.exists():
            return {"error": f"章节 {chapter} 不存在"}

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            "chapter": chapter,
            "content": content
        }

    def list_unresolved_foreshadowing(self, current_chapter: int) -> dict:
        """列出所有未回收的伏笔"""
        unresolved = []
        for char_name in self.list_characters():
            data = self.get_character(char_name)
            if "error" in data:
                continue

            for field_name, history in data["fields"].items():
                for entry in history:
                    if entry.get("is_foreshadowing", False) and entry["chapter"] < current_chapter:
                        unresolved.append({
                            "character": char_name,
                            "field": field_name,
                            "chapter": entry["chapter"],
                            "reason": entry["reason"],
                            "value": entry["value"]
                        })

        return {"unresolved_foreshadowing": unresolved}

    def get_all_characters_at_chapter(self, chapter: int) -> dict:
        """获取所有角色在指定章节的状态快照"""
        snapshot = {}
        for char_name in self.list_characters():
            char_data = self.get_character_at_chapter(char_name, chapter)
            if "error" not in char_data:
                snapshot[char_name] = char_data["fields"]

        return {"chapter": chapter, "characters": snapshot}

    def get_chapter_state_changes(self, chapter: int) -> dict:
        """获取指定章节中所有角色的状态变化"""
        changes = []
        for char_name in self.list_characters():
            data = self.get_character(char_name)
            if "error" in data:
                continue

            for field_name, history in data["fields"].items():
                for entry in history:
                    if entry["chapter"] == chapter:
                        changes.append({
                            "character": char_name,
                            "field": field_name,
                            "value": entry["value"],
                            "reason": entry["reason"],
                            "is_foreshadowing": entry.get("is_foreshadowing", False)
                        })

        return {"chapter": chapter, "changes": changes}

    def search_in_chapter(self, chapter: int, keyword: str) -> dict:
        """在指定章节中搜索关键词"""
        file_path = self.chapters_dir / f"chapter_{chapter}.txt"
        if not file_path.exists():
            return {"error": f"章节 {chapter} 不存在"}

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        matches = []
        for i, line in enumerate(lines, 1):
            if keyword in line:
                matches.append({"line": i, "text": line.strip()})

        return {
            "chapter": chapter,
            "keyword": keyword,
            "matches": matches
        }
