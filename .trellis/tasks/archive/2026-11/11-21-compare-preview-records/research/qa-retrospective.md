# 本轮界面与记录联调复盘

## 1. 根因类别

- D（集成测试缺口）：宽820的独立预览面板能显示全部路径，但真实1360×880页面的窄侧栏只给文本108高，完整文本需要209高。
- B/E（跨层/隐含假设）：线程isRunning已False不代表主线程finished回调完成，更不代表按钮已启用；紧接着的真实按钮click会被忽略，单跑测试偶尔通过而全量失败。
- C（传播遗漏）：记录核心已支持stale往返，旧页面测试仍断言拒绝导出；验证必须以冻结后的代码契约为准。
- D（环境依赖）：`test_unified_close` 初始化全功能统一窗，旧 Flyme 页 `LivePhotoFixTool` 找不到 ExifTool 后走 `main_gui.py:463` 的 `QMessageBox.critical`，**模态框永久阻塞**。本地有 ExifTool 且 CI 的单测早于 `ConfigureExifTool`，所以「本机能过」完全不代表 CI 能过。
- E（跨盘假设）：CI runner 上 repo 在 D:、`TEMP` 在 C:，`test_compare_page_features.py:299` 对跨盘路径调 `os.path.relpath(C:\temp, D:\cwd)` 直接 `ValueError`。本地同盘所以测不出。

## 2. 早期修复为何不足

1. 仅压缩minimumSizeHint解决横向撑开，未解决连续文件名任意字符换行。
2. QTextDocument的WrapAnywhere解决横向排版，但仅heightForWidth仍允许VBox在可用高度不足时压缩标签。
3. 只在窗口析构前断言无异常，会漏掉DeferredDelete后的TableView已删除错误；按obj是QAbstractItemView预筛又会误伤实际QWidget viewport的右键事件。
4. 只给record线程加引用忙态，漏掉既有scan/recycle同类退出窗口，完整discover才复现按钮无效。

## 3. 防止复发

| 优先级 | 机制 | 落点 |
|---|---|---|
| P0 | 记录加载后真实文件逐字节重验，改写/删除均不触发mock回收 | 两页测试、root_records_probe |
| P0 | 所有后台线程引用未清理前均算忙；finished后再更新按钮和关闭 | 两页实现与线程忙态测试 |
| P1 | 正常字体、实际页面宽高、独立/内嵌、中英、真实拖动与矩形不相交断言 | root_layout_probe、共享预览测试 |
| P1 | 真实viewport右键测试与已删table测试并存；析构后再汇总槽异常 | test_file_context_menu、页面测试 |
| P1 | CI先全量unittest后打包，静态断言原生多媒体插件与DLL | build.yml、verify_bundle |
| P0 | GUI 关闭/集成测试隔离非受测依赖（外部可执行工具、send2trash 等外部副作用）与模态对话框；预期对话框 mock 后断言已触发；至少跑一次「缺外部工具」环境 | test_unified_close 等集成测试、python/quality-guidelines.md |
| P1 | CI 单测步骤加 step 级有界超时（`timeout-minutes: 5`），区分「挂起」与「断言失败」 | .github/workflows/build.yml |
| P1 | 相对路径测试在临时根内用 `contextlib.chdir` 等有恢复保证的 cwd 上下文，不跨盘 `relpath`、不 skip；至少一次跨盘 TEMP 复验 | 页面测试、python/quality-guidelines.md |

## 4. 同类范围

共享预览同时影响目录比对和目录内去重，所以修在media_thumbnail并验证两页。
统一窗口搬走内容后收不到独立页closeEvent，必须显式协调两页忙态。
本轮不扩展其他六页的既有线程设计；只记录相同机制的维护风险。

## 5. 知识归档

已同步python/scan-records.md、python/packaging.md、pyqt/shared-previews.md、
pyqt/page-structure.md，以及已有threading-and-workers生命周期契约。
主探针改为向上查找仓库标记，任务归档后仍能找到源码；测试不触碰真实OneDrive文件或真实用户回收站。

## 6. CI 挂起事故（外部工具 + 模态框）

现象：CI 单测作业长时间不结束，无断言失败输出。

链路：`test_unified_close` 构造 `UnifiedMainWindow` → 初始化未受测的旧 Flyme 页 →
`LivePhotoFixTool` 解析不到 ExifTool → `main_gui.py:463` `QMessageBox.critical` 模态 →
无头环境下永久阻塞。

为什么本机测不出：本机已装 ExifTool；CI 的 `ConfigureExifTool` 步骤排在单测之后。
**「本机工具已安装」不能作为可移植性判据**。

处理责任划分（本轮约定）：
- p4：修测试隔离，不触碰无关 engine 的运行时逻辑。
- pB：CI 单测步骤加 `timeout-minutes: 5`，版本升 1.2.2。
- 本任务：把契约写进 `python/quality-guidelines.md`（集成测试隔离外部依赖/模态框、
  必须验证缺工具环境、CI 要有 step 级有界超时）。

不这么做的代价：作业占满配额直到平台默认超时；失败原因不可区分（挂起 vs 断言失败）；
其他真实缺陷被挂起掩盖。

### 补充：跨盘临时目录

第二个只在 CI 暴露的fixture假设：GitHub runner 的 repo 在 D:、`TEMP` 在 C:，
`test_compare_page_features.py:299` 对 `C:\temp` 相对 `D:\cwd` 调 `os.path.relpath` 直接抛
`ValueError`（本地同盘不会复现）。修法属测试侧：在临时根内用 `contextlib.chdir`（有恢复保证）
而不是跨盘 relpath，也不得用 skip 绕开；验收需至少一次跨盘 TEMP 环境复验。
