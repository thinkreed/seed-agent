# 优化点 03: 记忆系统升级 (L4 用户建模 + L5 工作日志)

> **版本**: v2.0 (已落地实现)
> **创建日期**: 2026-05-03
> **实现日期**: 2026-05-03
> **优先级**: 中
> **状态**: ✅ 已完成
> **依赖**: 01_session_event_stream_design
> **参考来源**: Harness Engineering "五层记忆架构"

---

## 实现状态

### ✅ 已完成模块

| 模块 | 文件 | 实现状态 |
|------|------|----------|
| **UserModelingLayer** | `src/tools/user_modeling.py` | ✅ 已实现，含辩证式进化 |
| **LongTermArchiveLayer** | `src/tools/long_term_archive.py` | ✅ 已实现，含 FTS5 + LLM 摘要 |
| **测试** | `tests/test_user_modeling.py`, `tests/test_long_term_archive.py` | ✅ 已实现 |

### 关键特性验证

- ✅ L4 用户建模：观察 → 矛盾检测 → 内部推理 → 升级模型
- ✅ L5 工作日志：FTS5 全文检索 + LLM 自动摘要
- ✅ 升级而非覆盖：保留例外情况和复杂偏好
- ✅ jieba 中文分词支持
- ✅ 跨会话知识检索

---

## 问题分析

### Harness Engineering 五层记忆架构

| 层级 | 名称 | Harness 描述 |
|------|------|-------------|
| L1 | 短期记忆 (便利贴) | 当前对话临时信息 |
| L2 | 技能手册 (肌肉记忆) | 复杂任务后自动生成 SKILL.md |
| L3 | 知识库 (语义记忆) | 向量存储，模糊检索 |
| **L4** | **对用户的了解 (用户建模)** | **黑格尔辩证式用户理解** |
| **L5** | **工作日志 (长期档案)** | **FTS5 + LLM 摘要，永久存储** |

**L4 用户建模核心概念**: 
> 不是一次判断就定终身，允许用户改变、允许情况复杂，通过不断观察、思考、调整，越来越懂真实的用户

**示例**:
- 旧版本: "林总喜欢喝美式"
- 新发现: 今天林总点了拿铁
- 冲突: 旧版本 和 新证据矛盾
- 解决方案: 不直接覆盖，而是升级 → "林总平时喝美式，但周三下午会换拿铁"

### seed-agent 当前四层架构

| 层级 | 名称 | 实现 | 状态 |
|------|------|------|------|
| L1 | 索引 | `notes.md` | ✅ 完成 |
| L2 | 技能 | `skills/*.md` | ✅ 完成 |
| L3 | 知识 | `knowledge/*.md` | ✅ 完成 |
| L4 | 原始 | SQLite+FTS5 | ✅ 完成 |

**缺失**:
- ❌ 无 L4 用户建模层 (辩证式进化)
- ❌ 无 L5 工作日志层 (LLM 自动摘要)
- ⚠️ L3 无语义向量存储

---

## 设计方案

### 1. 升级后的五层架构

```
┌─────────────────────────────────────────────────────────────┐
│ L5 工作日志 (长期档案)                                        │
│                                                              │
│    - FTS5 全文检索                                           │
│    - LLM 自动摘要 (每次长谈后总结)                             │
│    - 永久存储，支持语义搜索                                    │
│    - 跨会话知识检索                                           │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ 归档
┌─────────────────────────────────────────────────────────────┐
│ L4 用户建模 (辩证式理解)                                      │
│                                                              │
│    - 黑格尔辩证式进化                                         │
│    - 观察 → 矛盾检测 → 内部推理 → 升级模型                      │
│    - 越来越懂用户                                             │
│    - 允许例外和复杂情况                                        │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ 用户反馈提取
┌─────────────────────────────────────────────────────────────┐
│ L3 知识库 (语义记忆)                                          │
│                                                              │
│    - 向量存储，模糊检索                                       │
│    - "进度报告" vs "项目周报" → 相似度 0.92                    │
│    - 语义相似度匹配                                           │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ 模式蒸馏
┌─────────────────────────────────────────────────────────────┐
│ L2 技能手册 (肌肉记忆)                                        │
│                                                              │
│    - 完成复杂任务后自动生成 SKILL.md                            │
│    - 可复用操作流程                                           │
│    - Memory Graph 选择优化                                    │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ 技能注册
┌─────────────────────────────────────────────────────────────┐
│ L1 短期记忆 (便利贴)                                          │
│                                                              │
│    - 当前对话的临时信息                                       │
│    - 快速参考索引                                             │
│    - Trigger word 路由                                        │
└─────────────────────────────────────────────────────────────┘
```

