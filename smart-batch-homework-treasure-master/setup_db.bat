@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   智能作业批改系统 - 数据库初始化
echo ============================================
echo.

if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

%PYTHON% init_db.py %*
if %errorlevel% neq 0 pause
