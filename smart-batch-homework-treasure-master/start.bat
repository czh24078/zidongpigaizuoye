@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 检查 MySQL 是否已在运行
netstat -ano 2>nul | findstr ":3307 " >nul
if %errorlevel% neq 0 (
    echo [INFO] MySQL 未运行，正在启动...
    start "MySQL-Homework" /MIN "D:\mysql\bin\mysqld.exe" --defaults-file="%~dp0my.ini" --console
    :: 等待 MySQL 就绪
    :wait_mysql
    timeout /t 1 /nobreak >nul
    netstat -ano 2>nul | findstr ":3307 " >nul
    if %errorlevel% neq 0 goto wait_mysql
    echo [INFO] MySQL 已就绪
) else (
    echo [INFO] MySQL 已在运行
)

:: 启动 FastAPI 应用
echo [INFO] 启动应用...
.venv\Scripts\python.exe src\main.py

:: 应用退出后停止 MySQL
echo [INFO] 正在停止 MySQL...
taskkill /FI "WINDOWTITLE eq MySQL-Homework" /F 2>nul
echo [INFO] 已退出
pause
