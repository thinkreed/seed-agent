# Super-agent 机制级 benchmark（§7 复现）

生成时间：2026-11-01T10:09:36.266Z

参数：threads=4，模型延迟=40ms（确定性假模型），Worker 耗时=500ms，slots=2

## A. Router 批处理

| 方式 | 模型调用次数 | 墙钟时间 |
|---|---|---|
| 逐条串行 | 4 | 167 ms |
| 同轮批量（Router） | 1 | 42 ms |

批量调用把 4 个 Thread 合并成 1 次模型调用，墙钟约 3.98× 加速。

## B. 消融：单 Session 串行 vs Super-agent

| 形态 | 完成时间 | 模型调用 | Worker 并发 | 上下文隔离 |
|---|---|---|---|---|
| 单 Session 串行 | 2168 ms | 4（逐条） | 1 | 否 |
| Super-agent | 1042 ms | 1（Router 批）+ Worker | 2 | 是 |

Super-agent 形态约 2.08× 完成，且每个 Worker 上下文隔离。

## C. 真实模型批处理

未启用（加 `--real` 需要 BAILIAN_API_KEY）。
