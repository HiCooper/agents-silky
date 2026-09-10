<#
    clean.ps1 —— 按 tier 执行 C: 盘清理。

    重要：本脚本 **只负责执行**。让用户勾选确认是 agent 的职责：
    agent 必须先跑 scan.ps1、把候选整理成表格、用多选（multi_select）问过用户，
    拿到用户勾选的 tier 之后，才允许调用本脚本。禁止在用户未确认时运行。

    用法：
        # 先看计划，不删任何东西
        powershell -NoProfile -ExecutionPolicy Bypass -File clean.ps1 -Tiers A,B,F -DryRun

        # 用户已确认后执行
        powershell -NoProfile -ExecutionPolicy Bypass -File clean.ps1 -Tiers A,B,F

        # 追加：Docker 内部清理（保守，不动容器/卷）
        powershell -NoProfile -ExecutionPolicy Bypass -File clean.ps1 -DockerPrune

    Tier 说明：
        A = 纯缓存/临时/可重建（npm/pip/uv/NVIDIA/浏览器/飞书转储/Temp/更新缓存/updater 残留）
        B = JetBrains 旧版本索引与配置（自动保留当前已安装版本）
        E = HuggingFace 模型缓存（用户资产，必须单独确认）
        F = 系统升级残留与厂商引导镜像（$WINDOWS.~BT / Windows.old / Aomei …）
        C = 休眠文件 → 不是删除，用 powercfg，见 SKILL.md（需管理员）
        D = Docker 数据盘 → -DockerPrune 清内部，再用 shrink-docker-vhdx.ps1 压缩
        G = WinSxS 组件存储 → 用 DISM，见 SKILL.md（需管理员）
#>
[CmdletBinding()]
param(
    [string[]]$Tiers = @(),
    [switch]$DockerPrune,
    [switch]$DryRun,
    [string]$LogFile = (Join-Path $env:TEMP 'disk-clean.log')
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'

$script:removed = 0
$script:skipped = 0

function Log([string]$m) {
    $line = '{0}  {1}' -f (Get-Date -Format 'HH:mm:ss'), $m
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}
function FreeGB { [math]::Round((Get-PSDrive C).Free / 1GB, 2) }
function SizeOf([string]$p) {
    if (-not (Test-Path -LiteralPath $p)) { return 0 }
    $s = (Get-ChildItem -LiteralPath $p -Recurse -Force -File -ErrorAction SilentlyContinue |
          Measure-Object Length -Sum).Sum
    if ($null -eq $s) { return 0 }
    return [double]$s
}

# 删除一个路径；Remove-Item 对付不了超长路径时退回 robocopy /MIR 空目录
function Remove-Robust([string]$p) {
    if (-not (Test-Path -LiteralPath $p)) { Log ("SKIP(不存在)`t$p"); $script:skipped++; return }
    $before = SizeOf $p
    if ($DryRun) {
        Log ("DRYRUN  {0,8:N2} GB  {1}" -f ($before / 1GB), $p)
        $script:skipped++
        return
    }
    Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $p) {
        # 超长路径 / 部分占用 → robocopy 镜像空目录
        $empty = Join-Path $env:TEMP ('__empty_' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $empty -Force | Out-Null
        & robocopy.exe $empty $p /MIR /NFL /NDL /NJH /NJS /R:0 /W:0 | Out-Null
        Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $empty -Recurse -Force -ErrorAction SilentlyContinue
    }
    $after = SizeOf $p
    if (Test-Path -LiteralPath $p) {
        Log ("PARTIAL {0,8:N2} GB 释放，残留 {1:N2} GB（多被进程占用）`t{2}" -f (($before - $after) / 1GB), ($after / 1GB), $p)
        $script:removed += ($before - $after)
    } else {
        Log ("OK      {0,8:N2} GB  {1}" -f ($before / 1GB), $p)
        $script:removed += $before
    }
}

# 只清空目录内容，保留目录本身（Temp / SoftwareDistribution\Download）
function Clear-Contents([string]$p) {
    if (-not (Test-Path -LiteralPath $p)) { Log ("SKIP(不存在)`t$p"); return }
    if ($DryRun) { Log ("DRYRUN  {0,8:N2} GB (清空内容)  {1}" -f ((SizeOf $p) / 1GB), $p); return }
    $before = SizeOf $p
    Get-ChildItem -LiteralPath $p -Force -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    $after = SizeOf $p
    Log ("OK      {0,8:N2} GB 释放，残留 {1:N2} GB`t{2}" -f (($before - $after) / 1GB), ($after / 1GB), $p)
    $script:removed += ($before - $after)
}

# 归一化：兼容 -File 传参时 "A,B,F" 被当成单个字符串（PowerShell -File 不做逗号拆分）
$Tiers = @($Tiers | ForEach-Object { $_ -split ',' } |
           ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ })

