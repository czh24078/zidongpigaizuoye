@echo off
echo ============================================
echo  C 盘清理脚本 - 需要管理员权限运行
echo ============================================
echo.

echo [1/3] 清理 MySQL 旧组件 (约 2.0 GB)...
if exist "C:\Program Files\MySQL\MySQL Router 8.0" (
    rmdir /s /q "C:\Program Files\MySQL\MySQL Router 8.0" && echo   Router 8.0 已删除
)
if exist "C:\Program Files\MySQL\MySQL Server 8.0" (
    rmdir /s /q "C:\Program Files\MySQL\MySQL Server 8.0" && echo   Server 8.0 已删除
)
if exist "C:\Program Files\MySQL\MySQL Server 8.4" (
    rmdir /s /q "C:\Program Files\MySQL\MySQL Server 8.4" && echo   Server 8.4 已删除 (已移至 D 盘)
)
if exist "C:\Program Files\MySQL\MySQL Shell 8.0" (
    rmdir /s /q "C:\Program Files\MySQL\MySQL Shell 8.0" && echo   Shell 8.0 已删除
)
if exist "C:\Program Files\MySQL\MySQL Workbench 8.0" (
    rmdir /s /q "C:\Program Files\MySQL\MySQL Workbench 8.0" && echo   Workbench 8.0 已删除
)

echo.
echo [2/3] 清理 Docker 残留...
if exist "C:\Program Files\Docker" (
    rmdir /s /q "C:\Program Files\Docker" 2>nul && echo   Docker 已删除 || echo   Docker 残留（需重启后自动清理）
)

echo.
echo [3/3] 清理 Windows 临时文件...
del /f /s /q "%TEMP%\*" 2>nul
echo   完成

echo.
echo ============================================
echo  清理完成！
echo ============================================
pause
