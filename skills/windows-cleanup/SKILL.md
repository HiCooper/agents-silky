---
name: windows-cleanup
description: 在 WSL 中清理 Windows C 盘空间：只读扫描占用 → 让用户多选勾选确认 → 按 tier 清理缓存与临时残留、JetBrains 旧版本、HuggingFace 模型、系统升级残留、Docker 数据盘压缩、休眠文件，并在结束后校验 Docker 与磁盘状态、输出释放量报告。触发词：清理C盘、C盘满了、C盘空间不够、释放磁盘空间、磁盘快满了、docker_data.vhdx 太大。
---

# Windows C 盘清理 Skill

让 agent 在 WSL 中安全地帮用户清理 Windows C 盘：**先扫描、再让用户勾选、最后才动手**。

---

## 0. 铁律（不可跳过）

> **未经用户明确勾选确认，禁止删除任何文件。**
> 扫描（`scan.ps1`）是只读的，随时可以跑；删除（`clean.ps1`）必须等到用户在多选问题里勾了 tier 之后。

确认方式固定为 `ask_user_question` + `multi_select: true`，每个选项必须带**大小**和**性质/风险**说明。
不要用「要不要清理？」这种笼统问法 —— 用户要能看到每一项是什么、多大、删了会怎样。

同时必须遵守：

1. **不碰用户数据**：`Documents` / `Downloads` / `Desktop` / `Pictures` / `Videos` / 项目目录 / `Roaming\Tencent`(微信QQ) / `Roaming\Python`(已装依赖) 一律不删，只报告。
2. **不删「已安装程序」**：`AppData\Local\Programs`、`Program Files`、`ProgramData\Package Cache` 是程序本体，不是缓存。
3. **不执行 `wsl --shutdown`**：那会关掉 Ubuntu 发行版，把 agent 自己的会话一起杀掉。要用 `wsl --terminate <docker发行版>`。
4. **删除前先说明可逆性**：删掉的缓存会自动重建就说明；模型权重/数据库卷要明确说「不可逆/需重新下载」。
5. **系统文件不当普通文件删**：`hiberfil.sys`、`pagefile.sys`、`swapfile.sys`、`WinSxS` 由 Windows 管理，只能用 `powercfg` / DISM，且需要管理员。

---

## 1. 最短路径

```bash
SKILL="${SKILL_DIR:-$HOME/projects/agents-silky/skills/windows-cleanup}"   # 本 skill 所在目录

# PowerShell 读不了 Linux 路径 → 先把脚本复制到 Windows TEMP
WIN_TMP="$(wslpath -u "$(powershell.exe -NoProfile -Command 'Write-Output $env:TEMP' | tr -d '\r')")"
cp "$SKILL"/scripts/*.ps1 "$WIN_TMP"/

# 1) 只读扫描（C:\Windows 递归较慢，1–5 分钟 → 放后台）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$WIN_TMP/scan.ps1")"

# 2) 读结果（TSV: `tier<TAB>bytes<TAB>path`）
cat "$WIN_TMP/disk-scan.txt"
```

拿到结果后 → **整理成表格 + 让用户勾选**（见 §3）→ 再执行：

```bash
# 3) 先 dry-run 复核一遍将要删的东西
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$WIN_TMP/clean.ps1")" -Tiers A,B,F -DryRun

# 4) 用户确认后执行
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$WIN_TMP/clean.ps1")" -Tiers A,B,F -DockerPrune

# 5) Docker vhdx 压缩（真正的空间归还，会弹 UAC）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$WIN_TMP/shrink-docker-vhdx.ps1")"
```

---

## 2. Tier 定义（扫描结果的 `tier` 字段就是这些字母）

