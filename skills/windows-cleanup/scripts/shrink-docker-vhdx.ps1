<#
    shrink-docker-vhdx.ps1 —— 把 Docker Desktop 的 vhdx 真正压缩，让 C 盘拿回空间。

    背景：docker system prune 释放的空间只存在于 vhdx 内部；WSL2 的动态 vhdx 只增不减，
    必须「停止 Docker → 让 vhdx 不被占用 → diskpart compact」才能真正归还给 Windows。

    为什么不用 wsl --shutdown：
        本脚本只用 `wsl --terminate <docker 发行版>`，不会关掉其它发行版
        （Ubuntu 等里面可能正跑着 agent 会话）。

    需要管理员（自动 UAC 提权）。Docker 会短暂停止并自动重启，容器/镜像/数据卷不受影响
    （前提：你已按保守方式清理，没有 prune 掉容器和数据卷）。

    用法：
        powershell -NoProfile -ExecutionPolicy Bypass -File shrink-docker-vhdx.ps1
        powershell ... -File shrink-docker-vhdx.ps1 -NoStart      # 不自动重启 Docker
        powershell ... -File shrink-docker-vhdx.ps1 -WhatIf       # 只报告，不改动
#>
[CmdletBinding()]
param(
    [switch]$NoStart,
    [switch]$WhatIf
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
$log = Join-Path $env:USERPROFILE 'docker-vhdx-compact.log'

function Log([string]$m) {
    $line = '{0}  {1}' -f (Get-Date -Format 'HH:mm:ss'), $m
    Write-Host $line
    if (-not $WhatIf) { Add-Content -LiteralPath $log -Value $line -Encoding UTF8 }
}
function SizeGB([string]$p) {
    if (Test-Path -LiteralPath $p) { return [math]::Round((Get-Item -LiteralPath $p).Length / 1GB, 2) }
    return 0
}

# ---------- 定位 vhdx 与发行版 ----------
$candidates = @(
    (Join-Path $env:LOCALAPPDATA 'Docker\wsl\disk\docker_data.vhdx'),
    (Join-Path $env:LOCALAPPDATA 'Docker\wsl\data\ext4.vhdx')
)
$vhdx = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $vhdx) { Write-Host 'ERROR: 找不到 Docker 的 vhdx（Docker Desktop 未安装或使用了自定义位置）。' -ForegroundColor Red; exit 1 }

$distro = 'docker-desktop'
$listed = (& wsl.exe --list --quiet 2>$null) -replace "`0", '' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
if ($listed -notcontains 'docker-desktop') {
    $alt = $listed | Where-Object { $_ -like '*docker*' } | Select-Object -First 1
    if ($alt) { $distro = $alt }
}

Write-Host ("VHDX   : {0}" -f $vhdx)
Write-Host ("发行版 : {0}" -f $distro)

if ($WhatIf) {
    Write-Host ("当前大小: {0} GB" -f (SizeGB $vhdx))
    Write-Host 'WhatIf: 将执行 → 停止 Docker → 终止上述发行版 → 可选开启 sparse → diskpart compact → 重启 Docker'
    Write-Host '（未做任何修改）'
    exit 0
}

# ---------- 提权 ----------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host '申请管理员权限（会弹 UAC，请点“是”）...' -ForegroundColor Yellow
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    if ($NoStart) { $argList += '-NoStart' }
    Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -Verb RunAs
    exit
}

Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
Log '================ Docker VHDX 压缩 ================'
Log ("VHDX       : {0}" -f $vhdx)
Log ("发行版     : {0}" -f $distro)
$before = SizeGB $vhdx
Log ("压缩前     : {0} GB" -f $before)

$dockerExe = Join-Path ${env:ProgramFiles} 'Docker\Docker\resources\bin\docker.exe'

# ---------- 1. 停 Docker ----------
Log '停止 Docker Desktop...'
if (Test-Path -LiteralPath $dockerExe) { & $dockerExe desktop stop 2>&1 | ForEach-Object { Log ("  {0}" -f $_) } }
Get-Process -Name 'Docker Desktop', 'com.docker.backend', 'com.docker.build', 'docker-sandbox' -ErrorAction SilentlyContinue |
    ForEach-Object { Log ("  停止进程 {0} ({1})" -f $_.Name, $_.Id); Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 12

# ---------- 2. 只终止 docker 发行版 ----------
Log '终止 docker 发行版（其它发行版不受影响）...'
& wsl.exe --terminate $distro 2>&1 | ForEach-Object { Log ("  {0}" -f $_) }
Start-Sleep -Seconds 6
& wsl.exe --list --verbose 2>&1 | ForEach-Object { Log ("  {0}" -f $_) }

# ---------- 3. sparse（尽力而为，失败不影响后面的 compact）----------
Log '尝试开启 sparse vhdx（失败可忽略）...'
& wsl.exe --manage $distro --set-sparse true 2>&1 | ForEach-Object { Log ("  {0}" -f $_) }

# ---------- 4. diskpart compact（真正归还空间的一步）----------
Log 'diskpart 压缩中（视大小需要数十秒）...'
$dp = Join-Path $env:TEMP 'diskpart-compact.txt'
@(
    "select vdisk file=`"$vhdx`""
    'attach vdisk readonly'
    'compact vdisk'
    'detach vdisk'
    'exit'
) | Set-Content -LiteralPath $dp -Encoding ASCII
& diskpart.exe /s $dp 2>&1 | Where-Object { $_ -match 'DiskPart|百分比|成功|失败|错误|Virtual|virtual|percent' } |
    ForEach-Object { Log ("  {0}" -f $_) }
Remove-Item -LiteralPath $dp -Force -ErrorAction SilentlyContinue

$after = SizeGB $vhdx
Log ("压缩后     : {0} GB" -f $after)
Log ("本次回收   : {0} GB" -f [math]::Round($before - $after, 2))

# ---------- 5. 重启 Docker 并校验 ----------
if (-not $NoStart) {
    Log '启动 Docker Desktop...'
    Start-Process (Join-Path ${env:ProgramFiles} 'Docker\Docker\Docker Desktop.exe') | Out-Null
    Start-Sleep -Seconds 30
    if (Test-Path -LiteralPath $dockerExe) {
        for ($i = 0; $i -lt 20; $i++) {
            $ver = & $dockerExe info --format '{{.ServerVersion}}' 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) { Log ("引擎已恢复: {0}" -f $ver); break }
            Start-Sleep -Seconds 6
        }
        Log '容器:'
        & $dockerExe ps -a --format '  {{.Names}} | {{.Status}}' 2>&1 | ForEach-Object { Log $_ }
        $vc = (& $dockerExe volume ls -q 2>$null | Measure-Object).Count
        Log ("数据卷数量: {0}" -f $vc)
    }
}
Log 'DONE'
Write-Host ''
Write-Host ("完成，日志: {0}" -f $log) -ForegroundColor Green
