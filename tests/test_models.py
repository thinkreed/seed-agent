"""数据模型与配置加载模块单元测试

测试覆盖:
- RateLimitConfig: 限流配置模型、速率计算、窗口参数
- ModelConfig: 模型参数模型
- ProviderConfig: 提供商配置、空白字符剥离
- AgentModelConfig / AgentConfig: Agent 配置嵌套
- QueueConfigModel: 队列配置（TurnTicket 模式）
- TimeoutConfigModel: 超时配置
- FullConfig: 完整配置聚合
- load_config: 配置文件加载、旧版迁移、错误处理
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from models import (  # noqa: E402
    RateLimitConfig,
    ModelConfig,
    ProviderConfig,
    AgentModelConfig,
    AgentConfig,
    QueueConfigModel,
    TimeoutConfigModel,
    FullConfig,
    load_config,
    DEFAULT_CONFIG_PATH,
)


class TestRateLimitConfig(unittest.TestCase):
    """测试限流配置模型"""

    def test_default_values(self):
        """测试默认值"""
        config = RateLimitConfig()
        self.assertEqual(config.burstCapacity, 100)
        self.assertEqual(config.maxConcurrent, 3)
        self.assertEqual(config.queueMaxSize, 50)
        self.assertEqual(config.queueBackpressureThreshold, 0.8)
        self.assertIsNone(config.rpm)
        self.assertIsNone(config.rollingWindowRequests)
        self.assertIsNone(config.rollingWindowDuration)

    def test_get_effective_rate_rpm_mode(self):
        """测试 RPM 模式下的速率计算"""
        config = RateLimitConfig(rpm=60)
        self.assertEqual(config.get_effective_rate(), 1.0)  # 60/60 = 1.0 req/s

    def test_get_effective_rate_rolling_window_mode(self):
        """测试滚动窗口模式下的速率计算"""
        config = RateLimitConfig(rollingWindowRequests=6000, rollingWindowDuration=18000)
        self.assertAlmostEqual(config.get_effective_rate(), 6000 / 18000, places=4)

    def test_get_effective_rate_default(self):
        """测试无配置时的默认速率"""
        config = RateLimitConfig()
        self.assertAlmostEqual(config.get_effective_rate(), 6000 / 18000, places=4)

    def test_get_window_limit_rolling(self):
        """测试滚动窗口请求上限"""
        config = RateLimitConfig(rollingWindowRequests=5000)
        self.assertEqual(config.get_window_limit(), 5000)

    def test_get_window_limit_from_rpm(self):
        """测试从 RPM 推算窗口上限"""
        config = RateLimitConfig(rpm=20)
        self.assertEqual(config.get_window_limit(), 20 * 300)  # 20 * 300 = 6000

    def test_get_window_limit_default(self):
        """测试默认窗口上限"""
        config = RateLimitConfig()
        self.assertEqual(config.get_window_limit(), 6000)

    def test_get_window_duration_explicit(self):
        """测试显式窗口时长"""
        config = RateLimitConfig(rollingWindowDuration=3600)
        self.assertEqual(config.get_window_duration(), 3600.0)

    def test_get_window_duration_default(self):
        """测试默认窗口时长"""
        config = RateLimitConfig()
        self.assertEqual(config.get_window_duration(), 18000.0)

    def test_extra_fields_ignored(self):
        """测试额外字段被忽略"""
        data = {
            "burstCapacity": 50,
            "unknownField": "should_be_ignored",
            "anotherUnknown": 123,
        }
        config = RateLimitConfig(**data)
        self.assertEqual(config.burstCapacity, 50)


class TestModelConfig(unittest.TestCase):
    """测试模型配置"""

    def test_default_values(self):
        """测试默认值"""
        config = ModelConfig(id="qwen-max", name="Qwen Max")
        self.assertEqual(config.id, "qwen-max")
        self.assertEqual(config.name, "Qwen Max")
        self.assertEqual(config.contextWindow, 100000)
        self.assertEqual(config.maxTokens, 4096)
        self.assertIsNone(config.compat)

    def test_custom_values(self):
        """测试自定义值"""
        config = ModelConfig(
            id="gpt-4",
            name="GPT-4",
            contextWindow=128000,
            maxTokens=8192,
            compat={"temperature": 0.7},
        )
        self.assertEqual(config.id, "gpt-4")
        self.assertEqual(config.contextWindow, 128000)
        self.assertEqual(config.maxTokens, 8192)
        self.assertEqual(config.compat["temperature"], 0.7)

    def test_extra_fields_ignored(self):
        """测试额外字段被忽略"""
        config = ModelConfig(id="test", name="Test", unknown="value")
        self.assertEqual(config.id, "test")


class TestProviderConfig(unittest.TestCase):
    """测试提供商配置"""

    def _make_provider(self, **kwargs):
        """Helper to create a ProviderConfig"""
        defaults = {
            "baseUrl": "https://api.example.com",
            "apiKey": "test-key-123",
            "models": [ModelConfig(id="test-model", name="Test Model")],
        }
        defaults.update(kwargs)
        return ProviderConfig(**defaults)

    def test_default_api(self):
        """测试默认 API 类型"""
        provider = self._make_provider()
        self.assertEqual(provider.api, "openai-completions")

    def test_strip_whitespace_apiKey(self):
        """测试 apiKey 空白字符剥离"""
        provider = self._make_provider(apiKey="  test-key  ")
        self.assertEqual(provider.apiKey, "test-key")

    def test_strip_whitespace_baseUrl(self):
        """测试 baseUrl 空白字符剥离"""
        provider = self._make_provider(baseUrl="  https://api.example.com  ")
        self.assertEqual(provider.baseUrl, "https://api.example.com")

    def test_custom_api_type(self):
        """测试自定义 API 类型"""
        provider = self._make_provider(api="anthropic-messages")
        self.assertEqual(provider.api, "anthropic-messages")

    def test_with_rate_limit(self):
        """测试带限流配置"""
        rl = RateLimitConfig(rpm=100)
        provider = self._make_provider(rateLimit=rl)
        self.assertEqual(provider.rateLimit.rpm, 100)

    def test_no_rate_limit(self):
        """测试无限流配置"""
        provider = self._make_provider()
        self.assertIsNone(provider.rateLimit)


class TestAgentConfig(unittest.TestCase):
    """测试 Agent 配置"""

    def test_agent_model_config(self):
        """测试 AgentModelConfig"""
        config = AgentModelConfig(primary="qwen-max")
        self.assertEqual(config.primary, "qwen-max")

    def test_agent_config(self):
        """测试 AgentConfig 嵌套结构"""
        config = AgentConfig(defaults=AgentModelConfig(primary="gpt-4"))
        self.assertEqual(config.defaults.primary, "gpt-4")


class TestQueueConfigModel(unittest.TestCase):
    """测试队列配置模型"""

    def test_default_critical_queue(self):
        """测试 CRITICAL 队列默认值"""
        config = QueueConfigModel()
        self.assertEqual(config.critical_max_size, 10)
        self.assertEqual(config.critical_backpressure_threshold, 0.9)
        self.assertEqual(config.critical_dispatch_rate, 10.0)
        self.assertEqual(config.critical_target_wait_time, 5.0)

    def test_default_normal_queue(self):
        """测试普通队列默认值"""
        config = QueueConfigModel()
        self.assertEqual(config.normal_max_size, 50)
        self.assertEqual(config.normal_backpressure_threshold, 0.8)
        self.assertEqual(config.normal_dispatch_rate, 0.33)
        self.assertEqual(config.normal_target_wait_time, 30.0)

    def test_auto_adjust(self):
        """测试自动调整配置"""
        config = QueueConfigModel()
        self.assertTrue(config.auto_adjust_enabled)
        self.assertEqual(config.adjust_interval, 60.0)

    def test_custom_values(self):
        """测试自定义值"""
        config = QueueConfigModel(
            critical_max_size=20,
            normal_max_size=100,
            auto_adjust_enabled=False,
        )
        self.assertEqual(config.critical_max_size, 20)
        self.assertEqual(config.normal_max_size, 100)
        self.assertFalse(config.auto_adjust_enabled)


class TestTimeoutConfigModel(unittest.TestCase):
    """测试超时配置模型"""

    def test_default_timeouts(self):
        """测试默认超时值"""
        config = TimeoutConfigModel()
        self.assertEqual(config.critical_base_timeout, 30.0)
        self.assertEqual(config.high_base_timeout, 60.0)
        self.assertEqual(config.normal_base_timeout, 120.0)
        self.assertEqual(config.low_base_timeout, 300.0)

    def test_dynamic_adjustment(self):
        """测试动态调整配置"""
        config = TimeoutConfigModel()
        self.assertTrue(config.auto_adjust_enabled)
        self.assertEqual(config.load_factor_threshold, 0.7)
        self.assertEqual(config.min_multiplier, 0.5)
        self.assertEqual(config.max_multiplier, 2.0)

    def test_custom_timeouts(self):
        """测试自定义超时值"""
        config = TimeoutConfigModel(
            critical_base_timeout=60.0,
            low_base_timeout=600.0,
            auto_adjust_enabled=False,
        )
        self.assertEqual(config.critical_base_timeout, 60.0)
        self.assertEqual(config.low_base_timeout, 600.0)
        self.assertFalse(config.auto_adjust_enabled)


class TestFullConfig(unittest.TestCase):
    """测试完整配置"""

    def _make_full_config_data(self):
        """Helper to create a full config data dict"""
        return {
            "models": {
                "dashscope": {
                    "baseUrl": "https://dashscope.aliyuncs.com",
                    "apiKey": "test-key",
                    "models": [
                        {"id": "qwen-max", "name": "Qwen Max"}
                    ],
                }
            },
            "agents": {
                "defaults": {
                    "defaults": {
                        "primary": "qwen-max"
                    }
                }
            },
        }

    def test_basic_full_config(self):
        """测试基本完整配置"""
        data = self._make_full_config_data()
        config = FullConfig(**data)
        self.assertIn("dashscope", config.models)
        self.assertEqual(config.models["dashscope"].apiKey, "test-key")

    def test_full_config_with_queue_and_timeout(self):
        """测试带队列和超时的完整配置"""
        data = self._make_full_config_data()
        data["queue"] = {"critical_max_size": 20}
        data["timeout"] = {"critical_base_timeout": 60.0}
        config = FullConfig(**data)
        self.assertIsNotNone(config.queue)
        self.assertEqual(config.queue.critical_max_size, 20)
        self.assertIsNotNone(config.timeout)
        self.assertEqual(config.timeout.critical_base_timeout, 60.0)

    def test_full_config_without_queue(self):
        """测试无队列配置"""
        data = self._make_full_config_data()
        config = FullConfig(**data)
        self.assertIsNone(config.queue)
        self.assertIsNone(config.timeout)

    def test_extra_fields_ignored(self):
        """测试额外字段被忽略"""
        data = self._make_full_config_data()
        data["unknown_section"] = {"foo": "bar"}
        config = FullConfig(**data)
        self.assertNotIn("unknown_section", config.model_dump())


class TestLoadConfig(unittest.TestCase):
    """测试配置文件加载"""

    def _write_config(self, data, path=None):
        """Helper to write config to temp file"""
        if path is None:
            fd, path = tempfile.mkstemp(suffix='.json')
            os.close(fd)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        return path

    def test_load_valid_config(self):
        """测试加载有效配置"""
        data = {
            "models": {
                "dashscope": {
                    "baseUrl": "https://dashscope.aliyuncs.com",
                    "apiKey": "test-key",
                    "models": [{"id": "qwen-max", "name": "Qwen Max"}],
                }
            },
            "agents": {
                "defaults": {
                    "defaults": {"primary": "qwen-max"}
                }
            },
        }
        path = self._write_config(data)
        try:
            config = load_config(path)
            self.assertIsInstance(config, FullConfig)
            self.assertIn("dashscope", config.models)
        finally:
            os.unlink(path)

    def test_load_file_not_found(self):
        """测试文件不存在时抛出异常"""
        with self.assertRaises(ValueError) as ctx:
            load_config("/nonexistent/path/config.json")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_load_invalid_json(self):
        """测试无效 JSON 时抛出异常"""
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        with open(path, 'w') as f:
            f.write("{invalid json}")
        try:
            with self.assertRaises(ValueError):
                load_config(path)
        finally:
            os.unlink(path)

    def test_migration_old_models_providers(self):
        """测试旧版 models.providers 迁移"""
        data = {
            "models": {
                "providers": {
                    "dashscope": {
                        "baseUrl": "https://dashscope.aliyuncs.com",
                        "apiKey": "test-key",
                        "models": [{"id": "qwen-max", "name": "Qwen Max"}],
                    }
                }
            },
            "agents": {
                "defaults": {
                    "defaults": {"primary": "qwen-max"}
                }
            },
        }
        path = self._write_config(data)
        try:
            config = load_config(path)
            self.assertIn("dashscope", config.models)
            # 'providers' key should be gone
            self.assertNotIn("providers", config.models)
        finally:
            os.unlink(path)

    def test_migration_old_agent_model_format(self):
        """测试旧版 agents.defaults.model 迁移"""
        data = {
            "models": {
                "dashscope": {
                    "baseUrl": "https://dashscope.aliyuncs.com",
                    "apiKey": "test-key",
                    "models": [{"id": "qwen-max", "name": "Qwen Max"}],
                }
            },
            "agents": {
                "defaults": {
                    "model": "qwen-max"
                }
            },
        }
        path = self._write_config(data)
        try:
            config = load_config(path)
            self.assertEqual(config.agents["defaults"].defaults.primary, "qwen-max")
        finally:
            os.unlink(path)

    def test_migration_semi_migrated_agent_format(self):
        """测试半迁移格式 agents.defaults.primary → 嵌套"""
        data = {
            "models": {
                "dashscope": {
                    "baseUrl": "https://dashscope.aliyuncs.com",
                    "apiKey": "test-key",
                    "models": [{"id": "qwen-max", "name": "Qwen Max"}],
                }
            },
            "agents": {
                "defaults": {
                    "primary": "qwen-max"
                }
            },
        }
        path = self._write_config(data)
        try:
            config = load_config(path)
            self.assertEqual(config.agents["defaults"].defaults.primary, "qwen-max")
        finally:
            os.unlink(path)

    def test_migration_idempotent(self):
        """测试迁移幂等性（已迁移格式不应被再次修改）"""
        data = {
            "models": {
                "dashscope": {
                    "baseUrl": "https://dashscope.aliyuncs.com",
                    "apiKey": "test-key",
                    "models": [{"id": "qwen-max", "name": "Qwen Max"}],
                }
            },
            "agents": {
                "defaults": {
                    "defaults": {"primary": "qwen-max"}
                }
            },
        }
        path = self._write_config(data)
        try:
            config = load_config(path)
            self.assertEqual(config.agents["defaults"].defaults.primary, "qwen-max")
        finally:
            os.unlink(path)

    def test_default_config_path(self):
        """测试默认配置路径常量"""
        expected = os.path.join(os.path.expanduser("~"), ".seed", "config.json")
        self.assertEqual(DEFAULT_CONFIG_PATH, expected)


if __name__ == '__main__':
    unittest.main()
