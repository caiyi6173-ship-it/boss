@echo off
chcp 65001 >nul
echo ══════════════════════════════════════════════════════════
echo   Boss Task Agent - PyInstaller 打包脚本
echo ══════════════════════════════════════════════════════════
echo.

:: 检查 pyinstaller
where pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 pyinstaller，请先执行:
    echo     pip install -r requirements-dev.txt
    pause
    exit /b 1
)

:: 清理旧构建
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo [1/3] 正在打包 exe ...
pyinstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name BossTaskAgent ^
    --collect-all pydantic ^
    --collect-all pydantic_core ^
    --hidden-import openpyxl ^
    --hidden-import tiktoken_ext.openai_public ^
    --hidden-import tiktoken_ext ^
    gui.py

if %ERRORLEVEL% neq 0 (
    echo [错误] PyInstaller 打包失败！
    pause
    exit /b 1
)

echo [2/3] 复制用户文件到发布目录 ...

:: 创建用户目录结构
if not exist "dist\BossTaskAgent\input" mkdir "dist\BossTaskAgent\input"
if not exist "dist\BossTaskAgent\output" mkdir "dist\BossTaskAgent\output"
if not exist "dist\BossTaskAgent\sop_templates" mkdir "dist\BossTaskAgent\sop_templates"

:: 复制配置模板和说明
copy /y ".env.example" "dist\BossTaskAgent\.env" >nul
copy /y "使用说明.txt" "dist\BossTaskAgent\使用说明.txt" >nul

echo [3/3] 完成！
echo.
echo ══════════════════════════════════════════════════════════
echo   发布目录: dist\BossTaskAgent\
echo   主程序:   dist\BossTaskAgent\BossTaskAgent.exe
echo ══════════════════════════════════════════════════════════
echo.
echo 将 dist\BossTaskAgent 整个文件夹发给用户即可。
echo 用户首次使用需要编辑 .env 填入 API Key。
echo.
pause
