
import json
from typing import Literal

# ======== 伪 LLM 调用接口 ========

def llm_call(messages: list[dict]) -> dict:
    """
    这里用伪代码描述：
    你在实际实现中用 openai.chat.completions.create / Azure / 其他 SDK 替换即可。
    关键是：让模型输出一个结构化 JSON，里面包含：
      - action: "plan" / "run_code" / "finish"
      - code: （当 action=run_code 时）
      - analysis: （模型对当前状态的思考说明）
    """
    # pseudo-code:
    # response = openai.chat.completions.create(
    #     model="gpt-4.X",
    #     messages=messages,
    #     temperature=0.2,
    # )
    # text = response.choices[0].message.content

    # 为了示例，假装模型永远只执行一次简单代码，然后结束
    # 实际上你需要把 system+preset prompt 写好，让模型返回 JSON。
    text = """
    {
        "action": "run_code",
        "analysis": "先统计这一列的平均值。",
        "code": "import pandas as pd\\nprint('demo output')"
    }
    """
    return {"content": text}


# ======== 工具：执行 Python 代码 ========

import io
import sys
import textwrap

def run_python_code(code: str) -> dict:
    old_stdout = sys.stdout
    stdout_buffer = io.StringIO()
    sys.stdout = stdout_buffer

    error = None
    try:
        exec(textwrap.dedent(code), {})
    except Exception as e:
        error = repr(e)
    finally:
        sys.stdout = old_stdout

    return {
        "stdout": stdout_buffer.getvalue(),
        "error": error,
    }


# ======== Agent 主循环 ========

ActionType = Literal["plan", "run_code", "finish"]

def agent_loop(user_goal: str, max_steps: int = 8) -> None:
    """
    一个最小可行的 Agent 循环示例：
      1. 把用户目标告诉 LLM
      2. LLM 每轮返回一个 JSON，告诉我们下一步要干嘛
      3. 如果 action=run_code，就调用本地 run_python_code 工具
      4. 把工具的结果再喂回给 LLM，进入下一轮
      5. 直到 action=finish 或达到 max_steps
    """

    # 1. 构造初始对话
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个数据分析 Agent，可以规划步骤并调用一个工具 run_python_code。\n"
                "每一轮你必须输出一个严格的 JSON，对象结构如下：\n"
                "{\n"
                "  \"action\": \"plan\" | \"run_code\" | \"finish\",\n"
                "  \"analysis\": \"你当前的思考和理由\",\n"
                "  \"code\": \"当 action=run_code 时要执行的 Python 代码，否则可以省略\",\n"
                "  \"final_answer\": \"当 action=finish 时给用户的最终总结，否则可以省略\"\n"
                "}\n"
                "不要输出任何解释性文字，只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": f"我的目标是：{user_goal}",
        },
    ]

    for step in range(1, max_steps + 1):
        print(f"\n=== Agent Step {step} ===")

        # 2. 调用 LLM
        resp = llm_call(messages)
        raw_content = resp["content"].strip()
        print("[LLM raw output]")
        print(raw_content)

        # 3. 解析 JSON
        try:
            decision = json.loads(raw_content)
        except json.JSONDecodeError as e:
            print("[Agent] JSON 解析失败，终止循环：", e)
            break

        action: ActionType = decision.get("action", "finish")  # type: ignore
        analysis = decision.get("analysis", "")

        print(f"[Agent] action = {action}")
        print(f"[Agent] analysis = {analysis}")

        if action == "finish":
            final_answer = decision.get("final_answer", "")
            print("[Agent] Final answer to user:")
            print(final_answer)
            break

        elif action == "run_code":
            code = decision.get("code", "")
            print("[Agent] executing code:")
            print(code)

            # 4. 调用工具
            result = run_python_code(code)
            print("[Tool run_python_code] result:")
            print(result)

            # 5. 把工具结果发回 LLM，进入下一轮
            tool_feedback = (
                "我已经帮你执行了你刚才生成的代码，结果如下：\n"
                f"stdout:\n{result['stdout']}\n"
                f"error:\n{result['error']}"
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": raw_content,
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": tool_feedback,
                }
            )

        elif action == "plan":
            # 只更新对话，让 LLM 在下一轮给出进一步动作
            messages.append(
                {
                    "role": "assistant",
                    "content": raw_content,
                }
            )
            # 可选择性追加一个 user 提示，要求它给出下一步更具体动作
            messages.append(
                {
                    "role": "user",
                    "content": "好的，请根据这个计划给出下一步的具体 action。",
                }
            )

    else:
        print("[Agent] 达到最大步数，强制终止。")


if __name__ == "__main__":
    agent_loop("对上传的销售数据做描述性统计，并输出关键结论。")
