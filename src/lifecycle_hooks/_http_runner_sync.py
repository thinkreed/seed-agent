"""HTTP 钩子同步执行器

Wiki 知识落地 (Qwen-Code): HTTP Hooks

用于非异步环境。
"""

import asyncio
import json
import urllib.request
import urllib.error
from typing import Any

from ._http_runner_types import HttpHookResult
from ._http_runner_async import HttpHookRunner


def execute_http_hook_sync(
    url: str,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | str | None = None,
    timeout: float = 10.0,
) -> HttpHookResult:
    """同步执行 HTTP 钩子（用于非异步环境）"""
    start_time = asyncio.get_event_loop().time()

    try:
        req_body: bytes | None = None
        if body:
            if isinstance(body, dict):
                req_body = json.dumps(body).encode("utf-8")
            else:
                req_body = str(body).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=req_body,
            headers=headers or {},
            method=method.upper(),
        )

        if req_body and "Content-Type" not in (headers or {}):
            req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_text = response.read().decode("utf-8", errors="replace")
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            return HttpHookResult(
                success=True,
                status_code=response.status,
                response_body=response_text[:HttpHookRunner.MAX_RESPONSE_SIZE],
                duration_ms=duration_ms,
            )

    except urllib.error.HTTPError as e:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        return HttpHookResult(
            success=False,
            status_code=e.code,
            duration_ms=duration_ms,
            error=f"HTTP {e.code}: {str(e)[:100]}",
        )

    except urllib.error.URLError as e:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        return HttpHookResult(
            success=False,
            duration_ms=duration_ms,
            error=f"URL error: {str(e)[:100]}",
        )

    except Exception as e:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        return HttpHookResult(
            success=False,
            duration_ms=duration_ms,
            error=f"Unexpected: {type(e).__name__}: {str(e)[:100]}",
        )


__all__ = ["execute_http_hook_sync"]