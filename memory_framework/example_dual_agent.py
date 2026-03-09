"""双Agent架构使用示例"""
from dual_agent import StateAgent, ContentAgent


def my_llm_function(messages, tools=None):
    """
    这里接入你的LLM API

    示例：
    - OpenAI: client.chat.completions.create(messages=messages, tools=tools)
    - DeepSeek: 同上
    - Qwen: 同上
    """
    # TODO: 替换为实际的LLM调用
    pass


# 初始化双Agent
state_agent = StateAgent(llm_function=my_llm_function)
content_agent = ContentAgent(llm_function=my_llm_function)


def generate_chapter(chapter_num: int, previous_summary: str = ""):
    """生成一章小说的完整流程"""

    print(f"\n{'='*50}")
    print(f"开始生成第{chapter_num}章")
    print(f"{'='*50}\n")

    # 步骤1: StateAgent准备上下文
    print("[1] StateAgent: 查询角色状态...")
    context = state_agent.prepare_context(chapter_num)
    print(f"角色状态:\n{context}\n")

    # 步骤2: ContentAgent生成正文
    print("[2] ContentAgent: 生成章节内容...")
    content = content_agent.generate(chapter_num, context, previous_summary)
    print(f"生成内容:\n{content}\n")

    # 步骤3: StateAgent更新状态
    print("[3] StateAgent: 更新角色状态...")
    state_agent.update_states(content, chapter_num)
    print("状态更新完成\n")

    return content


# 使用示例
if __name__ == "__main__":
    # 生成第1章
    chapter1 = generate_chapter(1)

    # 生成第2章（可以传入前文摘要）
    chapter2 = generate_chapter(2, previous_summary="第1章：主角张三在华山...")
