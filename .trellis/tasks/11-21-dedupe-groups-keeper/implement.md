# 实施计划

用户已批准创建任务，并要求尽快执行和 push/tag/CI/CD。依 planning gate 完成最终审阅后 start；之后通过 herdr 工作区 w55 的现有四个 Pi 执行，模型保持原样。主会话负责协调、集成验收、提交发布，不启动替代实施代理。

## 顺序与所有权

1. [x] 最终计划已展示；用户后续明确回复“立刻实施发布”。`task.py validate` 通过，`task.py start` 成功，分支 `feat/dedupe-groups-keeper`，四个 herdr Pi 已确认 Working。
2. [x] w55:p4：核心接口、核心/记录测试完成，128 项通过；scan_record_core.py 和 schema v1 未改。
3. [x] w55:p8：类型筛选、逐路径其他禁预览、切换保留项、可见分类全选反选完成；补齐页面两个缩略图池关闭。
4. [x] w55:pA：GUI 交互与双池关闭回归完成；root 最终页面定向 25 项通过，实际记录往返与回收参数验证通过。
5. [x] w55:pB：独立全链路审查、四份相关 spec 与 CI-like 验证完成；201 项 0 失败/错误，缺少 ffmpeg 的三项样片测试明确跳过。
6. [ ] 主会话汇总并运行全量、语法和 GUI 验证，确认所有 Pi 停笔后提交；按用户授权 push、创建新版本 tag 并跟踪 CI/CD。
7. [ ] 发布资产校验、任务归档与 journal 收尾。

## 验证与门禁

- 定向：`.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -p 'test_folder_dedupe_features.py' -v`，核心和记录文件同样 discover。
- 全量：`.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -q`；CI 无外部工具、TEMP 跨盘兼容性不退化。
- 改动 Python 文件语法检查；无已配置 mypy/pyright，不以 compileall 冒充类型检查。
- 临时 APPDATA/LOCALAPPDATA、offscreen、所有回收 mock，不接触真实媒体。
- 保留 SHA-256/逐字节复核、线程 finished 后清理与关闭协议。
- 提交前 git diff --check，审查差异；不 amend、不覆盖 tag、不提交 dist/build/release。

## 本地最终验证

详见 research/root-final-check.md：标准全量 201 项全部通过（9.417s，exit 0），GUI 定向 25 项通过（2.753s），核心/记录 128 项通过；语法、差异空白检查和 v1.2.3 版本校验通过。独立/内嵌 × 中英布局、真实扫描/记录线程/回收 worker 参数有独立证据。等待本版本远端发布与资产校验，不将本地成功等同于 CI/CD 已完成。
