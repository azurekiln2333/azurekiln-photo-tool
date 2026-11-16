# pi-scan 实施报告：media_statistics_core.py

日期：2026-11-15 ｜ 归属：pi-scan ｜ 任务：11-15-folder-media-statistics

## 交付范围

- `media_statistics_core.py`（新增，仅标准库；不导入 PyQt、不导入 GUI 模块）
- 本报告 `research/pi-scan-report.md`
- 临时验证脚本（可删）：`research/_tmp_pi_scan_check.py`、`research/_tmp_pi_scan_smoke.py`、`research/_tmp_pi_scan_junction.py`、`research/_tmp_pi_scan_stream.py`

未触碰其他 Pi 的文件（`media_readme_core.py`、`media_statistics_gui.py`、`unified_gui.py`、README/docs、spec）。

## 公共 API（与 parallel-contract.md 一致，已移除测试专用计数器）

```python
@dataclass(frozen=True)
class ScanIssue:      path: Path; message: str                    # message 为中文原因
@dataclass(frozen=True)
class FolderSnapshot: path; parent_path; name; direct_image_count; direct_video_count;
                      image_count; video_count; complete; issue_count
                      # 额外只读属性：total = image+video，direct_total = direct_image+direct_video
@dataclass(frozen=True)
class ScanOutcome:    root; folders: tuple[FolderSnapshot, ...]; errors: tuple[ScanIssue, ...]; cancelled: bool
                      # 额外只读属性：complete = not cancelled and not errors；total = 根目录总项数

def scan_folders(root, image_suffixes, video_suffixes, *, stop_event=None, on_batch=None) -> ScanOutcome
```

模块导出：`ScanIssue`、`FolderSnapshot`、`ScanOutcome`、`scan_folders`、`BATCH_SIZE`(=64)。
（无 `counter` 参数、无 `MediaCounter`/`content_opens`、无 `MAX_PENDING_UPDATES`。）

- `root` 接受 `str | Path`，输出一律为**绝对路径**（`os.path.abspath`，不做 `resolve()`，不跟随链接）。
- 扩展名集合由调用方传入；内部 casefold + 自动补前导点（`"jpg"` 与 `".JPG"` 等价）。
- `on_batch: Callable[[list[FolderSnapshot]], None]`，每批 **≤ `BATCH_SIZE`(=64)**：
  - **父快照一定先于其后代**；每进入一个目录即发一次快照。
  - 同一目录会被再次通知（计数值更大的汇总快照）→ 调用方必须按路径**覆盖**，不可累加。
  - 收到子目录快照后，其**祖先计数会同步刷新并排队通知**，因此 GUI 持有的父节点计数不会长期滞后于已通知子目录之和（取消时也成立）。
  - 祖先更新同样逐条经 `emit()` 入队，**任何一批都不超过 BATCH_SIZE**（已修复历史上一次性批量 flush 祖先导致 111 条超限的问题）。
  - 扫描结束把全部目录最终快照再发一遍并 flush；回调抛异常被吞掉，不中断扫描。
- `stop_event`：协作式取消；取消后 `cancelled=True`、`complete=False`，所有已发现目录 `complete=False` 且 `issue_count>=1`，已发现计数保留。
- 目录枚举失败 / 条目类型判定失败 / 迭代中途失败：**不抛异常**，记入 `errors`（`ScanIssue.path` + 中文 message），该目录及全部祖先 `complete=False`、`issue_count` 累加。

GUI 侧使用建议（pi-gui）：按 `path` 覆盖入模型，`parent_path is None` 即根行；`complete=False` 显示“不完整”；`stop_event.set()` 请求停止，不要 `terminate()` 线程。

## 实现要点

- `os.scandir` + 显式栈（无递归调用，支持极深目录）；`with` 关闭迭代器。
- **流式迭代单个目录**（`next(iterator)` 而不是 `list(iterator)`）：大目录可被停止事件及时打断，迭代中途抛错也保留已统计条目。
- **先判定类型再匹配扩展名**：`link → 跳过`、`dir → 递归`、`file → 按扩展名计数`。因此名为 `album.JPG` / `clip.MP4` 的**目录**仍会被递归统计。
- 类型判定只使用 `is_symlink()/is_junction()/is_dir(follow_symlinks=False)/is_file(follow_symlinks=False)`；**不 stat、不 open、不读内容、不哈希、不缩略图**。
- 条目类型判定失败（如 `OSError`）会记录 `ScanIssue` 并标记祖先不完整；**不再静默当成“非文件”**，避免假的完整零结果。
- 真实符号链接 / 目录联接在最前排除（文件与目录皆然）；**不**因 `REPARSE_POINT/OFFLINE/UNPINNED/RECALL_ON_DATA_ACCESS` 排除，云占位文件正常计入。
- 内部节点 `_DirNode` 只保存目录路径与计数，**不保留任何媒体文件路径**；对外 `FolderSnapshot` 冻结。
- 输出顺序：根在首位，其余按 (路径层级, casefold 路径) 稳定排序。
- 完整性用 `has_issue` 单一标志（`complete` 为其反），问题只计一次，汇总幂等。
- 已移除 `MediaCounter` / `content_opens` 等仅测试用 API；不再用“计数器恒为 0”当作无内容读取的证据，改为 mock（monkeypatch `builtins.open`、`os.open`）证明。

