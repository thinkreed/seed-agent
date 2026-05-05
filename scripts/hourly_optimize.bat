@echo off
REM Hourly Code Optimization Task for seed-agent
REM This script launches Qwen Code to perform comprehensive automatic code optimization

cd /d E:\projects\seed-agent

REM Execute comprehensive optimization with YOLO mode (auto-approve all)
qwen -y -d E:\projects\seed-agent "执行 seed-agent 项目全面优化重构任务：

## 任务清单

### 1. 重构大文件
- 扫描 src/ 目录下所有 Python 文件
- 找出超过 300 行的文件
- 对每个大文件进行拆分重构：
  - 拆分为职责单一的小模块
  - 每个模块不超过 150 行
  - 提取公共逻辑为独立函数或类
- **不要兼容旧设计**，直接重写为最优架构
- 同步修改对应的测试文件
- 更新所有引用该模块的文档

### 2. Wiki 知识落地
- 读取 E:\projects\wiki 目录下的 markdown 文章
- 重点阅读以下项目的架构设计：
  - genericagent/ - Agent 核心循环、工具系统、记忆系统
  - hermes-agent/ - Self-Improving 模式、技能系统
  - mia/ - 记忆系统、Executor/Planner 训练
  - open-agents/ - 子代理系统、工作流
  - qwen-code-architecture/ - 核心引擎、工具系统、Hooks
- 提取可落地的优化：
  - 架构模式
  - 工具系统最佳实践
  - 记忆层级设计
  - 错误处理和容错机制
  - 性能优化技巧
- 将优化应用到 seed-agent：
  - 评估每个优化点的适用性
  - 实施改进，重写不兼容的部分
  - 更新测试和文档

### 3. 文档更新
- 扫描 docs/ 目录所有文档
- 确保文档与代码实现一致
- 补充缺失的架构说明
- 更新 API 变更说明
- 更新 AGENTS.md 和 README.md

## 执行规则

- 全自动执行，无需人工确认
- 小步提交，每个重构单元独立提交
- **禁止修改 core_principles/ 和 golden_rules/ 目录**
- 每次修改必须同步更新测试和文档
- 不兼容旧设计时直接重写，不保留兼容层

## 最终提交

所有优化完成后：
1. 运行完整测试套件确保通过
2. 提交所有变更到本地 git
3. 推送到 origin main

完成后输出详细报告，包含：
- 重构的文件列表和变更摘要
- 修复的 Bug 列表
- 落地的 Wiki 优化点
- 更新的文档列表
- 测试运行结果
- Git 提交记录"