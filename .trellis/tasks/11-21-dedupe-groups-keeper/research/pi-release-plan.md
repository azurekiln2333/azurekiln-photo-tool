# 独立复核与发布准备（planning，只读研究）

## 1. 状态与权限边界

- 当前任务：`.trellis/tasks/11-21-dedupe-groups-keeper`，`task.json.status=planning`。
- 已读：`prd.md`、`design.md`、`implement.md`、`implement.jsonl`、`check.jsonl`，及其中引用的 pyqt/python specs；另核对 `python/packaging.md` 和 `trellis-check` 工作指引。
- 本批仅检查现状并写本文；**未改产品/测试源码、版本、workflow 或 spec，未跑测试/构建/打包/安装/发布，未 commit/push/tag/fetch，未激活/归档任务，未 spawn**。
- 继续使用现有 Pi 与当前模型；不切换模型/供应商，不嵌套代理。
- 后续独立检查发现真实问题，附复现和断言交 root/owner；不并发编辑其他 Pi 的核心、页面或测试源码。spec 仅在实际行为定稿后同步，不提前把设计写成已实现事实。

## 2. 当前基线与版本来源（实际只读观察）

观察时间：`2026-11-21T06:22:24+08:00`。

| 项目 | 当前值 |
| --- | --- |
| HEAD | `93fef4555c9e14f796f3e36ff7cb9f9f6dac0c20` |
| 分支 | `feat/folder-media-statistics`（任务基线） |
| 初始工作区 | 仅本任务目录 untracked；无产品变更 |
| 版本唯一来源 | `unified_gui.py:38`：`APP_VERSION = "1.2.2"` |
| 读取/校验实现 | `scripts/ci/get_version.py` 正则读取源码，不导入 GUI；tag 必须为 `v` + APP_VERSION |
| 实际只读版本核对 | `.venv/Scripts/python.exe scripts/ci/get_version.py --tag v1.2.2` → 输出 `1.2.2`，exit `0`；运行时移除并恢复 `GITHUB_OUTPUT`，未写 CI 输出文件 |

### 远端已存在的 tag

实际执行：`git ls-remote --tags github 'v*'`，exit `0`；没有 fetch、改本地 refs 或推送。

| tag | annotated tag object | peeled commit |
| --- | --- | --- |
| `v1.1.0` | `5b0e5588f368d0f0f4ee9f670ce09cf8f3673244` | `2f8b0067635c61f1a383d25694fa22645c4d33fb` |
| `v1.2.0` | `2cb00de6fad1582767971b9fef29825bd3cdd662` | `0ff0b4e57a95fa26a6839dc6ce8fe8ada1c47ca7` |
| `v1.2.1` | `1deeb26f45e153f2965676f1c9791b203c0f60a3` | `239874b17bd9dc5b0d94297b1ab7f29281eec475` |
| `v1.2.2` | `37f36b6f6df00c75690abe99150f3c57c1aaf493` | `a594841fe4a24c9b1b65fd76b0726e4aa9119470` |

- 本地 `v1.2.2^{commit}` 同为 `a594841...`。
- 本次观察未见 `v1.2.3`。**候选后继版本为 `1.2.3` / `v1.2.3`，并非本 worker 已决定或已修改。** root 在源码完成、独立检查通过后最终确认，并在发布前重新检查远端是否占用。
- 旧 tag 不得移动、删除或覆盖。tag/Release 操作统一由 root 执行。

## 3. 现有 CI 的实际门禁与命令（仅阅读，未执行）

来源：`.github/workflows/build.yml`。

- 触发：任意分支 push、`v*` tag push、workflow_dispatch；Windows runner，Python `3.14`，PowerShell。
- 依赖：`python -m pip install -r requirements-build.txt`（运行依赖和打包依赖固定版本）。
- 测试：`python -B -m unittest discover -s tests -v`，step 级 `timeout-minutes: 5`。
  在测试前设置 `QT_QPA_PLATFORM=offscreen`，APPDATA/LOCALAPPDATA 均指向 runner 临时目录；失败立即中止，无 continue-on-error。
- tag 版本检查：`python scripts/ci/get_version.py --tag <tag>`；分支运行只读取版本。
- 测试先于 Configure ExifTool，必须继续保持无 ExifTool 可运行的统一窗测试隔离；不能依赖本机安装来判定 CI 通过。
- ExifTool：固定 `13.58` 和 SHA256，完整 `exiftool_files/` 注入构建，布局有前置检查。
- 构建：`python -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec`，**不加 `--clean`**。
- 自检：`python scripts/ci/verify_bundle.py dist/AzureKilnPhotoTool.exe`。
- portable：`python scripts/ci/package_portable.py --version <version> --exe dist/AzureKilnPhotoTool.exe --output-dir release`。
- installer：Inno Setup，传入 `AppVersion`、`SourceExe`、`OutputDir`、`OutputBaseFilename`；固定 AppId 不变。
- 分支只上传 workflow artifact；只有 `refs/tags/v*` 进入 `Publish GitHub Release`。

### 必须保留的打包覆盖

- onefile hiddenimports 已显式列入两页、`duplicate_scan_core`、`scan_record_core`、`media_thumbnail`、`PyQt6.QtMultimedia`。
- 当前任务在已有模块内扩展，按当前设计无需新增第三方依赖或修改打包流程；最终按实际 imports 再确认，不能预先保证产物通过。
- 原有 HEIC（pillow_heif 原生扩展 + libheif）、send2trash、完整 ExifTool 的自检不可删除。
- Qt 视频后端保留 QtMultimedia.pyd、Qt6Multimedia.dll、Qt6Network.dll、ffmpegmediaplugin.dll、av*/sw* DLL；不得再次 exclude QtNetwork，不把原生 .pyd 当成 PYZ 模块。
- 所有源码（包含版本行）最终冻结后才能构建；旧 `dist/`、上轮 hash 不作为本轮证据。

