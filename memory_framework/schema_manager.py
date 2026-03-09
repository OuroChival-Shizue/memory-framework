"""状态字段定义管理器"""
import yaml
from pathlib import Path

class SchemaManager:
    def __init__(self, schema_path="state_schema.yaml"):
        raw_path = Path(schema_path)
        if raw_path.is_absolute():
            self.schema_path = raw_path
        else:
            self.schema_path = Path(__file__).resolve().parent / raw_path

    def load_schema(self):
        """加载状态定义"""
        if not self.schema_path.exists():
            return {"required_fields": {}, "optional_fields": {}, "rules": []}
        with open(self.schema_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {"required_fields": {}, "optional_fields": {}, "rules": []}

    def save_schema(self, schema):
        """保存状态定义"""
        with open(self.schema_path, 'w', encoding='utf-8') as f:
            yaml.dump(schema, f, allow_unicode=True, sort_keys=False)

    def add_field(self, field_name, description, required=False):
        """添加字段"""
        schema = self.load_schema()
        target = "required_fields" if required else "optional_fields"
        schema[target][field_name] = description
        self.save_schema(schema)
        return {"success": True}

    def remove_field(self, field_name):
        """删除字段"""
        schema = self.load_schema()
        if field_name in schema["required_fields"]:
            del schema["required_fields"][field_name]
        if field_name in schema["optional_fields"]:
            del schema["optional_fields"][field_name]
        self.save_schema(schema)
        return {"success": True}

    def update_field(self, field_name, description, required):
        """更新字段"""
        self.remove_field(field_name)
        return self.add_field(field_name, description, required)

    def add_rule(self, rule_text):
        """添加规则"""
        schema = self.load_schema()
        if "rules" not in schema:
            schema["rules"] = []
        schema["rules"].append(rule_text)
        self.save_schema(schema)
        return {"success": True}

    def remove_rule(self, index):
        """删除规则"""
        schema = self.load_schema()
        if "rules" in schema and 0 <= index < len(schema["rules"]):
            schema["rules"].pop(index)
            self.save_schema(schema)
        return {"success": True}
