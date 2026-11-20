# 主会话检查点（2026-11-21，Asia/Shanghai）

## 用户决定

保持 herdr 四个 Pi 的 `newapi/deepseek-v4.1-flash` 当前模型，等待上游恢复；不切模型/供应商、不换隐藏 worker。用户已授权的修复、push、tag、CI/CD 仍然有效。

## 02:48 观察

- w55:p8 预览：已向 `media_thumbnail.py` 写入视频解码回退的第一批代码，尚未完成加载器重试/布局/回归。H.264/HEVC 独立探针成功仅说明方案可行，不等于产品修复已完成。
- w55:p4 记录：仍在读取代码和约束；尚无 `scan_record_core.py`。遇到 503 路由和短时 429。
- w55:pA 页面：503 后出现上游 `free_tier_limit_reached` 及 429；最后提示 59 分钟后重试，自动重试已结束。本地约 03:47 后再检查是否可重试，不应立即重复提交。
- w55:pB 发布：仍在读取打包/文档代码，尚无正式发布修复。
- 不改模型，不清会话，不抢占 Pi 文件所有权；没有提交、push 或 tag。

## 已补验证

`.venv/Scripts/python.exe -B .trellis/tasks/11-21-compare-preview-records/research/collision_safety_probe.py` 正常退出 0。临时创建两张真实可解码 BMP，64×64，一红一蓝，大小均 12342 字节，真实 SHA-256 不同。mock 哈希函数强制返回相同值后，目录比对输出 0 个重复组、1 个 mismatch；回收前逐字节复核返回 `skipped/content_differs`，send2trash 调用为 0。此为模拟碰撞，不能称为找到真实 SHA-256 碰撞。

版本检查 `scripts/ci/get_version.py --tag v1.2.1` 通过。主会话只同步了任务实施状态和 Python 质量规范中“无测试”的过时描述；完整回归需等 Pi 实现完成。

## 03:22 观察（替代上面的实施状态）

- 四个 herdr Pi 已恢复间歇工作，保持原模型。记录核心已完成（38项），共享预览首批已完成（26项），与原核心81项合计145项，主会话复跑全部通过。
- pA 正实施 compare 页并新增页面测试；p8 已转 folder 页（已有实际 diff）；p4 转独立预览复核，负责 media_thumbnail 与 file_context_menu；pB 发布侧已交付，转独立记录核心复核，最终打包待主会话通知。
- 真实窄侧栏验收仍失败：root_layout_probe --capture 中 path label实际108高、完整文本需要209高。析构还有 file_context_menu.py:240 已删除TableView异常。两项已交p4，不可用宽面板单测或退出0覆盖真实失败。
- 主会话新增 tests/test_unified_close.py；compare真实按钮扫描→保存挂起→关统一窗口→释放保存线程→自动关闭/DeferredDelete无槽异常已通过。folder用例等该页API落地后运行。
- design更新文件所有权；packaging/page-structure spec补充原生QtMultimedia/QtNetwork依赖、CI门禁和内嵌异步关闭契约。
- 版本仍1.2.1，远程无v1.2.1。尚未commit/push/tag；不能发布中途构建快照。

## 最终验证阶段（替代上面的未完成实施状态）

- 两页批量勾选、异步JSON记录导出/导入、扫描快照、坏导入保留结果、失效/取消保护均已完成。导入后实际回收强制逐字节复核，同大小同mtime修改和删除目标都被跳过，mock回收零调用。
- 预览长路径任意换行、A/B等宽、真实鼠标拖动、内部滚动已修；独立/内嵌、中/英四组合布局探针通过并检查截图。viewport右键事件和析构安全回归通过。
- 本地H.264/HEVC强制Shell失败的后台ThumbnailLoader实测通过。真实OneDrive仅联机占位文件仍未端到端实测，不能声称云端问题已完全验证。
- 扫描/回收/记录线程直到finished清理引用前均保持忙态，消除按钮短暂可见却忽略点击的竞态；统一窗口延后关闭的两模式回归通过。主会话全量182项通过，Pi正在最终全范围独立复核。
- 主会话最终git diff --check、7个源码文件compileall、AST重复函数/方法定义检查通过；APP_VERSION与v1.2.1一致，远程该tag仍不存在，远程分支HEAD仍为0ff0b4e。
- p4负责最终全范围trellis-check，pB负责当前源码完整PyInstaller构建及verify_bundle。未commit/push/tag，需两项真实通过后才发布。

## 已提交并触发远端发布

- p4最终全范围复核PASS；独立实跑183项全量测试通过，EOF格式修正后38项记录测试通过。最终staged diff检查通过，25个交付文件无未暂存差异。
- pB按最终源码增量重建成功（60.2s，exit0），verify_bundle exit0。最终本地EXE为81,410,674字节，2026-11-21 03:48:25+08:00；SHA256 `ef562c420eafefd8931d1089e6d60d2b1ded2b61adec0091e03b6602cadb6654`。
- 修复提交 `239874b17bd9dc5b0d94297b1ab7f29281eec475` 已推送 `github/feat/folder-media-statistics`；annotated `v1.2.1` 已推送，远程peeled tag指向同一修复提交。未覆盖任何已有tag。
- 分支Actions run `44805533013` 已进入in_progress；tag发布构建状态与资产仍待检查。最新API观察写入research/release-ci-status.json。此阶段不能声称CI或发布成功。

