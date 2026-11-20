# pi-ci-test-fix — CI unit test 卡死根因与最小修复

结论：**根因已复现并修复（仅改测试）**。CI 挂在
`test_unified_close.UnifiedRecordCloseTests.test_compare_record_save_finishes_before_embedded_page_destruction`
不是被测关闭逻辑问题，而是**该测试构造统一窗时意外触发 Flyme 引擎的 ExifTool 缺失模态对话框**。

范围：只改 `tests/test_unified_close.py` + 本报告。未改 runtime、未改 CI workflow、未删/未 skip 任何测试、未放宽断言、未 commit / 未 push。

---

## 1. 日志证据（research/ci-branch-cancelled.log）

```
19:49:10.4271300Z test_internal_rejects_foreign_root_in_snapshot (test_scan_record_core.InternalRecordTest...) ... ok
19:49:10.4619794Z test_internal_roundtrip (test_scan_record_core.InternalRecordTest.test_internal_roundtrip) ... ok
19:52:59.3697691Z test_compare_record_save_finishes_before_embedded_page_destruction (...) ...
19:52:59.3916538Z ##[error]The operation was canceled.
```

- 相邻两条 `test_scan_record_core` 正常 ok（19:49:10），下一条即卡住；直到主会话主动取消（19:52:59，间隔约 **229s**）都没有任何输出。旧 workflow 该 step **没有** `timeout-minutes`，因此不是被 timeout 终止，而是人工取消；5 分钟限制是本次修复中新增的硬门禁（见 `.github/workflows/build.yml:44-55` 注释）。
- 卡点恰为 `test_unified_close` 的第一个用例（字母序 `compare` < `internal`），说明阻塞发生在**用例开始后、`self._wait_for` 之前/构造阶段**，而非记录线程等待。
- 该测试是本 suite 中唯一构造真实 `UnifiedMainWindow()` 的用例（`git grep UnifiedMainWindow tests/` 仅此文件）。

## 2. 根因链（代码级，非猜测）

1. `UnifiedMainWindow.__init__`（`unified_gui.py:568-576`）无条件构造全部内嵌页：
   ```python
   self._feature_windows = [
       MergeLivePhotoWindow(self, embedded=True),
       SplitHuaweiWindow(self, embedded=True),
       FlymeFixWindow(self, embedded=True),   # ← main_gui.MainWindow
       ...
   ]
   ```
2. `main_gui.MainWindow.__init__`（`main_gui.py:461-464`）：
   ```python
   try:
       self.engine = LivePhotoFixTool()
   except FileNotFoundError as e:
       QMessageBox.critical(self, self.tr("missing_dependency_title"), str(e))
       raise
   ```
3. `LivePhotoFixTool.__init__`（`flyme_livephoto_fix_core.py:71-77`）→ `resolve_exiftool()` → `_check_exiftool()` 执行 `exiftool -ver`；找不到 exiftool 时抛 `FileNotFoundError`。
4. CI 步骤顺序（`.github/workflows/build.yml`）：`Run unit tests (offscreen, isolated APPDATA)` 在 `:44-55`，`Configure ExifTool` 在 `:101-109`——**跑测试时 `EXIFTOOL_DIR` 尚未设置、exiftool 也不在 PATH**。
5. 于是 `QMessageBox.critical(...)` 在 offscreen 平台弹出**同步模态框**，`exec()` 等用户点确定；CI 无交互 → 永久阻塞（测试进程无输出，也不会自行结束）→ 主会话手动取消该 run。
6. 本地/此前 183 测试约 9s 通过，是因为本机 `D:/ProgramFiles/exiftool` 可被 `exiftool_resolver` 解析到，`_check_exiftool()` 正常返回，从不进入该分支。

该路径与 v1.2.1 tag run `44805641929` 相同（同一 commit `239874b`，同样先跑测试）。

## 3. 隔离证据（确认“无外部 ExifTool → 精确走到该分支”）

用 offscreen + 隔离 `APPDATA`，把 `flyme_livephoto_fix_core.resolve_exiftool` 打成 `None`、`main_gui.QMessageBox.critical` 打成记录器，构造真实 `UnifiedMainWindow()`：

