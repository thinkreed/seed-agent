# 核心原则模块

定义 Agent 行为、身份和操作原则的系统提示。

---

## 文件列表

| 文件 | 描述 |
|------|------|
| `system_prompts_en.md` | 英文系统提示 |
| `system_prompts_zh.md` | 中文系统提示 |

---

## 核心功能

1. **Agent 身份**：物理级全能进化型执行者
2. **核心权限**：物理操作、浏览器干预、系统干预、进化权限
3. **行动原则**：`<thinking>` 推演、失败升级、自主进化
4. **工作记忆**：操作日志、经验库、能力清单
5. **核心禁忌**：不推诿、不盲目、不忽视进化、不可逆先确认

---

## 加载方式

```python
# main.py 加载
prompt_path = 'core_principles/system_prompts_en.md'
system_prompt = open(prompt_path).read()
agent = AgentLoop(gateway=gateway, system_prompt=system_prompt)
```

---

## ⚠️ 禁止修改

**根目录 AGENTS.md 约定**：禁止修改 `core_principles` 目录下的文件。

修改这些文件可能导致：
- 改变 Agent 核心身份
- 破坏行为约束
- 影响其他组件兼容性

---

## 相关文档

- 项目总览：[AGENTS.md](../AGENTS.md)