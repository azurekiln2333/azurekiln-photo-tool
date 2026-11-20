# pB 独立审查（最终 PASS，已停笔）

任务：`.trellis/tasks/11-21-dedupe-groups-keeper`；分支 `feat/dedupe-groups-keeper`。
状态：已获 root 实施阶段审查授权；仅拥有相关 spec 与本文，不编辑 owner 的产品/测试源码，不 commit/push/tag，不改任务状态，不 spawn/换模型。

## 1. 已读取 / 当前审查边界

- 已重新读任务 PRD/design/implement、manifests，读取三份 owner 设计：`research/contracts.md`、`pi-ui-plan.md`、`pi-test-plan.md`；及 before-dev/check skill、python/pyqt 索引、相关契约和共享跨层检查指南。
- 核心/页面/测试仍由 p4/p8/pA 所有；缺陷只以具体调用链/失败断言反馈 root/owner，不抢写其源码。
- 当前可见 source diff 仅 root 改动的 `unified_gui.py:38`，`APP_VERSION` 从 `1.2.2` 改为 `1.2.3`；无别的 runtime 差异。三份 owner 研究文档仍标 planning，待正式冻结/实现时按实际代码复核，不能把计划当作已交付 API。
- 不跑 PyInstaller；独立全量等 root 明确源码稳定通知。尚未声称本轮测试通过或发布成功。

## 2. git/gh 远端可用性（实际只读检查）

| 检查 | 结果 | 含义 |
| --- | --- | --- |
| `git branch --show-current` | `feat/dedupe-groups-keeper` | 与 active branch 一致 |
| `git ls-remote --heads github feat/dedupe-groups-keeper` | exit `0`，输出为空 | git transport 可用；该新分支目前尚无远端 ref，不代表连接失败 |
| `Get-Command gh` | 未安装 | 不安装新工具，不宣称 gh 登录/权限已验证 |
| GET GitHub repo API（首次匿名、无写操作） | HTTP **403 rate limit exceeded** | 匿名通路受限后停止重复请求；不是仓库不存在，也不是 CI 结论 |
| GET GitHub repo API（root 指定的内存凭证通路） | HTTP **200**，剩余额度 `4855`，default_branch=`main` | `subprocess.run(git credential fill)` 捕获输出只在内存解析 password 作 Bearer；关闭交互；未打印/保存凭证 stdout/token，未安装 gh |

后续可用已认证 REST 做只读 Actions/Release/资产观察，无需匿名重试或安装工具。发布时必须真实读取 run/资产，不能用 git 连通推断 Actions/Release 成功。

## 3. CI 无 ExifTool / 跨盘兼容检查方案

### 保留现有门禁

- CI `python -B -m unittest discover -s tests -v`，`QT_QPA_PLATFORM=offscreen`，临时 APPDATA/LOCALAPPDATA，step 超时 5min；不移动/跳过门禁，不新增 skip。
- `tests/test_unified_close.py` 只替身非受测 Flyme 的 `LivePhotoFixTool` 构造，真实统一窗/目录页/QThread 和关闭断言应保持；resolver/critical 的 `assert_not_called()` 不能删除。
- 相对根测试必须把真实扫描与异步导出完成放在 `contextlib.chdir(temp_root)` 范围内；不能从 D: repo 对 C: TEMP 做 `relpath`，异常也须恢复 cwd。

### source 稳定后执行（本批未运行）

1. 在独立进程、隔离 APPDATA/LOCALAPPDATA 下运行所有 unittest；`sys.excepthook` 和线程销毁错误须导致失败，不能只看打印的 PASS。
2. CI-like 过程把 `EXIFTOOL_PATH` 指向不存在的临时文件，限制 PATH 为 Python/Windows 必需路径；额外包裹 `flyme_livephoto_fix_core.resolve_exiftool` 为“触发即失败”，确保整个关闭测试构造不会借用本机默认目录里的 ExifTool。该 resolver 守卫仅用于该独立验证进程，不写测试/产品源码。
3. 若 C: 临时目录与 D: repo 可访问，在 C: 独立临时目录设置 TEMP/TMP，并在加载测试前设置 `tempfile.tempdir`，打印实际盘符、cwd 恢复状态，再跑同一全量（不能仅改 env 后让旧 tempfile 缓存继续用 D:）。
4. 所有测试文件生成物在独立 temp，mock 回收，不接触真实相册/回收站；记录测试数、fail/error/skip 及每个 skip 原因。无可用跨盘环境则明确写未覆盖，不伪称通过。

## 4. 重点独立断言（待实现 diff 到位）

