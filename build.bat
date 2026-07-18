@echo off
echo ==========================================================
echo   Boss Task Agent - PyInstaller Build Script
echo ==========================================================
echo.

echo [0/4] Installing build and audio dependencies...
pip install -r requirements-dev.txt -r requirements-audio.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Dependency installation failed!
    pause
    exit /b 1
)

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo [1/4] Building exe...
pyinstaller --noconfirm --onedir --windowed --name BossTaskAgent --collect-all pydantic --collect-all pydantic_core --collect-all customtkinter --collect-all faster_whisper --collect-all ctranslate2 --collect-all av --hidden-import openpyxl --hidden-import tiktoken_ext.openai_public --hidden-import tiktoken_ext gui.py

if %ERRORLEVEL% neq 0 (
    echo [ERROR] PyInstaller build failed!
    pause
    exit /b 1
)

echo [2/4] Copying user assets...
if not exist "dist\BossTaskAgent\input" mkdir "dist\BossTaskAgent\input"
if not exist "dist\BossTaskAgent\output" mkdir "dist\BossTaskAgent\output"
if not exist "dist\BossTaskAgent\sop_templates" mkdir "dist\BossTaskAgent\sop_templates"

copy /y ".env.example" "dist\BossTaskAgent\.env" >nul
copy /y "使用说明.txt" "dist\BossTaskAgent\使用说明.txt" >nul
if exist "domain_glossary.json" copy /y "domain_glossary.json" "dist\BossTaskAgent\domain_glossary.json" >nul
if exist "resources" (
    if not exist "dist\BossTaskAgent\resources" mkdir "dist\BossTaskAgent\resources"
    xcopy /e /y /q "resources" "dist\BossTaskAgent\resources\" >nul
)

echo [3/4] Audio transcription support included.
echo [4/4] Done!
echo.
echo ==========================================================
echo   Output folder: dist\BossTaskAgent\
echo   Executable:    dist\BossTaskAgent\BossTaskAgent.exe
echo ==========================================================
echo.
pause
