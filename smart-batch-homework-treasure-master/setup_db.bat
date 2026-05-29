@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   智能作业批改系统 - 数据库初始化
echo ============================================
echo.

:: 配置（按需修改）
set MYSQL_HOST=127.0.0.1
set MYSQL_PORT=3306
set MYSQL_USER=root
set MYSQL_PASSWORD=
set MYSQL_DATABASE=homework

:: 如果未设置密码，提示输入
if "%MYSQL_PASSWORD%"=="" (
    set /p MYSQL_PASSWORD="请输入 MySQL root 密码: "
)

echo.
echo [1/3] 创建数据库...
mysql -h %MYSQL_HOST% -P %MYSQL_PORT% -u %MYSQL_USER% -p%MYSQL_PASSWORD% -e "CREATE DATABASE IF NOT EXISTS %MYSQL_DATABASE% CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 无法连接 MySQL，请检查主机/端口/密码是否正确
    pause
    exit /b 1
)
echo [OK] 数据库已创建

echo [2/3] 导入表结构和数据...
mysql -h %MYSQL_HOST% -P %MYSQL_PORT% -u %MYSQL_USER% -p%MYSQL_PASSWORD% %MYSQL_DATABASE% < "%~dp0homework_dump.sql" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 导入失败
    pause
    exit /b 1
)
echo [OK] 数据导入完成

echo [3/3] 写入 .env 配置...
(
echo # 阿里云百炼 API 配置
echo MODEL_API_KEY=your_api_key_here
echo MODEL_NAME=qwen-vl-max-latest
echo MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
echo.
echo # 应用配置
echo HOST=127.0.0.1
echo PORT=8000
echo DEBUG=False
echo.
echo # 性能优化配置
echo MODEL_MAX_TOKENS=2048
echo MODEL_STREAMING=True
echo.
echo # MySQL 数据库配置
echo MYSQL_HOST=%MYSQL_HOST%
echo MYSQL_PORT=%MYSQL_PORT%
echo MYSQL_USER=%MYSQL_USER%
echo MYSQL_PASSWORD=%MYSQL_PASSWORD%
echo MYSQL_DATABASE=%MYSQL_DATABASE%
echo.
echo # OCR 配置
echo OCR_ENABLED=True
) > "%~dp0.env"

echo [OK] .env 已生成

echo.
echo ============================================
echo   数据库初始化完成！
echo   数据库: %MYSQL_DATABASE%
echo   表数量: 5 (exams, questions, corrections, correction_details, question_bank)
echo   题库数据: 5 条预置题目
echo.
echo   下一步: 在 .env 中填写你的 API Key
echo           MODEL_API_KEY=你的阿里云百炼API密钥
echo ============================================
pause
