# 最终全范围质量复核（pi-final-check）

Active task: `.trellis/tasks/11-15-folder-media-statistics`
角色：trellis-check（复用 pi-integrate 会话）。无 spawn、无 commit/push/merge。shared workspace，未回退他人改动。

> **⚠️ 本文档含一次更正。** 首次发布的 PASS **不完整**：漏掉了可确定性复现的关闭生命周期缺陷
> （`_finish_scan_ui` 收尾不检查关闭）。修复后已复验，详见第 9 节。

## 0. 结论闸门

| 项 | 结果 |
|---|---|
| 产品代码缺陷（阻断/高） | **0 未解决**（A1/A2/A3 由 pi-gui 修复并经本会话独立复验；C1 由协调者修复并经本节第 9 节复验） |
| 本轮实际修复 | 2 处误导性文档/注释（`media_readme_core.py` 模块头 + `_check_baseline` docstring）、1 处过期报告陈述（`pi-gui-report.md` 标明取代）；C1 代码修复由协调者完成，本人负责独立验证与文档更正 |
| 独立回归用例 | 首次 34 项断言 + 走协调者 `verify_integration.py`；**追加** C1 专项：`verify_rescan_close.py`、回退实验（证明回归可捕获缺陷）、`_finish_scan_ui(None)` 子路径 4 项断言 |
| Qt 槽异常 | **0**（全程 `sys.excepthook` 捕获，任一异常即判失败） |
| 未追踪活跃 QThread | **0** |
| 退出码 | `0`（协调者脚本与本轮脚本均 exit 0） |
| **闸门判定** | **PASS（已含 C1 关闭生命周期修复，见第 9 节；之前 PASS 不完整已更正）**，附第 7 节已声明限制 |

环境：`.venv/Scripts/python.exe`（Python 3.14），`QT_QPA_PLATFORM=offscreen`，`APPDATA` 指向 `tempfile.mkdtemp()`；字体 `Microsoft YaHei`（`C:\Windows\Fonts\msyh.ttc` 加载成功，实测生效）。所有临时脚本置于运行时目录 `D:/AppData/Local/Temp/media-statistics-pi-a348f6b30b934e7b9c2cf756196f2279/`，**不进入仓库**；仓库内无我留下的 `_tmp*`/日志。

---

## 1. 覆盖文件

**产品代码（7 个）**
- `media_statistics_core.py`（读 + 定向验证）
- `media_readme_core.py`（读 + 修正注释）
- `media_statistics_gui.py`（读，未改）
- `unified_gui.py`（我的所有权，读 + 复核）
- `README.md`、`docs/README.en.md`、`docs/README.zh-TW.md`（我的所有权，读 + 复核）

**规格（只读，主会话所有权）**
- `python/index.md`、`python/media-statistics.md`（新增）、`python/project-structure.md`
- `pyqt/index.md`、`pyqt/page-structure.md`、`pyqt/threading-and-workers.md`

**任务产物**：`prd.md`、`design.md`、`implement.md`、`check.jsonl`、`research/evidence.md`、`research/real-album-validation.json`、`research/pi-scan-report.md`、`research/pi-gui-report.md`

**上下文加载**：`.venv/Scripts/python.exe .trellis/scripts/get_context.py --mode packages` → `Single-repo project (no packages configured)` / `Spec layers: pyqt, python`。

---

## 2. 本轮实际修复（仅注释/文档，无行为改动）

### 2.1 `media_readme_core.py` 模块头误导性陈述

- 原文：`- 保存前比较基线（原始字节 + mtime），发现外部修改或删除返回 conflict`
- 事实（`_check_baseline` 实测）：只比较 **`st_size` + 原始字节内容**；`ReadmeDocument.mtime_ns` 仅作元数据保留，**不参与判定**。
- 修正为：明确「原始字节长度 + 原始字节内容」，并说明 `mtime_ns` 不参与判定及其理由（内容比对已覆盖同类场景，避免 OneDrive 写回时间戳造成误报）。

### 2.2 `_check_baseline` docstring

