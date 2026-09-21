@echo off
setlocal
title medical_chat launcher

cd /d E:\medical_chat

echo ==========================================
echo   medical_chat - start all services
echo ==========================================
echo.

echo [1/7] Starting PostgreSQL and Redis...
docker compose up -d postgres redis
if errorlevel 1 (
    echo.
    echo Failed to start Docker services.
    echo Please make sure Docker Desktop is running.
    pause
    exit /b 1
)

echo Waiting 3 seconds for Docker services...
timeout /t 3 /nobreak >nul

echo [2/7] Starting FastAPI...
start "medical_chat - API" powershell -NoExit -Command "Set-Location 'E:\medical_chat\backend'; uv run uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [3/7] Starting Dialog Worker...
start "medical_chat - Dialog Worker" powershell -NoExit -Command "Set-Location 'E:\medical_chat\backend'; uv run celery -A app.celery_app.celery_config:celery_app worker --pool=solo --concurrency=1 --without-gossip --without-mingle --without-heartbeat -Q dialog_queue -n dialog-real@%%h --loglevel=info"

echo [4/7] Starting Schedule Worker...
start "medical_chat - Schedule Worker" powershell -NoExit -Command "Set-Location 'E:\medical_chat\backend'; uv run celery -A app.celery_app.celery_config:celery_app worker --pool=solo --concurrency=1 --without-gossip --without-mingle --without-heartbeat -Q schedule_queue -n schedule-real@%%h --loglevel=info"

echo [5/7] Starting Extraction Worker...
start "medical_chat - Extraction Worker" powershell -NoExit -Command "Set-Location 'E:\medical_chat\backend'; uv run celery -A app.celery_app.celery_config:celery_app worker --pool=solo --concurrency=1 --without-gossip --without-mingle --without-heartbeat -Q extraction_queue -n extraction-real@%%h --loglevel=info"

echo [6/7] Starting Celery Beat...
start "medical_chat - Beat" powershell -NoExit -Command "Set-Location 'E:\medical_chat\backend'; uv run celery -A app.celery_app.celery_config:celery_app beat --loglevel=info"

echo [7/7] Starting Frontend...
start "medical_chat - Frontend" powershell -NoExit -Command "$env:Path += ';C:\Users\Administrator\AppData\Roaming\npm'; Set-Location 'E:\medical_chat\frontend'; pnpm dev"

echo.
echo ==========================================
echo All service windows have been launched.
echo Backend:  http://127.0.0.1:8000
echo Health:   http://127.0.0.1:8000/health
echo Nurse:    http://localhost:3000/nurse
echo Patient:  http://localhost:3000/patient
echo ==========================================
echo.
echo Do not run this launcher twice at the same time.
echo Close each service window with Ctrl+C when you want to stop it.
echo.
pause
endlocal