## 实际验证命令与结果

均在 `D:/MyNewProject/LivePhotosSpilt`，使用 `.venv/Scripts/python.exe`（Python 3.14.0）。

1. 语法检查
   ```
   .venv/Scripts/python.exe -m compileall -q media_statistics_core.py   → exit=0
   ```

2. 核心行为验证（`tempfile` 临时树，不碰用户 OneDrive）
   ```
   $env:PYTHONIOENCODING="utf-8"; $env:PYTHONPATH="D:/MyNewProject/LivePhotosSpilt"
   .venv/Scripts/python.exe .trellis/tasks/11-15-folder-media-statistics/research/_tmp_pi_scan_check.py
   PASS 基础树计数 / 不打开媒体内容 / 云占位计入 / 链接排除 / 错误与 partial / 取消 /
       批次与覆盖 / 媒体后缀目录 / 条目判定错误 / 迭代中断保留计数 / 批次上限（含祖先更新）
   失败数: 0
   ```
   覆盖与断言：
   - 临时树：根直属 2 图 1 视 + `readme.txt`/`notes.log` 干扰项、`2025/2025-01`、`2026`（直属 top.jpg/top.mp4）、`2026/2026-11`、`deep`、`extra`、空目录 `2024/2024-12`、`case/` 内全部 8 图 7 视频扩展名（含全大写）。
   - 逐目录断言 `(image_count, video_count)`、`total == image+video`、`complete`、根汇总 `(16, 11)`、`outcome.total == 根 total`、目录路径无重复。
   - 快照路径全为绝对路径；首批以根快照开头；用“首次出现序号”断言**父快照先于所有子快照**；末批含根最终快照。
   - **媒体内容零打开**：monkeypatch `builtins.open` 与 `os.open` 记录全部调用，扫描 3 个混合媒体后 `opened == []`。
   - 云占位模拟：包装 `os.scandir` 为“只暴露名称/类型、不是链接”的 DirEntry 替身，`cloud.jpg`、`online.mp4` 均计入且 `complete=True`。Windows 无法为普通文件伪造 `FILE_ATTRIBUTE_*`，此测试仅验证“云属性不等于应跳过”的判定路径，不代表真实 OneDrive 端到端验证。
   - 错误/partial：`scandir` 对 `locked/` 抛 `PermissionError` → `errors` 1 条（中文“没有访问权限”）、`locked` 与根均 `complete=False`、根 `issue_count==1`、根仍保留已发现计数 2、无错误子目录自身仍 `complete=True`；根目录不存在 → 1 条错误、`total==0`、不抛异常。
   - 取消：400 个子目录，`on_batch` 期间 `stop_event.set()` → `cancelled=True`、`complete=False`、`0 < total < 400`、根计数覆盖全部已通知子目录、所有目录 `complete=False` 且 `issue_count>=1`；预置 `stop_event` → 仅根快照、`total==0`、`cancelled=True`。
   - 批次：200 子目录 → `len(folders)==201`、每批 ≤64、多批、按路径覆盖后根 total 正确。
   - **回归 1（媒体后缀目录）**：`album.JPG/inner.png + inner2.mp4`、`clip.MP4/deeper/b.heic`、根 `normal.jpg` → `album.JPG` 与 `clip.MP4` 均被枚举，根 `direct_image_count==1`（目录不计为文件）、`total==4`、`complete=True`。
   - **回归 2（条目判定错误）**：DirEntry 替身对 `broken.jpg` 的 `is_symlink()` 抛 `PermissionError` → `errors` 1 条且 `path == broken.jpg`、信息含“条目类型”、根 `complete=False`、`issue_count==1`、其他条目计数不受影响（`total==1`）。
   - **回归 3（迭代中途异常）**：自定义迭代器先产出 3 个媒体再抛 `OSError` → `cancelled=False`、`complete=False`、`errors` 1 条、根 `direct_image_count==2 / direct_video_count==1`、`total==3`、`complete=False`、`issue_count==1`（旧 `list(iterator)` 实现会丢失这 3 个计数）。

