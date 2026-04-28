# Seed-Agent OpenTelemetry Observability Design

## 概述

本文档描述 Seed-Agent 的 OpenTelemetry 可观测性接入方案，聚焦核心诉求：

- **Token 消耗观测**：实时追踪 LLM 调用的 input/output tokens，按 provider/model 聚合
- **错误回溯能力**：完整调用链路追踪，支持在 Jaeger/Grafana 搜索 Error Trace 定位问题

---

## 部署架构

本地部署场景，推荐轻量级后端栈：

```
Seed-Agent ──OTLP(gRPC:4317)──> OTel Collector ──┬──> Prometheus (Metrics, :8889)
                                                ├──> Jaeger (Traces, :16686)
                                                └──> Grafana (可视化, :3000)
```

### 启动命令

```bash
# 1. Jaeger All-in-One (Traces + OTLP Receiver)
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest

# Jaeger UI: http://localhost:16686

# 2. Prometheus (Metrics)
docker run -d --name prometheus \
  -p 9090:9090 \
  -v ./prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus

# Prometheus UI: http://localhost:9090

# 3. Grafana (可视化)
docker run -d --name grafana \
  -p 3000:3000 \
  grafana/grafana

# Grafana UI: http://localhost:3000
```

### Prometheus 配置

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'otel-collector'
    scrape_interval: 15s
    static_configs:
      - targets: ['host.docker.internal:8889']
```

### OTel Collector 配置（可选，如果需要更复杂的路由）

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 10s
    send_batch_size: 100
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: errors-only
        type: status_code
        status_code: { status_codes: [ERROR] }
      - name: slow-traces
        type: latency
        latency: { threshold_ms: 5000 }

exporters:
  prometheus:
    endpoint: 0.0.0.0:8889
  otlp:
    endpoint: jaeger:4317

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [tail_sampling, batch]
      exporters: [otlp]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus]
```

---

## Metrics 设计

### LLM Token 相关 Metrics

| Metric Name | Type | Unit | Attributes | 描述 |
|-------------|------|------|------------|------|
| `seed.llm.tokens.input` | Counter | 1 | `provider`, `model` | 输入 Token 累计 |
| `seed.llm.tokens.output` | Counter | 1 | `provider`, `model` | 输出 Token 累计 |
| `seed.llm.request.duration` | Histogram | ms | `provider`, `model`, `status` (success/error) | LLM 请求耗时分布 |
| `seed.llm.request.count` | Counter | 1 | `provider`, `model`, `status` (success/error) | LLM 请求计数 |
| `seed.llm.error.count` | Counter | 1 | `provider`, `model`, `error_type` | LLM 错误分类统计 |

**Histogram Buckets（延迟分布）**：
```python
explicit_bucket_boundaries_advisory = [100, 500, 1000, 2000, 5000, 10000]  # ms
```

**错误类型分类**：
| error_type | 含义 |
|------------|------|
| `connection` | 网络连接错误 |
| `ratelimit` | 429 Rate Limit |
| `timeout` | 请求超时 |
| `api_error` | API 返回错误状态码 |
| `context_overflow` | 上下文窗口溢出 |

---

## Tracing Span 设计

### Span 层级结构

```
seed.session (Root Span)
│
├── seed.llm.request (每次 LLM 调用)
│   ├── seed.llm.retry (重试，如果有)
│   └── seed.llm.fallback (Fallback 切换，如果有)
│
├── seed.tool.{name} (工具调用)
│   ├── seed.tool.file_read
│   ├── seed.tool.file_write
│   ├── seed.tool.file_edit
│   ├── seed.tool.code_as_policy
│   └── seed.tool.memory_write
│
└── seed.subagent.execute (Subagent 执行)
```

### Span Attributes

#### `seed.llm.request`

| Attribute | 值 | 描述 |
|-----------|-----|------|
| `gen_ai.system` | `"openai"` | OTel Semantic Convention |
| `gen_ai.request.model` | model_id | 请求的模型 ID |
| `gen_ai.response.model` | actual_model | 实际响应的模型 |
| `gen_ai.usage.input_tokens` | prompt_tokens | 输入 Token 数 |
| `gen_ai.usage.output_tokens` | completion_tokens | 输出 Token 数 |
| `seed.provider` | provider_name | Provider 名称 (primary/fallback) |
| `seed.streaming` | true/false | 是否流式响应 |
| `seed.error.type` | error_type | 错误类型（仅 Error 状态） |
| `seed.error.message` | truncated_msg | 错误消息（截断至 500 字符） |

