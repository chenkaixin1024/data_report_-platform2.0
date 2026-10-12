"""
Stream protocol parser.

Parses LLM streaming output that uses explicit tags (<<<TAG>>>...<<<END_TAG>>>)
into structured events. Designed to work incrementally with streaming text chunks.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Generator


class EventType(str, Enum):
    THINKING = "thinking"
    PLAN = "plan"
    CODE = "code"
    CODE_OUTPUT = "code_output"
    CHART = "chart"
    MARKDOWN = "markdown"
    MERMAID = "mermaid"
    FINISH = "finish"
    ERROR = "error"
    DONE = "done"
    RAW = "raw"


@dataclass
class StreamEvent:
    type: EventType
    content: str
    metadata: dict = field(default_factory=dict)


# Tag definitions: (tag_name, open_tag, close_tag, event_type)
TAG_DEFS = [
    ("THINKING", "<<<THINKING>>>", "<<<END_THINKING>>>", EventType.THINKING),
    ("PLAN", "<<<PLAN>>>", "<<<END_PLAN>>>", EventType.PLAN),
    ("CODE", "<<<CODE>>>", "<<<END_CODE>>>", EventType.CODE),
    ("CHART", "<<<CHART>>>", "<<<END_CHART>>>", EventType.CHART),
    ("MARKDOWN", "<<<MARKDOWN>>>", "<<<END_MARKDOWN>>>", EventType.MARKDOWN),
    ("MERMAID", "<<<MERMAID>>>", "<<<END_MERMAID>>>", EventType.MERMAID),
    ("FINISH", "<<<FINISH>>>", "<<<END_FINISH>>>", EventType.FINISH),
]

# Build regex pattern for all tags
_ALL_TAGS = []
for _, open_t, close_t, _ in TAG_DEFS:
    _ALL_TAGS.append(re.escape(open_t))
    _ALL_TAGS.append(re.escape(close_t))
TAG_PATTERN = re.compile("(" + "|".join(_ALL_TAGS) + ")")


@dataclass
class ProtocolParser:
    """
    Incremental parser for the LLM stream protocol.

    Feed text chunks via `feed()` and receive StreamEvents as complete
    blocks are detected.
    """

    _buffer: str = field(default="", init=False)
    _current_tag: str | None = field(default=None, init=False)
    _current_event_type: EventType | None = field(default=None, init=False)
    _current_content: str = field(default="", init=False)
    _text_between_tags: str = field(default="", init=False)

    def _find_tag_def(self, tag: str):
        """Find the tag definition for a given tag string."""
        for name, open_t, close_t, event_type in TAG_DEFS:
            if tag == open_t or tag == close_t:
                return (name, open_t, close_t, event_type)
        return None

    def feed(self, chunk: str) -> Generator[StreamEvent, None, None]:
        """
        Feed a text chunk and yield any complete events.

        This handles the case where a chunk may:
        - Contain multiple complete tags
        - Split a tag across chunks
        - Contain partial content
        """
        self._buffer += chunk

        while True:
            if self._current_tag is None:
                # Looking for an opening tag
                match = TAG_PATTERN.search(self._buffer)
                if not match:
                    # No tag found, keep last 20 chars in case a tag is split
                    safe_len = max(0, len(self._buffer) - 30)
                    if safe_len > 0:
                        self._text_between_tags += self._buffer[:safe_len]
                        self._buffer = self._buffer[safe_len:]
                    break

                tag_str = match.group(0)
                tag_def = self._find_tag_def(tag_str)
                if tag_def is None:
                    break

                name, open_t, close_t, event_type = tag_def

                # Check if it's an opening tag
                if tag_str == open_t:
                    # Emit any text between tags as RAW
                    before = self._buffer[: match.start()]
                    between = self._text_between_tags + before
                    self._text_between_tags = ""
                    if between.strip():
                        yield StreamEvent(type=EventType.RAW, content=between)

                    self._current_tag = close_t
                    self._current_event_type = event_type
                    self._current_content = ""
                    self._buffer = self._buffer[match.end() :]
                else:
                    # Unexpected close tag without open - skip
                    before = self._buffer[: match.end()]
                    self._text_between_tags += before
                    self._buffer = self._buffer[match.end() :]
            else:
                # Looking for the closing tag
                close_pos = self._buffer.find(self._current_tag)
                if close_pos == -1:
                    # Closing tag not found yet, accumulate content
                    # Keep last len(tag) chars in case tag is split
                    safe_len = max(0, len(self._buffer) - len(self._current_tag))
                    self._current_content += self._buffer[:safe_len]
                    self._buffer = self._buffer[safe_len:]
                    break

                # Found closing tag
                self._current_content += self._buffer[:close_pos]
                self._buffer = self._buffer[close_pos + len(self._current_tag) :]

                # Emit event
                content = self._current_content.strip()
                if self._current_event_type and content:
                    event = StreamEvent(
                        type=self._current_event_type,
                        content=content,
                    )

                    # Post-process CHART events to parse JSON
                    if self._current_event_type == EventType.CHART:
                        try:
                            chart_data = json.loads(content)
                            event.content = content
                            event.metadata = chart_data
                        except json.JSONDecodeError:
                            pass

                    yield event

                # Reset state
                self._current_tag = None
                self._current_event_type = None
                self._current_content = ""

    def flush(self) -> Generator[StreamEvent, None, None]:
        """
        Flush remaining buffer content. Call this when the stream ends.
        """
        remaining = self._text_between_tags + self._buffer
        if remaining.strip():
            yield StreamEvent(type=EventType.RAW, content=remaining)

        if self._current_tag and self._current_content:
            content = self._current_content.strip()
            if not content:
                return
            # CHART events require valid JSON — don't emit if incomplete
            if self._current_event_type == EventType.CHART:
                try:
                    json.loads(content)
                except json.JSONDecodeError:
                    # Incomplete JSON, skip
                    return
            if self._current_event_type:
                yield StreamEvent(
                    type=self._current_event_type,
                    content=content,
                )

        # Reset
        self._buffer = ""
        self._current_tag = None
        self._current_event_type = None
        self._current_content = ""
        self._text_between_tags = ""


def create_sse_event(event_type: EventType, data: dict) -> str:
    """Format a Server-Sent Event string."""
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type.value}\ndata: {json_data}\n\n"