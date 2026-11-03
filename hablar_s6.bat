@echo off
rem Spike S6: conversación por voz en terminal. Espacio = hablar/terminar, q = salir.
chcp 65001 >nul
cd /d "%~dp0"
tasklist /fi "imagename eq whisper-server.exe" | find /i "whisper-server" >nul || (
  echo Arrancando whisper-server...
  start "whisper-server" /min C:\Tools\whisper.cpp\build\bin\Release\whisper-server.exe -m C:\Models\whisper\ggml-large-v3-q5_0.bin -l en --port 8182
  timeout /t 5 >nul
)
ollama list >nul 2>&1 && goto ollama_listo
echo Arrancando Ollama...
start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
:esperar_ollama
timeout /t 2 >nul
ollama list >nul 2>&1 || goto esperar_ollama
:ollama_listo
uv run --group spikes python spikes\s6_roundtrip.py %*
pause
