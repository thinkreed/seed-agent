@echo off
REM Hourly Code Optimization Task for seed-agent
REM This script launches Qwen Code to perform automatic code optimization

cd /d E:\projects\seed-agent

REM Read prompt from file and execute with YOLO mode (auto-approve all)
qwen -y -d E:\projects\seed-agent "对 seed-agent 项目执行代码优化：扫描 src/ 目录下所有 Python 文件，检查并优化代码质量、性能、错误处理、类型安全。全自动执行，小步提交。禁止修改 core_principles/ 和 golden_rules/ 目录。完成后输出简要报告。"

REM Log execution
echo %date% %time% - Optimization task executed >> E:\projects\seed-agent\scripts\optimization_log.txt