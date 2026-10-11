# Journal - lichengyu (Part 1)

> AI development session journal
> Started: 2026-10-11

---



## Session 1: 管理员权限拖拽提示：定位 UIPI 真因并加内嵌提示条
<!-- trellis-session: v=2 fp=3d6d0c8096a60e54 -->

**Date**: 2026-10-12
**Task**: 管理员权限拖拽提示：定位 UIPI 真因并加内嵌提示条
**Branch**: `main`

### Summary

排查'所有页面拖不进文件'：确认 Qt 事件链路正常，真因为管理员权限触发 Windows UIPI 阻断 Explorer 的 OLE 拖拽。新增 elevation_hint.py（IsUserAnAdmin 检测 + Fluent 内嵌提示条），接入 7 个入口标题下方；保留 merge 页拖拽健壮性改进。补 .gitignore 忽略 Trellis 各平台镜像与本地记忆。3 个标准化 commit。

### Git Commits

| Hash | Message |
|------|---------|
| `c1e0406` | chore: add trellis workflow scaffolding |
| `94818dd` | feat: add admin elevation drag-drop hint |
| `a8f5772` | feat: add exiftool resolver for bundled runtime |

### Status

[OK] **Completed**


## Session 2: 文档补齐六功能页 + Flyme 修复复用 exiftool_resolver
<!-- trellis-session: v=2 fp=39ab6444eb7f8770 -->

**Date**: 2026-10-12
**Task**: 文档补齐六功能页 + Flyme 修复复用 exiftool_resolver
**Branch**: `main`

### Summary

收尾上一条会话遗留的两个改动：README 补齐六个功能页/使用说明/项目结构；flyme_livephoto_fix_core.py 改为复用 exiftool_resolver.resolve_exiftool()，删除内联 _get_exiftool_path。工作区 clean。

### Git Commits

| Hash | Message |
|------|---------|
| `8cd4974` | docs: document all six feature pages |
| `c2ff1e2` | refactor: use shared exiftool resolver in flyme fix core |

### Status

[OK] **Completed**


## Session 3: 填充项目 spec：Web 模板改写为 python/pyqt 真实约定
<!-- trellis-session: v=2 fp=5ae85dd313ae4895 -->

**Date**: 2026-10-12
**Task**: 填充项目 spec：Web 模板改写为 python/pyqt 真实约定
**Branch**: `main`

### Summary

删除 trellis init 生成的 backend/frontend Web 全栈模板占位，按'记录现实而非理想'原则重建为两层：python（非 GUI 核心逻辑：结构、错误处理、日志现状、ExifTool 与元数据、打包、质量）+ pyqt（界面：页面结构/embedded 双模式、Fluent 控件、QThread+队列 drain、zh/en 翻译、质量）。内容全部来自真实代码与历史。归档 00-bootstrap-guidelines。

### Git Commits

| Hash | Message |
|------|---------|
| `527ad4b` | docs(spec): replace web templates with real python/pyqt guidelines |

### Status

[OK] **Completed**