- 分组分类由整组成员按 photo > video > other 决定；重选 keeper 不拆组/跳组，隐藏筛选不重建 source row。
- 已读新增 `research/ui-contract.md`：控件冻结为 `btn_filter_photo/video/other`、`btn_set_keeper`；明确混合组预览逐槽判断，selected=other/keeper=photo 仅清 slot0，slot1 可预览 photo。这是对早期 UI 计划“other 整面清空”的具体化，以正式逐槽契约为实现审查依据，不把媒体参照侧的合法预览误报为 other 请求。
- “其他”按具体路径禁表格/详情 loader 请求，混合扩展名同组也不能给 other 路径请求；切换清掉旧图。
- keeper 从 A 改 B 必须改变 ScanResult.groups，不只是 UI；旧 A pending/默认勾，B keeper/强制未勾，C 原合法状态不丢；所有同组 keeper 引用和真实 recycle worker 参数同步。
- busy/cancelled/stale/任一已处理成员组禁止重选；候选必须当前组成员、当前文件快照有效；失败不能先部分改数据。
- 可见批量动作只改当前类别合法 target；隐藏组勾选仍保存，回收确认统计所有实际将处理的勾选，不隐藏危险目标数。
- schema v1 无须增加角色字段；新 keeper 来自更新后的 groups，旧 v1 记录能读，导入后 byte_verify 强制，不放宽 compare A/B 和 keeper 状态限制。
- 三重判重、碰撞保护、变更/删除回收前重验不退化；共享核心无 Qt/新依赖。
- 独立/内嵌、中英实际控件、按钮与线程关闭均须有证据；测试新增断言不能只断言按钮存在、不能吞未预期错误或 skip 掩盖。

## 5. 契约检查点 C1：视频子集草案漏 `.mkv`（待 owner 冻结时修正）

- 真实读取现有 `duplicate_scan_core.py` 的 `MEDIA_EXTENSIONS`：共 55 项，其中含 `.mkv`。
- `research/contracts.md` 第 2.1 节列出的视频子集为 21 项，遗漏 `.mkv`；按其建议 `MEDIA_EXTENSIONS - VIDEO_EXTENSIONS = photo` 实施会把 MKV 错归照片。
- 建议 p4 冻结时把 `.mkv` 纳入视频子集，分类测试明确断言 `.mkv/.MKV -> video`，并做全集覆盖。此时尚无分类函数 implementation diff，因此这是**待修草案差异**，不是已复现运行时缺陷；不编辑 owner 的契约/源码/测试。

## 6. 在写测试检查点 T1：两处假通过断言（pA 草稿，待收尾复核）

`tests/test_folder_dedupe_features.py` 新 `DedupeGroupsKeeperTests` 已落盘，仍在编写中，暂不跑整套以免把 owner 中间态误报为最终失败：

- `test_embedded_mode_and_english_refresh_all_new_controls` 用 `isEnabled() is False or isEnabled()`，对任意 bool 都为真；另 `assertNotIn(category, {'photo','video','other'} - {category})` 也恒真，未验证新分类按钮翻译。建议检查真实 enabled 预期、每个分类实际英文文本与 keeper 按钮译文；独立/内嵌控件可见性/布局如有断言应对应真实窗口。
- `test_keeper_change_record_round_trip_preserves_roles_and_states` 定义 `captured`/patch `DedupeRecycleWorker` 后只调用 `select_all_checkable()`，没有点回收按钮且未断言 captured；这不能证明 imported byte_verify 或新 keeper 到 worker 的链路。建议实际点击回收按钮、等待线程清理并断言捕获参数。现有旧测试的 byte_verify 覆盖应保留，但不应让本项名称声称比实际更多。
- `_typed_scan` 中 `set(self.window._current_result.groups.__class__ and self.window.category_buttons)`、预览测试的 `assertGreaterEqual(photo_requests, 0)`、核心测试 `assertEqual(path, old_path := path)` 同样没有新增保证，建议改为真正的基线/反例断言，不要靠 tautology 获 PASS。

上述均为直接阅读表达式可确定的**测试有效性**问题，已反馈 pA/root；不属于已复现 runtime bug，不改 owner 文件。

## 7. 实施问题 B1：既有 v1 单 keeper 组无法分类（已复现，待 p4/p8 修）

