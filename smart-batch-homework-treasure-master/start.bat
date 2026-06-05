@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "MYSQL_EXE=C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe"
set "MYSQL_PORT=3307"
set "PYTHON=.venv\Scripts\python.exe"

echo ============================================
echo   Homework Grading System
echo ============================================
echo.

REM -- 1. Start MySQL --
netstat -ano 2>nul | findstr ":%MYSQL_PORT% " >nul
if %errorlevel% neq 0 (
    echo [1/2] Starting MySQL...
    start "MySQL-Homework" /MIN "%MYSQL_EXE%" --defaults-file="%~dp0my.ini"
    call :wait_mysql
    echo       Ready
) else (
    echo [1/2] MySQL already running
)

REM -- 2. Start app --
echo [2/2] Starting app...
echo ============================================
echo.
%PYTHON% src/main.py

REM -- Cleanup --
echo.
echo Stopping MySQL...
taskkill /FI "WINDOWTITLE eq MySQL-Homework" /F 2>nul
echo Stopped
pause
exit /b 0

REM -- Subroutines --
:wait_mysql
timeout /t 2 /nobreak >nul
netstat -ano 2>nul | findstr ":%MYSQL_PORT% " >nul
if %errorlevel% neq 0 goto wait_mysql
exit /b 0
