# v1.2.4 最终独立 CI-like 全量与时序回归审查

## 结论

**PASS，无阻塞问题；报告回读后停笔，不再启动测试或写文件。**
root 已确认产品/测试源码冻结。本 Pi 仅审阅最终 diff、运行独立 CI-like 全量并写本文；未改产品/测试/spec/任务状态，未 commit/push/tag、构建、重跑远端 workflow 或 spawn。

## 最终测试 diff 审查

基准 HEAD：`cdf4176f6911daca9b05e12c54530d62c9b194e2`。

- `tests/test_folder_dedupe_features.py` 只修正既有
  `test_imported_record_then_changed_files_skipped_without_send2trash` 的异步完成判定：保存真实 `_drain_timer.signalsBlocked()` 状态，`blockSignals(True)` 后启动真实回收按钮和 QThread。
- 等 `_recycle_thread is None` 后明确断言页面仍 `_is_busy()`，且 pending result 或 update queue 尚未排空；modified/deleted 两行都仍 pending。这确定复现旧断言所遗漏的中间态，不再依赖 runner 调度速度。
- 恢复真实 timeout 信号后，等 thread=None、not busy、pending result=None、queue 空；`finally` 再恢复原信号状态，异常时也不污染后续测试。
- 没有改变产品 timer 默认间隔、没有直接调 drain/apply、没有 sleep 伪造完成；最终等待仍为既有有界 15s，不通过无限延长 timeout 掩盖问题。
- 原断言全部保留：实际扫描→导出→导入，同大小/同 mtime 改写、删除 target、UI 关闭 byte_verify 后 imported 仍强制字节复核、`send2trash.assert_not_called()`、content_differs/target_changed、target_missing、无 recycled 行、recycled_count=0、skipped_count=2、无 Qt 槽异常。无新增 skip/expectedFailure 或期望放宽。
- 产品 `.py` diff 仅 root 的 `unified_gui.py:38` 版本 **1.2.3→1.2.4**（1 行替换）；其余产品实现无变更。既有 `test_media_thumbnail.py`、`test_unified_close.py`、`test_compare_page_features.py` 无 diff。

## 独立 CI-like 全量（本 Pi 实际执行）

使用明确临时脚本文件，避免 stdin 交互陷阱：

```powershell
.venv/Scripts/python.exe -X utf8 -B C:\Windows\Temp\dedupe-v124-ci-review-43ce58c5aa1946908652d8727a059445\run_ci_like.py
```

该独立进程设置：C: TEMP/TMP + `tempfile.tempdir`，D: repo，offscreen，隔离 APPDATA/LOCALAPPDATA；PATH 仅 .venv/Scripts 与 Windows 必需目录；EXIFTOOL_PATH/EXIFTOOL_DIR 指向不存在的临时位置。执行前真实 `shutil.which('exiftool')`、`shutil.which('ffmpeg')` 均 None，正式 `exiftool_resolver.resolve_exiftool()` 返回 None（未 mock resolver）。随后 unittest discover 全量，并核对 cwd/源码 hash/残留线程。

| 项目 | 实际结果 |
| --- | --- |
| 全量计数 | **201 tests** |
| fail / error / skip | **0 / 0 / 3** |
| 测试耗时 | **8.774s** |
| unittest 结果 | `OK (skipped=3)` |
| 进程退出码 | **0** |
| 汇总 | **`CI_LIKE_PASS=True`** |
| 实际盘符 | repo **D:**，TEMP **C:** |
| ExifTool / ffmpeg | PATH 不可用；正式 ExifTool resolver=None |
| cwd 恢复 | **True** |
| 全量后 thumbnail-loader 残留 | **0** |
| 10 个冻结产品/测试源码前后 SHA256 | **完全一致** |
| 语法 / whitespace | 所审 Python AST 全通过，`git diff --check` **exit 0** |

关键旧失败测试在本次全量真实执行为 `ok`，两个统一窗口真实记录线程关闭用例同样通过。

### 3 个 skip（全部既有，非本轮新增）

`test_media_thumbnail.LocalVideoDecodeTests`：

1. `test_h264_decodes_without_shell`
2. `test_hevc_decodes_without_shell`
3. `test_video_decoder_timeout_is_bounded`

均为“需要 ffmpeg 生成测试样片”。本轮特意验证**无 ffmpeg** 的 CI-like 条件，未将 skip 当成真实解码已验证。

### 原始证据

独立系统临时目录：
`C:\Windows\Temp\dedupe-v124-ci-review-43ce58c5aa1946908652d8727a059445\`

- `run_ci_like.py`：本次验证脚本；
- `test.log`：30,761 字节，含完整 201 项结果；
- `result.json`：2,038 字节，含实际环境、skip 明细、线程/cwd/源码哈希断言。

不提交临时配置或媒体；本报告不包含任何凭证。

## root 独立证据（与本 Pi 实跑分开）

root 本轮报告：完整环境全量 **201 tests / 9.634s / OK / exit 0，无 skip**；同一 250ms 旧失败 QA 现在 **1 test / 0.460s / PASS**；compileall、`v1.2.4` 版本检查、diffcheck 全通过。本 Pi 未以这些结果冒充自己的额外执行。

## 发布边界与停笔

本地审查/验证通过，支持 root 提交修复并 fast-forward main 后发布 **v1.2.4**。旧 **v1.2.3 不移动**。远端 main/tag CI、Release 资产、下载校验及安装/运行结果仍需之后真实只读核验；不能用本次本地 PASS 宣称远端发布成功。

**本文写入并回读后，停止全部测试和文件写入，等待 root 后续远端发布核验通知。**
