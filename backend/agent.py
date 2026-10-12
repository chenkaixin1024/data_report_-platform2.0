"""
LLM Agent Loop with streaming output.

The agent autonomously plans, executes code, analyzes results,
and generates reports. It uses the protocol tags to structure
its output into different content types.
"""

import asyncio
import json
import logging
import re
from typing import AsyncGenerator

from config import config
from llm_client import stream_chat_completion
from protocol import EventType, ProtocolParser, StreamEvent, create_sse_event
from prompts import build_messages
from run_code import run_python_code

logger = logging.getLogger(__name__)


def _sanitize_chart_json(raw: str) -> str:
    """
    Remove JavaScript code from LLM-generated JSON.
    Handles: function bodies, method calls (.reverse(), .sort(), etc.),
    malformed key-value pairs.
    """
    # 1. Remove "key": function(...) { ... } patterns
    pattern = re.compile(r'"(\w+)"\s*:\s*function\s*\([^)]*\)\s*\{')
    result: list[str] = []
    i = 0
    while i < len(raw):
        m = pattern.search(raw, i)
        if m is None:
            result.append(raw[i:])
            break
        result.append(raw[i:m.start()])
        key = m.group(1)
        result.append(f'"{key}": ""')
        brace_depth = 1
        j = m.end()
        while j < len(raw) and brace_depth > 0:
            if raw[j] == '{':
                brace_depth += 1
            elif raw[j] == '}':
                brace_depth -= 1
            j += 1
        i = j
    sanitized = ''.join(result)

    # 2. Remove JavaScript method calls on arrays: ].reverse(), ].sort(), etc.
    sanitized = re.sub(r'\]\s*\.\s*\w+\s*\(\s*\)', ']', sanitized)

    # 3. Fix malformed "key": "anotherKey": value → "key": value
    #    e.g. "type": "yAxisIndex": 1  →  "yAxisIndex": 1
    sanitized = re.sub(
        r'"(\w+)"\s*:\s*"(\w+)"\s*:\s*(\d+(?:\.\d+)?)',
        r'"\2": \3',
        sanitized,
    )

    return sanitized


def _parse_chart_json(content: str) -> dict | None:
    """Try to parse chart JSON with multiple fallback strategies."""
    sanitized = _sanitize_chart_json(content)

    # Strategy 1: direct parse
    try:
        data = json.loads(sanitized)
        return _normalize_chart_data(data)
    except json.JSONDecodeError:
        pass

    # Strategy 2: remove trailing commas
    try:
        no_trailing = re.sub(r',\s*([}\]])', r'\1', sanitized)
        data = json.loads(no_trailing)
        return _normalize_chart_data(data)
    except json.JSONDecodeError:
        pass

    # Strategy 3: extract JSON object from text (LLM may wrap in markdown)
    try:
        match = re.search(r'\{[\s\S]*\}', sanitized)
        if match:
            candidate = match.group(0)
            candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
            data = json.loads(candidate)
            return _normalize_chart_data(data)
    except (json.JSONDecodeError, Exception):
        pass

    return None


def _normalize_chart_data(data: dict) -> dict:
    """Normalize parsed chart data: ensure title is string, option is dict."""
    if isinstance(data.get("title"), dict):
        data["title"] = data["title"].get("text", "数据图表")
    if not isinstance(data.get("title"), str):
        data["title"] = "数据图表"
    if not isinstance(data.get("option"), dict):
        data = {"title": "数据图表", "option": data}
    data["option"] = _sanitize_echarts_option(data["option"])
    return data


def _sanitize_echarts_option(opt: dict) -> dict:
    """Ensure ECharts option fields have correct types."""
    # title: must be object, not string
    if isinstance(opt.get("title"), str):
        opt["title"] = {"text": opt["title"], "left": "center"}
    elif isinstance(opt.get("title"), list):
        opt["title"] = {"text": str(opt["title"]), "left": "center"}
    elif not isinstance(opt.get("title"), (dict, type(None))):
        opt.pop("title", None)

    # xAxis: must be object, not string or list
    if isinstance(opt.get("xAxis"), str):
        opt["xAxis"] = {"type": "category", "data": [opt["xAxis"]]}
    elif isinstance(opt.get("xAxis"), list):
        opt["xAxis"] = {"type": "category", "data": opt["xAxis"]}
    elif isinstance(opt.get("xAxis"), dict):
        # Ensure data inside xAxis is a list, not a string
        x = opt["xAxis"]
        if isinstance(x.get("data"), str):
            x["data"] = [x["data"]]

    # yAxis: must be object, not string or list
    if isinstance(opt.get("yAxis"), str):
        opt["yAxis"] = {"type": "value", "name": opt["yAxis"]}
    elif isinstance(opt.get("yAxis"), list):
        opt["yAxis"] = {"type": "value"}

    # series: must be a list
    if opt.get("series") and not isinstance(opt["series"], list):
        opt["series"] = [opt["series"]] if isinstance(opt["series"], dict) else []

    # Validate each series item
    if isinstance(opt.get("series"), list):
        clean_series = []
        for s in opt["series"]:
            if not isinstance(s, dict):
                continue
            if not s.get("type"):
                s["type"] = "bar"
            if not isinstance(s.get("data"), list):
                s["data"] = []
            clean_series.append(s)
        opt["series"] = clean_series

    # tooltip: must be object
    if isinstance(opt.get("tooltip"), str):
        opt["tooltip"] = {"trigger": "axis"}

    # legend: must be object
    if isinstance(opt.get("legend"), str):
        opt["legend"] = {"data": [opt["legend"]]}

    return opt


