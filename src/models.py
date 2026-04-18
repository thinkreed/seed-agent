
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict, Optional
import json

class ModelConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str
    name: str
    contextWindow: int = 100000
    maxTokens: int = 4096
    compat: Optional[Dict] = None

class ProviderConfig(BaseModel):
    baseUrl: str
    apiKey: str
    api: str = "openai-completions"
    models: List[ModelConfig]

    @field_validator('apiKey', 'baseUrl')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if v else v

class AgentModelConfig(BaseModel):
    primary: str

class AgentConfig(BaseModel):
    defaults: AgentModelConfig

class FullConfig(BaseModel):
    models: Dict[str, ProviderConfig]
    agents: Dict[str, AgentConfig]

def load_config(config_path: str) -> FullConfig:
    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if 'models' in data and 'providers' in data['models']:
        data['models'] = data['models']['providers']

    if 'agents' in data and 'defaults' in data['agents']:
        agent_defaults = data['agents']['defaults']
        if 'model' in agent_defaults:
            data['agents'] = {
                'defaults': {
                    'defaults': agent_defaults['model']
                }
            }

    return FullConfig(**data)
