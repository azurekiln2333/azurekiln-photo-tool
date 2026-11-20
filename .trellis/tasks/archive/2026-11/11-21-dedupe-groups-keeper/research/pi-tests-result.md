# pA GUI 回归结果（当前接手前）

状态：pA 已停止所有写入和测试进程；测试文件最终机械集成及全量验证已交 root。此报告只记录 pA 实际运行过的命令与结果，不代表当前最终版本全套通过。

## 实际命令与结果

1. 定向文件测试（当前最终编辑前的中间版本）：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:APPDATA=(Join-Path $env:TEMP 'dedupe-groups-test-appdata')
$env:LOCALAPPDATA=(Join-Path $env:TEMP 'dedupe-groups-test-local')
.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -p 'test_folder_dedupe_features.py' -v
```

结果：24 项中 22 通过、2 失败。失败为：
- `DedupeGroupsKeeperTests.test_embedded_mode_and_english_refresh_all_new_controls`：当时使用裸内嵌窗口并检查 `isVisible()`，未通过真实 `EmbeddedPage` host 验证。
- `DedupeGroupsKeeperTests.test_set_keeper_button_changes_core_group_and_real_worker_uses_new_keeper`：前一记录用例留下 `byte_verify=False` 设置，导致该用例 worker 参数断言失败。

2. root 指定的三个定向用例（后续编辑版本）：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:APPDATA=(Join-Path $env:TEMP 'dedupe-groups-test-appdata')
$env:LOCALAPPDATA=(Join-Path $env:TEMP 'dedupe-groups-test-local')
.venv/Scripts/python.exe -X utf8 -B -m unittest `
  tests.test_folder_dedupe_features.DedupeGroupsKeeperTests.test_set_keeper_button_changes_core_group_and_real_worker_uses_new_keeper `
  tests.test_folder_dedupe_features.DedupeGroupsKeeperTests.test_embedded_mode_and_english_refresh_all_new_controls `
  tests.test_folder_dedupe_features.DedupeGroupsKeeperTests.test_video_preview_loader_threads_stop_on_shutdown -v
```

结果：3 项通过（`Ran 3 tests ... OK`）。覆盖：真实按钮切换 keeper + 回收 worker 参数、真实 `EmbeddedPage` 承载与中英文案、伪视频触发真实 loader 后关闭线程。伪媒体解码在 GUI 新测试类中替换为快速 fixture decoder，loader/request/preview 控件仍真实。

## root 后续集成验证（pA 停止写入后）

root 在读取本报告并确认两个 fixture/`EmbeddedPage` 修正已落盘后，运行了最终页面定向测试：

```powershell
.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -p 'test_folder_dedupe_features.py' -v
# 25 项全绿，2.753s，exit 0（由 root 报告）
```

这是 root 在 pA 停止写入后的集成结果；pA 未自行重跑或改变源码/测试。当前全量测试由 root 运行，CI-like 由 pB 运行，等待各自报告。

## 尚待 root 验证

- 最终全量 unittest discover，并确认视频缩略图生命周期既有测试不再观察到残留 `thumbnail-loader-*`。
- 当前工作树中 root/其他 Pi 仍有并行变更；pA 未再执行测试或覆盖他人修改。

结论：root 报告的最终页面定向 25 项通过；全量与 CI-like 仍待 root / pB 的验证结果。
