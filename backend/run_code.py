"""
Python code execution sandbox with timeout protection.
Uses thread-based timeout (compatible with asyncio.to_thread).
"""

import io
import sys
import textwrap
import threading
from typing import Any


class CodeTimeoutError(Exception):
    """Raised when code execution exceeds timeout."""


class _ThreadWithResult:
    """A thread that captures its result and exception."""

    def __init__(self, target, args=()):
        self._target = target
        self._args = args
        self.result: Any = None
        self.exception: Exception | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            self.result = self._target(*self._args)
        except Exception as e:
            self.exception = e

    def start(self):
        self._thread.start()

    def join(self, timeout: float | None = None) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()


def run_python_code(
    code: str,
    file_path: str = "",
    timeout: int = 30,
    extra_vars: dict[str, Any] | None = None,
) -> dict:
    """
    Execute Python code in a sandboxed environment.

    Args:
        code: Python code string to execute
        file_path: Path to the uploaded data file (available as `file_path` variable)
        timeout: Maximum execution time in seconds
        extra_vars: Additional variables to inject into the execution namespace

    Returns:
        dict with keys: stdout, stderr, error, success
    """
    result_box: dict[str, Any] = {
        "stdout": "",
        "stderr": "",
        "error": None,
        "success": True,
    }

    def _execute():
        # Prepare the execution namespace with common imports
        namespace: dict[str, Any] = {
            "__builtins__": __builtins__,
        }

        if file_path:
            namespace["file_path"] = file_path

        if extra_vars:
            namespace.update(extra_vars)

        # Pre-import common libraries into namespace
        for mod_name, alias in [
            ("numpy", "np"), ("pandas", "pd"), ("json", "json"),
            ("collections", "collections"), ("statistics", "statistics"),
            ("itertools", "itertools"),
        ]:
            try:
                mod = __import__(mod_name)
                namespace[alias] = mod
                namespace[mod_name] = mod
            except ImportError:
                pass

        # Capture stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        sys.stdout = stdout_buf
        sys.stderr = stderr_buf

        try:
            exec(textwrap.dedent(code), namespace)
            result_box["success"] = True
        except Exception as e:
            result_box["error"] = f"{type(e).__name__}: {e}"
            result_box["success"] = False
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            result_box["stdout"] = stdout_buf.getvalue()
            result_box["stderr"] = stderr_buf.getvalue()

    # Run in a daemon thread with timeout
    worker = _ThreadWithResult(_execute)
    worker.start()
    finished = worker.join(timeout)

    if not finished:
        result_box["success"] = False
        result_box["error"] = f"CodeTimeoutError: 代码执行超时（{timeout}秒限制）"
        result_box["stdout"] = ""

    return result_box