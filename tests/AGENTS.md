# 测试套件目录

验证 Seed Agent 系统组件的测试文件。

---

## 测试文件

| 文件 | 描述 |
|------|------|
| `test_ralph_loop.py` | Ralph Loop 执行和验证测试 |
| `verify_ralph.py` | Ralph Loop 验证机制测试 |

---

## 测试类别

### Ralph Loop 测试

- 完成验证（TEST_PASS/FILE_EXISTS/MARKER_FILE/GIT_CLEAN/CUSTOM_CHECK）
- 安全上限（1000 轮 / 8 小时）
- 上下文管理（重置 + 提取）
- 状态持久化（崩溃恢复）

---

## 执行测试

```bash
# 全部测试
pytest tests/ -v

# 单文件
pytest tests/test_ralph_loop.py -v

# 覆盖率
pytest tests/ --cov=src --cov-report=html
```

---

## 依赖

- `pytest` - 测试框架
- `pytest-asyncio` - 异步测试
- `pytest-cov` - 覆盖率报告

---

## 相关文档

- Ralph 设计：[docs/long_cycle_loop_enhancement_design.md](../docs/long_cycle_loop_enhancement_design.md)
- 核心引擎：[src/AGENTS.md](../src/AGENTS.md)