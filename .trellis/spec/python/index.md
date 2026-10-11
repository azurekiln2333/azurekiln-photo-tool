# Python / 核心逻辑开发约定

> AzureKiln Photo Tool 的非 GUI 代码约定：媒体处理、元数据读写、文件系统操作、打包。
> 这一层指「不依赖 PyQt 界面」的逻辑，例如 `*_core.py`、`merge_live_photo.py`、
> `exiftool_resolver.py`、`timestamp_fix_gui.py` 中的时间/元数据读取函数。

---

## 这个项目是什么

面向 Windows 的动态照片（LivePhoto / Motion Photo）处理工具集。
技术栈：**Python 3.14 + PyQt6 + PyQt6-Fluent-Widgets + qframelesswindow**。
没有 Web 后端、没有数据库、没有网络服务——所有处理都在本机完成。

因此本目录**不包含** database / API / ORM 类约定；如果你的 spec 里看到这些词，
说明那是 `trellis init` 生成的模板残留，应删除。

---

## 指南索引

| 指南 | 内容 |
|------|------|
| [项目结构](./project-structure.md) | 文件放置、模块职责边界 |
| [错误处理](./error-handling.md) | 异常捕获与降级策略 |
| [日志约定](./logging-guidelines.md) | 本项目的「日志」现状 |
| [ExifTool 与元数据](./exiftool-and-metadata.md) | ExifTool 调用、EXIF SubIFD、时间来源优先级 |
| [打包约定](./packaging.md) | PyInstaller onefile/onedir、ExifTool 布局 |
| [质量约定](./quality-guidelines.md) | 验证方式、验收标准、禁止事项 |

---

## 预开发检查表（写代码前逐条过一遍）

- [ ] 改动是否落在共用层？`timestamp_fix_gui.py` 同时是**共用时间/元数据读取层**，
      `rename_photo_gui.py` / `dedupe_media_gui.py` / `merge_live_photo_gui.py` 都从这里 import。
      改共用函数会**同时影响多个页面**，先确认影响面。
- [ ] 是否引入新依赖？本项目坚持零新增第三方依赖，优先复用 `Pillow` / `send2trash` /
      `pywin32` / `qfluentwidgets` 里已有的能力。
- [ ] 是否涉及元数据时间？确认遵守「拍摄/容器元数据 → 文件名 → 文件最早时间」优先级。
- [ ] 是否需要打包验证？若改了 import 结构或新增数据文件，同步检查 `.spec` 与
      `exiftool_resolver._candidate_dirs()`。
- [ ] 注释/文档是否用中文？（本项目约定，见下）

---

## 质量检查（改完代码后逐条过一遍）

- [ ] 用 `.venv/Scripts/python.exe` 跑语法检查：`python -m compileall <changed files>`
- [ ] 涉及 GUI 的改动用无头方式冒烟：`QT_QPA_PLATFORM=offscreen` + 临时 `APPDATA`
- [ ] 未污染用户真实配置（测试时 `APPDATA` 指向临时目录）
- [ ] 关键回归用例：项目根 `IMG_20010101_000000.jpg`（占位文件名、真实时间在 EXIF
      `DateTimeOriginal=2006-05-30`）仍能识别正确时间
- [ ] 新增 UI 文案已补齐 zh/en 翻译键

---

**语言约定**：本目录文档用**中文**编写（本项目团队语言），代码注释同样用中文。