async def run_agent(
    file_path: str,
    user_requirement: str,
) -> AsyncGenerator[str, None]:
    """
    Run the agent loop and yield SSE-formatted events.

    Yields:
        SSE-formatted event strings
    """
    messages = build_messages(file_path, user_requirement)
    step = 0

    while step < config.max_steps:
        step += 1
        logger.info(f"Agent step {step}/{config.max_steps}")

        # Fresh parser for each step
        parser = ProtocolParser()

        # Yield step start event
        yield create_sse_event(EventType.THINKING, {"step": step, "status": "start"})

        # Stream LLM response
        full_response = ""
        code_blocks = []
        finished = False
        has_output = False  # Track if any non-thinking event was emitted

        async for chunk in stream_chat_completion(messages):
            full_response += chunk

            for event in parser.feed(chunk):
                sse = _handle_event(event, code_blocks)
                if sse:
                    yield sse
                    has_output = True
                if event.type == EventType.FINISH:
                    finished = True
                if event.type != EventType.THINKING:
                    has_output = True

        # Flush remaining content
        for event in parser.flush():
            sse = _handle_event(event, code_blocks)
            if sse:
                yield sse
                has_output = True
            if event.type == EventType.FINISH:
                finished = True

        if finished:
            logger.info("Agent finished with FINISH tag")
            yield create_sse_event(EventType.DONE, {"status": "finished", "steps": step})
            return

        # Execute any code blocks that were collected
        if code_blocks:
            for i, code in enumerate(code_blocks):
                yield create_sse_event(EventType.CODE, {
                    "content": code,
                    "language": "python",
                    "step": step,
                    "index": i,
                })

                result = await asyncio.to_thread(
                    run_python_code,
                    code=code,
                    file_path=file_path,
                    timeout=config.code_timeout,
                )

                yield create_sse_event(EventType.CODE_OUTPUT, {
                    "stdout": result["stdout"][:2000],
                    "stderr": result["stderr"][:1000],
                    "error": result["error"],
                    "success": result["success"],
                    "index": i,
                })

            # Add assistant message + tool results once per step
            messages.append({"role": "assistant", "content": full_response})
            for i, code in enumerate(code_blocks):
                # Note: result from the last execution loop iteration
                pass

            # Rebuild feedback from last code result (or aggregate)
            tool_feedback = _format_tool_feedback(result)
            messages.append({"role": "user", "content": tool_feedback})
            continue

        # No code blocks — add response and nudge
        messages.append({"role": "assistant", "content": full_response})

        if not full_response.strip():
            messages.append({
                "role": "user",
                "content": "你没有输出任何内容。请使用 <<<CODE>>> 标签编写代码。",
            })
        elif not has_output or "<<<" not in full_response:
            messages.append({
                "role": "user",
                "content": (
                    "请立即行动！不要再只输出思考，直接执行：\n"
                    "1. 用 <<<CODE>>> 编写 Python 代码处理数据\n"
                    "2. 用 <<<CHART>>> 生成 ECharts 图表（JSON 格式，不要用函数）\n"
                    "3. 用 <<<MARKDOWN>>> 写分析结论\n"
                    "4. 分析完毕用 <<<FINISH>>> 结束\n"
                    "现在就开始写代码！"
                ),
            })

    # Max steps reached
    logger.warning(f"Agent reached max steps ({config.max_steps})")
    yield create_sse_event(EventType.FINISH, {
        "content": f"分析已达到最大步数限制（{config.max_steps}步）。以下是已生成的分析结果。",
    })
    yield create_sse_event(EventType.DONE, {"status": "max_steps", "steps": step})


def _handle_event(
    event: StreamEvent,
    code_blocks: list[str],
) -> str | None:
    """Handle a parsed stream event. Returns SSE string or None."""
    if event.type == EventType.RAW:
        return None

    if event.type == EventType.CODE:
        code_blocks.append(event.content)
        return None

    if event.type == EventType.THINKING:
        return create_sse_event(EventType.THINKING, {"content": event.content})

    if event.type == EventType.PLAN:
        return create_sse_event(EventType.PLAN, {"content": event.content})

    if event.type == EventType.CHART:
        chart_data = _parse_chart_json(event.content)
        if chart_data is not None:
            return create_sse_event(EventType.CHART, chart_data)
        else:
            return create_sse_event(EventType.MARKDOWN, {
                "content": f"（图表配置解析失败，以下为原始配置）\n```json\n{event.content[:800]}\n```"
            })

    if event.type == EventType.MARKDOWN:
        return create_sse_event(EventType.MARKDOWN, {"content": event.content})

    if event.type == EventType.MERMAID:
        return create_sse_event(EventType.MERMAID, {"content": event.content})

    if event.type == EventType.FINISH:
        return create_sse_event(EventType.FINISH, {"content": event.content})

    return None


def _format_tool_feedback(result: dict) -> str:
    """Format code execution result as tool feedback for the LLM."""
    parts = ["代码执行完毕，结果如下："]
    if result["stdout"]:
        parts.append(f"stdout:\n{result['stdout'][:3000]}")
    if result["stderr"]:
        parts.append(f"stderr:\n{result['stderr'][:1000]}")
    if result["error"]:
        parts.append(f"error:\n{result['error']}")
    if not result["stdout"] and not result["stderr"] and not result["error"]:
        parts.append("（执行成功，无输出）")
    parts.append("\n请根据结果继续分析。用 <<<MARKDOWN>>> 写分析结论，用 <<<CHART>>> 生成图表，分析完成后用 <<<FINISH>>> 总结。")
    return "\n".join(parts)