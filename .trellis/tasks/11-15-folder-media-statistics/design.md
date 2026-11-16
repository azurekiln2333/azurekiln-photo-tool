# 技术设计：媒体统计与目录说明

## 架构与职责

这是一个有统计与编辑两个区块的单页功能，共享目录选择和线程退出生命周期，作为一个任务交付，不拆成独立子任务。

- 新增 media_statistics_core.py 与 media_readme_core.py：仅依赖标准库；分别负责目录扫描/汇总和说明文件读取/安全保存，输出明确的数据结构和错误状态。按用户要求由两个 Pi 分别拥有文件，以便同工作区并行且避免写冲突。
- 新增 media_statistics_gui.py：MainWindow(embedded=False)、Fluent 控件、Qt workers、树模型、说明编辑状态机和中英字典；支持直接运行。
- unified_gui.py：新增媒体统计页、导航文案、语言同步和新页退出协调；修正 SettingsPage 对功能页列表的六项精确解包，保留既有六页设置绑定。
- GUI 从 timestamp_fix_gui 导入 IMAGE_SUFFIXES/VIDEO_SUFFIXES 并作为参数传给核心扫描器；核心层不导入 GUI，也不复制后缀常量。
- 更新 README.md 及 docs/README.en.md、docs/README.zh-TW.md 的新页入口与功能说明；检查两份 PyInstaller spec 的静态导入收集，不为静态模块强加 hiddenimports。

## 交互布局

沿用项目标题/目录/内容/操作/状态卡片结构，内容区用垂直 QSplitter：
1. 上半区为 Fluent TreeView 与 QStandardItemModel，只展示目录行，列为文件夹、图片、视频、总项数。
2. 下半区为当前 readme.txt 路径、Fluent PlainTextEdit、保存与重新加载按钮、状态提示和必要时出现的草稿决策条。
3. 根目录默认展开，年份初始折叠；树保留完整实际名称，YYYY/YYYY-MM 自然形成年月层级，普通目录正常显示。
4. 根总数可显示在简洁汇总行；数值列右对齐，保存/错误状态不占用计数列。
5. 无说明、加载中、读取失败时编辑框只读并显示明确状态；空文件是可编辑的已加载文档，不等同于不存在。

## 核心数据契约

采用 dataclass（具体名称可微调，语义不可改变）：
- FolderSnapshot：path、parent_path、name、直属图片/视频数、子树图片/视频数、complete、issue_count；total 由图片+视频计算，不另存可漂移字段。
- ScanOutcome：root、cancelled、errors、扫描目录/媒体数量；错误至少含路径和原因。
- ReadmeDocument：实际路径、解码文本、encoding、bom、newline、baseline_bytes 或其摘要、原始文件大小/修改时间；上限 2 MiB。
- ReadmeResult：状态 ready/missing/too_large/error/conflict/saved 与可选文档/错误；读取失败不能伪装为 missing。
- Worker 信号携带 scan_id 或 request_id；GUI 只接受当前代号的结果，防止旧扫描/旧目录读写覆盖当前状态。

## 目录扫描

- 使用带 with 的 os.scandir 和显式栈，避免递归调用深度限制；每次处理目录或目录项时检查 threading.Event 停止标志。
- 只读取条目名称和类型信息；扩展名用 casefold，非媒体文件略过。禁止内容 open/read、Pillow/ExifTool、哈希或缩略图。
- 先判定实际符号链接/目录联接（is_symlink、is_junction）并跳过；不要因 REPARSE_POINT、OFFLINE、UNPINNED、RECALL 标记跳过云项。
- is_dir/is_file 使用 follow_symlinks=False；仅需要补充类型信息时读取必要属性，不全量 Path.resolve/stat。
- 对每个目录保留直属计数，结束时自下向上汇总。每次传递绝对快照，不对重复通知再次加和；不存全部媒体文件路径。
- 无法枚举/中途取消时把不完整状态传到祖先；显示已发现数及“不完整”说明，空目录仅在成功枚举后才视为完整零结果。
- 单个 worker 输出成批目录快照；主线程入队，10 ms 定时器每轮最多处理 120 行。完成消息须等待队列清空再应用。
- 扫描可与说明编辑相互独立；重新扫描或更换根目录必须先处理未保存文档，并停止旧扫描、使旧代号失效。

## OneDrive 兼容边界

