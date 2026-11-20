# 远端失败区分、完成语义复核与 main 合并范围

核验基准：`cdf4176f6911daca9b05e12c54530d62c9b194e2`。
观察时间：2026-11-20T23:14:14Z 起（本地 2026-11-21 +08:00）。
本批只读 Git/REST、下载失败日志、执行临时独立探针；只写本文，不改源码/版本/spec/任务状态，不 commit/push/tag、fetch、触发 workflow 或构建。v1.2.3 资产下载核验按 root 指令暂停，未宣称已验证资产完整性。

## 1. 同一 SHA 的全部 branch/tag runs（认证 REST 实测）

请求：`GET /repos/azurekiln2333/azurekiln-photo-tool/actions/runs?head_sha=cdf4176f6911daca9b05e12c54530d62c9b194e2&per_page=100`，返回 2 个 run；随后分别 GET jobs（filter=all）。两者均 attempt=1、event=push、head_sha 精确一致。

| Run ID | head_branch | 结果 | 关键证据 |
| --- | --- | --- | --- |
| `44834696733` | `feat/dedupe-groups-keeper` | **failure** | job `136628017829` 的 `Run unit tests (offscreen, isolated APPDATA)` 失败；日志 201 tests / failures=1 / skipped=3，9.083s，进程 exit 1 |
| `44834696476` | `v1.2.3` | **success** | job `136628017039` 全步骤成功，含测试、构建、自检、打包、Publish GitHub Release |

- 分支 run 创建 `2026-11-20T23:09:39Z`，最终更新 `23:10:26Z`；tag run 同时创建，最终更新 `23:12:21Z`。
- 用户贴出的 fail1 来自**分支 run**，不是 tag run。tag success 不能否定同 SHA 的失败，更不能靠重新运行掩盖不稳定时序。
- 分支 check annotations 的 failure 只有 `Process completed with exit code 1.`；另有 Node.js 20 弃用 warning，不是本次断言失败原因。
- REST Bearer 来自关闭交互的 `git credential fill`，仅内存解析使用。凭证 stdout/token 未打印、未保存；未安装 gh。

## 2. 失败 job 真实日志

通过认证 `GET /actions/jobs/136628017829/logs` 下载到独立系统临时目录，成功取得 **59,947 字节**：

```text
%TEMP%\azurekiln-main-review-4e8b7843c1094100af4749cd0a5ac6b4\
  runs-summary.json
  run-44834696733-job-136628017829.log
  completion-probe-result.json
```

日志关键内容（文件内约 455–467 行）：

```text
FAIL: test_imported_record_then_changed_files_skipped_without_send2trash
File "...tests/test_folder_dedupe_features.py", line 467
  self.assertTrue(statuses[modified_target].startswith("status_skipped|"), statuses[modified_target])
AssertionError: False is not true : status_pending
Ran 201 tests in 9.083s
FAILED (failures=1, skipped=3)
```

失败不是异常吞掉、真实回收调用或 core 返回错误的直接证据；需继续区分 worker 完成与 UI drain 完成。

## 3. 独立完成语义复核（已确定复现）

### 产品/旧测试调用链

- `DedupeRecycleWorker` 通过 updates 信号把行状态入 `_process_update_queue`，并启动默认 10ms `_drain_timer`。
- `_recycle_finished(result)` 只记录 `_pending_recycle_result` 并保证 timer 运行，不同步把结果显示到表格。
- `_recycle_thread_finished()` 将 worker/thread 引用清空；它不等同于 UI 行更新与汇总计数完成。
- `_drain_queues()` 先批量应用状态，队列清空后停止 timer，再调用 `_apply_recycle_finished()` 设置 `is_recycling=False`、计数、按钮和最终提示。
- `_is_busy()` 已包含 `is_recycling`、thread refs、timer 与 update queue。旧测试却只等 `_recycle_thread is None`，随后一次 `processEvents()` 不保证 10ms timer 到期，存在提前读行状态的窗口。

### 实际临时探针（非源码修改）

执行临时脚本 `probe_recycle_completion.py`，保持真实扫描→按钮导出→按钮导入→改/删文件→回收按钮→真实 worker→真实 core，只 mock `send2trash` 与确认对话框；无关缩略图底层解码用 2×2 QImage 替身。QA 进程内将真实 `_drain_timer.setInterval(500)`，不手动调用 drain/apply、不扩大等待上限（仍为有界 5s），以稳定暴露旧等待条件的缺陷。

| 观测点 | thread ref 清空时 | 真正 `not _is_busy()` 后 |
| --- | --- | --- |
| 回收开始后耗时 | **0.005s** | **0.509s** |
| `_is_busy()` / `is_recycling` | True / True | False / False |
| timer active / queued updates | True / **2** | False / **0** |
| pending final result | True | False |
| modified target 状态 | `status_pending` | `status_skipped|content_differs` |
| deleted target 状态 | `status_pending` | `status_skipped|target_missing` |
| skipped count | 0 | **2** |
| recycled count / send2trash | 未发生真实回收 | **0 / 零调用** |

- 两个实际 core outcome 均为 skipped，原因分别是 content_differs、target_missing，`byte_verify=True`；即使 UI byte_verify 被取消，导入守卫仍生效。
- 改写目标保持原 size 和 mtime，内容差异依旧被逐字节复核识别。
- DeferredDelete 后 Qt 槽异常为 0；独立探针 **PASS，进程 exit 0**。

**判断：已独立验证 root 的时序解释，不是盲从假设。** 此证据支持修正测试等待“真实完成”语义；本路径产品 `_is_busy`/drain/core 保护正确，未发现需要为此调整产品实现的理由。实际线程结束前后顺序不是单个 `processEvents()` 能保证的。

