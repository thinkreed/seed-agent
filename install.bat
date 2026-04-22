@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

title Seed Agent 安装程序

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║      Seed Agent 一键安装程序            ║
echo  ╚══════════════════════════════════════════╝
echo.

:: 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: ============================================
:: 第一步：检查并自动安装 Python
:: ============================================
echo [步骤 1/5] 检查 Python 环境...
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [!] 未检测到 Python，正在准备自动安装...
    echo.
    
    :: 检测系统架构
    if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
        set "PY_ARCH=amd64"
        set "PY_INSTALLER=python-3.11.9-amd64.exe"
    ) else (
        set "PY_ARCH=win32"
        set "PY_INSTALLER=python-3.11.9.exe"
    )
    
    set "PY_DOWNLOAD_URL=https://mirrors.aliyun.com/python/3.11.9/%PY_INSTALLER%"
    set "PY_INSTALLER_PATH=%TEMP%\%PY_INSTALLER%"
    
    echo     下载地址: %PY_DOWNLOAD_URL%
    echo     保存位置: %PY_INSTALLER_PATH%
    echo.
    echo [下载中] 正在下载 Python 安装包，请稍候...
    
    :: 使用 PowerShell 下载
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PY_DOWNLOAD_URL%' -OutFile '%PY_INSTALLER_PATH%' -UseBasicParsing}" 2>nul
    
    if not exist "%PY_INSTALLER_PATH%" (
        echo.
        echo [错误] Python 下载失败，请检查网络连接
        echo        您也可以手动下载安装: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    
    echo [OK] 下载完成，正在安装 Python...
    echo.
    echo [重要] 安装窗口中请勾选 "Add Python to PATH" 选项！
    echo.
    
    :: 静默安装 Python，自动添加到 PATH
    "%PY_INSTALLER_PATH%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_pip=1
    
    :: 等待安装完成
    timeout /t 10 /nobreak >nul
    
    :: 刷新环境变量
    call :refresh_path
    
    :: 再次检查
    python --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [!] Python 安装完成，但需要重启电脑才能生效
        echo     请重启电脑后重新运行此安装脚本
        pause
        exit /b 0
    )
    
    :: 清理安装包
    del "%PY_INSTALLER_PATH%" 2>nul
)

:: 显示 Python 版本
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python 已安装，版本: %PY_VER%
echo.

:: ============================================
:: 第二步：配置 pip 阿里云镜像
:: ============================================
echo [步骤 2/5] 配置 pip 阿里云镜像源...
echo.

set "PIP_INI=%APPDATA%\pip\pip.ini"

if not exist "%APPDATA%\pip" mkdir "%APPDATA%\pip"

(
echo [global]
echo index-url = https://mirrors.aliyun.com/pypi/simple/
echo trusted-host = mirrors.aliyun.com
echo.
echo [install]
echo trusted-host = mirrors.aliyun.com
) > "%PIP_INI%"

echo [OK] pip 镜像已配置为阿里云
echo     配置文件: %PIP_INI%
echo.

:: ============================================
:: 第三步：升级 pip
:: ============================================
echo [步骤 3/5] 升级 pip 到最新版本...
echo.

python -m pip install --upgrade pip -q 2>nul
if errorlevel 1 (
    echo [警告] pip 升级失败，但将继续安装...
) else (
    for /f "tokens=2 delims= " %%v in ('python -m pip --version 2^>^&1') do set PIP_VER=%%v
    echo [OK] pip 已升级到最新版本
)
echo.

:: ============================================
:: 第四步：安装项目依赖
:: ============================================
echo [步骤 4/5] 安装 Seed Agent 依赖...
echo.

if not exist "requirements.txt" (
    echo [错误] 未找到 requirements.txt 文件
    echo        请确保在 Seed Agent 项目目录中运行此脚本
    pause
    exit /b 1
)

echo [安装中] 这可能需要几分钟，请耐心等待...
echo.

python -m pip install -r requirements.txt -q 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败
    echo        请检查网络连接后重试
    pause
    exit /b 1
)

