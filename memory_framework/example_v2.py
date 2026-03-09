"""Example usage for the Memory Framework V2 pipeline."""

import threading

from context_builder import ContextBuilder
from dual_agent import ContentAgent, StateAgent
from prompt_cleaner import PromptCleaner
from summary_manager import SummaryManager


def my_llm_function(messages, tools=None):
    """Replace this with your actual LLM client call."""
    raise NotImplementedError("请接入实际的 LLM 调用函数。")


def main(chapter_num: int = 1):
    state_agent = StateAgent(llm_function=my_llm_function)
    content_agent = ContentAgent(llm_function=my_llm_function)
    summary_manager = SummaryManager(llm_function=my_llm_function)
    prompt_cleaner = PromptCleaner()
    context_builder = ContextBuilder(
        llm_function=my_llm_function,
        state_agent=state_agent,
        summary_manager=summary_manager,
        prompt_cleaner=prompt_cleaner,
    )

    final_prompt = context_builder.build_final_prompt(chapter_num)
    content = content_agent.generate(chapter_num, final_prompt)

    summary_thread = threading.Thread(
        target=summary_manager.generate_summary,
        args=(chapter_num, content),
    )
    state_thread = threading.Thread(
        target=state_agent.update_states,
        args=(content, chapter_num),
    )
    summary_thread.start()
    state_thread.start()
    summary_thread.join()
    state_thread.join()
    return content


if __name__ == "__main__":
    print(main(1))
