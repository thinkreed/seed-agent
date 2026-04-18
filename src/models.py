
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationError
from typing import List, Dict, Optional
import json
import sys

class ModelConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str
    name: str
    contextWindow: int = 100000
    maxTokens: int = 4096
    compat: Optional[Dict] = None

class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    baseUrl: str
    apiKey: str
    api: str = "openai-completions"
    models: List[ModelConfig]

    @field_validator('apiKey', 'baseUrl')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if v else v

class AgentModelConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    primary: str

class AgentConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    defaults: AgentModelConfig

class FullConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    models: Dict[str, ProviderConfig]
    agents: Dict[str, AgentConfig]

def load_config(config_path: str) -> FullConfig:
    """加载并解析配置文件，支持旧版 JSON 结构自动迁移"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to load config file {config_path}: {e}")

    # 迁移逻辑: 适配旧版 JSON 结构
    # 1. 处理 models.providers -> models
    if 'models' in data and isinstance(data['models'], dict) and 'providers' in data['models']:
        data['models'] = data['models']['providers']

    # 2. 处理 agents.defaults.model -> agents.defaults.defaults
    if 'agents' in data and isinstance(data['agents'], dict):
        agent_section = data['agents']
        if 'defaults' in agent_section and isinstance(agent_section['defaults'], dict):
            defaults = agent_section['defaults']
            if 'model' in defaults:
                # 将 {"defaults": {"model": "..."}} 转换为 {"defaults": {"primary": "..."}}
                agent_section['defaults'] = {
                    'defaults': {'primary': defaults['model']}
                }

    try:
        return FullConfig(**data)
    except ValidationError as e:
        raise
