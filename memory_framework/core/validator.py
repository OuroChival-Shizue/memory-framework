"""状态验证器"""
import yaml
from pathlib import Path
from typing import Dict, Any, List


class StateValidator:
    def __init__(self, template_path: str = "config/character_template.yaml"):
        self.template_path = Path(template_path)
        self.template = self._load_template()

    def _load_template(self) -> Dict[str, Any]:
        """加载状态模板"""
        with open(self.template_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def validate_state(self, state: Dict[str, Any]) -> List[str]:
        """验证状态是否符合模板"""
        errors = []

        # 检查核心状态
        core_states = self.template['character_states']['core']
        for state_def in core_states:
            name = state_def['name']

            # 检查是否存在
            if name not in state.get('core', {}):
                errors.append(f"缺失核心状态: {name}")
                continue

            value = state['core'][name]
            state_type = state_def['type']

            # 类型检查
            if state_type == 'boolean' and not isinstance(value, bool):
                errors.append(f"{name} 必须是 boolean 类型")
            elif state_type == 'string' and not isinstance(value, str):
                errors.append(f"{name} 必须是 string 类型")
            elif state_type == 'list' and not isinstance(value, list):
                errors.append(f"{name} 必须是 list 类型")
            elif state_type == 'dict' and not isinstance(value, dict):
                errors.append(f"{name} 必须是 dict 类型")

            # 枚举值检查
            if state_type == 'enum' and 'values' in state_def:
                if value not in state_def['values']:
                    errors.append(f"{name} 的值 '{value}' 不在允许范围: {state_def['values']}")

        return errors

    def get_core_state_names(self) -> List[str]:
        """获取所有核心状态名称"""
        return [s['name'] for s in self.template['character_states']['core']]

    def get_important_state_names(self) -> List[str]:
        """获取所有重要状态名称"""
        return [s['name'] for s in self.template['character_states']['important']]
