@echo off
chcp 65001 >nul
cd /d "%~dp0"

netstat -ano 2>nul | findstr ":3307 " >nul
if %errorlevel% neq 0 (
    echo [INFO] MySQL not running, starting...
    start "MySQL-Homework" /MIN "D:\mysql\bin\mysqld.exe" --defaults-file="%~dp0my.ini" --console
    :wait_mysql
    timeout /t 1 /nobreak >nul
    netstat -ano 2>nul | findstr ":3307 " >nul
    if %errorlevel% neq 0 goto wait_mysql
    echo [INFO] MySQL ready
) else (
    echo [INFO] MySQL already running
)

echo [INFO] Starting app...
.venv\Scripts\python.exe src\main.py

echo [INFO] Stopping MySQL...
taskkill /FI "WINDOWTITLE eq MySQL-Homework" /F 2>nul
echo [INFO] Done
pause
