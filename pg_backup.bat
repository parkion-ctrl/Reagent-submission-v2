@echo off
REM .env 파일에서 REAGENT_PGPASSWORD 값을 읽어 PGPASSWORD로 설정 (비밀번호를
REM 이 파일에 직접 적어두지 않기 위함 - .env는 git에 올라가지 않음)
for /f "usebackq tokens=1,2 delims==" %%A in ("%~dp0.env") do (
    if "%%A"=="REAGENT_PGPASSWORD" set PGPASSWORD=%%B
)
set BACKUP_DIR=C:\Users\ajou\Desktop\autoRe-agent\backups
set DATE=%date:~0,4%%date:~5,2%%date:~8,2%

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

"C:\Program Files\PostgreSQL\18\bin\pg_dump" -h localhost -p 5432 -U postgres -Fc reagent -f "%BACKUP_DIR%\reagent_%DATE%.dump"

if %errorlevel% == 0 (
    echo [%date% %time%] 백업 완료: reagent_%DATE%.dump >> "%BACKUP_DIR%\backup.log"
) else (
    echo [%date% %time%] 백업 실패 (errorlevel: %errorlevel%) >> "%BACKUP_DIR%\backup.log"
)
