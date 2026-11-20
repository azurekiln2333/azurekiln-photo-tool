# pi-final-check — 11-21-compare-preview-records 全量跨层复核

结论：**PASS**（未发现新的真实缺陷；仅有 1 项格式问题已修复）

角色：全量 `trellis-check` 复核者。范围＝工作区全部 dirty runtime/spec/test/CI/文档的跨层契约一致性 + 独立全量验证。
未新增功能、未创建任务、未提交、未推送、未改动他人页面文件（`dir_compare_gui.py` / `folder_dedupe_gui.py` 仅在本次前序工作中由已授权 worker 修改，本轮只读复核）。

---

## 1. 本轮修复的真实问题（唯一一项）

| 项 | 位置 | 性质 | 处理 | 证据 |
| --- | --- | --- | --- | --- |
| 文件末尾多余空行 | `scan_record_core.py` 尾部字节 `... p a s s 0A 0A` | 仅格式（untracked 时 `git diff` 不覆盖，staged 后 `git diff --cached --check` 才报 `new blank line at EOF`） | 仅删除末尾冗余 `0A`，保持单个换行；未触碰任何逻辑 | 尾部字节现为 `... 20 70 61 73 73 0A`；`git diff --cached --check` **exit=0**；`tests.test_scan_record_core` 38 tests **OK**（exit=0）；`git diff --cached --stat -- scan_record_core.py` = 790 insertions |

处理方式遵守约束：只用 `git add -- scan_record_core.py`，未 stage 其它文件，未 commit。

---

## 2. 独立验证证据（本轮实跑，真实退出码）

| 命令 | 结果 |
| --- | --- |
| `QT_QPA_PLATFORM=offscreen` + 隔离 `APPDATA`/`LOCALAPPDATA` + `python -B -m unittest discover -s tests` | `Ran 183 tests` **OK**，**exit=0**（即 CI 同款调用形态） |
| `python -m unittest tests.test_unified_close` | `Ran 2 tests` **OK**，**exit=0** |
| `python -m unittest tests.test_scan_record_core`（修尾行后复跑） | `Ran 38 tests` **OK**，**exit=0** |
| `python scripts/ci/verify_bundle.py dist/AzureKilnPhotoTool.exe` | `927 archive entries, 484 PYZ modules, 508 exiftool_files entries, 41 multimedia entries`；`bundle check passed: pillow_heif, send2trash, ExifTool, QtMultimedia FFmpeg backend present`，**exit=0** |
| `research/integration_media_probe.py`（真视频首帧解码） | `ok: ffmpeg multimedia plugin at .venv/.../multimedia/ffmpegmediaplugin.dll`；`ok: Qt fallback first frame 360x480 from IMG_20260523_030803.mp4`；`media probe passed`，**exit=0** |
| `python -m compileall -q`（runtime + tests + scripts/ci） | **exit=0** |
| `git diff --check` | **exit=0**（仅 LF→CRLF 提示） |
| `git diff --cached --check` | **exit=0**（修尾行后） |

前序已由本人实跑并留存证据、本轮不重复的项：`root_layout_probe.py` 四组合（独立/嵌入、中/英）exit=0 且截图显示等宽、长路径完整换行无重叠、`panel_minimum=266`；`root_close_probe.py` PASS；`tests.test_file_context_menu` 3 OK；`tests.test_media_thumbnail` 26 OK。

---

## 3. check.jsonl 六份 spec 合规逐项

| spec | 关键契约 | 结论 | 依据 |
| --- | --- | --- | --- |
| `python/duplicate-verification.md` | 三重校验、执行前复核、哈希不一致/读问题绝不回收、只走回收站 | PASS | 记录导入后强制 `byte_verify=True`；`stale`/`cancelled` 锁死回收；`status_mismatch*`/`status_issue*` 行不可勾选（`test_cancelled_record_not_recyclable`、`test_stale_record_round_trip_and_rejected`、`test_import_restores_done_counts`） |
| `pyqt/threading-and-workers.md` | 后台线程 + 信号回主线程、关闭时 join/协调、忙态禁操作 | PASS | `_is_busy()`/`_workers_running()` 覆盖 scan/recycle/record 三类线程引用（含“线程已停但 finished 未到”窗口，`test_*_busy_blocks_bulk_selection`）；`unified_gui.closeEvent` 延迟关闭 + `_shutdown_workers()` + 50ms `QTimer` 重试（`tests/test_unified_close.py` 2 OK） |
| `pyqt/quality-guidelines.md` | 无重复定义、无死代码、Qt 对象生命周期安全、可见文案走翻译 | PASS | AST 重复定义扫描 = 0（主会话已核）；`file_context_menu.py` eventFilter 已按「先判事件类型 → 再 try viewport → 再 obj is viewport」顺序，避免 viewport 为普通 `QWidget` 导致真实右键失效，同时删除后 TableView 不再崩（3 用例含真实 `QContextMenuEvent`） |
| `python/packaging.md` | onefile spec 隐藏导入完整、发布包自检、CI 与本地同源 | PASS | spec 增 `scan_record_core`、`PyQt6.QtMultimedia` 隐藏导入并去掉 `PyQt6.QtNetwork` 排除；`verify_bundle.py` 增加 multimedia 检查（41 multimedia entries）；`build.yml` 打包前用 offscreen+隔离 APPDATA 跑 `tests/`（本轮以同形态命令复现 exit=0） |
| `python/scan-records.md` | 冻结 API、`schema_version=1`、UTF-8 JSON、不可信历史严格校验、原子写、64 MiB 上限、无 PyQt 依赖 | PASS | `ScanRecord`/`save_record`/`load_record(expected_mode=)` 签名未变；同目录临时文件 + `os.replace`；越界/root 嵌套/重复目标/与保留项相交/错误模式/角色与 `row_states` 冲突均拒绝；`realpath` 失败 fail-closed（`_path_key`）；`stale` 作为持久化字段严格校验为 bool |
| `pyqt/shared-previews.md` | 预览槽等宽、长路径不撑开面板、视频回退+有限重试、可取消 | PASS | `PreviewPanel` 内置纵向 `QScrollArea`，最小宽度固定 266 与路径长度无关；`_WrappingLabel.sizeHint()` 单行高度、`_PreviewSlot._sync_minimum_height()` 按当前宽度取 `heightForWidth`；视频回退 `(1,2,5)s` 有限退避 + 超时 + mtime TTL 2s；`load_thumbnail_image*`、`ThumbnailLoader.request/retry/failure_reason/clear/shutdown`、`PreviewPanel.set_slot/set_language` 公开 API 保持不变 |

