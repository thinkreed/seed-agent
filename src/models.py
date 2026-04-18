
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationError
from typing import List, Dict, Optional
import json
import os
import sys

DEFAULT_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".seed", "config.json")

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

def load_config(config_path: str = None) -> FullConfig:
    """加载并解析配置文件，支持旧版 JSON 结构自动迁移
    
    Args:
        config_path: 配置文件路径，默认为 ~/.seed/config.json
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(
            f"Configuration file not found: {config_path}\n"
            f"Please create the file or specify a valid config path."
        )
    except Exception as e:
        raise ValueError(f"Failed to load config file {config_path}: {e}")

    # 迁移逻辑: 适配旧版 JSON 结构
    # 1. 处理 models.providers -> models
    if 'models' in data and isinstance(data['models'], dict) and 'providers' in data['models']:
        data['models'] = data['models']['providers']

    # 2. 处理 agents.defaults.model -> agents.defaults.defaults
    #    幂等迁移：已迁移过的配置不会被重复处理
    if 'agents' in data and isinstance(data['agents'], dict):
        agent_section = data['agents']
        if 'defaults' in agent_section and isinstance(agent_section['defaults'], dict):
            defaults = agent_section['defaults']
            # 旧格式: {"defaults": {"model": "..."}}
            if 'model' in defaults:
                agent_section['defaults'] = {
                    'defaults': {'primary': defaults['model']}
                }
            # 半迁移格式: {"defaults": {"primary": "..."}} → 补全嵌套
            elif 'primary' in defaults and 'defaults' not in defaults:
                agent_section['defaults'] = {
                    'defaults': {'primary': defaults['primary']}
                }
            # 已迁移格式: {"defaults": {"defaults": {"primary": "..."}}} → 无需处理

    try:
        return FullConfig(**data)
    except ValidationError as e:
        raise
