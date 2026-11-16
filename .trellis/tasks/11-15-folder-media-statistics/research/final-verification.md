# 最终验收记录

日期：2026-11-15。分支：`feat/folder-media-statistics`。

## 交付结果

- 新增 `media_statistics_gui.py` 独立窗口，并接入统一入口第七个功能页“媒体统计”。
- 支持选择/粘贴/拖入根目录，按实际目录层级显示可折叠年份、月份与普通目录。
- 列为文件夹、图片、视频、总项数；总项只含现有格式集的图片与视频。
- 树下方读取所选目录直接包含的已有 `readme.txt`，可编辑并显式保存；缺失不创建。
- 保留支持的编码/BOM/主要换行，保存冲突保留草稿；切换、重扫、关闭有草稿守卫。
- 扫描与说明读写使用后台线程，停止/换根/关闭安全收尾；中英界面均已验证。
- 四个实际 Pi CLI 在同一工作区完成扫描、说明核心、界面、集成及独立复核。
  最后一次关闭回调遗漏由主会话补测发现并作最小修复，Pi 复核确认。

## 验收映射

| 验收项 | 证据与结果 |
|---|---|
| AC1 目录树与计数 | 临时嵌套/空目录/后缀名目录/无关文件逐层比对；真实目录与 os.walk 一致 |
| AC2 独立/内嵌及操作 | 实际按钮、树选择、展开折叠、停止重扫、Qt 拖拽事件链、两种模式通过 |
| AC3 扩展名/云占位/零媒体读取 | 全扩展名及大写；精确排除 symlink/junction；拦截 builtins.open/os.open 断言不打开内容 |
| AC4 不完整结果 | 注入单条目错误、迭代中途失败、消失/拒绝访问、协作式取消，保留计数并标记祖先 |
| AC5 说明编辑 | 实际 btn_save.click() 写回临时文件，缺失清空，大小写 README 正常，媒体数不变 |
| AC6 编码和写入保护 | UTF-8/BOM、UTF-16 LE/BE BOM、GB18030、空文件及换行往返；超限/只读/替换失败原文件不受损 |
| AC7 草稿与异步生命周期 | 串行 README I/O、请求身份、旧线程 cleanup、保存后导航、关闭回调与最终 drain 回归均通过 |
| AC8 外部变更冲突 | 修改/删除后保存不覆盖、不重建；保留草稿并撤销续操作 |
| AC9 真实相册只读 | 真实相册只枚举目录项；所有说明写入测试使用临时目录 |

详细分工证据见 `pi-scan-report.md`、`pi-readme-report.md`、`pi-gui-report.md`、
`pi-integrate-report.md`；最终全范围闸门见 `pi-final-check.md`（包含后续 C1 修正）。

## 真实 OneDrive 只读核对

路径：`D:\WindowsExt\Netdisk\PersonalDisk\OneDrive\MyAllAlbums\MyAlbums\MyCamera`

- 图片 **12,162**，视频 **3,180**，媒体总项 **15,342**。
- 目录 **155**，扫描错误 **0**，15 个年份分项之和等于根总计。
- 独立 `os.walk` 参考结果逐项一致；扫描时禁止媒体内容打开。
- 最后一次扫描及参考核对共约 0.923 秒（仅本机当次实测，不作普遍性能保证）。
- 完整分年结果：`real-album-validation.json`。

## 主会话实际验证

使用 `.venv/Scripts/python.exe`（项目 Python 3.14）；GUI 测试隔离 `APPDATA`，
设置 `QT_QPA_PLATFORM=offscreen`，捕获 Qt 槽异常；显式清理窗口并运行事件循环退出。

1. `-m compileall -q media_statistics_core.py media_readme_core.py media_statistics_gui.py unified_gui.py`：通过。
2. `verify_integration.py`：计数/编码冲突/独立完整操作/七页统一入口与关闭均通过，exit 0。
3. `verify_rescan_close.py`：先完成一次扫描，再重扫并在 worker 退出前请求关闭，
   强制让最后 UI drain 晚于线程退出；修复前回调丢失，修复后只触发一次，后台已清空，exit 0。
   Pi 以运行时恢复旧实现的对照验证测试确实能检出该缺陷。
4. 图像检查：使用真实 Microsoft YaHei 字体查看独立 1000×800 与统一 1440×900 截图，
   树/编辑区清晰、数字列宽正确、路径不撑宽。Pi 另验证最小/default/长路径/英文布局。
5. `git diff --check`：无空白错误（仅 Windows 行尾转换提示）。任务 JSON、JSONL 路径验证通过。

临时脚本、截图与构建日志位于本会话临时目录
`D:\AppData\Local\Temp\media-statistics-pi-a348f6b30b934e7b9c2cf756196f2279`，不加入产品仓库。

## 最终可运行产物

```powershell
.venv/Scripts/python.exe -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec
.venv/Scripts/python.exe scripts/ci/verify_bundle.py
```

- 最后构建包含 C1 关闭修复，exit 0；未使用 `--clean`，未修改打包 spec 或依赖。
- 产物：`dist/AzureKilnPhotoTool.exe`，**80,659,018 字节**。
- 自检：922 个归档项、479 个 PYZ 模块、508 个 ExifTool 文件；
  pillow_heif/send2trash/ExifTool 完整。
- 从 EXE 的嵌入 PYZ 提取三个新模块的 code object，与最终源码编译结果相等，
  确认不是旧版产物。EXE 图形界面未另行真机交互验收，功能交互验证基于相同源码。
- 使用：运行该 EXE → 侧栏“媒体统计”；独立运行可用
  `.venv/Scripts/python.exe media_statistics_gui.py`。

## 验证边界与提交状态

- 真实 OneDrive 仅联机说明下载/离线行为未实测；真实目录项已验证，但未人为改变云文件状态。
- Qt 拖拽事件链通过，不代表已验证真实 Windows OLE/UIPI 拖拽。
- 无静态类型检查/lint 配置；compileall 仅表示语法通过。
- 外部修改保护为保存前字节基线检查，不是跨设备同步锁；混合换行会规范为检测到的主要风格。
- 功能、最终复核、构建与自检完成。未提交/未推送/未归档；按 Phase 3.4 等待
  `commit-plan.md` 的一次确认。并行的 github-ci-release 任务保持原状。