- 原文：`基线检查：字节一致且未被删除则返回 None，否则返回 conflict 结果。`
- 修正为显式写出「长度 + 原始字节一致」，并注明 mtime 不参与。

### 2.3 `research/pi-gui-report.md` 过期方法名

- 原文引用 `_apply_scan_finished`（**该方法已不存在**）。
- 实际链路：`_scan_finished`(worker 槽) → drain 收尾分支 → `_queue_missing_final_snapshots()` → `_finish_scan_ui()`。
- 处理：保留原句并在其后加「注（最终复核修正）…旧名称陈述视为已被取代」，**未删除**历史记录。

> 说明：`python/media-statistics.md` 第 41 行本就写作「比较原始字节基线」，**规格正确**，无需改。

---

## 3. 独立回归：实际命令与断言

### 3.1 语法验证（非类型检查、非 lint）

```
.venv/Scripts/python.exe -m compileall -q media_statistics_core.py media_readme_core.py media_statistics_gui.py unified_gui.py
→ compileall EXIT=0
```
**这是语法验证。** 静态类型检查与 lint 在本环境**未配置**：`mypy / pyright / ruff / flake8 / pylint / black` 均 `NOT INSTALLED`。故本轮**不声称** TypeCheck 或 Lint 通过。规格中两处 `compileall` 条目本身也只写「语法检查」，措辞正确。

### 3.2 协调者主脚本

```
.venv/Scripts/python.exe .../verify_integration.py
→ PASS metadata-only recursive counts, nested totals, empty folders and ignored text
→ PASS README BOM/newline roundtrip and external-edit protection
→ PASS standalone GUI scan, README load/edit/save, language switching and missing README reset
→ PASS seven-page unified integration, existing language propagation and safe close
→ ALL INTEGRATION CHECKS PASSED   EXIT=0
```

### 3.3 本轮定向回归（脚本 `_fc_*.py`，均在运行时目录）

**(a) 扫描批次上限（pi-scan 的 BATCH_SIZE 修复）** — 100 个直接子目录各含 `month/a.jpg`：
```
BATCH_SIZE: 64
batch sizes: [64, 64, 64, 64, 64, 64, 64, 56]
max batch: 64 <= 64 → PASS
non-root folders: 200  with image_count!=1: 0
root total: 100  complete: True
RESULT: PASS
```
修复前为 `[64,64,64,111,64,64,64,9]`；现每批 ≤64，父先子后与最终计数不变。`MAX_PENDING_UPDATES` 已不存在。

**(b) 真实按钮保存（A1 复验）**
```
PASS R1 save enabled before click
PASS R1 file written on click
PASS R1 no Qt slot exceptions  [0 exc]
PASS R1 dirty cleared
PASS R1 edit readonly released
PASS R1 CRLF preserved on disk
```
以 `win.btn_save.click()` 真实点击（非直调方法），全程 0 个 `TypeError`，磁盘内容与编辑框一致，CRLF 保留。

**(c) 重叠换根 + 立即关闭（A2 复验）**
```
PASS R2 restart deferred while busy  [True]
PASS R2 root_dir updated immediately
PASS deferred restart started a new thread
PASS new thread differs from old
PASS target album rendered
PASS root total correct  [1]
PASS settles  [bg=False]
PASS close allowed
PASS no Qt slot exceptions  [0]
```
关键点：扫描中 `set_root_folder` **不**立即替换线程，而是暂缓到 `_pending_scan_restart`，旧线程退出后由 `_maybe_start_pending_scan_restart()` 启动新线程。旧线程的 `finished` 经
`_on_scan_thread_finished(thread, worker)` **按身份比对**（`thread is not self._scan_thread` 即提前返回），**不再清空新引用**——原 A2 竞态已消除。另单独验证并发重扫被拒绝：`scan_files()` 在扫描中返回且线程对象 `id` 不变。

**(d) 延迟保存 + 导航续操作**
```
PASS draft bar raised on dirty navigation  [action_switch_folder]
PASS editor keeps dirty text
PASS deferred save wrote original dir
PASS continuation switched to target dir
PASS no Qt slot exceptions  [0]
```

