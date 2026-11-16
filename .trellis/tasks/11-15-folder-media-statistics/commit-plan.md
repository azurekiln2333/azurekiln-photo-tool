# 待确认的提交方案

工作分支：`feat/folder-media-statistics`。功能实现、验证及本地 EXE 构建不依赖提交确认；
本方案只涉及 Git 提交及随后 Trellis 的任务归档/日志记录，不推送远端。

## 1. 功能提交

`feat: add folder media statistics and readme editing`

本会话及四个 Pi 的修改，作为一个完整功能提交：

- `media_statistics_core.py`
- `media_readme_core.py`
- `media_statistics_gui.py`
- `unified_gui.py`
- `README.md`
- `docs/README.en.md`
- `docs/README.zh-TW.md`
- `.trellis/spec/python/media-statistics.md`
- `.trellis/spec/python/index.md`
- `.trellis/spec/python/project-structure.md`
- `.trellis/spec/pyqt/index.md`
- `.trellis/spec/pyqt/page-structure.md`
- `.trellis/spec/pyqt/threading-and-workers.md`
- `.trellis/tasks/11-15-folder-media-statistics/`：需求、设计、执行清单、上下文清单、
  四个 Pi 的报告、复核报告、只读相册统计证据、本提交方案及验收记录。

不包含 `dist/`、`build/`、运行期临时脚本或用户真实配置；无未识别的其他脏文件。

## 2. 任务收尾

功能提交成功后，按 `trellis-finish-work` 调用 task archive 与 add_session，生成
任务归档与开发日志的独立 `chore` 提交。只处理本任务，不处理并行的 github-ci-release 任务。

## 确认依据

`.trellis/workflow.md` Phase 3.4 第 5 步：
“Present the plan once, ask for one-shot confirmation”。
用户确认后执行上述提交与收尾；当前保持改动未提交、不归档。
