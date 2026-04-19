---
Subagent 机制分析报告
一、Subagent 核心特性（来自 Claude Code 文章）
特性	描述
独立上下文	每个 subagent 有独立的 context window，不共享主对话历史
并行执行	多个 subagent 可同时运行
权限隔离	可配置不同权限（如 read-only vs full-edit）
结果聚合	只返回关键结果给主对话，不污染主上下文
自动路由	根据描述自动匹配任务类型
适用场景：
1. 研究重任务：需要读取大量文件，但主对话不需要这些上下文
2. 并行独立任务：多个不依赖的子任务同时执行
3. 新鲜视角：避免主对话的假设和偏见
4. 验证：独立审查实现质量
5. 管道工作流：设计→实现→测试 的阶段隔离
---
二、seed-agent 现有架构分析
现有执行模式
组件	执行模式	特性
AgentLoop	单实例单线程	共享 history，迭代上限30
RalphLoop	外层循环控制	复用同一个 AgentLoop，重置 history
AutonomousExplorer	空闲触发	复用同一个 AgentLoop，临时替换 system_prompt
TaskScheduler	定时触发	触发 AgentLoop.run()
关键差异
Claude Code Subagent:
┌─────────────────────────────────────────────────────────────┐
│ Main Session                                                │
│   │                                                         │
│   ├── Spawn → Subagent A (独立 context) ──→ Return result   │
│   ├── Spawn → Subagent B (独立 context) ──→ Return result   │
│   ├── Spawn → Subagent C (独立 context) ──→ Return result   │
│   │                                                         │
│   └── Aggregate results → Continue                          │
└─────────────────────────────────────────────────────────────┘
seed-agent RalphLoop:
┌─────────────────────────────────────────────────────────────┐
│ Single AgentLoop Instance                                   │
│   │                                                         │
│   ├── Iteration 1 → Run → Reset history                     │
│   ├── Iteration 2 → Run → Reset history                     │
│   ├── Iteration 3 → Run → Reset history                     │
│   │                                                         │
│   └── External verification → Complete                      │
└─────────────────────────────────────────────────────────────┘
本质差异：
- Claude Code = 多实例并行，每个 subagent 是独立的 agent
- seed-agent = 单实例循环，RalphLoop 只是外层控制，不是新 agent
---
三、是否需要引入 Subagent？
关键痛点
1. 无并行执行：多个独立任务必须串行，效率低
2. 上下文污染：研究任务会污染主对话历史
3. 无独立审查：同一个模型审查自己的实现，偏见风险
4. 阶段耦合：设计阶段的上下文会影响实现阶段
---
四、引入 Subagent 的设计建议
方案 A：完全引入 Subagent（推荐）
架构变更：
┌─────────────────────────────────────────────────────────────┐
│                      新架构                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ MainAgentLoop (主对话)                                   ││
│  │ ─────────────────────                                   ││
│  │ 角色: 用户交互、任务编排、结果聚合                        ││
│  │ 权限: 保留现有全部权限                                   ││
│  │                                                          ││
│  │ 新增能力:                                                ││
│  │   ├── spawn_subagent(type, prompt, permissions)         ││
│  │   ├── wait_for_subagent(task_id)                        ││
│  │   └── aggregate_results(task_ids)                       ││
│  │                                                          ││
│  └─────────────────────────────────────────────────────────┘│
│                              ↓                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ SubagentManager (新增)                                   ││
│  │ ─────────────────────                                   ││
│  │ 角色: 子 agent 生命周期管理                              ││
│  │                                                          ││
│  │ 核心职责:                                                ││
│  │   ├── 创建独立 AgentLoop 实例                            ││
│  │   ├── 配置不同权限集                ││
│  │   ├── 并行执行调度                                       ││
│  │   ├── 结果收集与过滤                                     ││
│  │   ├── 超时管理                                           ││
│  │                                                          ││
│  └─────────────────────────────────────────────────────────┘│
│                              ↓                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ SubagentInstance (新增)                                  ││
│  │ ─────────────────────                                   ││
│  │ 角色: 独立上下文的执行实例                               ││
│  │                                                          ││
│  │ 特性:                                                    ││
│  │   ├── 独立 history (不共享主对话)                        ││
│  │   ├── 可配置权限集                                       ││
│  │   ├── 生命周期隔离                                       ││
│  │   ├── 只返回结果，不返回过程                             ││
│  │                                                          ││
│  │ 类型:                                                    ││
│  │   ├── ExploreSubagent (只读探索)                         ││
│  │   ├── ReviewSubagent (审查验证)                          ││
│  │   ├── ImplementSubagent (实现执行)                       ││
│  │   ├── PlanSubagent (规划分析)                            ││
│  │                                                          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  RalphLoop (保留) ───────────────────────────────────────────│
│  │ 角色变更:                                                ││
│  │   从"外层循环控制"变为"编排多个 subagent"                ││
│  │                                                          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
新增组件：
组件	文件	功能
SubagentManager	src/subagent_manager.py	子 agent 创建、调度、结果收集
SubagentInstance	src/subagent.py	独立 AgentLoop 实例封装
subagent_tools	src/tools/subagent_tools.py	工具注册：spawn, wait, aggregate
Subagent 类型设计：
class SubagentType(Enum):
    EXPLORE = "explore"      # 只读探索 (tools: file_read, grep, glob)
    REVIEW = "review"        # 审查验证 (tools: file_read, grep, glob, code_exec)
    IMPLEMENT = "implement"  # 实现执行
    PLAN = "plan"            # 规划分析 (tools: file_read, grep, glob, write_memory)
