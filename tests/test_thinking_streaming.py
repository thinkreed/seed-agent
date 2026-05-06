"""
Tests for thinking/reasoning content streaming support

Coverage targets:
- StreamChunkType.THINKING type
- Thinking content extraction from delta
- Embedded thinking tag parsing
- StreamExecutor thinking handling
- main.py thinking display logic
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from harness._streaming_types import StreamChunkType, IterationResult
from client._streaming import _parse_embedded_thinking


class TestStreamChunkType:
    """Test StreamChunkType constants"""

    def test_thinking_type_exists(self):
        """Test THINKING type is defined"""
        assert hasattr(StreamChunkType, 'THINKING')
        assert StreamChunkType.THINKING == "thinking"

    def test_chunk_types_order(self):
        """Test chunk types are correctly defined"""
        # THINKING should be first (for display ordering)
        types = [
            StreamChunkType.THINKING,
            StreamChunkType.CHUNK,
            StreamChunkType.TOOL_START,
            StreamChunkType.TOOL_END,
            StreamChunkType.AWAITING_USER_INPUT,
            StreamChunkType.CANCELLED,
            StreamChunkType.FINAL,
            StreamChunkType.ERROR,
        ]
        expected = ["thinking", "chunk", "tool_start", "tool_end",
                    "awaiting_user_input", "cancelled", "final", "error"]
        assert [t for t in types] == expected


class TestIterationResult:
    """Test IterationResult TypedDict"""

    def test_iteration_result_has_thinking(self):
        """Test IterationResult includes full_thinking field"""
        result: IterationResult = {
            "full_content": "response text",
            "full_thinking": "thinking process",
            "tool_calls": [],
            "duration_ms": 100.0,
        }
        assert result["full_thinking"] == "thinking process"

    def test_iteration_result_empty_thinking(self):
        """Test IterationResult with empty thinking"""
        result: IterationResult = {
            "full_content": "response",
            "full_thinking": "",
            "tool_calls": [],
            "duration_ms": 50.0,
        }
        assert result["full_thinking"] == ""


class TestParseEmbeddedThinking:
    """Test embedded thinking tag parsing"""

    def test_parse_thinking_tag(self):
        """Test parsing <thinking> tag"""
        content = "<thinking>Let me analyze this...</thinking>The answer is 42."
        thinking, remaining = _parse_embedded_thinking(content)
        assert thinking == "Let me analyze this..."
        assert remaining == "The answer is 42."

    def test_parse_no_thinking_tag(self):
        """Test content without thinking tag"""
        content = "Just a regular response without thinking."
        thinking, remaining = _parse_embedded_thinking(content)
        assert thinking is None
        assert remaining == content

    def test_parse_empty_thinking_tag(self):
        """Test empty thinking tag"""
        content = "<thinking></thinking>Response here."
        thinking, remaining = _parse_embedded_thinking(content)
        # Empty thinking should return None (after strip)
        assert thinking is None or thinking == ""
        assert remaining == "Response here."

    def test_parse_multiple_thinking_tags(self):
        """Test multiple thinking tags (only first is parsed)"""
        content = "<thinking>First thought</thinking>middle<thinking>Second thought</thinking>end"
        thinking, remaining = _parse_embedded_thinking(content)
        # Only first match is extracted
        assert thinking == "First thought"
        assert "middle" in remaining

    def test_parse_multiline_thinking(self):
        """Test multiline thinking content"""
        content = "<thinking>\nLine 1\nLine 2\n</thinking>Response"
        thinking, remaining = _parse_embedded_thinking(content)
        assert "Line 1" in thinking
        assert "Line 2" in thinking
        assert remaining == "Response"


class TestStreamingExecutor:
    """Test StreamingExecutor thinking handling"""

    @pytest.mark.asyncio
    async def test_execute_iteration_with_thinking_chunk(self):
        """Test execute_iteration handles thinking type chunks"""
        from harness._streaming_executor import execute_iteration

        # Mock LLMClient that yields thinking chunks
        mock_llm_client = MagicMock()
        async def mock_stream(*args, **kwargs):
            # Yield thinking chunk
            yield {"type": "thinking", "content": "Analyzing..."}
            # Yield content chunk
            yield {"type": "content", "content": "Answer"}
            # Yield iteration result marker
            yield {"_iteration_result": True, "full_content": "", "full_thinking": "", "tool_calls": [], "duration_ms": 0}

        mock_llm_client.stream_reason = mock_stream

        chunks = []
        async for chunk in execute_iteration(mock_llm_client, [], [], 0):
            if not chunk.get("_iteration_result"):
                chunks.append(chunk)

        # Should have thinking and content chunks
        thinking_chunks = [c for c in chunks if c.get("type") == StreamChunkType.THINKING]
        content_chunks = [c for c in chunks if c.get("type") == StreamChunkType.CHUNK]

        assert len(thinking_chunks) == 1
        assert len(content_chunks) == 1
        assert thinking_chunks[0]["content"] == "Analyzing..."

    @pytest.mark.asyncio
    async def test_execute_iteration_with_delta_thinking(self):
        """Test execute_iteration handles thinking field in delta"""
        from harness._streaming_executor import execute_iteration

        mock_llm_client = MagicMock()
        async def mock_stream(*args, **kwargs):
            # Yield OpenAI-style chunk with thinking field
            yield {
                "choices": [{
                    "delta": {
                        "thinking": "Thought process",
                        "content": ""
                    }
                }]
            }
            yield {
                "choices": [{
                    "delta": {
                        "content": "Final answer"
                    }
                }]
            }
            yield {"_iteration_result": True, "full_content": "", "full_thinking": "", "tool_calls": [], "duration_ms": 0}

        mock_llm_client.stream_reason = mock_stream

        chunks = []
        async for chunk in execute_iteration(mock_llm_client, [], [], 0):
            if not chunk.get("_iteration_result"):
                chunks.append(chunk)

        thinking_chunks = [c for c in chunks if c.get("type") == StreamChunkType.THINKING]
        assert len(thinking_chunks) == 1
        assert thinking_chunks[0]["content"] == "Thought process"

    @pytest.mark.asyncio
    async def test_execute_iteration_with_reasoning_content(self):
        """Test execute_iteration handles reasoning_content field"""
        from harness._streaming_executor import execute_iteration

        mock_llm_client = MagicMock()
        async def mock_stream(*args, **kwargs):
            # Yield OpenAI o-series style chunk
            yield {
                "choices": [{
                    "delta": {
                        "reasoning_content": "Deep reasoning",
                        "content": ""
                    }
                }]
            }
            yield {
                "choices": [{
                    "delta": {
                        "content": "Response"
                    }
                }]
            }
            yield {"_iteration_result": True, "full_content": "", "full_thinking": "", "tool_calls": [], "duration_ms": 0}

        mock_llm_client.stream_reason = mock_stream

        chunks = []
        async for chunk in execute_iteration(mock_llm_client, [], [], 0):
            if not chunk.get("_iteration_result"):
                chunks.append(chunk)

        thinking_chunks = [c for c in chunks if c.get("type") == StreamChunkType.THINKING]
        assert len(thinking_chunks) == 1
        assert thinking_chunks[0]["content"] == "Deep reasoning"


class TestHookPointUsage:
    """Test that HookPoint enum is used correctly"""

    def test_hook_point_response_after(self):
        """Test RESPONSE_AFTER enum value"""
        from lifecycle_hooks import HookPoint
        assert HookPoint.RESPONSE_AFTER.value == "response_after"

    def test_hook_point_session_end(self):
        """Test SESSION_END enum value"""
        from lifecycle_hooks import HookPoint
        assert HookPoint.SESSION_END.value == "session_end"

    @pytest.mark.asyncio
    async def test_trigger_hook_with_enum(self):
        """Test trigger_hook accepts HookPoint enum"""
        from lifecycle_hooks import LifecycleHookRegistry, HookPoint
        from harness._lifecycle_hooks import trigger_hook, build_response_after_ctx

        registry = LifecycleHookRegistry()

        # Register a test hook
        call_count = 0
        def test_hook(ctx):
            nonlocal call_count
            call_count += 1

        registry.register(HookPoint.RESPONSE_AFTER, test_hook, name="test_hook")

        # Create mock context components
        mock_session = MagicMock()
        mock_harness = MagicMock()
        mock_response = {"choices": [{"message": {"content": "test"}}]}

        context = build_response_after_ctx(mock_session, mock_harness, mock_response, False)

        await trigger_hook(registry, HookPoint.RESPONSE_AFTER, context)

        assert call_count == 1