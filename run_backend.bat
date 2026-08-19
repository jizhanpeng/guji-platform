@echo off
cd /d %~dp0
set PYTHONUTF8=1
call E:\anaconda\Scripts\activate.bat guji
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