- `scan_record_core.py:_validate_group` 明确允许 internal `duplicates=[]`；既有 `tests/test_scan_record_core.py:InternalRecordTest._build` 也含这个合法 fixture。PRD R5 要求旧 v1 记录继续可读，不能收紧旧记录规则规避。
- 新 `classify_duplicate_group()` 直接对空 duplicates 抛 `ValueError('group_empty')`；新页面 `_update_category_metadata()` 对所有 result.groups 无条件调用该 helper。
- 实际执行的纯标准库临时记录探针（无 GUI/无真实媒体/无回收）：构造 `DuplicateGroup(keeper.jpg, [], 'a'*64, 1)` → `save_record` → `load_record(expected_mode='internal')` 成功，随后分类抛错。输出：
  ```
  OLD_V1_LOAD_OK=True; groups=1
  GUI_CATEGORY_INPUT_ERROR=group_empty
  ```
- 这是已存在的合法数据与新展示层接口不兼容，不是中间缺失方法。建议 p4 允许合法单 keeper 组按 keeper 类型分类（reselect 仍可拒绝无副本组），或由 p8 明确兼容旧组；pA 补真实导入按钮覆盖，不得放宽 keeper/target 安全校验，也不得改成拒绝旧 v1。
- owner 源码不由本 Pi 改。
- **B1 已由 p4 修复并独立复验关闭**：classifier 对空 duplicates 改按 keeper 分类，reselect 仍拒绝无候选组；新增 core 测试覆盖 photo/video/other 单 keeper。实际临时 GUI 探针走 `btn_import_record.click()` + 真实 RecordLoadWorker/QThread，旧 v1 keeper.bin 恢复为 other 类唯一 keeper，设保留/回收均 disabled、无 error notification、线程引用清空。DeferredDelete 后 `QT_SLOT_ERRORS=0`，进程 exit `0`。

## 8. 已完成局部审查与 spec 同步

- 纯内存独立探针 exit `0`：patch `Path.stat`/`builtins.open` 为失败，仍完成 MKV/video、CR3/photo、unknown/other 分类；混合组 A.jpg/B.bin/C.mp4 重选 B 后分类仍 photo、SHA/size 不变、原 group/list 不变，跨根 compare 组拒绝。C1 `.mkv` 修正闭环（video=22/media=55）。
- 页面 diff 已确认：分类只 `setRowHidden`；group_id/source row 保持；预览逐槽 other 传空；实际回收仍遍历全部类别并从当前 row.keeper 取新参照，imported 强制 byte_verify 逻辑保留。最终全量结果见第 10 节。
- 已局部更新：`python/duplicate-verification.md`（分类/重选无 I/O 与 compare 隔离）、`python/scan-records.md`（v1 新 keeper、旧单 keeper 兼容、按钮往返/worker 参数）、`pyqt/page-structure.md`（稳定行分类、可见批量/全局回收、逐槽 other 门禁）。仅改这些相关章节，未改产品/测试源码。
- 三个 spec 的 `git diff --check` exit `0`。
- **T1 已复读关闭**：恒真表达式已移除；预览有 photo 请求正向断言和 other 槽路径清空断言；keeper 记录往返后真实点回收、等待实际 worker 结束并断言新 keeper 与 imported 强制 byte_verify；独立/内嵌新增控件和 zh/en 文本有具体断言。worker fixture 显式取消其它类别默认 checked，不把产品回收改成仅当前 tab。

## 9. root 首轮全量与关闭池问题 B2（已修复闭环）

- root 首轮全量 214 项 / 2 fail：worker fixture 隐藏组默认 checked 问题已交 pA；另一项媒体生命周期探针检测残留 thumbnail-loader 线程。
- root 已定位真实产品原因：folder 页 `_release_thumbnail_loader()` 只停止 `self.thumbnail_loader`，遗漏 `self.preview_panel.shutdown()`；后者持有独立 ThumbnailLoader/pool，idle worker 卡在 queue.get 不会退出。对照 `dir_compare_gui.py` 同方法已正确双 shutdown，直接代码核对一致。
- p8 已补与 compare 同样的 preview shutdown；pA 已补 `test_video_preview_loader_threads_stop_on_shutdown`，启动真实请求、在 shutdown 前捕获线程并断言两池 stopped/线程退出，最终定向与独立全量均通过。本 Pi 未编辑产品/测试源码；既有 `tests/test_media_thumbnail.py`、`test_unified_close.py`、`test_compare_page_features.py` 无 diff，生命周期与关闭断言未放宽。
- **B2 产品修复已独立定向复验**：控制底层解码但保留真实两个 loader，各发一次请求启动独立池（table=2 threads、preview=2 threads），先捕获全部 Thread 引用，再走 `window.close()`，有界等待断言两池 `_stopped=True`、4 条捕获线程全部不再 alive；DeferredDelete 后 Qt 槽异常为 0，exit `0`。不是只看被清空的 `_workers`。首个 QA 草稿把 `preview_panel.loader` 误当属性而非方法，退出 1；修正 QA 调用为 `loader()` 后上述真实关闭探针通过，产品未为此调整。
- 新增伪 MP4 fixture 可替身底层解码来避免无关编码行为，但不能用它掩盖缺失 preview shutdown；必须由产品修复 + 回归闭环。

