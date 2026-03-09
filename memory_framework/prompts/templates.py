"""LLM Prompt 模板"""


def get_state_extraction_prompt(chapter_text: str, current_states: dict, template: dict) -> str:
    """生成状态提取的prompt"""
    core_states = [s['name'] for s in template['character_states']['core']]
    important_states = [s['name'] for s in template['character_states']['important']]

    prompt = f"""# 任务：从章节中提取角色状态更新

## 章节内容
{chapter_text}

## 当前角色状态
{format_states(current_states)}

## 状态模板
核心状态（必须更新）: {', '.join(core_states)}
重要状态（有变化时更新）: {', '.join(important_states)}

## 输出要求
请以JSON格式输出所有角色的状态更新：

```json
{{
  "updates": [
    {{
      "character": "角色名",
      "core": {{
        "location": "位置",
        "alive": true/false,
        "health": "健康/轻伤/重伤/濒死"
      }},
      "important": {{
        "武功等级": "...",
        "主要装备": [...],
        "关键关系": {{...}}
      }},
      "changes": ["变化描述1", "变化描述2"]
    }}
  ]
}}
```

注意：
1. 所有核心状态必须填写
2. 只更新有变化的重要状态
3. changes字段描述本章发生的状态变化
"""
    return prompt


def get_event_extraction_prompt(chapter_text: str, chapter_num: int) -> str:
    """生成事件提取的prompt"""
    prompt = f"""# 任务：从章节中提取关键事件

## 章节 {chapter_num}
{chapter_text}

## 输出要求
请提取本章的关键事件，以JSON格式输出：

```json
{{
  "events": [
    {{
      "type": "movement/combat/injury/death/relationship_change/item_acquire",
      "character": "主要角色",
      "description": "事件描述",
      "details": {{
        // 事件相关的详细信息
      }}
    }}
  ]
}}
```

事件类型说明：
- movement: 角色移动
- combat: 战斗
- injury: 受伤
- death: 死亡
- relationship_change: 关系变化
- item_acquire: 获得物品
"""
    return prompt


def get_generation_prompt(chapter_outline: str, character_states: dict,
                         recent_chapters: str, world_setting: str) -> str:
    """生成章节的prompt"""
    prompt = f"""# 任务：根据大纲和当前状态生成章节

## 章节大纲
{chapter_outline}

## 角色当前状态（必须遵守）
{format_states(character_states)}

## 最近章节摘要
{recent_chapters}

## 世界设定
{world_setting}

## 要求
1. 严格遵守角色当前状态
2. 如果需要改变状态，必须在章节中描写变化过程
3. 保持与之前章节的连贯性
4. 字数：3000-5000字

请开始生成章节内容：
"""
    return prompt


def format_states(states: dict) -> str:
    """格式化状态为可读文本"""
    lines = []
    for name, state in states.items():
        lines.append(f"\n{name}:")
        if 'core' in state:
            for key, value in state['core'].items():
                lines.append(f"  - {key}: {value}")
        if 'important' in state:
            for key, value in state['important'].items():
                lines.append(f"  - {key}: {value}")
    return '\n'.join(lines)