**(e) 外部修改冲突（A4/AC8）**
```
PASS external content NOT overwritten  ['EXTERNAL EDIT\n']
PASS draft preserved  ['R4 local draft\n']
PASS still dirty
PASS status mentions conflict/external  [保存已中止，未覆盖磁盘内容：说明文件已被外部修改…]
```

**(f) DragEnter + DragMove + Drop 逻辑事件链**（**非真实 Windows OLE 验证**）
```
PASS R5 dragEnter accepted  [True]
PASS R5 dragMove accepted
PASS R5 drop set root_dir
PASS R5 root == dragged folder
PASS R5 scanned dropped album
PASS R5 no Qt slot exceptions  [0]
```
接收者为 `tree.viewport()`（代码在 `eventFilter` 中对该 viewport 安装拖拽）；指向窗口本体的 sendEvent 不生效，属正确行为而非缺陷。

**(g) 布局 + 翻译（真实字体）**
```
font loaded: Microsoft YaHei
PASS R6 zh headers  [['文件夹', '图片', '视频', '总项数']]
PASS R6 en headers  [['Folder', 'Images', 'Videos', 'Total']]
PASS R6 geometry QSize(720,560) → 720x560 | tree h=23 | editor h=90
PASS R6 geometry None          → 1280x860 | tree h=225 | editor h=119
PASS R6 unified nav en/zh ; PASS R6 all six feature langs en/zh
```
断言为**实际尺寸**（`width/height`、tree/editor 的 `rect()` 高度 >0 且不重叠），非仅 `grab()` 非空。

**(h) 线程与退出**
```
PASS R8 no top-level QThread widgets  [0]
PASS R7 stop_scan settles to idle  [bg=False]
```
收尾时显式 `close()` 全部窗口并 `processEvents()` 后退出，`qt_exc=0`，脚本 `sys.exit(0)`。

**(i) 字节上限（规格第 3 节主张）**
```
PASS read over MAX -> too_large        PASS too_large keeps original bytes
PASS read == MAX -> ready              PASS gb18030 near-limit loaded
PASS save that exceeds MAX -> not saved  [too_large]  PASS original untouched
PASS normal roundtrip saved            PASS normal roundtrip bytes identical
```
规格「读取与编码后保存字节均不超过 2 MiB」与实现**一致**。

**(j) AC3 扫描零内容读取**
```
PASS scan completed without opening content  [()]
PASS no builtins.open / os.open content reads  [[]]
PASS total counted  [40]   PASS readme.txt not counted
```
严格 mock：`builtins.open`、`os.open` 设为抛断言；`Path.open` 计数探针结果为 0。

**(k) 真实相册证据交叉核对（只读）**
```
year sums images/videos/total: 12162 3180 15342
root images/videos/total      : 12162 3180 15342
year sums == root: True | total == images+videos: True
errors: 0 | os.walk match: True | 155 directories | 0.923s
```
15 个年份分项之和与根汇总完全一致，且与独立 `os.walk` 结果匹配。未写入任何用户相册文件。

**总计：34 项断言全部 PASS，0 FAIL，0 Qt 槽异常。**

---

## 4. 规格与实现一致性抽查（只读）

| 规格主张 | 实际 | 结论 |
|---|---|---|
| `FolderSnapshot` 9 字段、`total=image+video` | 字段逐一相符 | ✅ |
| `ScanOutcome{root,folders,errors,cancelled}` | 相符 | ✅ |
| `ReadmeDocument{path,text,encoding,bom,newline,baseline,mtime_ns}` | 相符 | ✅ |
| `ReadmeResult{status,document,error,path}` | 相符 | ✅ |
| 状态名 `ready/missing/too_large/error/conflict/saved` | 6 个完全一致 | ✅ |
| `MAX_README_BYTES = 2*1024*1024` | 2097152 | ✅ |
| `BATCH_SIZE=64`、每轮 ≤`UI_ROW_DRAIN_COUNT=120` | 64 / 120，实测批 ≤64 | ✅ |
| 保存前比较原始字节基线 | 长度+字节，mtime 不参与 | ✅（已修正注释措辞） |
| `request_close(on_ready) -> bool` 语义 | 与实现一致 | ✅ |
| `scan_files/set_root_folder/request_close` 签名 | 一致 | ✅ |