```
FileNotFoundError: 未找到 exiftool！请确保 exiftool/exiftool.exe 在当前目录、EXIFTOOL_DIR、EXIFTOOL_PATH 或系统 PATH 中。
critical_calls: 1
critical_title: 依赖缺失
diag exit=0
```

即：无 ExifTool 时**必然**调用一次 `QMessageBox.critical`（CI 里就是这次调用卡住），异常随后从 `FlymeFixWindow` 构造抛出，`UnifiedMainWindow` 无法建成。

## 4. 最小修法（只在测试侧）

`tests/test_unified_close.py` 新增 `_make_unified_window_without_exiftool()`，`_check_close_during_save()` 里把 `UnifiedMainWindow()` 换为该 helper：

```python
with patch.object(main_gui, "LivePhotoFixTool",
                  return_value=MagicMock(name="LivePhotoFixTool")) as tool_constructor, \
     patch("flyme_livephoto_fix_core.resolve_exiftool") as resolve_exiftool, \
     patch.object(main_gui.QMessageBox, "critical") as critical:
    window = UnifiedMainWindow()
    tool_constructor.assert_called_once()
    resolve_exiftool.assert_not_called()      # 绝不探测/启动外部 ExifTool
    critical.assert_not_called()              # 绝不弹模态框
self.assertIsInstance(window._feature_windows[2].engine, MagicMock)
```

要点与保留项：

- 只隔离 **Flyme 引擎构造**（与本关闭测试完全无关的依赖）；`resolve_exiftool` 同时被禁用并断言未调用，等于在本地复刻“CI 无 ExifTool”环境且不开真实对话框。
- 仍然构造**真实 `UnifiedMainWindow`**、真实内嵌 `dir_compare_gui` / `folder_dedupe_gui` 页、真实扫描 `QThread`、真实记录保存 `QThread`（`delayed_save` 阻塞在 `release.wait`）。
- 原有关闭断言全部保留且未放宽：`window.close()` 返回 False、窗口仍可见、`_optional_close_timer.isActive()`、释放后 `_record_thread is None` 且窗口隐藏、定时器停止、`load_record(...).mode` 一致、`errors == []`。
- 没有删除用例、没有 `skip`、没有 try/except 包住断言。
- 不改 runtime：`unified_gui.py` 无条件构造各页、`main_gui.py` 弹框行为都保持原样（属于产品行为，不是本任务范围）。

## 5. 验证结果（真实退出码）

| 命令 | 结果 |
| --- | --- |
| `QT_QPA_PLATFORM=offscreen` + 隔离 `APPDATA`/`LOCALAPPDATA` + `python -m unittest tests.test_unified_close -v` | `Ran 2 tests` **OK**，**exit=0**，1.29s（此前 CI 形态下会挂起） |
| 同上 + `python -B -m unittest discover -s tests`（与 CI 的 `:54` 同形态，含 `-v` 复跑） | `Ran 183 tests` **OK**，**exit=0**，8.7s / 9.1s |
| `python -m compileall -q tests/test_unified_close.py` | **exit=0** |
| `git diff --check -- tests/test_unified_close.py` | **exit=0** |

## 6. 边界 / 未覆盖

- 未在真实 GitHub Windows runner 上复跑验证（需主会话重新触发 workflow）；本地以“ExifTool resolver 禁用 + critical 记录器 + 断言未调用”复刻了同一分支。
- 未实测 v1.2.1 tag 已发布的产物；`Configure ExifTool` 之后的打包步骤未受本次改动影响。
- 其他测试同样会构造 `UnifiedMainWindow` 吗？已确认没有（仅此文件引用），因此无需再改其他用例。
- 若将来 `main_gui.MainWindow` 被改为无 ExifTool 时降级而不是抛错，本 helper 的隔离仍然有效（只是不再必要），断言 `tool_constructor.assert_called_once()` 仍能防止“测试悄悄不构造引擎”的退化。

## 7. 建议（不改，留给主会话决策）

CI 侧可考虑把 ExifTool 配置提前到测试之前，或给 unit test 步骤单独设置 `EXIFTOOL_DIR` 到已下载目录——但本次测试已不依赖外部 ExifTool，属可选加固，不在本工作包内实施。

