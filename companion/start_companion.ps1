$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Checking Python..."
python --version

Write-Host "Checking Ollama..."
ollama list

if (-not (Test-Path (Join-Path $ScriptDir "private_data\persona.json"))) {
    Write-Warning "No distilled persona found yet. The server will use the public example persona."
}

Write-Host "Starting the private companion at http://127.0.0.1:8765"
python (Join-Path $ScriptDir "server.py")
