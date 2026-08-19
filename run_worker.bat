@echo off
cd /d %~dp0
set PYTHONUTF8=1
call E:\anaconda\Scripts\activate.bat guji
python -m worker.main