权限集设计：
PERMISSION_SETS = {
    "read_only": ["file_read", "grep", "glob", "search_history", "ask_user"],
    "review": ["file_read", "grep", "glob", "code_exec", "search_history"],
    "implement": ALL_TOOLS,  # 全权限
    "plan": ["file_read", "grep", "glob", "write_memory", "search_history"],
}
五、与 RalphLoop 的融合设计
如果引入 Subagent，RalphLoop 的角色可升级为：
RalphLoop V2:
┌─────────────────────────────────────────────────────────────┐
│ 角色: Subagent 编排器                                        │
│                                                              │
│ 执行模式:                                                    │
│   1. Spawn PlanSubagent → 获取执行计划                       │
│   2. Spawn multiple ImplementSubagent (并行)                 │
│   3. Spawn ReviewSubagent → 验证实现                         │
│   4. External verification → 循环或完成                      │
│                                                              │
│ 核心优势:                                                    │
│   - 阶段隔离（Plan→Implement→Review 不共享上下文）           │
│   - 并行执行（多个 ImplementSubagent 同时工作）              │
│   - 新鲜审查（ReviewSubagent 不受 Implement 影响）          │
└─────────────────────────────────────────────────────────────┘
---
六、决策建议
问题	建议	理由
是否引入 Subagent？	YES，推荐方案 A	解决并行、审查、阶段隔离三大痛点
与 RalphLoop 的关系？	RalphLoop 升级为编排器	不替代 RalphLoop，而是增强其能力
改动范围？	新增模块，不破坏现有	保持 AgentLoop 不变，新增 SubagentManager
优先级？	Phase 2，在 RalphLoop 稳定后	先确保长周期任务稳定，再引入并行
---
### 七、设计要点
1. **渐进式引入**：先实现 ExploreSubagent（只读探索），验证价值后再扩展
2. **权限隔离**：必须支持不同权限集，避免 read-only subagent 写文件
3. **结果过滤**：只返回关键发现，不返回原始文件内容
4. **超时机制**：subagent 执行必须有超时上限
5. **资源管理**：限制同时运行的 subagent 数量（避免 API 过载）
---
八、结论
Subagent 机制对 seed-agent 是有价值的，主要体现在：
1. 并行效率：当前串行执行，效率差距显著
2. 独立审查：解决"自己审查自己"的偏见风险
3. 上下文隔离：研究任务不污染主对话
4. 阶段解耦：设计→实现→测试 各阶段独立
引入完整 Subagent 机制，RalphLoop 升级为 Subagent 编排器。
实施路径：
- Phase 1：先确保 RalphLoop 稳定运行（已基本完成）
- Phase 2：引入 SubagentManager + ExploreSubagent
- Phase 3：扩展 ReviewSubagent, ImplementSubagent
- Phase 4：RalphLoop 升级为编排器
---