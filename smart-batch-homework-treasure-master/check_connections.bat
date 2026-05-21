@echo off
chcp 65001 >nul
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -h 127.0.0.1 --protocol=TCP -u root -p -e "SELECT ID, USER, SUBSTRING_INDEX(HOST, ':', 1) AS IP, DB, COMMAND, TIME FROM information_schema.processlist WHERE DB = 'homework_correction' OR USER = 'hw_app' ORDER BY TIME DESC;"
pause