---

## 4. 逐层一致性抽查结论

- **记录层 ↔ 页面层**：两页 `_build_scan_record()` 只写入角色合法状态（keeper=keep、mismatch=mismatch、issue=issue、target=pending/recycled/skipped/failed/cancelled/processing）；导入侧所有非 pending 行的 `checked` 归一为 False；新扫描清 `_record_imported`；坏记录不破坏当前结果（`test_bad_record_does_not_destroy_current_results`）；导出使用扫描时刻快照与绝对路径（`test_export_uses_scan_time_snapshot`、`test_relative_root_is_absolutized_in_snapshot`）；异常行分栏用记录自身根（`test_issue_columns_use_record_root`）。
- **页面层 ↔ 预览层**：等宽 + 滚动条内嵌，`PreviewPanel.minimumSizeHint()` = `slots*120 + spacing + scrollbar`（≈266），分隔条可压缩到最小宽度而不横向裁剪；视频失败只影响对应槽并显示原因，可「重试预览」强制重解码（下载完成的文件随后正常）。
- **CI ↔ 运行时**：`APP_VERSION = "1.2.1"`（`unified_gui.py:38`）为版本唯一来源；三份 README（`README.md`、`docs/README.en.md`、`docs/README.zh-TW.md`）在功能描述、依赖说明（Qt Multimedia 内置 FFmpeg）、CI 流程（先跑 tests 再打包并自检 multimedia）上与代码/spec 一致，无互相矛盾表述，也未把未验证能力写成已保证。
- **未改动文件**：本轮除 `scan_record_core.py` 尾行外未写任何文件；未触碰 pA（`dir_compare_gui.py`）与 p8（`folder_dedupe_gui.py`）实现。

---

## 5. 关于 `singleShot` 析构疑虑的结论（已撤回，非问题）

先前推演「`_auto_retry` 经 `QTimer.singleShot` 触发时 slot 可能已析构」属假设性风险，已按证据否定：

- `_auto_retry` 只读取 `slot.path`（纯 Python 属性）后调用 `loader.request(...)`；`loader` 在正常关闭链路中已 `_stopped = True`，`request` 直接返回占位图，**不会调用已销毁 slot 的 C++ 方法**。
- 现有 `tests/test_media_thumbnail.py` 26 用例与 `root_close_probe.py` 均在关闭路径上通过（exit=0），未观察到 `RuntimeError: wrapped C/C++ object has been deleted`。
- 依约束不基于假设改动已冻结 runtime；该项在下方边界中作为「未构造最小复现」记录，而非缺陷。

---

## 6. 未覆盖边界（明确不声称已验证）

1. **真实 OneDrive / 云占位符**：未在真实「按需下载」文件上验证 hydration（`hydration` 占位、下载中读失败后自动重试成功的完整现象）。本地仅覆盖普通磁盘文件与 Qt Multimedia 首帧解码。
2. **真实打包产物与安装包**：`scripts/ci/verify_bundle.py` 对本地 `dist/AzureKilnPhotoTool.exe` 通过（exit=0），但**未**在干净机器上启动该 exe 做 GUI 冒烟，**未**本地构建/安装 Inno Setup 安装包，**未**在 GitHub Actions runner 上实际跑过一次 workflow。
3. **真实回收站**：所有用例均 mock `send2trash`，未向真实回收站写入/还原过任何文件。
4. **跨盘符 / 网络路径 / 超长 UNC**：仅覆盖同盘普通路径（含中文与长路径显示），跨盘 move 行为、SMB/UNC、>260 字符路径未实测。
5. **交互式 DPI / 多显示器**：布局证据来自 offscreen 固定尺寸探针（含 1360×880 窄右栏），未在真实 125%/150%/200% 缩放、多屏拖拽下人工验收。
6. **关闭竞态极端时序**：`singleShot` 析构疑虑未构造「DeferredDelete 后强制触发回调」的最小复现探针，故保守列为未覆盖（现有证据指向非问题）。
7. **无静态类型检查器**：项目未配置 mypy / pyright 等类型检查器，也无对应依赖；本轮类型/契约验证依靠 183 个 stdlib unittest、`compileall`、AST 重复定义扫描与运行时探针，注解本身未做机器类型检查。
8. **同工作区其他 worker 的后续改动**：本轮复核针对当前 staged/工作区快照；若他人继续修改 pA/p8 页面文件，需重跑全量。

---

## 7. 复核结论

- 真实问题：1 项（`scan_record_core.py` 尾部多余空行），已最小化修复并 `git add -- scan_record_core.py`，`git diff --cached --check` exit=0，记录用例 38 OK 无回归；本轮最终修改仅此 EOF 空行，未改任何 runtime 逻辑或其它文件。
- 其余各层契约：PASS，未发现需改动的逻辑缺陷。
- 状态：**PASS**，可进入收尾提交（提交由主会话执行，本轮未 commit / 未 push）。
