@echo off
cd /d "%~dp0"
echo ================================================================
echo  DEPLOY SISTEM HRM PT ABC (KELOMPOK 12) KE RAILWAY
echo  Domain Target: https://hrm-pt-abc-production.up.railway.app
echo ================================================================
echo.
echo [1/2] Login CLI Railway (browser akan terbuka, klik Authorize)...
call railway login
if errorlevel 1 (
    echo Login Railway gagal atau dibatalkan.
    pause
    exit /b 1
)
echo.
echo [2/2] Mengunggah kode dan menjalankan deploy di Railway...
call railway up --project 8f550fe0-20fa-4491-800a-87ce28cd83a1 --environment c50a36e9-44c2-4ca8-a5da-ad5b5aafb1b9 --service fea7f338-4532-4fa6-9592-2f29b9301444 --ci -m "Deploy HRM PT ABC Kelompok 12"
echo.
echo ================================================================
echo  SELESAI! Akses online 24/7 di:
echo  - HRM Utama : https://hrm-pt-abc-production.up.railway.app
echo  - Keuangan  : https://hrm-pt-abc-production.up.railway.app/mock/keuangan/
echo  - CRM       : https://hrm-pt-abc-production.up.railway.app/mock/crm/
echo  - SCM       : https://hrm-pt-abc-production.up.railway.app/mock/scm/
echo ================================================================
pause
