# 主会话最终集成验收

日期：2026-11-21。目标版本：v1.2.3。用户已授权实施、提交、push、tag 与 CI/CD，无需再次审批。

## 完成项

- 照片/视频/其他按完整重复组分类，默认首个非空分类；筛选仅隐藏源行。
- 其他文件逐路径禁止列表及详情 loader 请求；媒体槽仍按实际路径独立工作。
- A/B/C 可从默认保留 A 改为保留 B；B 受保护，A 成为已勾选 pending 目标，其余副本合法状态保留。同步内存组、每行 keeper 和 schema v1 导出/导入。
- 实际全选/全不选/反选按钮仅作用当前可见合法目标；回收确认仍包含所有分类已勾选目标。
- 保留原 SHA-256、逐字节与回收前复核。旧 v1 单 keeper 记录正常导入，目录比对 A/B 角色不变。
- 页面关闭补齐 PreviewPanel 独立 loader.shutdown；持久回归捕获两个池的真实线程并确认退出。

## 实测结果

- 标准全量：`.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -q`，201 tests，9.417s，OK，进程 exit 0。
- GUI 定向：同命令增加 `-p test_folder_dedupe_features.py`，25 tests，2.753s，OK，exit 0。
- p4 核心与记录回归：128 tests，PASS，见 pi-core-result.md。
- pB 独立 CI-like：C: TEMP / D: repo，隔离 APPDATA/LOCALAPPDATA、无 ExifTool/ffmpeg；201 tests，9.233s，0 failures / 0 errors / 3 skips，exit 0。跳过仅为需 ffmpeg 生成样片的 H.264、HEVC、解码超时三项；本机完整标准全量已执行这些用例。cwd 恢复、源码哈希未变化、残留 thumbnail 线程为空。
- 变更 Python 文件 compileall、`git diff --check`、`get_version.py --tag v1.2.3` 均 exit 0；未配置静态类型工具，不将编译当作类型检查。
- 独立/内嵌 × 中英，1360×880，注册真实中文字体后可见控件/等宽预览/长路径换行正常，Qt 槽异常 0，见 root-layout-check.md。
- 真实扫描 → 改 keeper → 导出 → 导入 → 回收 worker，B 受保护、仅 A 被传入回收，导入后强制 byte_verify=True，见 root-flow-check.md。实际 send2trash 已 mock，未操作真实媒体/回收站。

## 边界与发布

真实 OneDrive 仅联机文件尚无端到端环境；本轮不声称其真实云端流程已覆盖。远端 Actions/Release 以随后发布报告为准。产品实现均由指定 herdr w55 四个 Pi 分工完成，主会话负责集成验收和发布。

## 首次远端失败后的修正验收（v1.2.4）

初次 cdf4176 标签流水线成功、分支流水线失败，旧测试在 QThread 清理后、10ms UI drain 前过早读取 pending 行；首次本地 PASS 不能排除此竞争。用户随后要求检查所有子分支并合入 main。

- 确定性复现：不改源码，仅将真实 drain 设 250ms，原用例于原467行稳定失败（status_pending，exit 1）。pB 独立500ms探针证明 queue仍2条、页面busy；真实idle后两行正确跳过且send2trash为0，产品逻辑不需修改。
- pA 加强同一用例：临时阻断真实 timer 的 timeout 信号，明确观察线程清理但UI仍busy、状态仍pending；恢复原信号后等待真实idle/queue与pending result全部清空。原内容不同、目标缺失、send2trash禁止、计数和Qt异常断言全部保留；finally恢复信号，无固定sleep或放宽超时。
- pA 定向8个独立进程全部通过，见pi-ci-failure.md。root用同一250ms复现脚本复验修复后通过，1 test / 0.460s / exit 0。
- root最终完整环境：201 tests / 9.634s / OK / exit 0，无skip。变更文件compileall、v1.2.4版本验证、diffcheck均通过。
- pB修复后CI-like：201 tests / 8.774s / 0 failures / 0 errors / 3既有ffmpeg样片skip / exit0；源码哈希不变、cwd恢复、无残留缩略图线程，详见pi-ci-final-review.md。
- main与子分支祖先关系已由pB独立审查：main/ci同2f8b006，folder-statistics=93fef45为当前分支祖先。最终按完整依赖链fast-forward，保留所有提交与旧标签；不单独摘取最新功能提交。
- 后继发布改为从main发v1.2.4，已有v1.2.3不移动；实际新提交/远端结果待发布报告补齐。
