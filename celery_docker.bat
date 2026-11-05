@echo off
REM Lance Redis + Celery (worker et beat) dans Docker Desktop.
REM Double-clic, ou dans un terminal :  celery_docker.bat
cd /d "%~dp0"
docker compose -f docker-compose.celery.yml up -d
echo.
echo Celery demarre. Logs en direct (Ctrl+C pour quitter les logs, Celery continue) :
docker compose -f docker-compose.celery.yml logs -f celery
