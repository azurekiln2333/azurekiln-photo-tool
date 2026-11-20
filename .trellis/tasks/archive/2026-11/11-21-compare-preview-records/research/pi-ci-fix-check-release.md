# CI 修复独立复核（239874b..55ed8fb）

范围：仅只读审阅 `239874b..55ed8fb` 的 4 个文件 diff，不跑测试、不改源码。
对照：CI 根因（无 ExifTool 时 `main_gui.py:463` 模态 `QMessageBox.critical` 卡住）、
`check.jsonl`、`python/quality-guidelines.md`。

## 变更清单（与 4 文件声明一致）

```
.github/workflows/build.yml                | +2
.trellis/spec/python/quality-guidelines.md | +17
tests/test_unified_close.py                | +22 -3
unified_gui.py                             | +1 -1
```

## 逐项核对

### 1. tests/test_unified_close.py（+22/-3）

- 新增 `_make_unified_window_without_exiftool()`：只 `patch.object(main_gui, "LivePhotoFixTool", return_value=MagicMock(...))`，
  即**只替换与本关闭测试无关的 Flyme 页引擎构造**；仍构造真实 `UnifiedMainWindow`，
  真实 `dir_compare_gui` / `folder_dedupe_gui` 页面、真实扫描/记录 `QThread` 与按钮点击保持不变。
- 原关闭断言全部保留（diff 仅在构造行替换）：`self.assertFalse(window.close())`、
  `window.isVisible()`、`_optional_close_timer.isActive()`、等待 `page._record_thread is None and not window.isVisible()`、
  结束后 `load_record(destination, expected_mode=mode)`。未删除/放宽任何断言。
- 隔离期间三条守卫断言有效：
  - `tool_constructor.assert_called_once()`：确认 Flyme 页构造确实被替身接管（没有悄悄走真实构造）；
  - `resolve_exiftool.assert_not_called()`：`flyme_livephoto_fix_core.py:75` 的 `LivePhotoFixTool.__init__`
    调用模块级 `resolve_exiftool()`，patch 目标正确；真实构造一旦发生会探测外部工具，此断言能抓住；
  - `critical.assert_not_called()`：构造期间不得弹 `QMessageBox.critical`。
  patch 范围仅限 `with` 块内（构造期），退出后统一窗/页面仍按真实代码运行；`window._feature_windows[2]`
  即 `unified_gui.py:579` 的 Flyme 页，索引正确。
- `tests/test_unified_close.py` 无 `skip` / `skipTest` / `expectedFailure`；未新增跳过。

### 2. unified_gui.py（+1/-1）

- 仅 `APP_VERSION = "1.2.1"` → `"1.2.2"`，`git diff -U0` 确认无其他 runtime 行。

### 3. .github/workflows/build.yml（+2）

- 仅在 `Run unit tests (offscreen, isolated APPDATA)` step 增加注释与 `timeout-minutes: 5`；
  没有 `continue-on-error`、没有改 `if`、没有移动/跳过测试门禁，命令仍是
  `python -B -m unittest discover -s tests -v`。

### 4. .trellis/spec/python/quality-guidelines.md（+17）

- 新增「GUI 关闭/集成测试的外部依赖隔离」与「CI 测试超时」两节，并把“本机已装 ExifTool/ffmpeg
  不能证明可移植”加入禁止事项；与实际修复方向一致，未放宽质量要求。

## 追加复核：分支 run 44807429197（2026-11-21）

主会话提供的完整日志 `research/ci-1.2.2-branch.log` 实测：

- `Ran 183 tests in 10.289s`，`FAILED (errors=1, skipped=3)`；关闭测试
  `test_compare_record_save_finishes_before_embedded_page_destruction` 与
  `test_internal_record_save_finishes_before_embedded_page_destruction` 均为 `ok`。
- 唯一 ERROR：`tests/test_compare_page_features.py:299` 的
  `test_relative_root_is_absolutized_in_snapshot`：
  `ValueError: path is on mount 'C:', start on mount 'D:'`。
  原因是 CI 的 `TEMP` 在 C:、repo 在 D:，对跨盘路径调用 `os.path.relpath` 直接抛错；
  不是扫描/记录逻辑失败。

### 追加小 diff（工作区，未提交）

```
tests/test_compare_page_features.py | +9 -5
.trellis/spec/python/quality-guidelines.md | +7
```

`tests/test_compare_page_features.py`：

- 仅把该相对根用例的构造/扫描/导出包进 `with chdir(self.tmp):`（`from contextlib import chdir`），
  使 `os.path.relpath(self.root_a, Path.cwd())` 只产生同盘相对路径 `A`/`B`；
  扫描与导出都在该 cwd 作用域内完成，`contextlib.chdir` 在异常时也会恢复原 cwd。
- 额外增加两条断言：`record.root_a/root_b == abspath(self.root_a/root_b)`，比原先只查
  `isabs` 更严格；未删除任何原断言，未新增 skip。
- 本用例仍走真实按钮扫描、真实相对路径、真实记录导出；无 runtime 改动。

`quality-guidelines.md`：新增“临时目录可能与仓库不同盘”约定（有恢复保证的 cwd 上下文、
禁止用 skip 绕过跨盘、至少一次跨盘 TEMP 复验）；属测试规范，不改产品质量标准。

### 复核结论

- `git diff --check` exit 0；测试文件 `ast.parse` 通过；`git diff --name-only HEAD -- '*.py' ':!tests/*'` 为空，
  即 **runtime 与已构建 v1.2.2 完全一致，无需重跑构建**。
- 该修复针对已复现的唯一 CI ERROR，方案与根因匹配，且不掩盖真实问题。
- 非阻塞备注：`contextlib.chdir` 需 Python 3.11+（项目源码运行文档写 3.10+，但测试/发布环境固定 3.14；
  不影响 CI 与发布）。最终是否通过以主会话跨盘 TEMP 全量运行结果为准；本报告只做只读复核。

## 结论

**PASS（无阻塞问题）。** 修复把 CI 卡死来源限定在“非受测 Flyme 页的外部 ExifTool 依赖”，
真实统一窗、两页记录线程与原关闭断言均保留；workflow 仅加有界超时；runtime 仅版本号。
追加的分支 run 唯一 ERROR 是测试自身跨盘 `relpath` 用法，p4 的 `chdir` 修复匹配根因、
强化断言且未改 runtime；待新 CI 结果确认后即可。

## 非阻塞备注

- spec 新增文案有一条“至少验证一次「外部工具缺失」环境，把工具解析器指向空目录或 patch 为 None”。
  本次改动选择**替身整个 Flyme 引擎构造**并断言 `resolve_exiftool` 未被调用；它解决了同类风险，
  但不是该句描述的字面场景（缺失工具后 UI 行为）。属文档表述与实现方式的差异，不影响本次 CI 修复。
- 本次未复跑测试（按指示只读复核）；可信运行证据来自主会话
  `research/root-ci-environment-check.md`（183 tests / 0 fail / 0 error / 3 skip）与 p4 正常全量 183 通过。
- 仓库现有 3 个 skip 均来自 `tests/test_media_thumbnail.py` 的 `skipUnless(shutil.which("ffmpeg"))`，
  与本次改动无关，CI runner 无 ffmpeg 时属预期。
