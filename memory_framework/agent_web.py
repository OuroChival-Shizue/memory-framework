"""Project-oriented web UI for the memory framework."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for,
)

from dynamic_state import DynamicStateManager
from project_manager import ProjectManager
from schema_manager import SchemaManager

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

app = Flask(__name__)
project_mgr = ProjectManager()
runtime_lock = threading.Lock()
generation_tasks: dict[str, dict] = {}
generation_tasks_lock = threading.Lock()
TERMINAL_TASK_STATUSES = {"done", "error"}

for path in (
    BASE_DIR / "data" / "characters",
    BASE_DIR / "data" / "chapters",
    BASE_DIR / "data" / "summaries",
):
    path.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data" / "config.json").touch(exist_ok=True)

DEFAULT_V2_CONFIG = {
    "recent_summary_count": 5,
    "compress_threshold": 10,
    "summary_length": {"min": 200, "max": 500},
    "compressed_summary_length": {"min": 500, "max": 1000},
    "use_llm_cleaning": False,
}

STATUS_STEPS = [
    ("planning", "规划"),
    ("outline_ready", "大纲就绪"),
    ("writing", "写作中"),
    ("completed", "已完成"),
]


@app.context_processor
def utility_processor():
    def asset_url(filename: str) -> str:
        path = BASE_DIR / "static" / filename
        version = int(path.stat().st_mtime) if path.exists() else 0
        return url_for("static", filename=filename, v=version)

    return {"asset_url": asset_url}


def jsonify_result(result: dict):
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


def get_project_paths(project_id: str) -> dict[str, Path]:
    project_dir = project_mgr._require_project_dir(project_id)
    data_dir = project_dir / "data"
    return {
        "project_dir": project_dir,
        "data_dir": data_dir,
        "characters_dir": data_dir / "characters",
        "chapters_dir": data_dir / "chapters",
        "summaries_dir": data_dir / "summaries",
        "config_path": data_dir / "config.json",
        "schema_path": project_dir / "state_schema.yaml",
        "outline_path": project_dir / "outline.md",
        "prompt_logs_dir": project_dir / "prompt_logs",
    }


def ensure_project_structure(project_id: str) -> dict[str, Path]:
    paths = get_project_paths(project_id)
    for key in ("characters_dir", "chapters_dir", "summaries_dir", "prompt_logs_dir"):
        paths[key].mkdir(parents=True, exist_ok=True)

    if not paths["config_path"].exists():
        root_config_path = BASE_DIR / "data" / "config.json"
        if root_config_path.exists() and root_config_path.read_text(encoding="utf-8").strip():
            paths["config_path"].write_text(
                root_config_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            paths["config_path"].write_text("{}", encoding="utf-8")

    if not paths["schema_path"].exists():
        source = BASE_DIR / "state_schema.yaml"
        if source.exists():
            paths["schema_path"].write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    return paths


def save_prompt_snapshot(
    prompt_logs_dir: Path,
    chapter_num: int,
    final_prompt: str,
    generation_messages: list[dict],
    suffix: str = "",
    kind: str = "generation",
) -> Path:
    prompt_path = prompt_logs_dir / f"chapter_{chapter_num:03d}{suffix}_prompt.json"
    payload = {
        "chapter": chapter_num,
        "kind": kind,
        "final_prompt": final_prompt,
        "messages": generation_messages,
    }
    with open(prompt_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return prompt_path


def strip_state_appendix(content: str) -> str:
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


def prune_generation_tasks(max_age_seconds: int = 3600) -> None:
    cutoff = time.time() - max_age_seconds
    with generation_tasks_lock:
        expired = [
            task_id
            for task_id, task in generation_tasks.items()
            if task["status"] in TERMINAL_TASK_STATUSES and task["updated_at"] < cutoff
        ]
        for task_id in expired:
            generation_tasks.pop(task_id, None)


def serialize_generation_task(task: dict) -> dict:
    return {
        "id": task["id"],
        "project_id": task["project_id"],
        "chapter": task["chapter"],
        "status": task["status"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "redirect": task.get("redirect"),
        "error": task.get("error"),
    }


def get_generation_task(task_id: str, project_id: str | None = None) -> dict | None:
    prune_generation_tasks()
    with generation_tasks_lock:
        task = generation_tasks.get(task_id)
    if not task:
        return None
    if project_id and task["project_id"] != project_id:
        return None
    return task


def find_active_generation_task(project_id: str) -> dict | None:
    prune_generation_tasks()
    with generation_tasks_lock:
        candidates = [
            task
            for task in generation_tasks.values()
            if task["project_id"] == project_id and task["status"] not in TERMINAL_TASK_STATUSES
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item["updated_at"])


def create_generation_task(project_id: str, chapter_num: int, summary: str) -> dict:
    task = {
        "id": f"task_{uuid.uuid4().hex[:12]}",
        "project_id": project_id,
        "chapter": chapter_num,
        "summary": summary,
        "status": "queued",
        "created_at": time.time(),
        "updated_at": time.time(),
        "events": [],
        "redirect": None,
        "error": None,
        "condition": threading.Condition(),
    }
    with generation_tasks_lock:
        generation_tasks[task["id"]] = task
    return task


def append_generation_event(task: dict, event: dict) -> None:
    with task["condition"]:
        task["events"].append(event)
        task["updated_at"] = time.time()
        if event.get("type") == "done":
            task["status"] = "done"
            task["redirect"] = event.get("redirect")
        elif event.get("type") == "error":
            task["status"] = "error"
            task["error"] = event.get("message")
        elif task["status"] not in TERMINAL_TASK_STATUSES:
            task["status"] = "running"
        task["condition"].notify_all()


def get_state_manager(project_id: str) -> DynamicStateManager:
    ensure_project_structure(project_id)
    return DynamicStateManager(project_id=project_id)


def get_schema_manager(project_id: str) -> SchemaManager:
    paths = ensure_project_structure(project_id)
    return SchemaManager(str(paths["schema_path"]))


def list_chapter_numbers(project_id: str) -> list[int]:
    paths = ensure_project_structure(project_id)
    chapters: list[int] = []
    for file_path in paths["chapters_dir"].glob("chapter_*.txt"):
        try:
            chapters.append(int(file_path.stem.split("_")[1]))
        except (IndexError, ValueError):
            continue
    return sorted(chapters)


def load_outline(project_id: str) -> str:
    paths = ensure_project_structure(project_id)
    if not paths["outline_path"].exists():
        return ""
    return paths["outline_path"].read_text(encoding="utf-8")


def save_outline(project_id: str, content: str) -> None:
    paths = ensure_project_structure(project_id)
    paths["outline_path"].write_text(content or "", encoding="utf-8")
    refresh_project_progress(project_id)


def load_config(config_path: Path) -> dict:
    try:
        with open(config_path, "r", encoding="utf-8") as file:
            config = json.load(file)
    except Exception:
        config = {}

    v2_config = dict(DEFAULT_V2_CONFIG)
    v2_config.update(config.get("v2_config") or {})
    v2_config["summary_length"] = {
        **DEFAULT_V2_CONFIG["summary_length"],
        **(v2_config.get("summary_length") or {}),
    }
    v2_config["compressed_summary_length"] = {
        **DEFAULT_V2_CONFIG["compressed_summary_length"],
        **(v2_config.get("compressed_summary_length") or {}),
    }
    config["v2_config"] = v2_config
    return config


def save_config(config_path: Path, config: dict) -> None:
    current = load_config(config_path)
    merged = dict(current)
    merged.update(config)
    merged["v2_config"] = dict(current.get("v2_config") or DEFAULT_V2_CONFIG)
    if "v2_config" in config:
        merged["v2_config"].update(config["v2_config"] or {})

    with open(config_path, "w", encoding="utf-8") as file:
        json.dump(merged, file, ensure_ascii=False, indent=2)


def build_openai_client(config: dict):
    from openai import OpenAI

    client = OpenAI(api_key=config["api_key"], base_url=config.get("api_url"))

    def llm_call(messages, tools=None):
        kwargs = {
            "model": config.get("model", "gpt-4"),
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        return client.chat.completions.create(**kwargs).choices[0].message

    return client, llm_call


def build_status_steps(current_status: str) -> list[dict]:
    order = [key for key, _ in STATUS_STEPS]
    try:
        active_index = order.index(current_status)
    except ValueError:
        active_index = 0

    steps = []
    for index, (key, label) in enumerate(STATUS_STEPS):
        steps.append(
            {
                "key": key,
                "label": label,
                "active": index <= active_index,
                "current": key == current_status,
            }
        )
    return steps


def refresh_project_progress(project_id: str) -> dict:
    project = project_mgr.get_project(project_id)
    if not project:
        abort(404)

    chapters = list_chapter_numbers(project_id)
    outline_exists = bool(load_outline(project_id).strip())
    total_chapters = int(project.get("total_chapters") or 0)

    if chapters and total_chapters and len(chapters) >= total_chapters:
        status = "completed"
    elif chapters:
        status = "writing"
    elif outline_exists:
        status = "outline_ready"
    else:
        status = "planning"

    current_chapter = max(chapters) if chapters else 0
    return project_mgr.update_project(
        project_id,
        current_chapter=current_chapter,
        status=status,
    )


def enrich_project(project: dict) -> dict:
    project = dict(project)
    project["completion_percent"] = (
        int((project["chapter_count"] / project["total_chapters"]) * 100)
        if project.get("total_chapters")
        else 0
    )
    project["status_steps"] = build_status_steps(project.get("status", "planning"))
    project["has_outline"] = bool(load_outline(project["id"]).strip())
    project["next_chapter"] = project.get("chapter_count", 0) + 1
    return project


def require_project(project_id: str) -> dict:
    refresh_project_progress(project_id)
    project = project_mgr.get_project(project_id)
    if not project:
        abort(404)
    return enrich_project(project)


def build_character_cards(project_id: str) -> list[dict]:
    manager = get_state_manager(project_id)
    cards = []
    for name in sorted(manager.list_characters()):
        latest = manager.get_character_latest(name)
        if "error" in latest:
            continue
        preview_fields = list(latest.get("fields", {}).items())[:4]
        cards.append(
            {
                "name": name,
                "preview_fields": preview_fields,
                "field_count": len(latest.get("fields", {})),
                "updated_at": latest.get("updated_at", ""),
            }
        )
    return cards


def build_chapter_cards(project_id: str) -> list[dict]:
    manager = get_state_manager(project_id)
    paths = ensure_project_structure(project_id)
    cards = []
    for chapter_num in reversed(list_chapter_numbers(project_id)):
        content = strip_state_appendix(
            (paths["chapters_dir"] / f"chapter_{chapter_num}.txt").read_text(encoding="utf-8")
        )
        summary_path = paths["summaries_dir"] / f"chapter_{chapter_num}.txt"
        summary = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
        change_count = len(manager.get_chapter_state_changes(chapter_num).get("changes", []))
        cards.append(
            {
                "num": chapter_num,
                "summary": summary,
                "preview": content[:220].strip(),
                "change_count": change_count,
                "content_length": len(content),
            }
        )
    return cards


def build_foreshadowing_groups(project_id: str) -> list[dict]:
    chapters = list_chapter_numbers(project_id)
    current_chapter = (max(chapters) + 1) if chapters else 1
    unresolved = get_state_manager(project_id).list_unresolved_foreshadowing(current_chapter)
    grouped = defaultdict(list)
    for item in unresolved.get("unresolved_foreshadowing", []):
        grouped[item["character"]].append(item)

    groups = []
    for character, items in sorted(grouped.items()):
        groups.append(
            {
                "character": character,
                "items": sorted(items, key=lambda item: item["chapter"], reverse=True),
            }
        )
    return groups


@contextmanager
def project_runtime(project_id: str):
    ensure_project_structure(project_id)

    import agent_tools
    import dynamic_state as dynamic_state_module

    original_state_manager = agent_tools.state_manager
    original_dynamic_state_manager = dynamic_state_module.DynamicStateManager

    def scoped_dynamic_state_manager(*args, **kwargs):
        if not args and "data_dir" not in kwargs and "project_id" not in kwargs:
            return original_dynamic_state_manager(project_id=project_id)
        return original_dynamic_state_manager(*args, **kwargs)

    runtime_lock.acquire()
    try:
        agent_tools.state_manager = original_dynamic_state_manager(project_id=project_id)
        dynamic_state_module.DynamicStateManager = scoped_dynamic_state_manager
        yield get_project_paths(project_id)
    finally:
        agent_tools.state_manager = original_state_manager
        dynamic_state_module.DynamicStateManager = original_dynamic_state_manager
        runtime_lock.release()


def sse_response(generator):
    return Response(
        stream_with_context(generator()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def stream_state_update_events(
    content,
    chapter_num,
    llm_call,
    schema_path: Path,
    prompt_logs_dir: Path | None = None,
    project_dir: Path | None = None,
):
    event_queue = queue.Queue()
    sentinel = object()

    def push_event(event):
        event_queue.put(event)

    def worker():
        try:
            from dual_agent import StateAgent

            state_agent = StateAgent(
                llm_function=llm_call,
                schema_path=str(schema_path),
                progress_callback=push_event,
            )
            update_messages = state_agent.build_update_messages(content, chapter_num)
            if prompt_logs_dir and project_dir:
                prompt_path = save_prompt_snapshot(
                    prompt_logs_dir,
                    chapter_num,
                    update_messages[1]["content"],
                    update_messages,
                    suffix="_state_update",
                    kind="state_update",
                )
                push_event(
                    {
                        "type": "state_prompt_capture",
                        "chapter": chapter_num,
                        "final_prompt": update_messages[1]["content"],
                        "messages": update_messages,
                        "path": str(prompt_path.relative_to(project_dir)),
                    }
                )
            state_agent.update_states(content, chapter_num)
            push_event({"type": "done"})
        except Exception as exc:
            push_event({"type": "error", "message": str(exc)})
        finally:
            event_queue.put(sentinel)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        event = event_queue.get()
        if event is sentinel:
            break
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def stream_active_query_events(chapter_num, history_context, llm_call, schema_path: Path):
    event_queue = queue.Queue()
    sentinel = object()
    result_holder = {}

    def push_event(event):
        event_queue.put(event)

    def worker():
        try:
            from dual_agent import StateAgent
            from prompt_cleaner import PromptCleaner

            state_agent = StateAgent(
                llm_function=llm_call,
                schema_path=str(schema_path),
                progress_callback=push_event,
            )
            query_result = state_agent.query_states_actively(chapter_num, history_context)
            prompt_cleaner = PromptCleaner()
            character_context = prompt_cleaner.clean_character_states(
                query_result.get("conversation", []),
                query_result.get("tool_results", {}),
            )
            queried_characters = sorted(
                name
                for name in query_result.get("tool_results", {})
                if name != "_character_list"
            )
            result_holder["query_result"] = query_result
            result_holder["character_context"] = character_context
            push_event(
                {
                    "type": "query_summary",
                    "stage": "query",
                    "message": f"主动查询结束，锁定 {len(queried_characters)} 个相关角色。",
                    "characters": queried_characters,
                }
            )
        except Exception as exc:
            result_holder["error"] = str(exc)
        finally:
            event_queue.put(sentinel)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        event = event_queue.get()
        if event is sentinel:
            break
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    if "error" in result_holder:
        raise RuntimeError(result_holder["error"])

    return result_holder


def stream_parallel_post_process_events(
    content,
    chapter_num,
    llm_call,
    config,
    data_dir: Path,
    schema_path: Path,
    prompt_logs_dir: Path,
    project_dir: Path,
):
    event_queue = queue.Queue()
    completion_markers = {"summary": False, "state_update": False}
    errors = []

    def push_event(event):
        event_queue.put(event)

    def build_summary_manager():
        from summary_manager import SummaryManager

        v2_config = config.get("v2_config") or {}
        summary_length = v2_config.get("summary_length") or DEFAULT_V2_CONFIG["summary_length"]
        compressed_length = v2_config.get("compressed_summary_length") or DEFAULT_V2_CONFIG["compressed_summary_length"]
        return SummaryManager(
            llm_function=llm_call,
            data_dir=str(data_dir),
            summary_length=(summary_length["min"], summary_length["max"]),
            compressed_summary_length=(compressed_length["min"], compressed_length["max"]),
        )

    def summary_worker():
        try:
            push_event(
                {
                    "type": "post_process",
                    "stage": "summary",
                    "status": "running",
                    "message": f"第 {chapter_num} 章摘要生成中。",
                }
            )
            summary = build_summary_manager().generate_summary(chapter_num, content)
            push_event(
                {
                    "type": "post_process",
                    "stage": "summary",
                    "status": "done",
                    "message": "章节摘要已生成。",
                    "summary_preview": summary[:120],
                }
            )
        except Exception as exc:
            errors.append(f"摘要生成失败：{exc}")
            push_event(
                {
                    "type": "post_process",
                    "stage": "summary",
                    "status": "error",
                    "message": f"摘要生成失败：{exc}",
                }
            )
        finally:
            event_queue.put({"type": "_worker_done", "stage": "summary"})

    def state_worker():
        try:
            from dual_agent import StateAgent

            push_event(
                {
                    "type": "post_process",
                    "stage": "state_update",
                    "status": "running",
                    "message": f"第 {chapter_num} 章状态更新中。",
                }
            )

            def forward_state_event(event):
                payload = dict(event)
                payload["stage"] = "state_update"
                push_event(payload)

            state_agent = StateAgent(
                llm_function=llm_call,
                schema_path=str(schema_path),
                progress_callback=forward_state_event,
            )
            update_messages = state_agent.build_update_messages(content, chapter_num)
            prompt_path = save_prompt_snapshot(
                prompt_logs_dir,
                chapter_num,
                update_messages[1]["content"],
                update_messages,
                suffix="_state_update",
                kind="state_update",
            )
            push_event(
                {
                    "type": "state_prompt_capture",
                    "stage": "state_update",
                    "chapter": chapter_num,
                    "final_prompt": update_messages[1]["content"],
                    "messages": update_messages,
                    "path": str(prompt_path.relative_to(project_dir)),
                }
            )
            state_agent.update_states(content, chapter_num)
            push_event(
                {
                    "type": "post_process",
                    "stage": "state_update",
                    "status": "done",
                    "message": "角色状态更新完成。",
                }
            )
        except Exception as exc:
            errors.append(f"状态更新失败：{exc}")
            push_event(
                {
                    "type": "post_process",
                    "stage": "state_update",
                    "status": "error",
                    "message": f"状态更新失败：{exc}",
                }
            )
        finally:
            event_queue.put({"type": "_worker_done", "stage": "state_update"})

    threading.Thread(target=summary_worker, daemon=True).start()
    threading.Thread(target=state_worker, daemon=True).start()

    while True:
        event = event_queue.get()
        if event.get("type") == "_worker_done":
            completion_markers[event["stage"]] = True
            if all(completion_markers.values()):
                if errors:
                    raise RuntimeError("；".join(errors))
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "post_process",
                            "stage": "all",
                            "status": "done",
                            "message": "摘要生成和状态更新都已完成。",
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                break
            continue

        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def run_generation_task(task: dict) -> None:
    project_id = task["project_id"]
    chapter_num = task["chapter"]
    summary = task.get("summary", "")

    def emit(event_type: str, **payload) -> None:
        append_generation_event(task, {"type": event_type, **payload})

    emit("status", message="后台任务已创建，离开页面不会中断生成。")

    with project_runtime(project_id) as paths:
        try:
            emit("status", message="加载项目配置...")

            config = load_config(paths["config_path"])
            if not config.get("api_key"):
                emit("error", message="请先在项目配置中填写 API 信息")
                return

            from context_builder import ContextBuilder
            from dual_agent import ContentAgent, StateAgent
            from prompt_cleaner import PromptCleaner
            from summary_manager import SummaryManager

            client, llm_call = build_openai_client(config)
            state_agent = StateAgent(llm_function=llm_call, schema_path=str(paths["schema_path"]))
            content_agent = ContentAgent(llm_function=llm_call)
            prompt_cleaner = PromptCleaner()
            summary_length = config["v2_config"]["summary_length"]
            compressed_length = config["v2_config"]["compressed_summary_length"]
            summary_manager = SummaryManager(
                llm_function=llm_call,
                data_dir=str(paths["data_dir"]),
                summary_length=(summary_length["min"], summary_length["max"]),
                compressed_summary_length=(compressed_length["min"], compressed_length["max"]),
            )
            context_builder = ContextBuilder(
                llm_function=llm_call,
                state_agent=state_agent,
                summary_manager=summary_manager,
                prompt_cleaner=prompt_cleaner,
                data_dir=str(paths["data_dir"]),
                recent_summary_count=config["v2_config"]["recent_summary_count"],
                compress_threshold=config["v2_config"]["compress_threshold"],
            )
            outline_text = load_outline(project_id)

            emit("status", message="构建历史上下文...")
            history_context = context_builder.build_history_context(chapter_num)

            emit("status", message="主动查询角色状态...")
            query_stream = stream_active_query_events(
                chapter_num,
                history_context,
                llm_call,
                paths["schema_path"],
            )
            while True:
                try:
                    chunk = next(query_stream)
                except StopIteration as stop:
                    query_bundle = stop.value
                    break
                event = json.loads(chunk.removeprefix("data: ").strip())
                append_generation_event(task, event)

            context_builder.cache_query_context(
                chapter_num,
                history_context,
                query_bundle["query_result"],
                query_bundle["character_context"],
            )

            emit("status", message="整理最终 Prompt...")
            final_prompt = context_builder.build_final_prompt(
                chapter_num,
                extra_context=summary,
                outline_text=outline_text,
            )
            generation_messages = content_agent.build_messages(chapter_num, final_prompt)
            prompt_path = save_prompt_snapshot(
                paths["prompt_logs_dir"],
                chapter_num,
                final_prompt,
                generation_messages,
            )
            emit(
                "prompt_capture",
                chapter=chapter_num,
                final_prompt=final_prompt,
                messages=generation_messages,
                path=str(prompt_path.relative_to(paths["project_dir"])),
            )

            emit("status", message="生成章节内容...")
            content_chunks = []
            stream = client.chat.completions.create(
                model=config.get("model", "gpt-4"),
                messages=generation_messages,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    content_chunks.append(text)
                    emit("content", text=text)

            content = strip_state_appendix("".join(content_chunks))
            (paths["chapters_dir"] / f"chapter_{chapter_num}.txt").write_text(content, encoding="utf-8")

            emit("status", message="并发执行摘要生成和状态更新...")
            for chunk in stream_parallel_post_process_events(
                content,
                chapter_num,
                llm_call,
                config,
                paths["data_dir"],
                paths["schema_path"],
                paths["prompt_logs_dir"],
                paths["project_dir"],
            ):
                event = json.loads(chunk.removeprefix("data: ").strip())
                append_generation_event(task, event)

            refresh_project_progress(project_id)
            emit("done", chapter=chapter_num, redirect=f"/project/{project_id}/chapter/{chapter_num}")
        except Exception as exc:
            emit("error", message=str(exc))


@app.route("/")
def home():
    return redirect(url_for("projects_page"))


@app.route("/projects")
def projects_page():
    projects = [enrich_project(project) for project in project_mgr.list_projects()]
    stats = {
        "project_count": len(projects),
        "chapter_count": sum(project["chapter_count"] for project in projects),
        "character_count": sum(project["character_count"] for project in projects),
        "active_count": sum(1 for project in projects if project["status"] != "completed"),
    }
    return render_template(
        "projects.html",
        title="项目列表",
        section="projects",
        projects=projects,
        stats=stats,
    )


@app.route("/projects/new")
def new_project_page():
    return render_template(
        "project_create.html",
        title="创建项目",
        section="projects",
    )


@app.route("/projects/create", methods=["POST"])
def create_project():
    data = request.get_json(silent=True) or request.form.to_dict()
    try:
        project_id = project_mgr.create_project(
            title=data.get("title"),
            description=data.get("description", ""),
            genre=data.get("genre", ""),
            style=data.get("style", ""),
            total_chapters=data.get("total_chapters", 10),
        )
        ensure_project_structure(project_id)
        if request.is_json:
            return jsonify({"success": True, "project_id": project_id})
        return redirect(url_for("project_dashboard", project_id=project_id))
    except Exception as exc:
        if not request.is_json:
            return render_template(
                "project_create.html",
                title="创建项目",
                section="projects",
                error=str(exc),
                form_data=data,
            ), 400
        return jsonify({"error": str(exc)}), 400


@app.route("/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    try:
        project_mgr.delete_project(project_id)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/project/<project_id>")
def project_dashboard(project_id):
    project = require_project(project_id)
    chapters = build_chapter_cards(project_id)[:5]
    characters = build_character_cards(project_id)[:6]
    foreshadowing_groups = build_foreshadowing_groups(project_id)[:4]
    return render_template(
        "project_dashboard.html",
        title=project["title"],
        section="dashboard",
        project=project,
        chapters=chapters,
        characters=characters,
        outline=load_outline(project_id),
        foreshadowing_groups=foreshadowing_groups,
    )


@app.route("/project/<project_id>/update", methods=["POST"])
def update_project(project_id):
    require_project(project_id)
    data = request.json or {}
    try:
        project = project_mgr.update_project(
            project_id,
            title=data.get("title"),
            description=data.get("description"),
            genre=data.get("genre"),
            style=data.get("style"),
            total_chapters=data.get("total_chapters"),
        )
        return jsonify({"success": True, "project": enrich_project(project)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/project/<project_id>/outline")
def outline_page(project_id):
    project = require_project(project_id)
    return render_template(
        "outline.html",
        title=f"{project['title']} · 大纲",
        section="outline",
        project=project,
        outline=load_outline(project_id),
    )


@app.route("/project/<project_id>/outline/save", methods=["POST"])
def save_outline_page(project_id):
    require_project(project_id)
    data = request.json or {}
    save_outline(project_id, data.get("outline", ""))
    return jsonify({"success": True})


@app.route("/project/<project_id>/characters")
def characters_page(project_id):
    project = require_project(project_id)
    return render_template(
        "characters.html",
        title=f"{project['title']} · 角色",
        section="characters",
        project=project,
        characters=build_character_cards(project_id),
    )


@app.route("/project/<project_id>/characters/new")
def new_character_page(project_id):
    project = require_project(project_id)
    return render_template(
        "character_create.html",
        title=f"{project['title']} · 创建角色",
        section="characters",
        project=project,
    )


@app.route("/project/<project_id>/character/create", methods=["POST"])
def create_character(project_id):
    project = require_project(project_id)
    data = request.get_json(silent=True) or request.form.to_dict()
    fields = data.get("fields") or {}
    if isinstance(fields, str):
        try:
            fields = json.loads(fields)
        except json.JSONDecodeError:
            fields = {}
    result = get_state_manager(project_id).create_character(
        data["name"],
        int(data.get("chapter", 0) or 0),
        data.get("reason", "手动创建"),
        data.get("is_foreshadowing", False),
        **fields,
    )
    refresh_project_progress(project_id)
    if request.is_json:
        return jsonify_result(result)
    if "error" in result:
        return render_template(
            "character_create.html",
            title=f"{project['title']} · 创建角色",
            section="characters",
            project=project,
            error=result["error"],
            form_data=data,
            field_data=fields,
        ), 400
    return redirect(url_for("character_detail", project_id=project_id, name=data["name"]))


@app.route("/project/<project_id>/character/<name>")
def character_detail(project_id, name):
    project = require_project(project_id)
    data = get_state_manager(project_id).get_character(name)
    if "error" in data:
        return data["error"], 404

    latest_fields = {
        field: history[-1]["value"]
        for field, history in data.get("fields", {}).items()
        if history
    }
    field_histories = [
        {"name": field, "history": list(reversed(history))}
        for field, history in sorted(data.get("fields", {}).items())
    ]
    return render_template(
        "character_detail.html",
        title=f"{name} · 角色详情",
        section="characters",
        project=project,
        name=name,
        latest_fields=latest_fields,
        field_histories=field_histories,
        data=data,
    )


@app.route("/project/<project_id>/character/<name>/update", methods=["POST"])
def update_character(project_id, name):
    require_project(project_id)
    data = request.json or {}
    result = get_state_manager(project_id).update_character(
        name,
        data.get("chapter", 0),
        data.get("reason", "手动编辑"),
        data.get("is_foreshadowing", False),
        **(data.get("fields") or {}),
    )
    refresh_project_progress(project_id)
    return jsonify_result(result)


@app.route("/project/<project_id>/character/<name>", methods=["DELETE"])
def delete_character(project_id, name):
    require_project(project_id)
    result = get_state_manager(project_id).delete_character(name)
    refresh_project_progress(project_id)
    return jsonify_result(result)


@app.route("/project/<project_id>/chapters")
def chapters_page(project_id):
    project = require_project(project_id)
    chapters = build_chapter_cards(project_id)
    return render_template(
        "chapters.html",
        title=f"{project['title']} · 章节",
        section="chapters",
        project=project,
        chapters=chapters,
        next_chapter=max([chapter["num"] for chapter in chapters], default=0) + 1,
    )


@app.route("/project/<project_id>/chapter/<int:num>")
def chapter_detail(project_id, num):
    project = require_project(project_id)
    paths = ensure_project_structure(project_id)
    chapter_path = paths["chapters_dir"] / f"chapter_{num}.txt"
    if not chapter_path.exists():
        return "章节不存在", 404

    content = strip_state_appendix(chapter_path.read_text(encoding="utf-8"))
    summary_path = paths["summaries_dir"] / f"chapter_{num}.txt"
    summary = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
    changes = get_state_manager(project_id).get_chapter_state_changes(num).get("changes", [])
    return render_template(
        "chapter_detail.html",
        title=f"第 {num} 章",
        section="chapters",
        project=project,
        chapter_num=num,
        content=content,
        summary=summary,
        changes=changes,
    )


@app.route("/project/<project_id>/chapter/<int:num>/save", methods=["POST"])
def save_chapter(project_id, num):
    require_project(project_id)
    paths = ensure_project_structure(project_id)
    data = request.json or {}
    (paths["chapters_dir"] / f"chapter_{num}.txt").write_text(
        strip_state_appendix(data.get("content", "")),
        encoding="utf-8",
    )
    refresh_project_progress(project_id)
    return jsonify({"success": True})


@app.route("/project/<project_id>/chapter/<int:num>", methods=["DELETE"])
def delete_chapter(project_id, num):
    require_project(project_id)
    paths = ensure_project_structure(project_id)
    chapter_path = paths["chapters_dir"] / f"chapter_{num}.txt"
    if chapter_path.exists():
        chapter_path.unlink()
    summary_path = paths["summaries_dir"] / f"chapter_{num}.txt"
    if summary_path.exists():
        summary_path.unlink()
    refresh_project_progress(project_id)
    return jsonify({"success": True})


@app.route("/project/<project_id>/schema")
def schema_page(project_id):
    project = require_project(project_id)
    return render_template(
        "schema.html",
        title=f"{project['title']} · 状态定义",
        section="schema",
        project=project,
        schema=get_schema_manager(project_id).load_schema(),
    )


@app.route("/project/<project_id>/schema/field", methods=["POST"])
def add_field(project_id):
    require_project(project_id)
    data = request.json or {}
    result = get_schema_manager(project_id).add_field(
        data["name"],
        data["description"],
        data.get("required", False),
    )
    return jsonify_result(result)


@app.route("/project/<project_id>/schema/field/<name>", methods=["DELETE"])
def delete_field(project_id, name):
    require_project(project_id)
    return jsonify_result(get_schema_manager(project_id).remove_field(name))


@app.route("/project/<project_id>/schema/rule", methods=["POST"])
def add_rule(project_id):
    require_project(project_id)
    data = request.json or {}
    return jsonify_result(get_schema_manager(project_id).add_rule(data["rule"]))


@app.route("/project/<project_id>/schema/rule/<int:index>", methods=["DELETE"])
def delete_rule(project_id, index):
    require_project(project_id)
    return jsonify_result(get_schema_manager(project_id).remove_rule(index))


@app.route("/project/<project_id>/config", methods=["GET", "POST"])
def config_page(project_id):
    project = require_project(project_id)
    paths = ensure_project_structure(project_id)
    if request.method == "POST":
        save_config(paths["config_path"], request.json or {})
        return jsonify({"success": True})
    return render_template(
        "config.html",
        title=f"{project['title']} · 配置",
        section="config",
        project=project,
        config=load_config(paths["config_path"]),
    )


@app.route("/project/<project_id>/foreshadowing")
def foreshadowing_page(project_id):
    project = require_project(project_id)
    return render_template(
        "foreshadowing.html",
        title=f"{project['title']} · 伏笔",
        section="foreshadowing",
        project=project,
        groups=build_foreshadowing_groups(project_id),
    )


@app.route("/project/<project_id>/generate", methods=["GET", "POST"])
def generate_chapter(project_id):
    project = require_project(project_id)
    if request.method == "GET":
        chapters = build_chapter_cards(project_id)
        next_chapter = max([chapter["num"] for chapter in chapters], default=0) + 1
        return render_template(
            "generate.html",
            title=f"{project['title']} · 创建任务",
            section="chapters",
            project=project,
            next_chapter=next_chapter,
            recent_chapters=chapters[:3],
            outline=load_outline(project_id),
        )

    data = request.json or {}
    chapter_num = int(data["chapter"])
    summary = data.get("summary", "")

    existing_task = find_active_generation_task(project_id)
    if existing_task:
        return jsonify(
            {
                "success": True,
                "existing": True,
                "task": serialize_generation_task(existing_task),
                "stream_url": url_for(
                    "stream_generation_task",
                    project_id=project_id,
                    task_id=existing_task["id"],
                ),
            }
        )

    task = create_generation_task(project_id, chapter_num, summary)
    worker = threading.Thread(target=run_generation_task, args=(task,), daemon=True)
    worker.start()
    return jsonify(
        {
            "success": True,
            "task": serialize_generation_task(task),
            "stream_url": url_for(
                "stream_generation_task",
                project_id=project_id,
                task_id=task["id"],
            ),
        }
    )


@app.route("/project/<project_id>/generate/tasks/latest")
def latest_generation_task(project_id):
    require_project(project_id)
    task = find_active_generation_task(project_id)
    if not task:
        return jsonify({"active": False})
    return jsonify({"active": True, "task": serialize_generation_task(task)})


@app.route("/project/<project_id>/generate/tasks/<task_id>")
def generation_task_detail(project_id, task_id):
    require_project(project_id)
    task = get_generation_task(task_id, project_id=project_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify({"success": True, "task": serialize_generation_task(task)})


@app.route("/project/<project_id>/generate/tasks/<task_id>/stream")
def stream_generation_task(project_id, task_id):
    require_project(project_id)
    task = get_generation_task(task_id, project_id=project_id)
    if not task:
        abort(404)

    def generate():
        index = 0
        while True:
            with task["condition"]:
                while index >= len(task["events"]) and task["status"] not in TERMINAL_TASK_STATUSES:
                    task["condition"].wait(timeout=15)
                pending = list(task["events"][index:])
                status = task["status"]

            for event in pending:
                index += 1
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            if status in TERMINAL_TASK_STATUSES and index >= len(task["events"]):
                break

    return sse_response(generate)


@app.route("/project/<project_id>/chapter/<int:chapter_num>/regenerate", methods=["POST"])
def regenerate_states(project_id, chapter_num):
    require_project(project_id)

    def generate():
        with project_runtime(project_id) as paths:
            try:
                chapter_file = paths["chapters_dir"] / f"chapter_{chapter_num}.txt"
                if not chapter_file.exists():
                    yield f"data: {json.dumps({'type': 'error', 'message': '章节不存在'}, ensure_ascii=False)}\n\n"
                    return

                content = strip_state_appendix(chapter_file.read_text(encoding="utf-8"))
                config = load_config(paths["config_path"])
                if not config.get("api_key"):
                    yield f"data: {json.dumps({'type': 'error', 'message': '请先在项目配置中填写 API 信息'}, ensure_ascii=False)}\n\n"
                    return

                _, llm_call = build_openai_client(config)
                yield f"data: {json.dumps({'type': 'status', 'message': '进入逐角色更新流...'}, ensure_ascii=False)}\n\n"
                yield from stream_state_update_events(
                    content,
                    chapter_num,
                    llm_call,
                    paths["schema_path"],
                    paths["prompt_logs_dir"],
                    paths["project_dir"],
                )
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return sse_response(generate)


if __name__ == "__main__":
    print("启动 Agent Web 界面: http://localhost:5001")
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=5001)
