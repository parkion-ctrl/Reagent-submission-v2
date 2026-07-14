@echo off
net start postgresql-x64-18
cd /d C:\Users\ajou\Desktop\autoRe-agent
call C:\Users\ajou\anaconda3\Scripts\activate.bat
start /MIN "" python run_server.py
