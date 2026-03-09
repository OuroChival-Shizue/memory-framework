"""简单的Agent执行器 - MVP版本"""
import json
from agent_tools import TOOLS, execute_tool


def clean_messages(messages: list) -> list:
    """清洗消息，移除工具调用信息，只保留对话内容"""
    cleaned = []
    for msg in messages:
        if msg["role"] in ["user", "assistant"]:
            if "content" in msg and msg["content"]:
                cleaned.append({"role": msg["role"], "content": msg["content"]})
    return cleaned


class SimpleAgent:
    def __init__(self, llm_function=None):
        """
        llm_function: 你的LLM调用函数
        格式: llm_function(messages, tools) -> response
        """
        self.llm_function = llm_function
        self.tools = TOOLS

    def run(self, task: str, max_iterations: int = 10) -> dict:
        """执行Agent任务"""
        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": task}
        ]

        results = {"iterations": [], "final_response": None}

        for i in range(max_iterations):
            print(f"\n[迭代 {i+1}]")

            # 调用LLM
            if self.llm_function:
                response = self.llm_function(messages, self.tools)
            else:
                # 模拟模式：手动输入工具调用
                response = self._mock_llm_response(messages)

            # 检查是否有工具调用
            if hasattr(response, 'tool_calls') and response.tool_calls:
                # 执行工具
                for tool_call in response.tool_calls:
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)

                    print(f"  调用工具: {tool_name}({arguments})")
                    result = execute_tool(tool_name, arguments)
                    print(f"  结果: {result}")

                    results["iterations"].append({
                        "tool": tool_name,
                        "arguments": arguments,
                        "result": result
                    })

                    # 添加工具结果到消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
            else:
                # LLM完成任务
                results["final_response"] = response.content if hasattr(response, 'content') else str(response)
                print(f"  完成: {results['final_response']}")
                break

        return results

    def _get_system_prompt(self) -> str:
        return """你是一个小说写作助手Agent。你可以使用以下工具管理角色状态：

1. create_character - 创建新角色
2. get_character - 查询角色状态
3. update_character - 更新角色状态
4. delete_character - 删除角色

角色的字段完全由你决定，可以包含任何信息（姓名、年龄、位置、健康、装备等）。

当用户要求生成章节时：
1. 先查询相关角色的当前状态
2. 根据状态生成章节内容
3. 根据章节内容更新角色状态
4. 如果出现新角色，创建它们"""

    def _mock_llm_response(self, messages):
        """模拟LLM响应（用于测试）"""
        print("\n[模拟模式] 请输入工具调用（JSON格式）或输入'done'完成：")
        user_input = input("> ")

        if user_input.strip().lower() == 'done':
            return type('obj', (object,), {'content': '任务完成'})()

        try:
            tool_call_data = json.loads(user_input)
            # 模拟工具调用对象
            tool_call = type('obj', (object,), {
                'id': 'mock_id',
                'function': type('obj', (object,), {
                    'name': tool_call_data['name'],
                    'arguments': json.dumps(tool_call_data['arguments'])
                })()
            })()
            return type('obj', (object,), {'tool_calls': [tool_call]})()
        except:
            return type('obj', (object,), {'content': '输入格式错误'})()