- 支持资源管理器已展示在本机目录树中的文件；不访问账号 API。
- 目录枚举可能让云客户端获取目录元数据，不承诺完全无网络；应用统计路径绝不打开媒体数据。
- UNPINNED/RECALL_ON_DATA_ACCESS 只说明云状态，不是“文件不存在”或“应忽略”的依据。
- readme.txt 的读取单独按选择触发；仅联机文本可能下载，离线失败显示提示。不能在扫描整个目录时读取全部说明。
- 操作系统提供的云 I/O 可能延迟返回；线程保持运行直到系统调用返回，页面保持响应，显示等待状态，不用 thread.terminate。

## README 查找、编码和读写

- 查找只针对所选目录直接子项，名称 casefold 等于 readme.txt；保留实际大小写路径。跳过实际符号链接/联接说明路径，云占位文件仍可读。
- 每次选择先分配 request_id。仅一个说明 I/O worker 活跃；快速切换时只保留最新待读请求，已失效结果丢弃，防止堆积下载与线程。
- 最多读取 2 MiB + 1 字节，超过上限返回 too_large。路径、错误与状态对用户可见。
- 编码依次识别 UTF-8 BOM、UTF-16 LE/BE BOM，再严格 UTF-8，再 GB18030；保持原 BOM。检测常见 CRLF/LF/CR 风格，显示时可统一换行，写回恢复原风格。
- 禁用 errors=ignore/replace；原编码容不下新字符时保留草稿并报错，不自动改编码。不声称任意无 BOM 文本编码都可准确识别。
- 保存请求冻结 document.path、baseline 和编辑器文本，禁止读取一个后来已选中目录的路径。保存期间编辑器暂时只读。
- 先严格编码，再对原文件做小型内容/版本检查；外部改变、删除或读取失败时返回冲突/错误，保留草稿。
- 在原文件同一目录创建唯一临时文件，完整写入、flush、关闭，再 os.replace 写回；失败只清理本次确知创建的临时文件，不先截断原文件。
- 保留原文件读写权限约束，不绕过只读属性/ACL。替换前再次检查基线，减小外部变更竞争窗口；该检查不是跨设备或云端分布式锁。
- 成功后重新建立保存基线，清除 dirty 标记；重新加载不得静默丢草稿。

## UI 状态与退出

- 状态包含当前目录、当前 ReadmeDocument、dirty、load/save busy、pending_action 和异步请求代号。
- 目录切换/新根/重扫/退出统一调用草稿守卫。使用内嵌“保存 / 放弃 / 取消”条；普通错误也以内嵌提示或 InfoBar 呈现，不新增阻塞 QMessageBox。
- “保存”异步成功后执行 pending_action；失败时保留原选择与草稿。“放弃”才执行动作；“取消”恢复原节点选择。
- 普通切换其他功能页不关闭媒体统计页，编辑草稿保留。
- 独立 closeEvent 与 UnifiedMainWindow.closeEvent 均协调新页：有草稿/活动任务则先 ignore，选择保存或放弃后请求扫描停止，待说明 I/O 和线程清理结束再重新 close。
- 每个 worker 必须确保完成信号从 finally 发出，并连接 thread.quit、worker.deleteLater、thread.deleteLater；主线程持续持有引用直到 finished。禁止从工作线程操作控件。

## 兼容与回滚

- 不新增运行依赖；现有项目环境 Python 3.14 已具备 TreeView、TreeWidget、PlainTextEdit、IndeterminateProgressBar。
- 不改已有媒体格式集与时间识别算法；不硬编码个人 OneDrive 路径作为全用户默认配置。
- 设置使用独立 APP_NAME 路径，测试 APPDATA 必须隔离。
- 回滚时移除新导航/导入/设置兼容改动及两个新模块；磁盘相册无需迁移。用户显式保存的说明内容属于用户数据，不由代码回滚自动撤销。

## 验证与剩余边界

- 核心验证计数、云项属性、未完成状态和无媒体内容读取；文本验证编码/换行、保存失败、冲突和数据保留。
- GUI 验证两种运行方式、动态中英、快速切换、草稿守卫、保存/取消以及扫描/读写期间退出。
- 真实相册只验证枚举统计；联机文本 hydration、同步上传结果依赖客户端，无法仅以模拟测试声称全部实测。
- 混合换行文本编辑后采用检测到的原主要风格；无 BOM 文本编码有歧义。外部变更检查降低覆盖风险，但不实现系统级并发编辑锁。