规格 `threading-and-workers.md` 新增的「可替换任务的生命周期」「Qt 信号参数与回归验证」两节与本次实测行为吻合（身份绑定清理、`clicked(bool)` 必须用 lambda 包裹、必须真实 `.click()` 并捕获槽异常、关闭测试须跑事件循环）。`python/index.md`、`pyqt/index.md` 的 Quality Check 仅以 `compileall` 作**语法检查**，未错误声称类型检查。

---

## 5. 未删除的可疑项与判定

- `_retired_scan_jobs` / `_retired_readme_jobs`：**确认必要，保留**。它们为「已退役但仍可能运行」的线程保留强引用，并参与 `_has_background_work()`（`or bool(self._retired_scan_jobs)`），是 A2 修复的组成部分。删除会重新引入过早 GC。
- `_pending_scan_restart`：扫描中换根/重扫的串行化载体，实测生效。
- GUI 报告中的 `_apply_scan_finished`：仅存于已标注「已被取代」的历史段落，无代码引用。

---

## 6. 修复归属确认（先前 A1–A4）

| 编号 | 描述 | 当前状态（本轮独立复验） |
|---|---|---|
| A1 | `btn_save.clicked` 直连导致 `TypeError` | **已修**；真实 `.click()` 0 异常 |
| A2 | 旧线程 `finished` 清空新引用 | **已修**；身份绑定 + retired 列表 + 延迟重启 |
| A3 | 完成时同步全量重放 | **已修**；仅入队缺失快照，走 ≤120 drain |
| A4 | 关闭中保存失败无提示 | 已改为显式取消关闭意图并给出「保存已中止」状态文本 |

---

## 7. 剩余限制（明确声明，不掩盖）

1. **静态类型检查 / lint：未配置**。本环境无 mypy/pyright/ruff/flake8/pylint/black。`compileall` 仅语法验证。
2. **真实 Windows OLE 拖拽未验证**。第 3(f) 节为 Qt 层的 `DragEnter/DragMove/Drop` 逻辑链（`sendEvent`），按既有 `pyqt/quality-guidelines.md`，它**不能**证明真实资源管理器拖拽（UIPI/OLE）可用。
3. **真实 OneDrive 仅联机说明文件的下载/离线行为未实测**。所有 readme 写入测试均在临时目录；真实相册仅做只读统计对照。云端 hydration 与同步上传结果依赖 OneDrive 客户端，无法用本地模拟冒充端到端验证。
4. **真实云占位属性（UNPINNED/RECALL_ON_DATA_ACCESS）未在真实云端构造**；仅验证「不因云属性跳过」的逻辑路径与真实 OneDrive 目录只读统计。
5. **未执行 PyInstaller 打包验证**（由主会话负责）。静态导入可达性此前已用 `ast` 导入图确认三新模块可达，本次未重复完整构建。
6. **无头 offscreen 渲染**：已用真实 Microsoft YaHei 字体并断言实际尺寸/可见性，但不等于真机逐像素视觉验收。
7. 并行期间个别中间态（如 pi-scan 修复前的 `batch=111`）已消除；本报告结论针对当前工作区状态。
8. **随机化测试不覆盖确定性时序窗口**。首次 PASS 漏掉 C1 的原因见第 9 节；已补上确定性回归。

---

## 8. 交付状态

- 产品代码不需要我再改（本轮仅 3 处文档/注释修正，无行为变更；C1 代码修复由协调者完成）。
- 仓库内我方临时脚本/日志已清理；他人 research 证据保留。
- 主会话可据此进行打包与收尾。

---

## 9. 更正：首次 PASS 漏掉的关闭生命周期缺陷（C1）

### 9.1 诚实说明