### 给 owner 的最小修复/回归建议（本文不实施）

1. 原回收断言前等待 `_recycle_thread is None and not window._is_busy()`（或同等完整语义），不要只等 thread ref 清空。
2. 加可重复的真实 drain 延迟回归：延长真实 timer 到有界小间隔，先验证 thread 已结束时页面仍 busy 且更新未显示；然后等 idle，再验证所有原安全断言。
3. 保留 `send2trash.assert_not_called()`、modified 内容差异、deleted missing、无 recycled 行、recycled=0、skipped=2、imported 强制 byte_verify；不增 skip、不放宽预期状态、不靠延长整体超时掩盖。
4. 真实 timer 间隔只在测试作用域调整/恢复，不为让测试通过修改产品默认 drain、busy 或线程行为。

## 4. 本地 / 远端 main 与功能分支关系（实际 Git 只读）

`git ls-remote --heads github main feat/dedupe-groups-keeper feat/folder-media-statistics` exit 0；远端 ref 与本地对应 refs 一致：

| Ref | commit |
| --- | --- |
| local main / github/main / remote main | `2f8b0067635c61f1a383d25694fa22645c4d33fb` |
| local ci/github-release / github/ci/github-release | `2f8b0067635c61f1a383d25694fa22645c4d33fb` |
| local + remote feat/folder-media-statistics | `93fef4555c9e14f796f3e36ff7cb9f9f6dac0c20` |
| local + remote feat/dedupe-groups-keeper | `cdf4176f6911daca9b05e12c54530d62c9b194e2` |

- `git merge-base --is-ancestor main cdf4176` → **exit 0**。
- 反向 `git merge-base --is-ancestor cdf4176 main` → **exit 1**（尚未合入 main）。
- `git rev-list --left-right --count main...cdf4176` → **0 / 13**，main 无独有提交、功能分支领先 13。
- `git merge-base --is-ancestor 93fef45 cdf4176` → **exit 0**；前一个 feature 分支是当前分支祖先。
- 区间 `main..cdf4176` 无 merge commit，现状允许 fast-forward；未执行任何 merge/fetch/ref 写入。

### main 尚未包含的完整范围

13 个提交（旧→新）：

```text
40b603c feat: add folder media statistics and readme editing
8306d0c feat(media-statistics): compact layout and auto-save readme.txt
fc7229a feat: add folder compare and in-folder dedupe pages
40b002c docs: document folder compare, in-folder dedupe and readme auto-save
50daf90 chore(release): bump version to 1.2.0
b006e2f chore: record journal
0ff0b4e chore(task): archive 11-20-dir-compare-dedupe
239874b fix: improve compare previews and persist safe scan records
55ed8fb fix(ci): isolate close tests from ExifTool and release 1.2.2
a594841 test: handle relative-path fixtures across Windows drives
8c595a3 chore(task): archive 11-21-compare-preview-records
93fef45 chore: record journal
cdf4176 feat: group duplicate files and allow choosing the keeper
```

- `git diff --stat main...cdf4176`：**129 files，22,910 insertions，46 deletions**（含 .trellis 研究/spec/任务/归档/journal）。
- 排除 `.trellis`：**23 files，16,035 insertions，32 deletions**，涵盖媒体统计/readme、目录比对/去重、共享核心/预览/记录、测试、三语 README、打包及 CI。
- 相对 `93fef45`，当前任务仅有 `cdf4176` 这一提交；但该提交是在尚未合入 main 的旧功能基础上扩展，不可把“当前任务 1 commit”误当成“main 只缺 1 commit”。

## 5. 合并与后继发布建议（root 执行，本文不执行）

1. 本次确认的测试时序修复与回归应先由 owner 落地、全量/CI-like 验证，不能重新运行 cdf 分支失败当作修复证据。
2. 要使 main 包含当前已发布/开发功能，应**完整纳入上述 13 提交依赖链，加后续修复**。main 当前是祖先，适合 root 对最终核验过的分支做 fast-forward 整合；不要单独 cherry-pick cdf4176 到旧 main（main 尚无 folder_dedupe_gui/core 等前置文件），也不要覆盖/回滚其他分支历史。
3. 合并前重新只读核对远端 main/ref，防止本报告之后出现新提交；确有分叉再由 root 审核，不默认 force 或 reset。
4. root 明确指定后继为 **v1.2.4，从 main 发布**；版本修改/提交/推送/tag 统一由 root 操作。已存在的 v1.2.3 不移动、不删除、不重打；本报告不将旧 tag success 当成新版本验收。
5. main 的修复 commit 与版本对齐后先看远端分支 unit gate/完整构建结果，再创建后继 tag；核对 peeled tag、run head_sha、APP_VERSION 后才能声明发布成功。
6. root 之后恢复资产核验时，继续区分 API 存在性和真实下载哈希：ZIP digest 对 GitHub asset digest，zip 内 exe 对 checksum，内外 checksum 字节一致；不执行 EXE。

## 6. 当前结论

- 远端失败来源已明确：**branch 44834696733 fail，tag 44834696476 success，同 SHA cdf4176**。
- 本地独立探针确定暴露旧测试的提前完成断言；实际 core 保护与最终 drain 结果均安全，建议最小测试修复，不为测试强改产品。
- **main 尚未合并**，可 fast-forward 完整依赖链；具体执行和 v1.2.4 发布由 root 协调。
- v1.2.3 资产下载核验已暂停，未下载/运行任何 EXE，未触发远端写操作；本文不是新版本发布成功报告。
