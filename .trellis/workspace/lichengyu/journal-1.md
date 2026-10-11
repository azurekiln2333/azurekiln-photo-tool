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
