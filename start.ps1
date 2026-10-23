# ============================================================================
#  密态智图 · MiA-RAG 一键启动 / 停止（Windows PowerShell）
#
#  启动：
#      powershell -ExecutionPolicy Bypass -File .\start.ps1
#  停止：
#      powershell -ExecutionPolicy Bypass -File .\start.ps1 -Stop
#
#  会启动四个服务：
#      1. 后端主 API      backend/api/main.py        :6006
#      2. 联邦节点服务    backend/node_server.py      :6008
#      3. 中心聚合服务    frontend/central_server.py  :9000
#      4. 前端 Next.js    frontend/                  :3000
#
#  日志写入 .logs\，PID 写入 .logs\pids.json。
#  关闭本窗口或按 Ctrl+C，会一并停止所有服务。
#
#  注意：本文件保存为 UTF-8 with BOM，Windows PowerShell 5.1 才能正确读取中文。
# ============================================================================

param(
  [int]$BackendPort = 6006,
  [int]$NodePort = 6008,
  [int]$CentralPort = 9000,
  [int]$FrontendPort = 3000,
  [switch]$Stop,
  [switch]$NoWait
)

$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$LogDir = Join-Path $Root ".logs"

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }
function Ok($msg) { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [注意] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "  [错误] $msg" -ForegroundColor Red; exit 1 }

try {
  New-Item -ItemType Directory -Force -Path $LogDir -ErrorAction Stop | Out-Null
} catch {
  $LogDir = Join-Path $env:TEMP ("mia-rag-logs-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
  New-Item -ItemType Directory -Force -Path $LogDir -ErrorAction SilentlyContinue | Out-Null
}
$PidFile = Join-Path $LogDir "pids.json"

function Resolve-Pnpm {
  $g = Get-Command pnpm -ErrorAction SilentlyContinue
  if (-not $g) { return $null }
  if ($g.CommandType -eq "Application") { return $g.Source }
  $dir = Split-Path $g.Source -Parent
  foreach ($name in @("pnpm.cmd", "pnpm.exe", "pnpm.bat")) {
    $cand = Join-Path $dir $name
    if (Test-Path $cand) { return $cand }
  }
  return $null
}

function Stop-Tree($procId) {
  if (-not $procId) { return }
  Get-CimInstance Win32_Process -Filter "ParentProcessId=$procId" -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

# ============================================================================
#  停止模式
# ============================================================================
if ($Stop) {
  Say "============================================================" Cyan
  Say "  停止 MiA-RAG 服务" Cyan
  Say "============================================================" Cyan
  $killed = 0

  if (Test-Path $PidFile) {
    try {
      $ids = Get-Content $PidFile -Raw | ConvertFrom-Json
      foreach ($name in @("frontend", "central", "node", "backend")) {
        $procId = $ids.$name
        if ($procId) {
          $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
          if ($p) {
            Stop-Tree $procId
            Ok "已停止 $name (PID $procId)"
            $killed++
          }
        }
      }
    } catch { Warn "读取 pids.json 失败：$($_.Exception.Message)" }
  }

  foreach ($port in @($FrontendPort, $CentralPort, $NodePort, $BackendPort)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($x in $conn) {
      $p = Get-Process -Id $x.OwningProcess -ErrorAction SilentlyContinue
      if ($p) {
        Stop-Process -Id $x.OwningProcess -Force -ErrorAction SilentlyContinue
        Ok "端口 $port 已释放（$($p.ProcessName) PID $($x.OwningProcess)）"
        $killed++
      }
    }
  }

  Say ""
  if ($killed) { Say "共停止 $killed 个进程。" Green } else { Say "没有找到正在运行的服务。" Yellow }
  exit 0
}

# ============================================================================
#  启动模式
# ============================================================================
Say "============================================================" Cyan
Say "  密态智图 · MiA-RAG 一键启动" Cyan
Say "============================================================" Cyan
Say ""

if (-not (Test-Path $BackendDir)) { Fail "找不到后端目录：$BackendDir" }
if (-not (Test-Path $FrontendDir)) { Fail "找不到前端目录：$FrontendDir" }
if (-not (Test-Path (Join-Path $BackendDir ".env"))) {
  Fail "缺少 backend\.env，请先执行： copy backend\.env.example backend\.env  并填写密钥"
}
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
  Fail "前端依赖未安装，请先执行： cd frontend; pnpm install; cd .."
}

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { Fail "找不到 python，请确认已加入 PATH 并激活虚拟环境" }
$pnpm = Resolve-Pnpm
if (-not $pnpm) { Fail "找不到 pnpm，请先执行： npm i -g pnpm@10.6.1" }
Ok "python : $py"
Ok "pnpm   : $pnpm"
Ok "日志   : $LogDir"

# ── 加载 backend/.env ───────────────────────────────────────────────────────
Get-Content (Join-Path $BackendDir ".env") -Encoding UTF8 | ForEach-Object {
  $line = $_.Trim()
  if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
    $i = $line.IndexOf("=")
    $k = $line.Substring(0, $i).Trim()
    $v = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
    Set-Item -Path "Env:$k" -Value $v
  }
}