if ($Tiers.Count -eq 0 -and -not $DockerPrune) {
    Write-Host '未指定 -Tiers。先跑 scan.ps1，拿到用户勾选后再执行。' -ForegroundColor Yellow
    Write-Host '示例: clean.ps1 -Tiers A,B,F -DryRun'
    exit 2
}

Remove-Item -LiteralPath $LogFile -Force -ErrorAction SilentlyContinue
$start = FreeGB
Log ('================ disk clean ================')
Log ("Tiers={0}  DockerPrune={1}  DryRun={2}" -f ($Tiers -join ','), $DockerPrune, $DryRun)
Log ("START free = {0} GB" -f $start)

# ---------------------------------------------------------------- Tier A
if ($Tiers -contains 'A') {
    Log '--- Tier A: 缓存/临时/可重建 ---'
    $paths = @(
        (Join-Path $env:LOCALAPPDATA 'npm-cache'),
        (Join-Path $env:LOCALAPPDATA 'pip'),
        (Join-Path $env:LOCALAPPDATA 'uv'),
        (Join-Path $env:LOCALAPPDATA 'NVIDIA\DXCache'),
        (Join-Path $env:LOCALAPPDATA 'NVIDIA\GLCache'),
        (Join-Path $env:APPDATA      'LarkShell.exception_backup'),
        (Join-Path $env:LOCALAPPDATA 'ms-playwright')
    )
    Get-ChildItem -LiteralPath $env:LOCALAPPDATA -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like '*-updater' } | ForEach-Object { $paths += $_.FullName }

    $browserRoots = @(
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\User Data')
    )
    foreach ($root in $browserRoots) {
        foreach ($sub in 'Cache', 'Code Cache', 'GPUCache', 'ShaderCache', 'GrShaderCache', 'GraphiteDawnCache', 'GPUPersistentCache') {
            $paths += (Join-Path $root $sub)
            Get-ChildItem -LiteralPath $root -Directory -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -ne 'System Profile' } |
                ForEach-Object { $paths += (Join-Path $_.FullName $sub) }
        }
    }
    # 只保留真实存在的路径，避免日志被大量 SKIP 噪声淹没
    foreach ($p in ($paths | Select-Object -Unique | Where-Object { Test-Path -LiteralPath $_ })) { Remove-Robust $p }

    Clear-Contents (Join-Path $env:LOCALAPPDATA 'Temp')
    Clear-Contents 'C:\Windows\Temp'
    Clear-Contents 'C:\Windows\SoftwareDistribution\Download'   # 需管理员才能全清，否则部分残留
}

