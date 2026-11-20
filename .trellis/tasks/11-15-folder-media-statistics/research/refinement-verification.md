# 紧凑布局与自动保存修订验收（2026-11-16）

## 基线与范围

- 用户要求“先commit再改”；已在本轮修改前提交 `40b603c`。
- 本轮范围以 `../refinement.md` 为准：精简界面、缩小说明区、增加表格高度、说明自动保存与缺失文件创建。
- 新改动保留为独立工作区 diff；未 push、未触发 CI、未归档当前任务。
- 主会话运行目录：`D:/AppData/Local/Temp/media-compact-1hd50jfd`。

## 主会话独立验收

`verify_refinement.py` 运行通过、进程退出 0，捕获到的 Qt 槽异常为 0：

- 可访问且缺失说明的目录显示可编辑空白；仅选中不创建文件。
- 副标题精确为“统计文件夹内图片、视频数量”；缺失提示、底部完成条、永久保存/重载按钮不存在。
- 停止输入约 800 ms 自动创建 UTF-8 说明；FocusOut 立即触发保存。
- 强制延迟第一次保存，保存中继续输入并切换目录：最终文本落在原目录；目标目录不创建说明；最大并发保存数为 1。
- 外部抢先创建说明会冲突，本地草稿与外部字节均保留；只有明确放弃才执行待定导航。
- 在防抖定时器到期前请求关闭，先写完最新输入再触发回调；独立窗口回调一次，统一窗口最终安全关闭。
- QApplication、窗口及工作线程显式退出，未用退出阶段异常冒充测试通过。

原回归 `media-statistics-pi-a348f6b30b934e7b9c2cf756196f2279/verify_rescan_close.py`
同样通过：同根重扫期间关闭，在最后 UI 队列 drain 后只触发一次关闭回调，线程引用全部清理。

## 界面比较

基线脚本加载 `git show 40b603c:media_statistics_gui.py`；新旧使用相同字体、窗口尺寸和年月目录样例。
默认行高均为 31 px。表中为独立窗口完整可见行数（含根及年份行），编辑区为实际控件高度。

| 窗口尺寸 | 原版表格高度 / 完整行 | 新版表格高度 / 完整行 | 新版编辑区高度 |
|---|---|---|---|
| 1000×800 | 154 px / 4 行 | 368 px / 11 行 | 83 px |
| 1280×860 | 190 px / 6 行 | 428 px / 13 行 | 83 px |
| 1440×900 | 214 px / 6 行 | 468 px / 15 行 | 83 px |

主会话已目视核对 `compact-1000-zh.png`、`compact-1440-en.png` 和 `compact-unified.png`：标题单行说明、工具栏、数字列、
说明标题及路径无重叠；说明区没有多余状态占位；新增高度交给目录表。英文与其他尺寸亦由断言覆盖。
测量数据为 `baseline-geometry.json`、`compact-geometry.json`。

## 静态检查与边界

- `.venv/Scripts/python.exe -m compileall -q media_readme_core.py media_statistics_gui.py media_statistics_core.py unified_gui.py` 通过。
- `git diff --check` 通过。项目没有配置 linter 或类型检查器，语法检查不等同于类型检查。
- 核心 19 组临时目录验证见 `refinement-core-report.md`；GUI 额外事件与尺寸验证见对应 worker 报告。
- 所有本轮说明写入仅在临时目录；未写真实 OneDrive 相册或用户设置。
- 本轮未重测云端仅联机说明的下载/离线行为，不能将本地自动保存验证称为云端端到端测试。

## 独立检查收尾

`trellis-check` 全范围复核发现并修复一处异常恢复问题：重扫遇到保存冲突后放弃修改，
需要重新读取当前目录说明以采用外部新基线。修复后的针对性回归、主验收及 23 组 GUI 回归
均通过，进程退出 0，无剩余发现；详见 `refinement-check-report.md`。

实际 Windows 窗口点击验证因 Computer Use 初始化错误未执行：`failed to write kernel assets:
系统找不到指定的路径。 (os error 3)`；重置重试与可用备用入口均失败。没有将离屏截图验证
冒充真实桌面操作验证。

## 最终构建与运行

- 在检查代理的最终修复后重新执行
  `.venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath dist/compact AzureKilnPhotoTool_onefile.spec`，
  exit 0；未使用 `--clean`，没有覆盖原版 `dist/AzureKilnPhotoTool.exe`。
- 最终产物 `dist/compact/AzureKilnPhotoTool.exe`，80,660,210 字节。
- `scripts/ci/verify_bundle.py` 通过：922 归档项、479 PYZ 模块、508 ExifTool 文件；
  HEIF、回收站和 ExifTool 依赖齐全。
- 提取最终 EXE 中 `media_statistics_core`、`media_readme_core`、`media_statistics_gui`
  的 code object，与最终源码编译结果相等，确认最后一处基线刷新修复已打入产物。
- 已发起最终产物启动并观测到窗口标题；后续进程已退出，未确认退出原因，不能据此声称
  桌面交互验证通过。再次启动观察 15 秒及随后复查，最终窗口 PID 71760 均正常响应，
  标题为 AzureKiln Photo Tool。当前可确认的验证为隔离 GUI 回归、截图、包自检、源码一致性及启动响应。
  打包的可选 WebEngine / macOS AppKit 提示与本次修改无关。