## 4. source 完成后的独立复核重点（尚未执行）

以 core owner 写入 `research/contracts.md` 的正式接口为准；当前只记录验收维度，不替 owner 决定实现 API。

| 需求 | 需要看到的真实证据 |
| --- | --- |
| R1 类型与组边界 | 照片/视频/其他数量区分文件数与重复组数；混合扩展名按 photo > video > other 固定归组；换 keeper 不导致组跳转；筛选用稳定 source row，不重建导致 worker 回写错位 |
| R2 其他不预览 | loader spy 覆盖表格缩略图与详情请求；路径自身为 other 时不请求媒体预览；从照片/视频切到 other 清空旧图，混合组也按具体路径判断 |
| R3 唯一保留项 | A/B/C 实际按钮改保留 B 后，实际 ScanResult keeper=B、duplicates 包括 A/C；B 不可勾选、A 默认可勾选、C 原合法状态保留；worker 真正使用 B 为参照 |
| R4 可见分组批量动作 | 真实按钮点击全选/取消全选/反选，只改当前可见合法副本；切组不丢原勾选；回收确认统计全部勾选；keeper/异常/mismatch/已处理不被选中 |
| R5 守卫与记录 | busy/stale/cancelled/已处理组禁止切换；候选不属于组或当前快照失效时拒绝且不破坏原组；修改 result.groups 而非只改显示；v1 旧记录兼容；新角色和逐路径状态往返一致 |
| R6 回收安全与 compare 回归 | 大小→完整 SHA256→逐字节不退化；导入强制 byte_verify；变更/删除、碰撞不调 send2trash；compare A/B 方向与记录角色不放宽 |
| R7 UI/线程/集成 | zh/en 文案与动态计数刷新；独立/内嵌布局均可用；真实按钮/真实 QThread，Qt 槽异常被捕获；统一关闭等待记录线程完成；无新 skip 掩盖失败 |

不泛化重构、不修改模糊查重算法、不新增永久删除。真实 OneDrive 仅联机端到端仍标为未验证，不把本地临时目录用例当作云环境证据。

## 5. 后续检查命令与环境（等待实施授权/源码完成，现未执行）

- 定向：`.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -p 'test_folder_dedupe_features.py' -v`；核心/记录测试按相同 discover 方式分别运行。
- 全量：`.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -q`。
- GUI 之前强制临时 APPDATA/LOCALAPPDATA 和 offscreen；所有回收 mock，只用临时媒体。
- 至少一轮 CI-like 无 ExifTool 条件与跨盘 TEMP 复验；相对路径用例不得跨盘 relpath 或新增 skip 绕过。
- changed Python 语法检查、`git diff --check`；未配置独立 lint/type checker，不把 compileall 称为类型检查。
- 最终按 root 通知再运行 `.venv/Scripts/python.exe -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec` 和 `verify_bundle.py`，记录实际退出码、exe 大小/时间/SHA256。

## 6. 预期 spec 同步（只在实现与测试证据齐备后）

- `python/duplicate-verification.md`：实际类型分类/组类别与纯内存 keeper 重选契约、保护条件；不改变精确判重算法。
- `python/scan-records.md`：schema v1 下新 keeper 关系必须来自更新后的 groups，逐路径状态角色一致；旧记录可读、compare 约束保持严格。
- `pyqt/page-structure.md`：当前类型筛选、稳定 row 索引、可见批量动作与全局勾选统计的差别；无关页规则不改。
- 其他 spec 仅在本轮确有新约定时做局部补充，避免重复/泛化。
- 独立审查报告输出本任务 `research/pi-review.md`；真实缺陷交所有者修复后复读差异与验证，不抢写源码。

## 7. root 发布时建议顺序（本文不执行）

1. 汇总四 Pi 停笔、核心契约、独立报告与全量结果；确认 runtime/版本最终冻结。
2. root 确认后继版本，重新核对远端 tag 未占用；版本只改 APP_VERSION，按新 tag 运行 get_version 检查。
3. 最终构建/自检；审查精确 staged diff、cached diffcheck，不提交 build/dist/release。
4. root 提交并 push 分支，先确认该 commit 的远端 unit gate/全流程成功，再新建和 push annotated tag；禁止改写旧 tag。
5. 只读核对 tag peeled commit、run head_sha、版本一致；监控间隔至少 45s。失败报告具体 step/annotations，不自行改 tag 或重跑。
6. Release 检查 portable.zip、portable.sha256.txt、setup.exe 均 uploaded 且 size>0。
7. 独立 temp 中真实下载 checksum 与 zip：zip SHA256 对照资产 digest；解包只读计算 exe SHA256 对照 checksum；zip 内/外 checksum 必须逐字节一致。checksum 记的是 **exe** 哈希，不是 zip。仅 API 元数据通过不能写成真实下载验证通过；不运行任何下载 EXE。

## 8. 本批结论

发布基线/门禁已核对，未发现需要在 planning 阶段修改发布基础设施的阻塞问题。
**只读研究完成；等待 root 明确实施/审查通知。** 当前无本任务测试通过或发布成功的声明。
