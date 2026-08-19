@echo off
:: 同时拉起 backend + worker + frontend（三个窗口）
start "guji-backend" cmd /k %~dp0run_backend.bat
start "guji-worker" cmd /k %~dp0run_worker.bat
start "guji-frontend" cmd /k %~dp0run_frontend.bat