| Tier | 内容 | 典型回收 | 风险 | 需要管理员 |
|---|---|---|---|---|
| **A** | npm/pip/uv 缓存、NVIDIA DXCache、浏览器缓存、飞书崩溃转储、Temp、Windows 更新缓存、`*-updater` 残留安装包 | 20–30 GB | 极低，全部自动重建 | 部分（更新缓存） |
| **B** | JetBrains **旧版本**索引与配置（自动保留当前已安装版本） | 5–16 GB | 低；仅丢失旧版本 IDE 设置 | 否 |
| **E** | HuggingFace 模型/数据集缓存 | 视模型 | **中，不可逆** —— 需重新下载，可能很慢 | 否 |
| **F** | `$WINDOWS.~BT` / `$Windows.~WS` / `$WinREAgent` / `ESD` / `Windows.old` / `Aomei` 引导镜像 | 0.5–10 GB | 低；Aomei 会失去厂商启动恢复环境 | 否 |
| **C** | `hiberfil.sys` 休眠文件 | ≈ 内存的 40% | **系统文件**，改设置；见 §5 | **是** |
| **D** | Docker 数据盘 `docker_data.vhdx` | 视情况 | 内部清理保守安全；压缩需短暂重启 Docker | **压缩需要** |
| **G** | `WinSxS` 组件存储 | 1–5 GB | 只能用 DISM，见 §5 | **是** |

> Tier A 里 `$env:LOCALAPPDATA\ms-playwright` 只有在确认用户不用 Playwright 时才删；扫描脚本会把它列为候选，**提问时单独说明**。

---

## 3. 确认提问模板（照这个来）

先输出表格，再用 `ask_user_question` 多选：

```jsonc
{
  "id": "cleanup_scope",
  "header": "确认清理范围",
  "multi_select": true,
  "question": "选择要清理的项目（可多选）。A/B/F 是缓存与残留，删除后会自动重建，风险低。",
  "options": [
    { "label": "A. 纯缓存与临时残留（约 25 GB）(Recommended)",
      "description": "npm/pip/uv 缓存、NVIDIA DXCache、浏览器缓存、飞书崩溃转储、Temp、更新缓存、updater 安装包。安全，会自动重建。" },
    { "label": "B. JetBrains 旧版本索引与配置（约 16 GB）",
      "description": "只删非当前版本的索引与配置；当前已安装版本自动保留。" },
    { "label": "F. 系统升级残留与厂商引导镜像（约 1 GB）",
      "description": "$WINDOWS.~BT 等升级残留；含 Aomei 引导镜像（会失去厂商恢复环境）。" },
    { "label": "E. HuggingFace 模型缓存（约 15 GB）",
      "description": "删除模型权重，需重新下载。若训练/推理脚本依赖这些权重请勿选。" },
    { "label": "C. 关闭休眠并删除 hiberfil.sys（约 13 GB）",
      "description": "系统文件。powercfg /h off 会同时禁用休眠与快速启动，可随时恢复。" },
    { "label": "D. Docker 数据整理（最多约 26 GB）",
      "description": "清构建缓存与无容器引用的镜像；压缩 vhdx 才能真正归还 C 盘。" }
  ]
}
```

按需追加第二个问题（例如是否删 `*-updater` 残留、是否保留 Docker 的已停止容器与数据卷）。

**只要用户勾了 D，就必须再问一次 Docker 力度**（见 §4），因为「已停止的容器 + 它的数据卷」常常是用户项目的本地数据库，不是垃圾。

---

## 4. Docker：最容易误伤的部分

顺序永远是：**先看清 → 问力度 → 内部清理 → 压缩**。

```bash
docker system df
docker ps -a                                              # 已停止的容器是不是用户项目的？
docker images
docker volume ls                                          # 卷名常带项目名，如 sass-starter-kit_pgdata
```

必须让用户在两种力度里选：

- **保守（默认推荐）**：`docker builder prune -a` + 只删「无任何容器引用」的镜像。
  **保留**已停止容器、它们的镜像、所有数据卷。→ `clean.ps1 -DockerPrune`
- **彻底**：`docker system prune -a --volumes`。会删除已停止容器 + 其镜像 + 数据卷，**本地数据库数据丢失**。
  只有用户明确知道后果才做。

### 两个真实踩过的坑

1. **`docker network prune` 会删掉 compose 建的、但只被「已停止容器」引用的网络**，
   之后 `docker start <容器>` 会报 `network not found`。
   → 保守清理时**不要** `docker network prune`；万一删了，用 compose 标签重建：

   ```bash
   docker network create --driver bridge \
     --label com.docker.compose.project=<项目名> \
     --label com.docker.compose.network=<网络名> \
     <项目名>_<网络名>
   ```
   （`docker inspect <容器> --format '{{json .Config.Labels}}'` 能看到 `com.docker.compose.project`。）

