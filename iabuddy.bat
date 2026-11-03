@echo off
rem IABuddy: arranca todo (whisper-server, Ollama, backend) y abre la app en el navegador.
chcp 65001 >nul
cd /d "%~dp0"

tasklist /fi "imagename eq whisper-server.exe" | find /i "whisper-server" >nul || (
  echo Arrancando whisper-server...
  start "whisper-server" /min C:\Tools\whisper.cpp\build\bin\Release\whisper-server.exe -m C:\Models\whisper\ggml-large-v3-q5_0.bin -l en --port 8182
)

rem Ollama propio en el puerto 11435 con 2 peticiones en paralelo (compañero + tutor a la vez).
rem El de la bandeja (11434) se cierra: si los dos cargan gemma, no cabe en la VRAM (Fase 2).
rem No se toca su configuración; vuelve a abrirse con el equipo o desde el menú Inicio.
powershell -NoProfile -Command "Get-Process 'ollama app' -ErrorAction SilentlyContinue | Stop-Process -Force; Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
call :ollama_vivo && goto ollama_listo
echo Arrancando Ollama (puerto 11435, 2 en paralelo)...
start "ollama-iabuddy" /min cmd /c "set "OLLAMA_HOST=127.0.0.1:11435"&& set "OLLAMA_NUM_PARALLEL=2"&& ollama serve"
:esperar_ollama
timeout /t 2 >nul
call :ollama_vivo || goto esperar_ollama
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
goto :eof

:ollama_vivo
powershell -NoProfile -Command "try { Invoke-WebRequest http://127.0.0.1:11435/api/version -UseBasicParsing -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }"
exit /b %errorlevel%
