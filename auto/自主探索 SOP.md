# 自主探索 SOP
**记忆层级**：L1索引 | L2技能 | L3知识 | L4用户建模 | L5工作日志

---

## 一、任务规划

### 前提
价值公式：`实际可落地 × 进化沉淀价值 × 稀缺性 × 长期任务推进度`

**强制**：每轮必执行长期任务(STR-01/02/03/04轮换)，完成前调用 `start_long_term_update`
**强制**: 禁止停下来询问，完全自己进行探索

### 流程
- **有TODO**: 推演后执行，优先长期任务
- **无TODO**: 规划模式 → 复盘history.md → 产5-7条TODO(含1-2条STR) → subagent评审 → 更新工作记忆

---

## 二、执行流程

1. 读取TODO，推演逻辑(优先长期任务)
2. 适配权限，不可逆操作确认用户
3. 失败升级：1次重试 → 2次调策略 → 3次换方案/询用户
4. 核对验收标准，长期任务未完成不得下一轮
5. 更新工作记忆，调用 `start_long_term_update`
6. **用户偏好观察**: 发现偏好线索 → `observe_user_preference`
7. 未完成长期任务纳入下一轮TODO
8. 归纳至history.md

---

## 三、长期任务(STR) - 每轮必执行

| STR | 来源 | 目标 | 策略 |
|------|------|------|------|
| STR-01 | `wikiDir/` | 架构优化 | 1篇/轮，输出PR/Skill/L3 |
| STR-02 | `projects/GenericAgent/` | 能力扩展 | 1文件/轮，转L2 Skills |
| STR-03 | `seedBaseDir/memory/skills/` | Skill精简(Gene化) | 1文件/轮，Token降50%+ |
| STR-04 | `seedBaseDir/memory/` | 记忆维护 | L1完整性，L4合并，L5清理 |

**STR-03 Gene格式**: signals + strategy + constraints + validation

---

## 四、记忆工具(L1-L5)

### L1-L3
- `write_memory(level, content, title)` - 写入
- `search_memory(keyword, levels)` - 跨层搜索

### L4 用户建模
- `observe_user_preference(key, value, context?, confidence)` - 观察偏好
- `get_user_preference(key, context?)` - 获取偏好(上下文感知)
- 辩证式升级：不覆盖，添加例外

### L5 工作日志
- `search_archives(keyword)` - FTS5检索归档
- `get_archive_stats()` - 归档统计

---

## 五、排序原则(降序)

1. 执行落地 + 能力扩展
2. 环境探测 + 资源挖掘
3. 进化策略优化
4. 经验复用迭代
5. 用户偏好观察(低频)
6. 工作记忆审查(每3TODO清理)

---

## 六、禁忌

❌ 推诿"无法操作"，无方案需提建议
❌ 未推演直接执行
❌ 未调用 `start_long_term_update`
❌ 不可逆操作未确认用户
❌ 浅层验证/重复探索/泛采集
❌ 机械操作/标题搬运/不复盘
❌ 跳过长期任务
❌ L4直接覆盖(非辩证升级)
❌ L5手动删除摘要
❌ Skill精简仅表面压缩