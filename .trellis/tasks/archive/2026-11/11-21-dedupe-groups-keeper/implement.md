# 实施计划

用户已批准创建任务，并要求尽快执行和 push/tag/CI/CD。依 planning gate 完成最终审阅后 start；之后通过 herdr 工作区 w55 的现有四个 Pi 执行，模型保持原样。主会话负责协调、集成验收、提交发布，不启动替代实施代理。

## 顺序与所有权

1. [x] 最终计划已展示；用户后续明确回复“立刻实施发布”。`task.py validate` 通过，`task.py start` 成功，分支 `feat/dedupe-groups-keeper`，四个 herdr Pi 已确认 Working。
2. [x] w55:p4：核心接口、核心/记录测试完成，128 项通过；scan_record_core.py 和 schema v1 未改。
3. [x] w55:p8：类型筛选、逐路径其他禁预览、切换保留项、可见分类全选反选完成；补齐页面两个缩略图池关闭。
4. [x] w55:pA：GUI 交互与双池关闭回归完成；root 最终页面定向 25 项通过，实际记录往返与回收参数验证通过。
5. [x] w55:pB：独立全链路审查、四份相关 spec 与 CI-like 验证完成；201 项 0 失败/错误，缺少 ffmpeg 的三项样片测试明确跳过。
6. [x] 主会话完成全量/语法/GUI 验证和提交推送；CI 竞争修复后 main/feature 全流程通过，新 v1.2.4 标签已从 main 推送，继续跟踪正式发布。
7. [x] 发布资产真实下载/哈希校验通过；任务归档与 journal 由 finish-work 收尾记录。

## 验证与门禁

- 定向：`.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -p 'test_folder_dedupe_features.py' -v`，核心和记录文件同样 discover。
- 全量：`.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -q`；CI 无外部工具、TEMP 跨盘兼容性不退化。
- 改动 Python 文件语法检查；无已配置 mypy/pyright，不以 compileall 冒充类型检查。
- 临时 APPDATA/LOCALAPPDATA、offscreen、所有回收 mock，不接触真实媒体。
- 保留 SHA-256/逐字节复核、线程 finished 后清理与关闭协议。
- 提交前 git diff --check，审查差异；不 amend、不覆盖 tag、不提交 dist/build/release。

## 本地最终验证

详见 research/root-final-check.md：标准全量 201 项全部通过（9.417s，exit 0），GUI 定向 25 项通过（2.753s），核心/记录 128 项通过；语法、差异空白检查和 v1.2.3 版本校验通过。独立/内嵌 × 中英布局、真实扫描/记录线程/回收 worker 参数有独立证据。等待本版本远端发布与资产校验，不将本地成功等同于 CI/CD 已完成。

## 追加：CI 时序回归与 main 集成

用户在首次 push 后提供 CI 失败日志，并明确要求检查各子分支后合并 main。无需再次确认授权。

- 首次工作提交 cdf4176：v1.2.3 tag run 44834696476 成功；同 SHA 分支 run 44834696733 在导入后变更文件的 GUI 回归中失败。不能将标签成功视为整体无缺陷。
- root 确定性复现：仅延长真实 drain timer 至 250ms，旧测试等 `_recycle_thread is None` 后立即读行，稳定读到 `status_pending`。产品 `_is_busy` 已包含 is_recycling/timer/queue；线程 finished 不等于 UI 更新排空。
- [x] pA 以真实 timer 信号门禁修正完整 idle 等待和中间态断言，定向8轮+页面25项通过；p8/p4 核对产品安全，pB 复核日志/分支范围。所有内容变更/删除/send2trash 禁止/计数断言保留。
- [x] root 修复后完整环境201项通过（9.634s，无skip，exit0），旧250ms失败探针现在通过；pB修复后CI-like201项通过（8.774s，缺ffmpeg的3项skip，exit0），源码哈希不变、无残留缩略图线程。
- [x] 定向/完整环境/CI-like 复验后提交 b0d4335，完整快进合入并推送 main；ci/github-release、feat/folder-media-statistics、feat/dedupe-groups-keeper 均为 main 祖先，未删分支。main run44836184819 / feature run44836184833 全流程success。
- [x] main/修复分支均推送且全流程success；v1.2.4标签/Release成功，三资产真实下载/解包哈希核验通过，v1.2.3未移动。执行finish-work归档本任务。
