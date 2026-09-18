param([switch]$CheckOnly, [switch]$Example, [switch]$Cpu)
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
try {
    $Python = Get-Command python -ErrorAction Stop
    & $Python.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
    if ($LASTEXITCODE -ne 0) { throw '需要 Python 3.10 或更新版本。' }
    $null = Get-Command ollama -ErrorAction Stop
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_NO_CLOUD = '1'
    $env:OLLAMA_DEBUG_LOG_REQUESTS = 'false'
    $env:OLLAMA_NOPRUNE = 'true'
    if ($Cpu) { $env:GZL_OLLAMA_CPU = '1' }
    $modelCheck = "import json,urllib.request; o=urllib.request.build_opener(urllib.request.ProxyHandler({})); d=json.loads(o.open('http://127.0.0.1:11434/api/tags',timeout=3).read()); raise SystemExit(0 if any(m['name']=='qwen2.5:3b' for m in d['models']) else 2)"
    & $Python.Source -c $modelCheck 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Ollama 未启动或缺少 qwen2.5:3b。请先运行 ollama serve；本脚本不会下载模型。' }
    $persona = Join-Path $ScriptDir 'private_data\persona.json'
    if (-not (Test-Path -LiteralPath $persona) -and -not $Example) { throw '尚未生成角色。完成本地蒸馏后重试，或使用 -Example 验证公开示例。' }
    foreach ($port in @(8765, 8888)) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
        try { $listener.Start() } catch { throw "端口 $port 已被占用，请先关闭占用服务。" } finally { $listener.Stop() }
    }
    Write-Host '环境检查通过。仅使用本机模型，不需要管理员权限。'
    if ($CheckOnly) { exit 0 }
    $previewPath = Join-Path $ScriptDir 'preview.py'
    $previewProcess = Start-Process -FilePath $Python.Source -ArgumentList @('"' + $previewPath + '"') -WindowStyle Hidden -PassThru
    Write-Host '游戏地址：http://127.0.0.1:8888/；按 Ctrl+C 停止 API。'
    try { & $Python.Source (Join-Path $ScriptDir 'server.py') }
    finally { if (-not $previewProcess.HasExited) { Stop-Process -Id $previewProcess.Id } }
} catch {
    Write-Host '启动失败：请确认 Python、Ollama、模型及角色文件可用。' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    exit 1
}
