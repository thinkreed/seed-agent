from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional
import json

class ModelConfig(BaseModel):
    """单个模型配置：仅 id 和 name 为必填，忽略多余字段以兼容不同格式"""
    model_config = ConfigDict(extra='ignore')
    id: str                           # "qwen3.6-plus"
    name: str                         # "qwen3.6-plus"
    contextWindow: int = 100000       # 上下文窗口大小
    maxTokens: int = 4096             # 最大输出 tokens
    compat: Optional[Dict] = None     # 兼容性配置 (如 thinkingFormat: "qwen")

class ProviderConfig(BaseModel):
    """模型提供商配置"""
    baseUrl: str                      # "https://coding.dashscope.aliyuncs.com/v1"
    apiKey: str                       # API Key 或环境变量引用
    api: str = "openai-completions"   # 协议类型
    models: List[ModelConfig]         # 该提供商下的模型列表

class AgentModelConfig(BaseModel):
    """Agent 默认模型配置"""
    primary: str                      # "bailian/qwen3.6-plus"

class AgentConfig(BaseModel):
    """Agent 配置"""
    defaults: AgentModelConfig

class FullConfig(BaseModel):
    """完整配置"""
    models: Dict[str, ProviderConfig]  # provider_id -> ProviderConfig
    agents: Dict[str, AgentConfig]     # "defaults" -> AgentConfig

def load_config(config_path: str) -> FullConfig:
    """从 JSON 文件加载配置"""
    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 适配 config.json 结构: models.providers -> models
    if 'models' in data and 'providers' in data['models']:
        data['models'] = data['models']['providers']

    # 适配 config.json 结构: agents.defaults.model -> agents.defaults.defaults
    if 'agents' in data and 'defaults' in data['agents']:
        agent_defaults = data['agents']['defaults']
        if 'model' in agent_defaults:
            # 构造 FullConfig 期望的结构: agents -> {"defaults": {"defaults": {...}}}
            data['agents'] = {
                'defaults': {
                    'defaults': agent_defaults['model']
                }
            }

    return FullConfig(**data)