### 2. L4 用户建模层设计

```python
class UserModelingLayer:
    """L4 用户建模 - 黑格尔辩证式进化"""
    
    def __init__(self, storage_path: Path):
        self._storage_path = storage_path
        self._user_profile: dict = {
            "preferences": {},
            "work_patterns": {},
            "interaction_style": {},
            "dialectical_history": []  # 进化历史
        }
        self._observations: list[dict] = []  # 观察记录
        self._conflict_detector: ConflictDetector = None
        self._llm_reasoner: LLMGateway = None
    
    # === 观察 ===
    
    def observe(self, evidence: dict) -> None:
        """观察新证据
        
        Args:
            evidence: {
                "type": "preference" | "behavior" | "feedback" | "context",
                "data": 具体观察内容,
                "context": 观察上下文,
                "confidence": 置信度
            }
        """
        observation = {
            "id": len(self._observations) + 1,
            "timestamp": time.time(),
            "type": evidence["type"],
            "data": evidence["data"],
            "context": evidence["context"],
            "confidence": evidence.get("confidence", 0.8)
        }
        self._observations.append(observation)
        self._persist_observation(observation)
    
    def observe_from_interaction(self, interaction: dict) -> None:
        """从用户交互中提取观察
        
        Args:
            interaction: 用户消息 + Agent 响应 + 工具调用
        """
        # 提取偏好线索
        preferences = self._extract_preferences(interaction)
        for pref in preferences:
            self.observe({
                "type": "preference",
                "data": pref,
                "context": interaction["user_message"],
                "confidence": 0.7
            })
        
        # 提取行为模式
        behaviors = self._extract_behaviors(interaction)
        for beh in behaviors:
            self.observe({
                "type": "behavior",
                "data": beh,
                "context": interaction["tool_calls"],
                "confidence": 0.6
            })
    
    # === 辩证式更新 ===
    
    async def dialectical_update(self) -> dict:
        """辩证式更新
        
        流程:
        1. 检测新证据与旧模型矛盾
        2. 内部推理讨论
        3. 升级用户模型 (不直接覆盖)
        
        Returns:
            更新报告
        """
        # 1. 检测矛盾
        conflicts = await self._detect_conflicts()
        
        if not conflicts:
            # 无矛盾，直接强化
            await self._reinforce_model()
            return {"status": "reinforced", "conflicts": []}
        
        # 2. 内部推理讨论
        resolution = await self._reason_about_conflicts(conflicts)
        
        # 3. 升级模型 (不直接覆盖)
        updates = self._upgrade_model(resolution)
        
        # 4. 记录进化历史
        self._record_dialectical_history(conflicts, resolution, updates)
        
        return {
            "status": "upgraded",
            "conflicts": conflicts,
            "resolution": resolution,
            "updates": updates
        }
    
    async def _detect_conflicts(self) -> list[dict]:
        """检测新证据与旧模型的矛盾
        
        Returns:
            冲突列表: [{
                "old_belief": "用户喜欢美式咖啡",
                "new_evidence": "用户点了拿铁",
                "confidence_old": 0.85,
                "confidence_new": 0.9,
                "context": "周三下午"
            }]
        """
        conflicts = []
        
        # 检查最近观察 vs 当前模型
        for pref_key, pref_value in self._user_profile["preferences"].items():
            for obs in self._observations[-10:]:
                if obs["type"] == "preference" and obs["data"].get("key") == pref_key:
                    # 检查是否矛盾
                    if self._is_conflicting(pref_value, obs["data"]["value"]):
                        conflicts.append({
                            "old_belief": pref_value,
                            "new_evidence": obs["data"]["value"],
                            "confidence_old": pref_value.get("confidence", 0.8),
                            "confidence_new": obs["confidence"],
                            "context": obs["context"]
                        })
        
        return conflicts
    
    async def _reason_about_conflicts(self, conflicts: list[dict]) -> dict:
        """内部推理讨论
        
        使用 LLM 分析矛盾，得出升级方案
        """
        prompt = self._build_reasoning_prompt(conflicts)
        response = await self._llm_reasoner.chat_completion([{"role": "user", "content": prompt}])
        resolution = self._parse_resolution(response)
        return resolution
    
    def _upgrade_model(self, resolution: dict) -> dict:
        """升级模型而非简单覆盖
        
        示例:
        - 不是: preference = "拿铁"
        - 而是: preference = {"usual": "美式", "exceptions": {"周三下午": "拿铁"}}
        """
        updates = {}
        
        for conflict_resolution in resolution.get("resolutions", []):
            pref_key = conflict_resolution["preference_key"]
            
            # 获取当前值
            current = self._user_profile["preferences"].get(pref_key, {})
            
            # 升级而非覆盖
            upgraded = self._apply_upgrade(current, conflict_resolution)
            
            self._user_profile["preferences"][pref_key] = upgraded
            updates[pref_key] = {
                "before": current,
                "after": upgraded,
                "reason": conflict_resolution["reason"]
            }
        
        self._persist_profile()
        return updates
    
    def _apply_upgrade(self, current: dict, resolution: dict) -> dict:
        """应用升级逻辑"""
        if not current:
            # 新偏好，直接设置
            return {
                "usual": resolution["value"],
                "exceptions": {},
                "confidence": resolution["confidence"],
                "last_updated": time.time()
            }
        
        # 已有偏好，添加例外
        exceptions = current.get("exceptions", {})
        context_key = resolution.get("context_key", "general")
        exceptions[context_key] = {
            "value": resolution["value"],
            "when": resolution.get("when", ""),
            "confidence": resolution["confidence"]
        }
        
        return {
            "usual": current["usual"],
            "exceptions": exceptions,
            "confidence": min(current["confidence"], resolution["confidence"]),
            "last_updated": time.time()
        }
    
    # === 用户画像查询 ===
    
    def get_user_preference(self, key: str, context: dict = None) -> dict:
        """获取用户偏好
        
        Args:
            key: 偏好键 (如 "coffee", "work_style")
            context: 当前上下文 (用于检查例外)
        
        Returns:
            基于上下文的偏好值
        """
        pref = self._user_profile["preferences"].get(key, {})
        
        # 检查是否有例外匹配当前上下文
        if context and pref.get("exceptions"):
            for exception_key, exception in pref["exceptions"].items():
                if self._context_matches(context, exception["when"]):
                    return {
                        "value": exception["value"],
                        "reason": f"例外情况: {exception['when']}",
                        "confidence": exception["confidence"]
                    }
        
        return {
            "value": pref.get("usual"),
            "reason": "常规偏好",
            "confidence": pref.get("confidence", 0.5)
        }
    
    def get_user_profile_summary(self) -> str:
        """获取用户画像摘要"""
        lines = []
        
        # 常规偏好
        for key, pref in self._user_profile["preferences"].items():
            usual = pref.get("usual", "未知")
            exceptions = pref.get("exceptions", {})
            
            if exceptions:
                exception_strs = [f"{k}: {v['value']}" for k, v in exceptions.items()]
                lines.append(f"{key}: 平时 {usual}, 例外情况 {', '.join(exception_strs)}")
            else:
                lines.append(f"{key}: {usual}")
        
        return "\n".join(lines)
```

