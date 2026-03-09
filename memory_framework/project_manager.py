"""项目管理器 - 支持多小说项目的隔离管理"""
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


class ProjectManager:
    """管理多个小说项目，每个项目有独立的角色、章节、配置"""

    PROJECT_ID_PATTERN = re.compile(r"^project_[a-f0-9]{12}$")
    MAX_TITLE_LENGTH = 200
    MIN_TOTAL_CHAPTERS = 1
    MAX_TOTAL_CHAPTERS = 1000

    def __init__(self, base_dir: str = "projects"):
        self.base_dir = Path(__file__).parent / base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _validate_project_id(self, project_id: str):
        if not isinstance(project_id, str) or not self.PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ValueError(f"非法项目ID: {project_id}")

    def _project_dir(self, project_id: str) -> Path:
        self._validate_project_id(project_id)
        return self.base_dir / project_id

    def _require_project_dir(self, project_id: str) -> Path:
        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            raise FileNotFoundError(f"项目不存在: {project_id}")
        return project_dir

    def _atomic_write(self, path: Path, content: str):
        """原子写入文件，避免写入过程中断导致数据损坏"""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Windows 文件锁定重试
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    os.replace(temp_path, path)
                    break
                except OSError as e:
                    if hasattr(e, 'winerror') and e.winerror == 5 and attempt < max_retries - 1:
                        time.sleep(0.1)
                        continue
                    raise
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def _write_json(self, path: Path, data: Dict):
        self._atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))

    def _read_json(self, path: Path) -> Dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def create_project(
        self,
        title: str,
        description: str = "",
        genre: str = "",
        style: str = "",
        total_chapters: int = 10,
    ) -> str:
        """创建新项目"""
        title = str(title or "").strip()
        if not title or len(title) > self.MAX_TITLE_LENGTH:
            raise ValueError(f"标题长度必须在 1-{self.MAX_TITLE_LENGTH} 之间")

        try:
            chapter_count = int(total_chapters)
        except (TypeError, ValueError):
            raise ValueError("total_chapters 必须是整数")

        if not (self.MIN_TOTAL_CHAPTERS <= chapter_count <= self.MAX_TOTAL_CHAPTERS):
            raise ValueError(f"章节数必须在 {self.MIN_TOTAL_CHAPTERS}-{self.MAX_TOTAL_CHAPTERS} 之间")

        project_id = f"project_{uuid.uuid4().hex[:12]}"
        project_dir = self._project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=False)

        # 创建子目录
        (project_dir / "data" / "characters").mkdir(parents=True, exist_ok=True)
        (project_dir / "data" / "chapters").mkdir(parents=True, exist_ok=True)

        timestamp = self._now_iso()
        meta = {
            "id": project_id,
            "title": title,
            "description": description,
            "genre": genre,
            "style": style,
            "total_chapters": chapter_count,
            "current_chapter": 0,
            "status": "planning",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._write_json(project_dir / "meta.json", meta)

        # 复制配置文件模板
        framework_dir = Path(__file__).parent
        if (framework_dir / "state_schema.yaml").exists():
            shutil.copy2(framework_dir / "state_schema.yaml", project_dir / "state_schema.yaml")

        return project_id

    def list_projects(self) -> List[Dict]:
        """列出所有项目"""
        projects = []
        for meta_path in self.base_dir.glob("*/meta.json"):
            try:
                meta = self._read_json(meta_path)
                project_id = meta["id"]

                # 统计章节和角色数量
                chapters_dir = meta_path.parent / "data" / "chapters"
                characters_dir = meta_path.parent / "data" / "characters"

                meta["chapter_count"] = len(list(chapters_dir.glob("chapter_*.txt"))) if chapters_dir.exists() else 0
                meta["character_count"] = len(list(characters_dir.glob("*.json"))) if characters_dir.exists() else 0

                projects.append(meta)
            except Exception:
                continue

        projects.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return projects

    def get_project(self, project_id: str) -> Optional[Dict]:
        """获取项目详情"""
        try:
            meta_path = self._require_project_dir(project_id) / "meta.json"
            meta = self._read_json(meta_path)

            # 添加统计信息
            project_dir = self._project_dir(project_id)
            chapters_dir = project_dir / "data" / "chapters"
            characters_dir = project_dir / "data" / "characters"

            meta["chapter_count"] = len(list(chapters_dir.glob("chapter_*.txt"))) if chapters_dir.exists() else 0
            meta["character_count"] = len(list(characters_dir.glob("*.json"))) if characters_dir.exists() else 0

            return meta
        except (FileNotFoundError, ValueError):
            return None

    def update_project(self, project_id: str, **fields) -> Dict:
        """更新项目元数据"""
        project_dir = self._require_project_dir(project_id)
        meta_path = project_dir / "meta.json"
        meta = self._read_json(meta_path)

        # 更新字段
        for key, value in fields.items():
            if value is not None:
                meta[key] = value

        meta["updated_at"] = self._now_iso()
        self._write_json(meta_path, meta)
        return meta

    def delete_project(self, project_id: str):
        """删除项目"""
        project_dir = self._require_project_dir(project_id)
        shutil.rmtree(project_dir)

    def get_project_data_dir(self, project_id: str) -> Path:
        """获取项目的 data 目录路径，用于 DynamicStateManager"""
        return self._require_project_dir(project_id) / "data"