if (-not $env:EMBEDDING_API_KEY -and $env:DASHSCOPE_API_KEY) {
  $env:EMBEDDING_API_KEY = $env:DASHSCOPE_API_KEY
}
if (-not $env:DEEPSEEK_API_KEY) { Warn "DEEPSEEK_API_KEY 为空，问答与摘要会失败" }
if (-not $env:EMBEDDING_API_KEY) { Warn "EMBEDDING_API_KEY / DASHSCOPE_API_KEY 为空，检索会失败" }

if (-not $env:TIKTOKEN_CACHE_DIR) {
  $env:TIKTOKEN_CACHE_DIR = Join-Path $BackendDir "data\tiktoken_cache"
}
if (-not (Test-Path $env:TIKTOKEN_CACHE_DIR)) {
  Fail "找不到 tiktoken 缓存目录：$env:TIKTOKEN_CACHE_DIR（项目应自带 backend\data\tiktoken_cache）"
}
Ok "tiktoken 缓存：$env:TIKTOKEN_CACHE_DIR"

$env:SKIP_DOC_LOAD = "1"
$env:PYTHONPATH = "$BackendDir\LightRAG;$BackendDir;$env:PYTHONPATH"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

# ── PostgreSQL（可选）───────────────────────────────────────────────────────
Say ""
Say "[1/5] 检查 PostgreSQL ..."
$pg = Get-Service -Name "*postgres*" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pg) {
  Warn "未发现 PostgreSQL 服务；前端聊天历史需使用 auto 或 mock 模式"
} elseif ($pg.Status -ne "Running") {
  Warn "PostgreSQL 未运行（$($pg.Name)）；如需持久化聊天历史请先启动"
} else {
  Ok "$($pg.Name) 正在运行"
}

# ── 端口检查 ────────────────────────────────────────────────────────────────
Say ""
Say "[2/5] 检查端口占用 ..."
foreach ($port in @($BackendPort, $NodePort, $CentralPort, $FrontendPort)) {
  $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if ($busy) {
    $proc = Get-Process -Id $busy[0].OwningProcess -ErrorAction SilentlyContinue
    Warn "端口 $port 已被占用（PID $($busy[0].OwningProcess) $($proc.ProcessName)）"
    Warn "可先执行： .\start.ps1 -Stop"
  } else {
    Ok "端口 $port 空闲"
  }
}

# ── 启动服务 ────────────────────────────────────────────────────────────────
function Start-Service-Process($name, $file, $arguments, $workingDir) {
  $out = Join-Path $LogDir "$name.log"
  $err = Join-Path $LogDir "$name.err.log"
  try {
    $proc = Start-Process -FilePath $file -ArgumentList $arguments `
      -WorkingDirectory $workingDir -PassThru -NoNewWindow `
      -RedirectStandardOutput $out -RedirectStandardError $err -ErrorAction Stop
    Start-Sleep -Milliseconds 900
    if ($proc.HasExited) {
      Warn "$name 启动后立即退出（退出码 $($proc.ExitCode)），日志：$err"
    } else {
      Ok "$name 已启动（PID $($proc.Id)）"
    }
    return $proc
  } catch {
    Warn "$name 启动失败：$($_.Exception.Message)"
    return $null
  }
}

Say ""
Say "[3/5] 启动后端与联邦节点 ..."
$backendProc = Start-Service-Process "backend" $py @("-B", "-m", "api.main", "--host", "127.0.0.1", "--port", "$BackendPort") $BackendDir
$nodeProc = Start-Service-Process "node" $py @("-B", "node_server.py", "--host", "127.0.0.1", "--port", "$NodePort") $BackendDir

Say ""
Say "[4/5] 启动中心聚合与前端 ..."
$centralProc = Start-Service-Process "central" $py @("-B", "central_server.py", "--port", "$CentralPort", "--node", "local=http://127.0.0.1:$NodePort") $FrontendDir
$frontendProc = Start-Service-Process "frontend" $pnpm @("--filter", "main-platform", "dev", "--", "--port", "$FrontendPort") $FrontendDir

