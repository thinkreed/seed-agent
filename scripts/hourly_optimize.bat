@echo off
REM Hourly Code Optimization Task for seed-agent
REM This script launches Qwen Code to perform automatic code optimization

cd /d E:\projects\seed-agent

REM Read prompt from file and execute with YOLO mode (auto-approve all)
qwen -y "加载 E:\projects\seed-agent\scripts\optimize_prompt.md 并严格根据文档步骤执行。"

REM Log execution
echo %date% %time% - Optimization task executed >> E:\projects\seed-agent\scripts\optimization_log.txt