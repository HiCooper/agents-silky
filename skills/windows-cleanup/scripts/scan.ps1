<#
    scan.ps1 —— 只读扫描 Windows C: 盘空间占用，为「勾选式清理」生成候选清单。

    安全保证：本脚本只做 Get-ChildItem / Measure-Object，不删除、不修改任何东西。

    用法（建议后台运行，C:\Windows 递归较慢，通常 1–5 分钟）：
        powershell -NoProfile -ExecutionPolicy Bypass -File scan.ps1
        powershell -NoProfile -ExecutionPolicy Bypass -File scan.ps1 -OutFile D:\tmp\scan.txt

    输出（UTF-8 TSV）格式：
        ### <section 名>
        <bytes>\t<path>
        tier\t<A|B|C|D|E|F>\t<bytes>\t<path>
    其中 tier 行是「可直接勾选的清理候选」，agent 应据此生成确认表格。
#>
[CmdletBinding()]
param(
    [string]$OutFile = (Join-Path $env:TEMP 'disk-scan.txt')
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'

# 重新以 UTF-8 无 BOM 写出，方便 Linux/WSL 侧直接读取
$sb = New-Object System.Text.StringBuilder
function Emit([string]$line) { [void]$sb.AppendLine($line) }

function Get-Size([string]$p) {
    if (-not (Test-Path -LiteralPath $p)) { return -1 }
    $s = (Get-ChildItem -LiteralPath $p -Recurse -Force -File -ErrorAction SilentlyContinue |
          Measure-Object Length -Sum).Sum
    if ($null -eq $s) { return 0 }
    return [double]$s
}

function Emit-Candidate([string]$tier, [string]$path, [double]$size) {
    if ($size -lt 0) { return }                       # 不存在则跳过
    if ($size -lt 50MB) { return }                    # 小于 50MB 不值得让用户勾选
    Emit ("{0}`t{1}`t{2}" -f $tier, [math]::Round($size), $path)
}

# ---------------------------------------------------------------- 目录体型
function Section([string]$name) { Emit "### $name" }

function DirsOf([string]$parent, [double]$minBytes = 0) {
    Get-ChildItem -LiteralPath $parent -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $s = Get-Size $_.FullName
        if ($s -ge $minBytes) { Emit ("{0}`t{1}" -f [math]::Round($s), $_.FullName) }
    }
}

Section 'TOP-LEVEL DIRS'
DirsOf 'C:\'

Section 'TOP-LEVEL FILES'
Get-ChildItem 'C:\' -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
    Emit ("{0}`t{1}" -f [math]::Round($_.Length), $_.FullName)
}

Section 'USER PROFILE DIRS'
DirsOf $env:USERPROFILE

Section 'APPDATA LOCAL DIRS'
DirsOf $env:LOCALAPPDATA

Section 'APPDATA ROAMING DIRS'
DirsOf $env:APPDATA

Section 'PROGRAMDATA DIRS'
DirsOf 'C:\ProgramData'

Section 'PROGRAM FILES DIRS'
DirsOf 'C:\Program Files'

Write-Output "[scan] 目录体型扫描完成，开始计算清理候选…"

# ---------------------------------------------------------------- Tier 候选
Section 'TIER CANDIDATES'

# ---- Tier A：纯缓存 / 临时 / 可重建 ----
$tierA = @(
    (Join-Path $env:LOCALAPPDATA 'npm-cache'),
    (Join-Path $env:LOCALAPPDATA 'pip'),
    (Join-Path $env:LOCALAPPDATA 'uv'),
    (Join-Path $env:LOCALAPPDATA 'NVIDIA\DXCache'),
    (Join-Path $env:LOCALAPPDATA 'NVIDIA\GLCache'),
    (Join-Path $env:APPDATA      'LarkShell.exception_backup'),
    (Join-Path $env:LOCALAPPDATA 'Temp'),
    (Join-Path $env:LOCALAPPDATA 'ms-playwright'),
    'C:\Windows\Temp',
    'C:\Windows\SoftwareDistribution\Download',
    'C:\Windows\Prefetch'
)
# 浏览器缓存（覆盖所有 profile）
$browserRoots = @(
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'),
    (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\User Data')
)
foreach ($root in $browserRoots) {
    foreach ($sub in 'Cache', 'Code Cache', 'GPUCache', 'ShaderCache', 'GrShaderCache', 'GraphiteDawnCache', 'GPUPersistentCache') {
        $tierA += (Join-Path $root $sub)
        Get-ChildItem -LiteralPath $root -Directory -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne 'System Profile' } |
            ForEach-Object { $tierA += (Join-Path $_.FullName $sub) }
    }
}
# 各类 *-updater 残留安装包
Get-ChildItem -LiteralPath $env:LOCALAPPDATA -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*-updater' } |
    ForEach-Object { $tierA += $_.FullName }