@{
  backend      = if ($backendProc) { $backendProc.Id } else { 0 }
  node         = if ($nodeProc) { $nodeProc.Id } else { 0 }
  central      = if ($centralProc) { $centralProc.Id } else { 0 }
  frontend     = if ($frontendProc) { $frontendProc.Id } else { 0 }
  backendPort  = $BackendPort
  nodePort     = $NodePort
  centralPort  = $CentralPort
  frontendPort = $FrontendPort
  logDir       = $LogDir
  started      = (Get-Date).ToString("s")
} | ConvertTo-Json | Set-Content $PidFile -Encoding UTF8

if ($NoWait) {
  Say ""
  Say "已启动（未等待就绪）。前端： http://localhost:$FrontendPort" Green
  exit 0
}

# ── 等待就绪 ────────────────────────────────────────────────────────────────
Say ""
Say "[5/5] 等待服务就绪 ..."

$backendReady = $false
for ($i = 1; $i -le 60; $i++) {
  try {
    $r = Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/health" -TimeoutSec 3
    if ($r.status -eq "ok") { $backendReady = $true; break }
  } catch { }
  Start-Sleep -Seconds 1
}
if ($backendReady) { Ok "后端就绪（$i 秒）" } else { Warn "后端 60 秒内未就绪，请看 $LogDir\backend.err.log" }

$nodeReady = $false
for ($i = 1; $i -le 45; $i++) {
  try {
    Invoke-RestMethod "http://127.0.0.1:$NodePort/health" -TimeoutSec 3 | Out-Null
    $nodeReady = $true; break
  } catch { }
  Start-Sleep -Seconds 1
}
if ($nodeReady) { Ok "节点服务就绪（$i 秒）" } else { Warn "节点服务 45 秒内未就绪，请看 $LogDir\node.err.log" }

$centralReady = $false
for ($i = 1; $i -le 45; $i++) {
  try {
    Invoke-RestMethod "http://127.0.0.1:$CentralPort/health" -TimeoutSec 3 | Out-Null
    $centralReady = $true; break
  } catch { }
  Start-Sleep -Seconds 1
}
if ($centralReady) { Ok "中心聚合就绪（$i 秒）" } else { Warn "中心聚合 45 秒内未就绪，请看 $LogDir\central.err.log" }

$frontendReady = $false
for ($i = 1; $i -le 120; $i++) {
  try {
    $r = Invoke-WebRequest "http://localhost:$FrontendPort/" -TimeoutSec 3 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $frontendReady = $true; break }
  } catch { }
  Start-Sleep -Seconds 1
}
if ($frontendReady) { Ok "前端就绪（$i 秒）" } else { Warn "前端 120 秒内未就绪，请看 $LogDir\frontend.err.log" }

Say ""
Say "============================================================" Green
Say "  启动完成" Green
Say "============================================================" Green
Say "  前端界面 : http://localhost:$FrontendPort"
Say "  后端 API : http://127.0.0.1:$BackendPort"
Say "  API 文档 : http://127.0.0.1:$BackendPort/docs"
Say "  节点服务 : http://127.0.0.1:$NodePort"
Say "  中心聚合 : http://127.0.0.1:$CentralPort"
Say "  登录账号 : admin / admin123456"
Say ""
Say "  日志目录 : $LogDir" Cyan
Say ""
Say "  停止服务： powershell -ExecutionPolicy Bypass -File .\start.ps1 -Stop"
Say "============================================================" Green
Say ""
Say "服务正在运行 —— 保持本窗口打开；关闭窗口或按 Ctrl+C 会一并停止。" Green
Say ""

# ── 前台驻留：任一服务退出或 Ctrl+C 就统一收尾 ────────────────────────────
function Stop-All {
  Say ""
  Say "正在停止服务 ..." Cyan
  foreach ($p in @($backendProc, $nodeProc, $centralProc, $frontendProc)) {
    if ($p -and -not $p.HasExited) {
      Stop-Tree $p.Id
      Ok "已停止 PID $($p.Id)"
    }
  }
}

try {
  while ($true) {
    Start-Sleep -Seconds 2
    if ($backendProc -and $backendProc.HasExited) { Warn "后端已退出，请看日志"; break }
    if ($nodeProc -and $nodeProc.HasExited) { Warn "节点服务已退出，请看日志"; break }
    if ($centralProc -and $centralProc.HasExited) { Warn "中心聚合已退出，请看日志"; break }
    if ($frontendProc -and $frontendProc.HasExited) { Warn "前端已退出，请看日志"; break }
  }
} finally {
  Stop-All
}
