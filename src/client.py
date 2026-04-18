import os
from typing import List, Dict, AsyncGenerator, Any
from openai import AsyncOpenAI
from models import load_config, FullConfig, ProviderConfig, ModelConfig
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class LLMGateway:
    """通用 LLM 网关"""
    
    def __init__(self, config_path: str):
        self.config: FullConfig = load_config(config_path)
        self.clients: Dict[str, AsyncOpenAI] = {}
        self._init_clients()
    
    def _init_clients(self):
        """为每个 provider 初始化客户端"""
        for provider_id, provider_cfg in self.config.models.items():
            if provider_cfg.api == "openai-completions":
                api_key = self._resolve_api_key(provider_cfg.apiKey)
                self.clients[provider_id] = AsyncOpenAI(
                    base_url=provider_cfg.baseUrl,
                    api_key=api_key
                )
    
    def _resolve_api_key(self, api_key: str) -> str:
        """解析 API Key,支持环境变量引用"""
        if api_key.startswith("${") and api_key.endswith("}"):
            env_var = api_key[2:-1]
            return os.environ.get(env_var, "")
        return api_key
    
    def get_client(self, model_id: str) -> AsyncOpenAI:
        """根据 model_id 获取客户端
        
        Args:
            model_id: "bailian/qwen3.6-plus"
        Returns:
            AsyncOpenAI 实例
        """
        provider_id = model_id.split('/')[0]
        if provider_id not in self.clients:
            raise ValueError(f"Unknown provider: {provider_id}")
        return self.clients[provider_id]
    
    def get_model_config(self, model_id: str) -> ModelConfig:
        """获取模型详细配置"""
        provider_id, model_name = model_id.split('/', 1)
        provider = self.config.models[provider_id]
        for model in provider.models:
            if model.id == model_name:
                return model
        raise ValueError(f"Unknown model: {model_id}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception) # Placeholder for specific network errors
    )
    async def chat_completion(
        self, 
        model_id: str, 
        messages: List[Dict],
        **kwargs
    ) -> Dict:
        """非流式聊天补全"""
        client = self.get_client(model_id)
        model_config = self.get_model_config(model_id)
        
        response = await client.chat.completions.create(
            model=model_config.id,
            messages=messages,
            max_tokens=model_config.maxTokens,
            **kwargs
        )
        return response.model_dump()
    
    async def stream_chat_completion(
        self,
        model_id: str,
        messages: List[Dict],
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """流式聊天补全"""
        client = self.get_client(model_id)
        model_config = self.get_model_config(model_id)
        
        stream = await client.chat.completions.create(
            model=model_config.id,
            messages=messages,
            stream=True,
            max_tokens=model_config.maxTokens,
            **kwargs
        )
        
        async for chunk in stream:
            yield chunk.model_dump()