echo [OK] 所有依赖已安装完成
echo.

:: ============================================
:: 第五步：初始化配置文件
:: ============================================
echo [步骤 5/5] 初始化配置文件...
echo.

set "SEED_HOME=%USERPROFILE%\.seed"

:: 创建目录结构
if not exist "%SEED_HOME%" mkdir "%SEED_HOME%"
if not exist "%SEED_HOME%\memory" mkdir "%SEED_HOME%\memory"
if not exist "%SEED_HOME%\memory\raw" mkdir "%SEED_HOME%\memory\raw"
if not exist "%SEED_HOME%\tasks" mkdir "%SEED_HOME%\tasks"
if not exist "%SEED_HOME%\logs" mkdir "%SEED_HOME%\logs"

echo [OK] 配置目录已创建: %SEED_HOME%

:: 创建配置文件
if not exist "%SEED_HOME%\config.json" (
    (
    echo {
    echo   "models": {
    echo     "bailian": {
    echo       "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
    echo       "apiKey": "${BAILIAN_API_KEY}",
    echo       "api": "openai-completions",
    echo       "models": [
    echo         {
    echo           "id": "qwen-coder-plus",
    echo           "name": "Qwen Coder Plus",
    echo           "contextWindow": 100000,
    echo           "maxTokens": 4096
    echo         }
    echo       ]
    echo     }
    echo   },
    echo   "agents": {
    echo     "defaults": {
    echo       "defaults": {
    echo         "primary": "bailian/qwen-coder-plus"
    echo       }
    echo     }
    echo   }
    echo }
    ) > "%SEED_HOME%\config.json"
    echo [OK] 配置文件已创建
) else (
    echo [OK] 配置文件已存在
)

:: 创建 .env 示例文件
if not exist "%SCRIPT_DIR%.env.example" (
    (
    echo # Seed Agent 环境变量配置
    echo # 复制此文件为 .env 并填入你的 API Key
    echo.
    echo # 百炼 API Key ^(阿里云^)
    echo BAILIAN_API_KEY=your-api-key-here
    echo.
    echo # OpenAI API Key ^(可选^)
    echo OPENAI_API_KEY=your-openai-key-here
    ) > "%SCRIPT_DIR%.env.example"
    echo [OK] 环境变量示例文件已创建
)

echo.

:: ============================================
:: 安装完成
:: ============================================
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║           安装完成！                    ║
echo  ╚══════════════════════════════════════════╝
echo.
echo.
echo  ┌──────────────────────────────────────────┐
echo  │  下一步：配置 API Key                    │
echo  └──────────────────────────────────────────┘
echo.
echo  方法 1：设置系统环境变量（推荐）
echo         - 右键"此电脑" - 属性 - 高级系统设置
echo         - 环境变量 - 新建用户变量
echo         - 变量名: BAILIAN_API_KEY
echo         - 变量值: 你的API密钥
echo.
echo  方法 2：使用 .env 文件
echo         - 复制 .env.example 为 .env
echo         - 编辑 .env 文件，填入你的 API Key
echo.
echo  ┌──────────────────────────────────────────┐
echo  │  启动方式                               │
echo  └──────────────────────────────────────────┘
echo.
echo  双击运行 start.bat 即可启动 Seed Agent
echo.
echo  或者打开命令行运行：
echo      cd /d "%SCRIPT_DIR%"
echo      python main.py
echo.
echo ================================================
echo.

:: 创建启动脚本
(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "%SCRIPT_DIR%"
echo title Seed Agent
echo echo.
echo echo 正在启动 Seed Agent...
echo echo.
echo python main.py
echo pause
) > "%SCRIPT_DIR%start.bat"

echo [OK] 已创建 start.bat 启动脚本
echo.
pause
exit /b 0

:: ============================================
:: 子程序：刷新环境变量
:: ============================================
:refresh_path
:: 从注册表重新读取 PATH
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
set "PATH=%USR_PATH%;%SYS_PATH%"
goto :eof