# ---------------------------------------------------------------- Tier B
if ($Tiers -contains 'B') {
    Log '--- Tier B: JetBrains 旧版本（保留当前已安装版本）---'
    $installed = @{}
    foreach ($base in (Join-Path $env:LOCALAPPDATA 'Programs'), 'C:\Program Files') {
        Get-ChildItem -LiteralPath $base -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
            $bt = Join-Path $_.FullName 'build.txt'
            if (Test-Path -LiteralPath $bt) {
                $build = (Get-Content -LiteralPath $bt -Raw -ErrorAction SilentlyContinue).Trim()
                if ($build -match '^[A-Z]+-(\d{3})') { $installed[[int]$Matches[1]] = $true }
            }
        }
    }
    Log ("已安装 build: {0}" -f (($installed.Keys | Sort-Object) -join ', '))
    foreach ($root in (Join-Path $env:LOCALAPPDATA 'JetBrains'), (Join-Path $env:APPDATA 'JetBrains')) {
        Get-ChildItem -LiteralPath $root -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
            $n = $_.Name
            if ($n -notmatch '^[A-Za-z]+(\d{4})\.(\d)') { return }        # Toolbox/Daemon 等跳过
            $bn = (([int]$Matches[1] - 2000) * 10) + [int]$Matches[2]
            if ($installed.ContainsKey($bn)) { Log ("KEEP(当前版本 {0})`t{1}" -f $bn, $_.FullName); return }
            Remove-Robust $_.FullName
        }
    }
}

# ---------------------------------------------------------------- Tier E
if ($Tiers -contains 'E') {
    Log '--- Tier E: HuggingFace 模型缓存（用户资产）---'
    foreach ($hub in (Join-Path $env:USERPROFILE '.cache\huggingface\hub'),
                     (Join-Path $env:USERPROFILE '.cache\huggingface\datasets')) {
        Get-ChildItem -LiteralPath $hub -Directory -Force -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Robust $_.FullName }
    }
}

# ---------------------------------------------------------------- Tier F
if ($Tiers -contains 'F') {
    Log '--- Tier F: 系统升级残留 / 厂商引导镜像 ---'
    foreach ($p in 'C:\$WINDOWS.~BT', 'C:\$Windows.~WS', 'C:\$WinREAgent', 'C:\ESD',
                   'C:\Windows.old', 'C:\Aomei', 'C:\OneDriveTemp') {
        Remove-Robust $p
    }
}

# ---------------------------------------------------------------- Tier D（内部清理部分）
if ($DockerPrune) {
    Log '--- Tier D: Docker 内部清理（保守：保留容器/其镜像/数据卷）---'
    $dockerExe = 'docker'
    if (Test-Path -LiteralPath (Join-Path ${env:ProgramFiles} 'Docker\Docker\resources\bin\docker.exe')) {
        $dockerExe = Join-Path ${env:ProgramFiles} 'Docker\Docker\resources\bin\docker.exe'
    }
    if ($DryRun) {
        Log 'DRYRUN  docker system df / docker builder prune -a（不执行）'
    } else {
        & $dockerExe system df 2>&1 | ForEach-Object { Log ("  {0}" -f $_) }
        # 1) 构建缓存（可重建）
        & $dockerExe builder prune -a -f 2>&1 | Select-Object -Last 1 | ForEach-Object { Log ("  builder prune: {0}" -f $_) }
        # 2) 只删「没有任何容器引用」的镜像；保留容器用到的镜像
        $used = (& $dockerExe ps -aq 2>$null | ForEach-Object { & $dockerExe inspect --format '{{.Image}}' $_ 2>$null }) | Sort-Object -Unique
        & $dockerExe images --no-trunc --format '{{.ID}} {{.Repository}}:{{.Tag}}' 2>$null | Sort-Object -Unique | ForEach-Object {
            $id, $repo = $_ -split ' ', 2
            if ($used -contains $id) { Log ("  KEEP  {0}" -f $repo) }
            else { Log ("  RM    {0}" -f $repo); & $dockerExe rmi -f $id 2>&1 | Out-Null }
        }
        & $dockerExe image prune -f 2>&1 | Select-Object -Last 1 | ForEach-Object { Log ("  image prune: {0}" -f $_) }
        Log '  注意：不要 prune 卷或容器（会丢用户数据库）。'
        Log '  下一步如需真正归还 C 盘空间，请运行 shrink-docker-vhdx.ps1（需 UAC）。'
    }
}

$end = FreeGB
Log ('--------------------------------------------')
Log ("END free   = {0} GB" -f $end)
Log ("释放约     = {0:N2} GB" -f ($end - $start))
Log ("日志       = {0}" -f $LogFile)
Log 'DONE'
