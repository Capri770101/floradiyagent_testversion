@echo off
title "Tiaowulan - One-Click Start"
echo ====================================================
echo   Tiaowulan Flower Studio - One-Click Start
echo   (Backend 8080 + Frontend 5173)
echo ====================================================
echo.

cd /d "%~dp0"

echo [1/3] Starting backend (http://127.0.0.1:8080) ...
start "Tiaowulan-Backend" cmd /k "cd /d %~dp0 && python -m uvicorn backend.api:app --host 127.0.0.1 --port 8080"

echo [2/3] Waiting for backend ready ...
set /a tries=0
:wait_health
timeout /t 2 /nobreak >nul
curl -s http://127.0.0.1:8080/health >nul 2>&1
if not errorlevel 1 goto health_ok
set /a tries+=1
if %tries% lss 20 goto wait_health
echo Backend start timeout. Check misc/.env (LLM_API_KEY etc).
goto end

:health_ok
echo       Backend ready.

echo [3/3] Starting frontend (http://localhost:5173) ...
start "Tiaowulan-Frontend" cmd /k "cd /d %~dp0H5 && npm run dev"

timeout /t 5 /nobreak >nul
start "" http://localhost:5173/

echo.
echo ====================================================
echo   Done!
echo   C-end   : http://localhost:5173/
echo   Merchant: http://localhost:5173/merchant.html
echo   Admin   : http://localhost:5173/admin.html
echo.
echo   Demo accounts:
echo   customer_demo / 123456       C-end user
echo   capri_demo    / 123456       merchant (S001)
echo   admin         / admin123456  admin
echo ====================================================
echo.
echo Keep the Backend/Frontend windows open to run the service.
echo This window can be closed anytime.
echo.

:end
pause