3. 停止与大目录（`_tmp_pi_scan_stream.py`）
   ```
   A cancelled=True root_total=318 notified_children_sum=318 ok=True last_root_snap=318
   A all incomplete: True
   B cancelled=True partial=19620/200000 preserved=True complete=False issue=2
   C total=600 folders=601 complete=True elapsed=0.04s
   ```
   - A：500 个子目录在中途停止后，根计数 ≥ 所有已通知子目录之和（不再滞后）。
   - B：单目录 20 万个文件，20ms 后置位停止 → 流式迭代及时中断，保留部分计数并标记不完整。
   - C：300 组年/月目录完整扫描 600 项，0.04s，结果完整。

4. 契约/冒烟（只读 `sample/` 与临时目录）
   ```
   FolderSnapshot fields: ['path','parent_path','name','direct_image_count','direct_video_count','image_count','video_count','complete','issue_count']
   ScanOutcome fields:    ['root','folders','errors','cancelled']
   ScanIssue fields:      ['path','message']
   sample → 根 8 图 5 视 = 13，子目录 HarmonyOS2/4/6 汇总正确，outcome.complete=True
   str 根 + 无点扩展名（"jpg"/"JPG"/"mp4"）→ 正常，13
   ```

5. 真实目录联接排除（临时目录 + `cmd mklink /J`）
   ```
   mklink /J rc: 0
   junction present: True | folders: ['r', 'y', 'm'] | total: 1
   ```
   联接 `jm -> y` 未被遍历、未重复计数；`os.symlink` 在获授权环境下同样断言通过。

## 已知边界（与 design 一致）

- 取消是协作式的：已阻塞的云文件系统调用不会被强行中断，线程需等系统调用返回。
- 扫描是文件系统瞬时快照，不保证事务一致性；扫描期间目录变化会体现为部分计数或错误。
- 未在本模块中进行真实 OneDrive 仅联机项的大规模端到端验证（仅本地临时树 + 属性语义模拟）。
- 未对真实用户相册做写入或修改；验证仅读取仓库 `sample/` 与临时目录。

## 本轮修复记录（协调者复核 4 项）

1. **媒体后缀目录被忽略** → 判定顺序改为 `link/dir/file` 优先，扩展名只在 `file` 分支使用；新增回归用例 `媒体后缀目录`。
2. **条目类型判定异常被吞** → 新增 `_classify_entry`，异常时 `mark_issue` 并记录 `ScanIssue`（中文），祖先不完整；新增回归用例 `条目判定错误`。
3. **`list(iterator)` 阻塞取消 / 丢计数** → 改为流式 `next(iterator)` + 每次循环检查停止标志，迭代异常保留已统计条目；显式栈保留；新增回归用例 `迭代中断保留计数` 与大目录停止验证 A/B。
4. **测试专用 `MediaCounter/content_opens`** → 已删除，API 回到契约（无 `counter` 参数）；“不打开内容”只用 mock 断言。

### 追加修复（批次上限）

5. **`flush_updates` 绕开 `emit` 导致批次超限** → 协调者复现：100 个直属子目录（各含 `month/a.jpg`）时 `sizes=[64,64,64,111,64,64,64,9]`。原因是祖先快照直接 `pending_batch.append(...)` 后一次性 `flush()`。现改为**逐条经 `emit()` 入队**，保留“按路径排序 ⇒ 父先于子”与最终计数。
   - 修复后同一夹具：`sizes=[64,64,64,64,64,64,64,56]`，`max=64 <= 64`，`total=100`、`complete=True`、`folders=201`。
   - 已作为常设回归用例 `批次上限（含祖先更新）`，全套 11 项 PASS。
   - 取消/部分结果不受影响：A 根计数 318 ≥ 已通知子目录之和 318 且全部不完整；B 20 万文件中途取消保留 7798 项并标记不完整。
   - `MAX_PENDING_UPDATES` 常量与注释、`MediaCounter` 相关残留均已不存在。

## 未执行/交回主会话

- 未做 Qt 集成（属 pi-gui）与统一入口接入（属 pi-integrate）。
- 未打包验证（core 无新增依赖，静态 import 由 spec 分析器收集）。
- 临时脚本 `research/_tmp_pi_scan_check.py`、`_tmp_pi_scan_smoke.py`、`_tmp_pi_scan_junction.py`、`_tmp_pi_scan_stream.py`、`_tmp_pi_scan_batchvar.py` 可删除或保留为验证证据。
