"""单 Provider 调用模块

提供 chat_completion_single 函数，执行单次非流式聊天补全。
"""


async def chat_completion_single(
    client,
    model_config,
    messages: list[dict],
    **kwargs,
) -> dict:
    """单 provider 调用

    Args:
        client: AsyncOpenAI 实例
        model_config: 模型配置
        messages: 消息列表
        **kwargs: 其他参数

    Returns:
        响应字典
    """
    # 清理空 tools 数组（部分 API 不允许空数组）
    tools = kwargs.get("tools")
    if not tools:
        kwargs.pop("tools", None)

    response = await client.chat.completions.create(
        model=model_config.id,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=model_config.maxTokens,
        **kwargs,
    )
    return response.model_dump()