### 3. L5 工作日志层设计

```python
class LongTermArchiveLayer:
    """L5 工作日志 - FTS5 + LLM 摘要"""
    
    def __init__(self, db_path: Path, llm_gateway: LLMGateway):
        self._db = SQLiteFTS5Database(db_path)
        self._llm_gateway = llm_gateway
        self._jieba_tokenizer = jieba
    
    # === 归档 ===
    
    async def archive_session(self, session: SessionEventStream) -> str:
        """归档会话
        
        流程:
        1. LLM 生成核心结论摘要
        2. 存储到数据库
        3. FTS5 自动索引
        
        Returns:
            archive_id
        """
        events = session.get_events()
        
        # 1. LLM 生成摘要 (写读书笔记)
        summary = await self._generate_summary(events)
        
        # 2. 提取关键发现
        key_findings = await self._extract_key_findings(events)
        
        # 3. 存储到数据库
        archive_id = self._db.insert_archive(
            session_id=session.session_id,
            events=events,
            summary=summary,
            key_findings=key_findings,
            timestamp=time.time()
        )
        
        # 4. FTS5 自动索引 (智能目录)
        self._update_fts_index(archive_id, events, summary)
        
        return archive_id
    
    async def _generate_summary(self, events: list[dict]) -> str:
        """LLM 生成核心结论摘要
        
        要求: 1-2 句话总结核心结论
        """
        # 构建对话历史
        history_text = self._format_events_for_summary(events)
        
        prompt = f"""请用1-2句话总结以下对话的核心结论，保留最有价值的信息:

{history_text}

摘要格式:
- 核心结论: ...
- 关键发现: ...
"""
        
        response = await self._llm_gateway.chat_completion([
            {"role": "user", "content": prompt}
        ])
        
        return response["choices"][0]["message"]["content"]
    
    async def _extract_key_findings(self, events: list[dict]) -> list[str]:
        """提取关键发现"""
        findings_prompt = f"""从以下对话中提取3-5个关键发现:

{self._format_events_for_summary(events)}

关键发现格式 (每行一个):
1. 发现内容
2. 发现内容
...
"""
        
        response = await self._llm_gateway.chat_completion([
            {"role": "user", "content": findings_prompt}
        ])
        
        findings = response["choices"][0]["message"]["content"].strip().split("\n")
        return [f.strip() for f in findings if f.strip()]
    
    # === 搜索 ===
    
    def search_with_context(self, keyword: str, limit: int = 20) -> list[dict]:
        """语义搜索 + 摘要提取
        
        Returns:
            [{
                "archive_id": "...",
                "session_id": "...",
                "summary": "核心结论摘要",
                "matched_snippet": "匹配片段",
                "key_findings": ["发现1", "发现2"],
                "timestamp": "..."
            }]
        """
        # 1. FTS5 搜索关键词 (jieba 分词)
        tokens = list(self._jieba_tokenizer.cut(keyword))
        fts_query = " OR ".join(tokens)
        
        matches = self._db.search_fts(fts_query, limit)
        
        # 2. 返回摘要 + 关键上下文片段
        results = []
        for match in matches:
            results.append({
                "archive_id": match["archive_id"],
                "session_id": match["session_id"],
                "summary": match["summary"],
                "matched_snippet": match["snippet"],
                "key_findings": match.get("key_findings", []),
                "timestamp": match["timestamp"],
                "relevance_score": match.get("score", 0)
            })
        
        return results
    
    def search_by_time_range(self, start_time: float, end_time: float) -> list[dict]:
        """时间范围搜索"""
        return self._db.search_by_time_range(start_time, end_time)
    
    def get_archive(self, archive_id: str) -> dict:
        """获取完整归档"""
        return self._db.get_archive(archive_id)
    
    # === 统计 ===
    
    def get_archive_stats(self) -> dict:
        """获取归档统计"""
        return {
            "total_archives": self._db.count_archives(),
            "total_events": self._db.count_events(),
            "avg_events_per_archive": self._db.avg_events_per_archive(),
            "recent_archives": self._db.get_recent_archives(5)
        }
```