---

## 8. 追加：v1.2.2 branch run 44807429197 相对路径用例修复

本次是新的单点 CI ERROR，与上面的 ExifTool 阻塞无关。

### 8.1 日志证据（`research/ci-1.2.2-branch.log`）

```
test_relative_root_is_absolutized_in_snapshot (test_compare_page_features.RecordRoundTripTests...) ... ERROR
...
File "D:\a\azurekiln-photo-tool\azurekiln-photo-tool\tests\test_compare_page_features.py", line 299, in test_relative_root_is_absolutized_in_snapshot
    self.window.root_a_edit.setText(os.path.relpath(self.root_a, Path.cwd()))
ValueError: path is on mount 'C:', start on mount 'D:'

Ran 183 tests in 10.289s
FAILED (errors=1, skipped=3)
```

- run `44807429197` 其余全部通过（含 2 项 close 用例），唯一 ERROR 是该用例。
- CI 的临时目录 `tempfile.TemporaryDirectory` 位于 `C:`，而 repo 工作目录是 `D:\a\...`；`ntpath.relpath(C:\..., D:\...)` 跨盘时直接 `ValueError`。
- 该用例原本假定临时目录与 cwd 同盘，本地（临时目录也在 D:）从未暴露；不是 runtime 的路径规范化逻辑失败，而是测试夹具对盘符的隐含依赖。

### 8.2 最小修法（仅 `tests/test_compare_page_features.py`）

只改 `test_relative_root_is_absolutized_in_snapshot`：

```python
import contextlib
...
with contextlib.chdir(self.tmp):
    self.window.root_a_edit.setText(os.path.relpath(self.root_a, Path.cwd()))
    self.window.root_b_edit.setText(os.path.relpath(self.root_b, Path.cwd()))
    self.window.btn_scan.click()
    self.assertTrue(_pump(15.0, lambda: self.window._has_scan), "扫描未完成")
    self.assertTrue(_pump(15.0, lambda: not self.window._is_busy()))
    target = self.tmp / "relative.json"
    record = self.export_to(target)
self.assertTrue(os.path.isabs(str(record.root_a)))
self.assertTrue(os.path.isabs(str(record.root_b)))
self.assertEqual(record.root_a, Path(os.path.abspath(self.root_a)))
self.assertEqual(record.root_b, Path(os.path.abspath(self.root_b)))
```

- `contextlib.chdir(self.tmp)` 在作用域内把 cwd 切到临时目录，`relpath` 得到合法的 `A` / `B`；**异常路径也会恢复 cwd**（已验证）。
- 仍走真实扫描按钮、真实记录导出，原断言保留并加强为精确等于扫描前的绝对 roots。
- 没有强行跨盘 `relpath`、没有 `skip`、没有放宽断言、未改 runtime。

### 8.3 验证（真实退出码）

| 命令 | 结果 |
| --- | --- |
| `QT_QPA_PLATFORM=offscreen` + 隔离 `APPDATA`/`LOCALAPPDATA` + `python -B -m unittest tests.test_compare_page_features -v` | `Ran 17 tests` **OK**，**exit=0**，1.76s；`test_relative_root_is_absolutized_in_snapshot ... ok` |
| `python -m compileall -q tests/test_compare_page_features.py` | **exit=0** |
| `git diff --check -- tests/test_compare_page_features.py` | **exit=0** |
| `contextlib.chdir` 异常恢复探针 | 进入后 cwd==tmp、退出后恢复、异常后仍恢复，**exit=0** |

补充证据：主会话另在 `PATH` 仅含 Windows 系统目录、移除 `EXIFTOOL_DIR`/`EXIFTOOL_PATH`、`flyme resolve` 强制 `None` 的 CI-like 环境中复验：183 tests / 0 fail / 0 error / 3 skip / 7.578s / **exit=0**（见 `research/root-ci-environment-check.md`）。

### 8.4 边界

- 未在真实 GitHub runner 上重跑；需主会话以真实 C: 临时目录 / D: repo 的 CI 复验确认。
- 未改 `.github/workflows/build.yml`、`unified_gui.py` 或任何 runtime；v1.2.2 版本号不变。
