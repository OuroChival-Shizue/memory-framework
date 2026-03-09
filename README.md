# Memory Framework

AI 辅助小说写作框架，使用双智能体架构管理角色状态和生成章节内容。

## 核心特性

- **双智能体架构**：分离状态管理（StateAgent）和内容生成（ContentAgent）
- **仅追加历史**：角色状态采用时间线记录，支持状态回溯
- **显式状态更新**：通过工具调用管理状态，避免隐式变更
- **Web UI**：实时流式传输章节生成进度
- **多项目支持**：独立管理多个小说项目

## 快速开始

### 1. 安装依赖

```bash
cd memory_framework
pip install -r requirements.txt
```

### 2. 配置 API

复制配置模板并填入你的 API 信息：

```bash
cp config.example.json data/config.json
```

编辑 `data/config.json`：

```json
{
  "api_url": "https://api.example.com/v1",
  "api_key": "your-api-key-here",
  "model": "your-model-name"
}
```

### 3. 启动服务

```bash
python agent_web.py
```

访问 http://localhost:5001

## 项目结构

```
memory_framework/
├── dual_agent.py          # 双智能体实现
├── dynamic_state.py       # 状态存储
├── agent_tools.py         # 工具定义
├── agent_web.py           # Web UI
├── context_builder.py     # 上下文构建
├── summary_manager.py     # 摘要管理
├── schema_manager.py      # 模式管理
├── state_schema.yaml      # 字段定义
└── data/
    ├── characters/        # 角色状态
    ├── chapters/          # 章节内容
    └── summaries/         # 章节摘要
```

## 核心架构

### 双智能体系统

**StateAgent** - 状态管理
- 生成前读取角色状态
- 生成后更新角色状态
- 仅使用工具调用

**ContentAgent** - 内容生成
- 生成章节文本
- 不接触状态管理
- 接收清理后的上下文

### 状态历史模型

角色数据采用仅追加历史：

```json
{
  "fields": {
    "location": [
      {"value": "华山", "chapter": 1, "reason": "初始位置"},
      {"value": "东城", "chapter": 3, "reason": "追踪敌人"}
    ]
  }
}
```

## 使用说明

1. 创建项目并配置大纲
2. 添加角色并设置初始状态
3. 生成章节（支持实时进度查看）
4. 查看和编辑生成的内容

详细说明见 [CLAUDE.md](CLAUDE.md)

## 许可证

仅供学习和研究使用。