### 4. 数据库 Schema

```sql
-- L5 归档表
CREATE TABLE IF NOT EXISTS archives (
    archive_id TEXT PRIMARY KEY,
    session_id TEXT,
    summary TEXT,
    key_findings TEXT,  -- JSON array
    events_count INTEGER,
    created_at REAL,
    metadata TEXT
);

-- L5 事件表 (详细归档)
CREATE TABLE IF NOT EXISTS archive_events (
    id INTEGER PRIMARY KEY,
    archive_id TEXT,
    event_id INTEGER,
    event_type TEXT,
    event_data TEXT,  -- JSON
    timestamp REAL,
    FOREIGN KEY (archive_id) REFERENCES archives(archive_id)
);

-- L5 FTS5 索引
CREATE VIRTUAL TABLE IF NOT EXISTS archives_fts USING fts5(
    archive_id,
    session_id,
    summary,
    key_findings,
    event_content,
    tokenize='jieba'
);

-- L4 用户画像表
CREATE TABLE IF NOT EXISTS user_profiles (
    profile_id TEXT PRIMARY KEY,
    preferences TEXT,  -- JSON
    work_patterns TEXT,  -- JSON
    interaction_style TEXT,  -- JSON
    confidence REAL,
    last_updated REAL
);

-- L4 观察记录表
CREATE TABLE IF NOT EXISTS user_observations (
    id INTEGER PRIMARY KEY,
    observation_type TEXT,
    observation_data TEXT,  -- JSON
    context TEXT,
    confidence REAL,
    timestamp REAL
);

-- L4 进化历史表
CREATE TABLE IF NOT EXISTS dialectical_history (
    id INTEGER PRIMARY KEY,
    conflict TEXT,  -- JSON
    resolution TEXT,  -- JSON
    update TEXT,  -- JSON
    timestamp REAL
);
```

