"""
OpenAI-compatible LLM client with streaming support.
"""

import json
from typing import AsyncGenerator

from openai import AsyncOpenAI

from config import config


def get_client() -> AsyncOpenAI:
    """Create an async OpenAI client with configured settings."""
    return AsyncOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=300.0,  # 5 minutes timeout
        max_retries=2,
    )


async def stream_chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    Stream a chat completion from the LLM.

    Args:
        messages: Chat messages in OpenAI format
        model: Model name (defaults to config.model)
        temperature: Sampling temperature

    Yields:
        Text chunks as they arrive
    """
    client = get_client()
    model = model or config.model

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
            timeout=300.0,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # Capture content (and reasoning_content if the model uses it)
            if delta and getattr(delta, "content", None):
                yield delta.content

    except Exception as e:
        yield f"\n\n<<<THINKING>>>\nLLM 调用出错: {str(e)}\n<<<END_THINKING>>>"
        yield f"\n\n<<<FINISH>>>\n抱歉，LLM 服务出现错误: {str(e)}。请检查 API 配置后重试。<<<END_FINISH>>>"