## 10. 最终独立 CI-like 全量（真实执行）

root 确认源码冻结、页面定向 25 tests OK 后，本 Pi 执行独立脚本文件，未使用交互 stdin、未改产品/测试源码：

```powershell
.venv/Scripts/python.exe -X utf8 -B C:\Windows\Temp\dedupe-ci-review-1e827e8be2c34111bd1bbdf60db914e1\run_ci_like.py
```

该临时脚本设置 C: TEMP/TMP 与 `tempfile.tempdir`、offscreen、隔离 APPDATA/LOCALAPPDATA；限制 PATH 并把 EXIFTOOL_PATH/EXIFTOOL_DIR 指到不存在的临时位置。正式 `exiftool_resolver.resolve_exiftool()` 实测返回 None（不是 mock resolver 后声称工具缺失）。随后使用 unittest discover 加载全部 `tests/test*.py`，测试后检查 cwd、源码哈希及 loader 线程残留。

| 断言 | 实际结果 |
| --- | --- |
| 全量 | **201 tests，0 failures，0 errors，3 skipped，9.233s** |
| 进程退出码 / 最终结论 | **0 / `CI_LIKE_PASS=True`** |
| 实际盘符 | 仓库 D:，临时目录 C: |
| ExifTool / ffmpeg | PATH 均找不到；正式 ExifTool resolver 返回 None |
| 相对根真实测试与统一关闭测试 | 均通过，执行结束 cwd 恢复 True |
| 全套结束 thumbnail-loader 残留 | **0**（有界排空后线程列表为空） |
| 冻结源码是否在测试期间变化 | **无变化**（10 个产品/测试文件前后 SHA256 一致） |
| 语法 / whitespace | 所审 10 个 Python 文件 AST 解析通过；`git diff --check` exit 0 |

逐模块数量：compare 17、duplicate core 89、file context menu 3、folder page 25、media thumbnail 26、scan records 39、unified close 2，合计 **201**。此前首轮 214 是中间态计数，最终 fixture 改为无测试方法的 mixin，不重复继承执行旧用例；最终应以 201 为准，未用删断言/新增 skip 降低门禁。

3 个 skip 均为既有 `test_media_thumbnail.LocalVideoDecodeTests`：`test_h264_decodes_without_shell`、`test_hevc_decodes_without_shell`、`test_video_decoder_timeout_is_bounded`，原因为“需要 ffmpeg 生成测试样片”。受限 PATH 特意不提供 ffmpeg；没有本任务新增 skip。

临时原始证据：上述独立 C: 目录下 `test.log`、`result.json`；不提交临时配置或媒体。root 另外报告最终标准全量 **201 tests OK / exit 0**、页面 **25 tests OK**、compileall 与 diffcheck 通过；这些与本 Pi 的 CI-like 实跑证据分开陈述。

## 11. 最终结论与停笔

**PASS，无未解决阻塞问题。** C1 分类遗漏、B1 旧 v1 keeper-only 兼容、B2 详情池关闭均已由 owner 修复并独立复验；T1 测试有效性已修正，完整 CI-like 全量通过。三重判重、compare A/B 方向、记录 schema v1 与导入强制逐字节复核保持。

已按 `trellis-update-spec` 局部更新四份文档：
- `python/duplicate-verification.md`：具体类型签名、无 I/O / compare 隔离、主要 ValueError 矩阵、正常/基线/异常与 wrong/correct 调用；
- `python/scan-records.md`：新 keeper/逐路径状态、旧 keeper-only 兼容与真实 worker 断言；
- `pyqt/page-structure.md`：稳定行分类、可见批量与全局回收、逐槽 other 预览；
- `pyqt/shared-previews.md`：独立双池关闭、捕获实际线程引用的生命周期回归。

当前发布候选由 root 管理为 **1.2.3**。本 Pi 未改产品/测试源码，未运行 PyInstaller，未 commit/push/tag、改任务状态或 spawn；已认证 REST 可读且凭证未输出/落盘。**本报告写入并回读后停止全部文件写入和测试，等待 root 后续发布资产只读核验通知。**

未覆盖边界：真实 OneDrive 仅联机端到端；本次受限 PATH 下跳过的三项真实视频样片测试；远端 CI/Release/安装或 exe 运行尚非本轮验证结论，不将本地 PASS 充当发布成功。
