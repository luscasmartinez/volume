@echo off
echo ============================================
echo   Volume Platform - Iniciando servidor
echo   http://localhost:8000
echo ============================================
cd backend
C:\Users\Lusca\AppData\Local\Programs\Python\Python314\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