2. **`docker system prune` 不会缩小 vhdx**，C 盘一点空间都不会回来。
   必须跑 `shrink-docker-vhdx.ps1`：停 Docker → `wsl --terminate docker-desktop` → `diskpart compact vdisk` → 重启。
   实测 25.9 GB → 9.5 GB，回收 16.4 GB。

---

## 5. 只能改设置、不能删文件的 Tier

### C —— 休眠文件 `hiberfil.sys`
它是**受保护的系统文件**：资源管理器里看不到，直接 `del`/`Remove-Item` 会失败（ACL 拒绝）。
它同时支撑**休眠**和**快速启动**（`HiberbootEnabled=1` 时即使从不休眠它也在用）。必须用 `powercfg`（管理员）：

```powershell
powercfg /h /type reduced     # 推荐折中：保留快速启动，文件通常缩到约一半
powercfg /h off               # 彻底删除，同时禁用休眠 + 快速启动
powercfg /h on                # 恢复
```
想先看状态：`powercfg /a`、`Get-ChildItem C:\ -Force -File | ? Name -eq 'hiberfil.sys'`。

### G —— WinSxS
```powershell
DISM /Online /Cleanup-Image /AnalyzeComponentStore     # 先分析能回收多少
DISM /Online /Cleanup-Image /StartComponentCleanup     # 再清理（管理员）
```

---

## 6. 已知坑（照做可省时间）

| 现象 | 原因 / 对策 |
|---|---|
| `du` 在 `/mnt/c` 上极慢 | 9p 文件系统开销大 → **一律用 PowerShell 的 `Get-ChildItem` 统计** |
| 大目录递归超时 | `C:\Windows` 单次 >60s → 脚本放后台跑，结果写文件再读 |
| 删除报「路径不存在」但 `Get-ChildItem` 能看到 | 受保护系统文件（hiberfil/pagefile）→ 不是 bug，改用 `powercfg` |
| 一堆文件删不掉，剩几个 GB | 超长路径或进程占用 → `clean.ps1` 已内置 `robocopy /MIR` 空目录兜底 |
| 浏览器 / 飞书缓存删不净 | 进程持有句柄 → 报告残留即可，不影响 |
| `SoftwareDistribution\Download` 清不干净 | 需管理员停 `wuauserv`/`bits`；非管理员下残留 ~1 GB 属正常 |
| PowerShell 输出中文乱码 | 加 `[Console]::OutputEncoding=[Text.Encoding]::UTF8`，或只看结构不看文案 |
| `Test-Path`/`Get-Item` 拿不到 `hiberfil.sys` | 同上，受保护；用 `Get-ChildItem C:\ -Force` 枚举父目录 |
| 脚本报「字符串缺少终止符」等一堆语法错误 | **`.ps1` 丢了 UTF-8 BOM**：PowerShell 5.1 无 BOM 时按 GBK 解析，中文字符串会被截断。改完脚本必须确认 `head -c3 x.ps1 \| od -An -tx1` 是 `ef bb bf` |
| `-File x.ps1 -Tiers A,B,F` 里 tier 全部不生效 | PowerShell 用 `-File` 传参时**不做逗号拆分**，`"A,B,F"` 会变成单个字符串。`clean.ps1` 已内置归一化；自己写脚本时要记得 `-split ','` |

---

## 7. 执行后必须校验并汇报

```bash
df -h /mnt/c                                    # 释放了多少
docker info --format '{{.ServerVersion}}'       # 引擎是否恢复
docker ps -a --format '{{.Names}} | {{.Status}}'
docker volume ls -q | wc -l                     # 卷数量应与清理前一致
docker network ls
```

汇报格式：

1. **结论**：C: 可用空间 `A → B GB`（净释放 X GB），占用率变化。
2. **明细表**：每个 tier 实际释放多少（用 `clean.ps1` 的日志），标出 `PARTIAL`（被占用未删净）的项及原因。
3. **保留未动**：明确列出为了安全没碰的东西（休眠文件、用户数据、Docker 容器/卷…）。
4. **副作用与修复**：例如重建了被误删的 compose 网络。
5. **残留**：少量因占用未删净的项，说明是否需要再来一次。