---

## 实施步骤

### Phase 1: L4 用户建模层 (5天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 1.1 | 设计用户画像 Schema | 数据库表创建成功 |
| 1.2 | 实现 UserModelingLayer 类 | observe/dialectical_update |
| 1.3 | 实现冲突检测逻辑 | detect_conflicts 正确 |
| 1.4 | 实现升级逻辑 (不覆盖) | apply_upgrade 正确 |
| 1.5 | 集成到 AgentLoop | 自动观察用户交互 |

### Phase 2: L5 工作日志层 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 2.1 | 设计归档 Schema | 数据库表创建成功 |
| 2.2 | 实现 LongTermArchiveLayer 类 | archive_session |
| 2.3 | 实现 LLM 自动摘要 | generate_summary 正确 |
| 2.4 | 实现 FTS5 搜索 | search_with_context |
| 2.5 | 集成到生命周期钩子 | 会话结束自动归档 |

### Phase 3: 五层架构集成 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 3.1 | 定义统一的 MemoryManager | 管理 L1-L5 |
| 3.2 | 实现跨层查询接口 | search_all_levels |
| 3.3 | 更新 memory_tools.py | 新工具注册 |

---

## 预期收益

| 收益 | 描述 |
|------|------|
| **用户理解持续进化** | L4 辩证式建模，越来越懂用户 |
| **长期知识沉淀** | L5 归档，跨会话检索 |
| **智能摘要** | LLM 自动生成核心结论 |
| **例外情况处理** | 不简单覆盖，允许复杂偏好 |
| **语义搜索增强** | FTS5 + jieba + 向量相似 |

---

## 测试计划

```python
# L4 用户建模测试
def test_dialectical_update():
    user_model = UserModelingLayer(Path("/tmp/user_model"))
    
    # 观察常规偏好
    user_model.observe({"type": "preference", "data": {"key": "coffee", "value": "美式"}})
    
    # 观察例外情况
    user_model.observe({
        "type": "preference",
        "data": {"key": "coffee", "value": "拿铁"},
        "context": "周三下午",
        "confidence": 0.9
    })
    
    # 辩证式更新
    result = await user_model.dialectical_update()
    
    # 验证升级而非覆盖
    pref = user_model.get_user_preference("coffee")
    assert pref["usual"] == "美式"
    assert "周三下午" in pref["exceptions"]

# L5 工作日志测试
def test_archive_with_summary():
    archive = LongTermArchiveLayer(Path("/tmp/archive.db"), gateway)
    
    # 归档会话
    session = SessionEventStream("test_session", Path("/tmp/test"))
    session.emit_event("user_input", {"content": "帮我重构代码"})
    session.emit_event("llm_response", {"content": "好的，开始重构"})
    
    archive_id = await archive.archive_session(session)
    
    # 验证摘要生成
    record = archive.get_archive(archive_id)
    assert record["summary"] is not None
    assert len(record["key_findings"]) > 0
    
    # 验证搜索
    results = archive.search_with_context("重构")
    assert len(results) > 0
```

---

## 相关文档

- [01_session_event_stream_design.md](01_session_event_stream_design.md) - Session 事件流
- [05_lifecycle_hooks_design.md](05_lifecycle_hooks_design.md) - 生命周期钩子 (归档触发)
- [memory/AGENTS.md](../../memory/AGENTS.md) - 当前记忆系统文档