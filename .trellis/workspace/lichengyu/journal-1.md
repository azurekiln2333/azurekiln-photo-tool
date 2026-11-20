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


## Session 4: 目录比对与目录内去重（4 个 pi 并行）
<!-- trellis-session: v=2 fp=34d6560a0bc55f6f -->

**Date**: 2026-11-20
**Task**: 目录比对与目录内去重（4 个 pi 并行）
**Branch**: `feat/folder-media-statistics`

### Summary

新增目录比对页与目录内去重页，共用 duplicate_scan_core（大小→完整 SHA-256→逐字节比对，回收前复核，只进回收站）；缩略图与预览面板、右键打开目录；4 个 pi 按 WP 并行实现，81 个核心单测通过；同时提交 11-15 媒体统计完善，发布 v1.2.0

### Git Commits

| Hash | Message |
|------|---------|
| `fc7229a` | feat: add folder compare and in-folder dedupe pages |

### Status

[OK] **Completed**


## Session 5: 目录比对预览与扫描记录修复，发布 v1.2.2
<!-- trellis-session: v=2 fp=8494b0b7501c2d03 -->

**Date**: 2026-11-21
**Task**: 目录比对预览与扫描记录修复，发布 v1.2.2
**Branch**: `feat/folder-media-statistics`

### Summary

修复等宽可拖预览、视频首帧回退、批量勾选和安全扫描记录；修正CI外部依赖及跨盘测试环境后发布v1.2.2。

### Main Changes

- 通过herdr现有四个Pi完成实现、独立复核与发布核验，保持原模型。
- JSON历史记录严格校验，执行回收强制逐字节复核，修改或删除目标跳过；全部回收测试用临时文件和mock。

### Git Commits

| Hash | Message |
|------|---------|
| `239874b` | fix: improve compare previews and persist safe scan records |
| `55ed8fb` | fix(ci): isolate close tests from ExifTool and release 1.2.2 |
| `a594841` | test: handle relative-path fixtures across Windows drives |

### Testing

- [OK] 本地全量183项通过；真实C盘TEMP/D盘repo、无外部工具环境183项0失败0错误3条件跳过，7.720秒。
- [OK] GitHub分支44808199635、标签44808571694均success；Release三类资产齐全，下载ZIP与包内EXE哈希、内外校验文本均一致。

### Status

[OK] **Completed**

### Next Steps

- 真实OneDrive仅联机占位视频尚未端到端实机验证；未运行发布安装包。


## Session 6: Dedupe grouping, keeper choice, CI race fix and main release v1.2.4
<!-- trellis-session: v=2 fp=911447771341475f -->

**Date**: 2026-11-21
**Task**: Dedupe grouping, keeper choice, CI race fix and main release v1.2.4
**Branch**: `main`

### Summary

Implemented with four existing herdr Pi agents: photo/video/other groups, per-path preview guard, keeper reselection, visible batch selection and v1 record compatibility. Reproduced and fixed CI test completion race using real timer gate; 201 full tests passed. Fast-forwarded complete feature chain into main; main/feature/tag CI passed; v1.2.4 published and actual release downloads/EXE checksum verified. OneDrive online-only end-to-end remains unverified.

### Git Commits

| Hash | Message |
|------|---------|
| `cdf4176` | feat: group duplicate files and allow choosing the keeper |
| `b0d4335` | test: wait for recycle UI completion and prepare 1.2.4 |

### Status

[OK] **Completed**