## 首次远端测试挂起及恢复方案

- 分支run44805533013的unit tests从19:49:00Z持续229s，本地全量约9s。主会话取消该重复分支run并下载完整job日志到本地忽略文件research/ci-branch-cancelled.log；末项是test_unified_close第一个compare关闭用例。此前核心/两页/预览/记录用例均已结束（CI无ffmpeg生成器，3项真视频样片用例按既定条件skip）。
- 原因：UnifiedMainWindow初始化旧Flyme页，main_gui.py461构造LivePhotoFixTool，缺ExifTool时463打开同步QMessageBox.critical。CI的ConfigureExifTool在unit tests之后，本地安装的ExifTool掩盖了这个非受测依赖。与扫描、指纹或回收实现无关。
- 旧tag run44805641929同样停在unit tests，主会话也取消；v1.2.1标签原样保留，不移动或覆盖。当前任务保持in_progress，尚无成功发布。
- p4仅隔离关闭用例中的无关Flyme引擎并增加不探测外部工具/不弹模态框断言，保留真实统一窗、目录页、扫描/保存QThread和原有关闭断言；pA独立复核；p8补spec与复盘；pB仅加CI step timeout5分钟及APP_VERSION=1.2.2，并重建最终包。
- 最终改发v1.2.2。新分支构建测试门禁通过后才推新标签，继续验证完整构建和Release三项资产。

## v1.2.2 测试修正和标签推送

- `55ed8fb`修复无ExifTool模态挂起并增加5分钟step超时，版本1.2.2；新分支run44807429197在10.289秒执行183项，0断言失败、1错误、3条件跳过，唯一错误为测试临时目录C盘/repo D盘跨盘relpath。两个统一关闭用例均通过，挂起已解决。
- p4将相对根用例置于临时根cwd作用域、保证正常/异常恢复cwd，保留真实扫描和导出，增加精确绝对根断言；提交`a594841fe4a24c9b1b65fd76b0726e4aa9119470`已推送。最终快照使用`from contextlib import chdir`别名；后续等效import风格变动已协调恢复，不回退逻辑。
- 主会话真实C盘唯一临时目录、D盘repo、无ExifTool/ffmpeg PATH、隔离APPDATA/LOCALAPPDATA全量复验：183项、0失败、0错误、3条件跳过，7.720s，cwd最终恢复，临时目录自动清理（root-ci-crossvolume-check.md）。pB独立定向复核PASS（pi-ci-fix-check-release.md）；pA此前完成2关闭测试后上游CPU overloaded 503，未更换模型/供应商/会话，报告由现有pB补足。
- pB最终v1.2.2本地构建exit0（63.0s）、verify_bundle exit0；81,412,521字节，2026-11-21 03:58:45+08:00，SHA256 `d52171d56c36264215bd862126851ee26c1d8fcf4e16ea756702cd078b830250`。之后只有测试/spec变动，runtime完全一致，无需重复构建。
- 新分支run44808199635的远程unit tests门禁已success，当前进入PyInstaller构建。确认门禁后才推送annotated v1.2.2，远程peeled tag为a594841，tag对象37f36b6f6df00c75690abe99150f3c57c1aaf493。v1.2.1保留原位，未覆盖。最终Release资产仍待验证。

## 最终发布核验完成

- 分支run44808199635全流程success；v1.2.2标签run44808571694全流程success（2026-11-20T20:12:10Z完成），两者均指向a594841。主会话已独立读回run状态、tag job 20个成功step与Release API。
- 正式Release id453134507，非draft/非prerelease，2026-11-20T20:11:58Z发布（北京时间11月21日04:11:58）。portable ZIP 84,203,502字节、SHA256文本90字节、setup安装包86,056,519字节，均uploaded。
- 现有herdr pB真实下载核验完成：ZIP哈希68bc5b681503c18cb3e3451340a73a4f08f029ff19edf51f7a464fa720ed3d59，与API digest一致；包内EXE哈希d6c3d950f222d16387b4cb02d114532c14a8feb3821f146dd09bada36f9b30ac，与SHA256文本一致；包内外校验文本逐字节一致。未运行任何EXE，临时下载目录已清理。证据见pi-remote-release-report.md。
- 最终代码工作区无未提交变化，仅本任务文档待Trellis自动归档/日志提交。任务JSONL验证通过；用隔离临时Git index校验本任务新增证据文件的cached diff whitespace check exit0，未改变真实index。
- 保留边界：真实OneDrive仅联机占位文件未端到端实测；本地真H.264/HEVC强制Shell失败已通过，发布安装包未实际安装/运行。当前AC全部满足，按既定顺序归档本任务、记录日志并推送收尾元数据；不归档另外两个进行中的任务。

## Trellis归档提交恢复

`task.py archive`已成功移动任务、标记completed并清除活动指针；自动提交因原任务目录从未单独入库，旧路径pathspec不存在而警告失败。主会话已读回真实Git状态：仅本任务归档目录的新增文件被暂存、没有代码或其它任务变动。无需重跑archive或改Trellis框架；在归档路径完成cached diff检查后手动完成原计划的`chore(task): archive 11-21-compare-preview-records`提交，再按原顺序记录journal并推送。
