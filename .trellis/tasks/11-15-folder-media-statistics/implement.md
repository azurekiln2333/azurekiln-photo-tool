# 执行计划：媒体统计与目录说明

## 开始条件

- [x] 用户确认统计只包含图片与视频，并要求目录已有 readme.txt 编辑写回。
- [x] PRD 以需求/验收为主，设计与执行步骤独立保存；执行/检查上下文需指向真实 spec/research。
- [x] 向用户展示最新方案摘要并获得后续明确批准（用户：“做，将任务分派给同工作区4个pi，快速完成”）。
- [x] 已执行 task.py start，工作分支 feat/folder-media-statistics。
- 不在 planning 状态修改产品代码或分派实施。

## 1. 实施派发与代码边界

用户明确要求四个 Pi 同工作区并行。当前 Trellis 0.6.17 channel adapter 仅支持 claude/codex，故直接运行四个 Pi CLI，加载 implement 角色与任务上下文。职责和固定接口见 research/parallel-contract.md。主会话协调，不代替四个 Pi 写其负责模块。

- [x] 按 Phase 2.1 加载上下文，分派 trellis-implement；提示以 Active task: .trellis/tasks/11-15-folder-media-statistics 开头。
- [x] 原生上下文注入优先，缺失时由子代理拉取 PRD/design/implement 与 implement.jsonl。
- [x] 实施代理负责 media_statistics_core.py、media_statistics_gui.py、unified_gui.py 及相关 README 集成；明确它并非仓库唯一工作者，不得撤销他人编辑。
- [x] 主会话协调、维护任务文档和规格；实施前读取 trellis-before-dev，跨 GUI/核心均遵循对应 spec。
- [x] 先实现标准库核心扫描和说明读写；再接入异步页面；最后统一导航/语言/设置兼容/关闭协调。
- [x] 任何实质范围改变先回到规划更新并请用户评审，不静默扩展格式集或说明创建功能。

## 2. 核心行为验证

不引入测试框架；用临时验证脚本与 tempfile 创建独立样例，保留验证结论到任务记录。

- [x] 构造根直属媒体、2025/2025-01、2026/2026-11/子目录、空目录、大小写后缀、readme.txt 和无关文件；核对每层图片/视频/总计。
- [x] 覆盖现有全部媒体扩展名；注入文件打开监测，确认计数阶段没有任何媒体内容读取。
- [x] 用可控目录项模拟云占位、非链接 reparse、junction/symlink、权限错误、目录消失；实际云属性不能直接通过本地设置伪造为已测试云服务。
- [x] 中断大样例扫描，断言 partial 状态及祖先汇总；避免仅测试常量或复制实现逻辑的断言。
- [x] 文本样例覆盖 UTF-8、UTF-8 BOM、UTF-16 LE/BE BOM、GB18030、空文件、CRLF/LF、README.TXT 与缺失文件。
- [x] 保存后重新读取比对内容、BOM/编码/换行；保存失败、只读、外部修改/删除、超 2 MiB、不能编码时断言原文件与草稿保留。
- [x] 原子替换失败清理仅本次临时文件，不能截断原说明。

## 3. 集成和 GUI 验证

- [x] 运行 .venv/Scripts/python.exe -m compileall -q media_statistics_core.py media_statistics_gui.py unified_gui.py。
- [x] 临时脚本在 QApplication/模块加载前设置 QT_QPA_PLATFORM=offscreen 与隔离 APPDATA，阻断模态提示造成挂起。
- [x] 构造新 MainWindow 两种模式及 UnifiedMainWindow；核验原六功能设置仍绑定正确，新页不触发六项解包异常。
- [x] 完整事件流程验证目录选择/拖入、展开折叠、扫描停止、重新扫描和不完整提示（Qt 拖拽握手通过；真实 Windows OLE 未验证）。
- [x] 验证节点切换触发对应 README、旧请求不覆盖新选择，missing 状态清空旧文本。
- [x] 验证 dirty 状态下保存/放弃/取消及外部冲突；模拟保存未完成时换目录/关闭，不能串写。
- [x] 扫描/读取/保存期间关闭独立和统一窗口，确认事件循环保持响应、线程退出安全。
- [x] 切换 zh/en 检查导航、表头、按钮、编辑状态及错误提示。
- [x] offscreen 渲染检查最小窗口与默认尺寸、长路径、英文文案、树/编辑器分区无裁切；如需真机交互使用已安装的电脑控制能力。
- [x] 语法、核心及无头通过后，仅读取用户给出的 OneDrive 目录项做统计对照，不改真实媒体或说明文件。

## 4. 打包、复核与回滚点

- [x] 检查静态导入可收集新模块，核查 AzureKilnPhotoTool_onefile.spec 与本地目录 spec；只在确有遗漏时改 spec。
- [x] 如需构建验证，用 .venv/Scripts/python.exe -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec，不加 --clean；执行 scripts/ci/verify_bundle.py 对实际产物自检，参数先查看 --help。
- [x] 按 Phase 2.2 分派 trellis-check 做最终全范围检查并修复发现；不由实施代理自称完成来替代独立检查。
- [x] 复核查读任何媒体数据、readonly 路径/云目录误判、异步串写、数据覆盖、退出线程、翻译遗漏等重点。
- [x] 回滚点：新模块未接导航时可单独验证；导航接入失败可回退该集成；说明保存失败须保留原文件。不得回滚用户在程序中主动保存的文本。
- [x] 记录已执行/未执行验证并更新 python/pyqt 规格；见 research/final-verification.md。
- [ ] Phase 3.4 提交与随后归档/日志：具体方案见 commit-plan.md，等待一次确认；未提交、未推送。

## 交付判定

AC1–AC9 全部有验证证据或明确标注真实云环境未覆盖的边界；文档与最终功能一致；用户能从统一界面打开页面进行统计及已有说明编辑。
