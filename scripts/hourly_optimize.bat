@echo off
REM Hourly Code Optimization Task for seed-agent
REM This script launches Qwen Code to perform automatic code optimization
REM 使用 %~dp0 获取脚本所在目录，实现平台无关路径

REM 获取项目根目录（脚本所在目录的上一级）
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set OPTIMIZE_PROMPT=%PROJECT_ROOT%\scripts\optimize_prompt.md
set LOG_FILE=%SCRIPT_DIR%optimization_log.txt

REM 切换到项目根目录
cd /d %PROJECT_ROOT%

REM Read prompt from file and execute with YOLO mode (auto-approve all)
qwen -y "加载 %OPTIMIZE_PROMPT% 并严格根据文档步骤执行。"

REM Log execution
echo %date% %time% - Optimization task executed >> %LOG_FILE%