foreach ($p in ($tierA | Select-Object -Unique)) { Emit-Candidate 'A' $p (Get-Size $p) }

# ---- Tier B：JetBrains 旧版本索引/配置（保留当前已安装版本）----
$installed = @{}
foreach ($base in (Join-Path $env:LOCALAPPDATA 'Programs'), 'C:\Program Files') {
    Get-ChildItem -LiteralPath $base -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $bt = Join-Path $_.FullName 'build.txt'
        if (Test-Path -LiteralPath $bt) {
            # build.txt 形如 IU-261.26222.65 → 版本轮次 261 = 2026.1
            $build = (Get-Content -LiteralPath $bt -Raw -ErrorAction SilentlyContinue).Trim()
            if ($build -match '^[A-Z]+-(\d{3})') {
                $installed[[int]$Matches[1]] = $true
            }
        }
    }
}
function Test-InstalledBuild([string]$dirName) {
    # JetBrains 目录名形如 PyCharm2025.3 → build 253；2026.1 → 261
    if ($dirName -notmatch '(\d{4})\.(\d)') { return $true }   # 认不出来就保守保留
    $year = [int]$Matches[1]; $rel = [int]$Matches[2]
    $bn = (($year - 2000) * 10) + $rel                        # 2025.3 → 253
    return $installed.ContainsKey($bn)
}
foreach ($root in (Join-Path $env:LOCALAPPDATA 'JetBrains'), (Join-Path $env:APPDATA 'JetBrains')) {
    Get-ChildItem -LiteralPath $root -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $n = $_.Name
        if ($n -notmatch '^[A-Za-z]+(\d{4}\.\d)') { return }   # 跳过 Toolbox / Daemon / acp-agents 等
        if (Test-InstalledBuild $n) { return }                # 当前版本 → 保留
        Emit-Candidate 'B' $_.FullName (Get-Size $_.FullName)
    }
}

# ---- Tier C：休眠文件（不是普通删除，需 powercfg，需管理员）----
$hib = Get-ChildItem 'C:\' -Force -File -ErrorAction SilentlyContinue |
       Where-Object { $_.Name -eq 'hiberfil.sys' } | Select-Object -First 1
if ($hib) { Emit ("C`t{0}`t{1}" -f [math]::Round($hib.Length), 'C:\hiberfil.sys') }

# ---- Tier D：Docker Desktop 数据盘 ----
$dockerVhdx = Join-Path $env:LOCALAPPDATA 'Docker\wsl\disk\docker_data.vhdx'
if (-not (Test-Path -LiteralPath $dockerVhdx)) {
    $dockerVhdx = Join-Path $env:LOCALAPPDATA 'Docker\wsl\data\ext4.vhdx'
}
if (Test-Path -LiteralPath $dockerVhdx) {
    Emit ("D`t{0}`t{1}" -f [math]::Round((Get-Item -LiteralPath $dockerVhdx).Length), $dockerVhdx)
}

# ---- Tier E：HuggingFace 模型缓存（可能是用户资产，务必单独确认）----
foreach ($hub in (Join-Path $env:USERPROFILE '.cache\huggingface\hub'),
                 (Join-Path $env:USERPROFILE '.cache\huggingface\datasets')) {
    Get-ChildItem -LiteralPath $hub -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Emit-Candidate 'E' $_.FullName (Get-Size $_.FullName)
    }
}

# ---- Tier F：系统升级残留 / 厂商引导镜像 ----
foreach ($p in 'C:\$WINDOWS.~BT', 'C:\$Windows.~WS', 'C:\$WinREAgent', 'C:\ESD',
               'C:\Windows.old', 'C:\Aomei', 'C:\OneDriveTemp') {
    Emit-Candidate 'F' $p (Get-Size $p)
}

# ---- Tier G：Windows Update / 组件存储（需管理员或 DISM，只报告不自动清）----
$winsxs = Get-Size 'C:\Windows\WinSxS'
if ($winsxs -gt 0) { Emit ("G`t{0}`t{1}" -f [math]::Round($winsxs), 'C:\Windows\WinSxS') }

# ---------------------------------------------------------------- 写盘
[System.IO.File]::WriteAllText($OutFile, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
Write-Output "[scan] 已写出: $OutFile"
Write-Output "[scan] 现在读取该文件，生成表格并让用户勾选确认；未经确认不得执行任何删除。"
