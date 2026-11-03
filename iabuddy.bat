@echo off
rem IABuddy: arranca todo (whisper-server, Ollama, backend) y abre la app en el navegador.
chcp 65001 >nul
cd /d "%~dp0"

tasklist /fi "imagename eq whisper-server.exe" | find /i "whisper-server" >nul || (
  echo Arrancando whisper-server...
  start "whisper-server" /min C:\Tools\whisper.cpp\build\bin\Release\whisper-server.exe -m C:\Models\whisper\ggml-large-v3-q5_0.bin -l en --port 8182
)

ollama list >nul 2>&1 && goto ollama_listo
echo Arrancando Ollama...
start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
:esperar_ollama
timeout /t 2 >nul
ollama list >nul 2>&1 || goto esperar_ollama
:ollama_listo

if not exist frontend\dist\index.html (
  echo Compilando el frontend...
  pushd frontend
  call npm install --no-fund --no-audit || goto fallo
  call npm run build || goto fallo
  popd
)

rem Abre el navegador en cuanto el backend responda (en segundo plano).
start "" /b powershell -NoProfile -Command "for($i=0;$i -lt 120;$i++){try{Invoke-WebRequest http://127.0.0.1:8000/api/health -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process http://127.0.0.1:8000; break}catch{Start-Sleep 1}}"

echo Backend en http://127.0.0.1:8000  (Ctrl+C para salir)
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
goto :eof

:fallo
popd
echo No se pudo compilar el frontend.
pause