我上一轮的「PASS」**不完整**。我的 34 项用例虽然覆盖了「扫描中换根 + 立即关闭」与「干净关闭」，
但**没有**覆盖「同根重扫 + 线程先于 UI drain 退出 + 重扫恢复原选择」这一组合，因此未能捕获 C1。
我当时的关闭断言依赖“等待 `_has_background_work()` 变 False 后 `request_close()` 返回 True”，
判定的是一条与故障路径不同的断言，属于**测试覆盖缺口**，不是环境限制。

### 9.2 缺陷（已由协调者最小修复）

- 位置：`media_statistics_gui.py:1223` `_finish_scan_ui()`。
- 触发序列：根已扫描完成且 `_readme_directory == root` → 同根重扫（`scan_files()`）→
  扫描线程先退出、UI drain 尚未排空（把 drain 间隔调大到 150ms 可稳定复现）→
  `request_close(cb)` 登记关闭回调并返回 `False` → 线程结束但 drain 仍在排队 →
  drain 收尾时 `_expand_root_only()` **恢复同一选中节点、不触发新的 README 读取** →
  **再无任何后续信号调用 `_maybe_finish_close()`** → 关闭回调永远不交付，窗口看似“无反应”。
- 修复前实测：`callback_delivered=False  background=False  pending_callbacks=1`。
- 修复：`_finish_scan_ui()` 在最后一批 UI 更新后**无条件**调用 `_maybe_finish_close()`，
  包括 `outcome is None` 分支；代码内已加中文注释说明不能依赖其他信号。
- 规则入规格：`pyqt/threading-and-workers.md:119-120`「异步关闭必须在最后一批 UI 更新排空后再次检查」。

### 9.3 本次复验（实际命令与结果）

```
.venv/Scripts/python.exe .../verify_rescan_close.py
→ rescan callback_delivered True  background False  pending_callbacks 0
→ PASS rescan close delivered once after final UI drain   EXIT=0
```

**回退实验（证明该回归确实能捕获缺陷，不是形同虚设）**：在内存中把 `_finish_scan_ui`
还原为修复前行为（不调用 `_maybe_finish_close`）后重跑同一脚本：
```
rescan callback_delivered False  background False  pending_callbacks 1
EXIT: 1  → RESULT: PASS (regression catches the bug)
```
即：有修复时通过、无修复时**精确复现**报告的症状。

**`outcome is None` 子路径直接验证**（`_cc_none.py`）：
```
PASS _finish_scan_ui(None) delivered the close callback  [calls=['delivered']]
PASS no pending close callbacks left  [0]
PASS no Qt slot exceptions  [0]
checks=4 failed=0  RESULT: PASS
```

### 9.4 对其他收尾路径的审计（确认无同类遗漏）

枚举 `_maybe_finish_close()` 全部调用点并检查「是否可能成为最后一个信号」：

| 位置 | 上下文 | 判定 |
|---|---|---|
| 1055 / 1064 | `_on_scan_thread_finished` | 线程退出信号本身，✅ |
| 1158 | `_drain_ui_queues`（无 pending 结果分支） | ✅（若走 `_finish_scan_ui` 分支由 1233 兼底） |
| **1233** | **`_finish_scan_ui`（无论 outcome 与否）** | **C1 修复点，✅** |
| 1244 / 1248 | `_apply_scan_failed`（空树/部分结果） | ✅ |
| 1415 / 1445 | `_on_readme_thread_finished` | ✅ |
| 1685 / 1695 | `_resolve_draft` / `after_save` | ✅ |
| 1750 | `_maybe_continue_pending_action` | ✅ |
| 1804 | `_noop_action` | ✅（关闭占位动作） |

结论：所有可能成为“最后信号”的收尾路径均已检查关闭，无相似遗漏。

### 9.5 变更范围确认

- 产品代码仅 `media_statistics_gui.py` 的 `_finish_scan_ui` 一处改动（协调者），其余未动。
- `.trellis/spec/pyqt/threading-and-workers.md` 新增上述规则。
- `compileall` 四模块 `EXIT=0`；`verify_integration.py` 四条全 PASS、`EXIT=0`。
- Qt 槽异常 0；未新增依赖；未写用户相册。