#### `seed.llm.fallback`

| Attribute | 值 | 描述 |
|-----------|-----|------|
| `seed.fallback.from` | old_provider | 原 Provider |
| `seed.fallback.to` | new_provider | 新 Provider |
| `seed.fallback.reason` | error/ratelimit/timeout | 切换原因 |
| `seed.fallback.attempt` | attempt_count | 当前尝试次数 |

#### `seed.tool.{name}`

| Attribute | 值 | 描述 |
|-----------|-----|------|
| `code.function.name` | tool_name | 工具名称 |
| `seed.tool.file_path` | path | 文件路径（文件操作工具） |
| `seed.tool.duration_ms` | duration | 执行耗时 |
| `seed.error.message` | truncated_msg | 错误消息（仅 Error 状态） |

#### `seed.subagent.execute`

| Attribute | 值 | 描述 |
|-----------|-----|------|
| `seed.subagent.type` | EXPLORE/REVIEW/IMPLEMENT/PLAN | Subagent 类型 |
| `seed.subagent.task_id` | task_id | Subagent 任务 ID |
| `seed.subagent.status` | completed/failed/timeout | 执行状态 |

---

## 错误回溯工作流

### 搜索 Error Trace

在 Jaeger UI (http://localhost:16686)：

1. **筛选条件**：
   - Service: `seed-agent`
   - Operation: `seed.llm.request`
   - Status: `Error`
   - Time Range: `Last 1h`

2. **搜索特定错误类型**：
   - Tags: `seed.error.type=ratelimit`
   - Tags: `seed.provider=primary`

### 定位问题流程

```
找到 Error Trace → 点击展开
│
├── seed.llm.request
│   ├── provider: "primary"
│   ├── model: "gpt-4o"
│   ├── seed.error.type: "ratelimit"
│   ├── seed.error.message: "Rate limit exceeded: 429..."
│   ├── gen_ai.usage.input_tokens: 5000
│   └── duration: 1200ms
│
└── seed.llm.fallback
    ├── seed.fallback.from: "primary"
    ├── seed.fallback.to: "fallback"
    ├── seed.fallback.reason: "ratelimit"
    └── seed.fallback.attempt: 2
```

**定位结论**：
- Primary Provider 触发 Rate Limit
- Fallback 成功切换
- 查看时间戳确认发生频率
- Grafana 查看 Metrics 趋势决定是否调整配置

---

## Sampling 策略

推荐 Tail Sampling（在 OTel Collector 配置）：

| Policy | 条件 | 目的 |
|--------|------|------|
| `errors-only` | Status = ERROR | 全量保留错误 Trace |
| `slow-traces` | Duration > 5s | 保留慢请求 Trace |
| `success-sampling` | Status = OK, 10% probability | 采样正常 Trace |

**理由**：
- Error Trace 是回溯核心，必须全量保留
- 慢 Trace 可能预示问题
- 正常 Trace 只需采样，节省存储

---

## 代码接入位置

### 核心埋点位置

| 组件 | 文件 | 方法/位置 | 接入方式 |
|------|------|-----------|----------|
| **LLMGateway** | `src/client.py` | `_chat_completion_with_fallback_internal()` (~line 770) | 入口 start_span，出口 record_exception if error |
| **LLMGateway** | `src/client.py` | Response parsing (~line 800) | `span.set_attribute("gen_ai.usage.input_tokens", ...)` |
| **LLMGateway** | `src/client.py` | `mark_degraded()` (~line 120) | Fallback event + span attributes |
| **AgentLoop** | `src/agent_loop.py` | `tools.execute()` (~line 458) | wrap with span, catch exception → record_exception |
| **Subagent** | `src/subagent.py` | `run()` (~line 310) | wrap with span |

### 上下文传播方案

**问题**：`asyncio.create_task()` 默认不继承 OTel context。

**解决方案（Python 3.11+）**：

```python
from opentelemetry import context

# 显式传递 context
ctx = context.get_current()
asyncio.create_task(do_work(), context=ctx)
```

**Subagent 场景特殊处理**：

Subagent 有独立 context window（设计上隔离），Tracing 上应**共享 trace_id** 但有独立 span。

```python
# 主 Agent 创建 Subagent
with tracer.start_as_current_span("seed.subagent.spawn") as spawn_span:
    trace_id = spawn_span.context.trace_id
    
    subagent = SubagentInstance(
        type=subagent_type,
        parent_trace_id=trace_id,  # 传递 trace_id
        ...
    )

# Subagent 执行时链接到 parent trace
# （不继承 parent span，但共享 trace_id）
```

---

## SDK 初始化代码骨架

### 目录结构

```
src/observability/
├── __init__.py          # 公共接口导出
├── setup.py             # SDK 初始化
├── metrics.py           # Metrics instruments 定义
├── tracing.py           # Tracing helpers（装饰器、context helpers）
└── logging_config.py    # structlog 配置（可选）
```

### 初始化代码

```python
# src/observability/setup.py
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

def setup_observability(
    service_name: str = "seed-agent",
    otlp_endpoint: str = "http://localhost:4317",
    metrics_export_interval: int = 15000
):
    """初始化 OpenTelemetry SDK"""
    
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "1.0.0",
        "deployment.environment": "local",
    })
    
    # === Traces ===
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=otlp_endpoint),
            max_queue_size=1000,
            schedule_delay_millis=5000,
        )
    )
    trace.set_tracer_provider(trace_provider)
    
    # === Metrics ===
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint),
        export_interval_millis=metrics_export_interval
    )
    metrics_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader]
    )
    metrics.set_meter_provider(metrics_provider)
    
    return trace.get_tracer(service_name), metrics.get_meter(service_name)
```

### Metrics Instruments 定义

```python
# src/observability/metrics.py
from opentelemetry import metrics

meter = metrics.get_meter("seed-agent")

# Token Counters
tokens_input_counter = meter.create_counter(
    name="seed.llm.tokens.input",
    description="Total input tokens consumed",
    unit="1"
)

tokens_output_counter = meter.create_counter(
    name="seed.llm.tokens.output",
    description="Total output tokens generated",
    unit="1"
)

# Request Counter
request_counter = meter.create_counter(
    name="seed.llm.request.count",
    description="Total LLM requests",
    unit="1"
)

# Error Counter
error_counter = meter.create_counter(
    name="seed.llm.error.count",
    description="LLM errors by type",
    unit="1"
)

# Duration Histogram
duration_histogram = meter.create_histogram(
    name="seed.llm.request.duration",
    description="LLM request duration",
    unit="ms",
    explicit_bucket_boundaries_advisory=[100, 500, 1000, 2000, 5000, 10000]
)
```

### Tracing Helper

```python
# src/observability/tracing.py
from opentelemetry import trace, context
from opentelemetry.trace import StatusCode, Span
from functools import wraps
import asyncio

tracer = trace.get_tracer("seed-agent")

def classify_error(error: Exception) -> str:
    """将异常分类为标准错误类型"""
    error_str = str(error).lower()
    
    if "rate limit" in error_str or "429" in error_str:
        return "ratelimit"
    if "timeout" in error_str or "timed out" in error_str:
        return "timeout"
    if "connection" in error_str or "connect" in error_str:
        return "connection"
    if "context" in error_str and "overflow" in error_str:
        return "context_overflow"
    return "api_error"

def record_llm_span_error(span: Span, error: Exception):
    """在 Span 上记录 LLM 错误"""
    error_type = classify_error(error)
    
    span.record_exception(error)
    span.set_attribute("seed.error.type", error_type)
    span.set_attribute("seed.error.message", str(error)[:500])
    span.set_status(StatusCode.ERROR, str(error)[:200])
    
    return error_type

def create_task_with_context(coro, ctx=None):
    """创建继承 OTel context 的 asyncio task"""
    if ctx is None:
        ctx = context.get_current()
    return asyncio.create_task(coro, context=ctx)
```

---

## LLMGateway 接入示例

```python
# src/client.py 改动示例
import time
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from observability import (
    tracer,
    tokens_input_counter,
    tokens_output_counter,
    request_counter,
    error_counter,
    duration_histogram,
    record_llm_span_error,
    classify_error
)

async def _chat_completion_with_fallback_internal(self, model_id, messages, ...):
    """带 OpenTelemetry 嵌入的 LLM 调用"""
    
    with tracer.start_as_current_span("seed.llm.request") as span:
        # 设置 Span Attributes
        span.set_attribute("gen_ai.system", "openai")
        span.set_attribute("gen_ai.request.model", model_id)
        span.set_attribute("seed.provider", self._fallback_chain.active_provider)
        span.set_attribute("seed.streaming", stream)
        
        start_time = time.time()
        
        try:
            response = await self._execute_with_retry(...)
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Token 统计
            usage = response.usage
            if usage:
                span.set_attribute("gen_ai.usage.input_tokens", usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", usage.completion_tokens)
                
                # Metrics 记录
                attrs = {
                    "provider": self._fallback_chain.active_provider,
                    "model": model_id,
                    "status": "success"
                }
                tokens_input_counter.add(usage.prompt_tokens, attrs)
                tokens_output_counter.add(usage.completion_tokens, attrs)
                request_counter.add(1, attrs)
                duration_histogram.record(duration_ms, attrs)
            
            span.set_status(StatusCode.OK)
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            # 记录错误到 Span
            error_type = record_llm_span_error(span, e)
            
            # Metrics 记录错误
            attrs = {
                "provider": self._fallback_chain.active_provider,
                "model": model_id,
                "status": "error"
            }
            request_counter.add(1, attrs)
            duration_histogram.record(duration_ms, attrs)
            error_counter.add(1, {
                "provider": self._fallback_chain.active_provider,
                "model": model_id,
                "error_type": error_type
            })
            
            # 继续原有 fallback 逻辑...
            raise

def mark_degraded(self, reason: str):
    """记录 Fallback 切换"""
    old_provider = self.active_provider
    new_provider = self._fallback_chain[self._current_index + 1]
    
    # 在当前 Span 添加 Fallback Event
    current_span = trace.get_current_span()
    if current_span.is_recording():
        current_span.add_event("seed.llm.fallback", {
            "seed.fallback.from": old_provider,
            "seed.fallback.to": new_provider,
            "seed.fallback.reason": reason,
            "seed.fallback.attempt": self._current_index + 1
        })
    
    # 原有逻辑...
    self._current_index += 1
```

---

## Grafana Dashboard 建议面板

### 核心面板

| Panel | Type | Query | 用途 |
|-------|------|-------|------|
| Token 消耗总量 | Stat | `sum(seed_llm_tokens_input_total) + sum(seed_llm_tokens_output_total)` | 总 Token 用量 |
| Token 输入趋势 | Time Series | `sum(rate(seed_llm_tokens_input_total[5m])) by (provider, model)` | Token 输入速率 |
| Token 输出趋势 | Time Series | `sum(rate(seed_llm_tokens_output_total[5m])) by (provider, model)` | Token 输出速率 |
| LLM 错误率 | Gauge | `sum(rate(seed_llm_error_count_total[5m])) / sum(rate(seed_llm_request_count_total[5m]))` | 请求错误率 |
| P95 延迟 | Stat | `histogram_quantile(0.95, rate(seed_llm_request_duration_bucket[5m]))` | 请求延迟 P95 |
| 错误分布 | Pie Chart | `sum(seed_llm_error_count_total) by (error_type)` | 错误类型分布 |

---

## 依赖包

```txt
# requirements.txt 新增
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp>=1.20.0
opentelemetry-semantic-conventions>=0.41b0
```

---

## 启用方式

### 环境变量

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=seed-agent
```

### main.py 初始化

```python
# main.py
from observability.setup import setup_observability

# 启动时初始化
setup_observability(
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
)

# 继续原有逻辑...
gateway = LLMGateway(...)
agent = AgentLoop(...)
```

---

## 数据脱敏策略

### 不存储的内容

| 类型 | 原因 |
|------|------|
| 完整 prompt 内容 | 避免敏感数据泄露 |
| 完整 response 内容 | 存储成本 + 隐私 |
| API Key | 安全风险 |
| 完整文件路径（敏感目录） | 隐私 |

### 存储策略

| 数据 | 存储方式 |
|------|----------|
| error_message | 截断至 500 字符 |
| file_path | 仅存相对路径，不含用户目录前缀 |
| tool arguments | 仅存 `args_hash`（可选） |

---

## 后续扩展方向

1. **Logs 集成**：使用 `structlog` + OTel Context Injection，自动注入 `trace_id` 到日志
2. **Token 成本计算**：根据 provider/model 的定价，计算实际成本 Metrics
3. **Dashboard 模板**：提供 Grafana Dashboard JSON 导出
4. **告警规则**：Prometheus AlertManager 配置（Error rate > 5%, P95 latency > 10s）

---

## 参考文档

- [OpenTelemetry Python Docs](https://opentelemetry.io/docs/languages/python/)
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [Prometheus Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)