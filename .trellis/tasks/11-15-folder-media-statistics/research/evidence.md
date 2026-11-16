# 研究记录（2026-11-15）

## 本地代码与目录证据

- unified_gui.py:198：EmbeddedPage 使用 takeCentralWidget 嵌入功能窗口。
- unified_gui.py:313：SettingsPage 对 feature_windows 精确解包六个窗口；新增第七项必须兼容原有设置绑定。
- unified_gui.py:455、unified_gui.py:464：窗口及页面注册位置；unified_gui.py:621、unified_gui.py:650：统一语言传递。
- unified_gui.py 没有 closeEvent；新增说明编辑器需要统一窗口协调草稿和后台退出，不能只依赖嵌入窗口自己的 closeEvent。
- timestamp_fix_gui.py:49、:50 为当前媒体扩展名唯一来源；核心模块通过参数接收，避免导入 Qt 或复制格式集。
- 全仓库 Python 检索未发现已有 readme.txt 编辑器或通用文本保存实现。
- 本地 .venv 为 Python 3.14.0；实测 qfluentwidgets 具有 TreeView、TreeWidget、PlainTextEdit、TextEdit、IndeterminateProgressBar。
- 两份 PyInstaller spec 使用 unified_gui.py 作为入口；新增静态导入模块由分析器收集，仍需打包检查。
- 用户根目录包含 2006、2007、2008、2015–2026 等年份；2026 下有 2026-01 等月份；抽查月文件扩展名 .jpg。
- 某媒体条目属性为 5242912，即 0x500020（ARCHIVE + UNPINNED + RECALL_ON_DATA_ACCESS）；此为有云取回标记的本地可见项，不能过滤成不存在。
- 根目录、2026、2026/2026-11 三个位置未发现直接 readme.txt。只枚举名称和属性，没有读取真实媒体或说明内容。

## 官方资料与设计推论

1. Microsoft Learn：File Attribute Constants
   https://learn.microsoft.com/en-us/windows/win32/fileio/file-attribute-constants
   REPARSE_POINT 不等于符号链接；UNPINNED 表示用户不要求常驻，RECALL_ON_DATA_ACCESS 表示内容未完全在本地。读取文件或枚举虚拟目录可能取回远程内容。设计推论：计数只用名称/类型，并区分云属性与实际链接；不要承诺绝对无网络。
2. Microsoft Support：Save disk space with OneDrive Files On-Demand for Windows
   https://support.microsoft.com/en-us/office/save-disk-space-with-onedrive-files-on-demand-for-windows-0e6860d3-d9f3-4971-b321-7092438fb38e
   仅联机文件打开时下载，离线时不能打开。设计推论：媒体统计与选中 readme.txt 的内容读取分开；文本加载可失败，用户需见到状态。
3. Python 3.14 官方 os 文档
   https://docs.python.org/3.14/library/os.html#os.scandir
   Windows scandir 使用 FindFirstFileW/FindNextFileW，DirEntry 暴露名称和尽可能缓存的类型信息。
   https://docs.python.org/3.14/library/os.html#os.DirEntry.is_junction
   is_junction 自 3.12 提供；可与 is_symlink 精确排除链接，避免排除所有 reparse 项。follow_symlinks=False 适合目录类型检查。

## 边界

- 文件目录内容可能扫描期间变化；这是扫描快照，不是文件系统事务。
- 标准库暂不尝试强行中止已阻塞的云文件系统调用；取消为协作式，退出等待线程清理。
- 无 BOM 文本存在编码歧义；采用 UTF-8 后 GB18030 的有限策略并严格保存，未知编码不静默替换字符。
- 保存前基线比较属于尽力防止外部覆盖，不解决跨设备 OneDrive 同步冲突。
- README 的真实云下载/上传状态尚未通过写用户目录验证；实施时不可宣称模拟测试已证明端到端云同步。
