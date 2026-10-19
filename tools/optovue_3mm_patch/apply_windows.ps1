# ARIAKE OCTA — Optovue 3mm patch (Windows v1.2.3)
#Requires -Version 5.1
param(
    [Parameter(Position = 0)]
    [string]$Target
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Payload = Join-Path $Here "payload"

function Pause-End {
    if ($env:ARIAKE_PATCH_SKIP_PAUSE -ne "1") {
        Write-Host ""
        Read-Host "Enterキーで閉じる" | Out-Null
    }
}

function Fail([string]$Message) {
    Write-Host "[エラー] $Message" -ForegroundColor Red
    Pause-End
    exit 1
}

Write-Host ""
Write-Host "ARIAKE OCTA — Optovue 3mm パッチ（Windows）"
Write-Host ""

if (-not (Test-Path -LiteralPath $Payload)) {
    Fail "payload フォルダがありません。ZIP を展開したフォルダで実行してください。"
}

if (-not $Target) {
    Write-Host "ARIAKE_OCTA.exe があるフォルダを入力してください。"
    Write-Host "例: C:\Users\name\Desktop\ARIAKE_OCTA"
    $Target = Read-Host "フォルダ"
}
$Target = $Target.Trim().Trim('"')
if (-not $Target) {
    Fail "フォルダが指定されていません。"
}

if (Test-Path -LiteralPath $Target -PathType Leaf) {
    $Target = Split-Path -Parent $Target
}
$exe = Join-Path $Target "ARIAKE_OCTA.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    Fail "ARIAKE_OCTA.exe が見つかりません: $Target"
}

$internal = Join-Path $Target "_internal"
$sentinel = Join-Path $internal "src\core\mnv_pipeline.py"
if (-not (Test-Path -LiteralPath $sentinel)) {
    Fail "v1.2.3 の Windows 版ではありません（_internal\src\core\mnv_pipeline.py がありません）。"
}

$running = Get-Process -Name "ARIAKE_OCTA" -ErrorAction SilentlyContinue
if ($running) {
    Fail "ARIAKE_OCTA が起動中です。終了してから、もう一度実行してください。"
}

Write-Host "[1/2] Python と参照 JSON を差し替え..."
$payloadRoot = (Resolve-Path -LiteralPath $Payload).Path.TrimEnd('\', '/')
$count = 0
Get-ChildItem -LiteralPath $Payload -Recurse -File | ForEach-Object {
    $full = $_.FullName
    $rel = $full.Substring($payloadRoot.Length).TrimStart('\', '/')
    $dest = Join-Path $internal ($rel -replace '/', '\')
    $destDir = Split-Path -Parent $dest
    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    }
    Copy-Item -LiteralPath $full -Destination $dest -Force
    $script:count += 1
    if ($_.Extension -eq ".py") {
        $pyc = [System.IO.Path]::ChangeExtension($dest, ".pyc")
        if (Test-Path -LiteralPath $pyc) {
            Remove-Item -LiteralPath $pyc -Force
        }
        $cache = Join-Path $destDir "__pycache__"
        $base = [System.IO.Path]::GetFileNameWithoutExtension($dest)
        if (Test-Path -LiteralPath $cache) {
            Get-ChildItem -LiteralPath $cache -Filter ($base + ".cpython-*.pyc") -ErrorAction SilentlyContinue |
                Remove-Item -Force
        }
    }
}
Write-Host "       $count ファイル"
Write-Host "[2/2] 完了"
Write-Host ""
Write-Host "3 mm (Optovue) と 3 mm (Zeiss HD) が起動ウィザードに出ます。"
Write-Host "数値の 3.0 と、手入力の 3 mm は Zeiss HD のままです。"
Write-Host "ARIAKE_OCTA.exe を起動してください。"
Pause-End
