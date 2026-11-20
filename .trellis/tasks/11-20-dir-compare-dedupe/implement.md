# 执行计划

所有工作包并行开始，严格只改 design.md「模块边界」表中分配给自己的文件。禁止 git commit / push / merge / stash / checkout / reset。
Python 解释器：优先 `.venv\Scripts\python.exe`（存在时），否则 `python`。

## WP1 核心（pi-core）
- [ ] 读 design.md「契约 1」，实现 `duplicate_scan_core.py`，签名与语义必须和契约一致（GUI 页面正并行按契约编码）。
- [ ] `tests/test_duplicate_scan_core.py`（unittest + tempfile，无新依赖），至少覆盖：
  - AC1 A 中 1 个文件、B 中 3 份副本（不同子目录不同文件名）→ 1 组 3 个 duplicates，keeper 在 A。
  - AC2 同大小仅末尾 1 字节不同 → 不成组；大文件（> 2 个 chunk）同样。
  - AC3 monkeypatch `sha256_file` 让不同内容返回相同哈希 → 进入 mismatches，不进 duplicates。
  - AC4 扫描后修改 target 或 keeper（内容 / 大小 / mtime）→ `revalidate_pair` 返回对应原因，`recycle_duplicate` 不调用 send2trash（mock）。
  - AC5 扫描后删除 keeper → keeper_missing。
  - AC6 相同 / 嵌套目录 → ValueError，各 code 正确。
  - AC7 三种保留策略选出的 keeper 正确且多次运行结果一致。
  - B 内部重复但 A 中没有 → 比对模式不输出。0 字节文件被跳过。scope="media" 过滤生效。
  - 取消：should_cancel 立即返回 True → result.cancelled 为 True，不抛异常。
- [ ] 验证：`python -m unittest tests.test_duplicate_scan_core -v` 全绿；`python -m py_compile duplicate_scan_core.py`。
- [ ] 完成后在汇报里贴出最终公开 API 签名（便于 WP3/WP4 核对）。

## WP2 缩略图 + 集成（pi-thumb）
- [ ] 读 design.md「契约 2」，实现 `media_thumbnail.py`（ThumbnailLoader、PreviewPanel、placeholder_pixmap）。
- [ ] 写一个仅本地手动运行的小 demo（`if __name__ == "__main__":` 内，传入目录参数显示网格），用于自测；不要新增独立 demo 文件。
- [ ] `unified_gui.py`：导入 `dir_compare_gui.MainWindow`、`folder_dedupe_gui.MainWindow`，按现有 EmbeddedPage / feature_windows / 导航 / 图标 / 语言切换 / closeEvent 的方式注册两个新页面（key 与中英文名见 design.md），放在现有"去重"页之后。只做增量修改，不要动该文件其他已有改动。
- [ ] 若 PyInstaller spec 需要显式 hiddenimports 才能打包新模块，则补上；静态 import 能被自动发现就不改。
- [ ] README 三语：新增"目录比对""目录内去重"两节，说明三重校验（大小 → 完整 SHA-256 → 逐字节）与只进回收站。
- [ ] 验证：`python -m py_compile media_thumbnail.py unified_gui.py`；新页面文件就绪后（WP3/WP4 完成前可能还不存在），运行 `python -c "import unified_gui"` 冒烟。缩略图 demo 对一个含 jpg/png/mp4 的目录能出图。

## WP3 目录比对页（pi-compare）
- [ ] 读 design.md 页面契约与「比对页」小节；参照 `dedupe_media_gui.py`（只读）实现 `dir_compare_gui.py`。
- [ ] 调用 `duplicate_scan_core.find_cross_duplicates` / `recycle_duplicate`；缩略图与预览用 `media_thumbnail`；右键复用 `file_context_menu.py`。
- [ ] 核心或缩略图模块尚未就绪时，按契约编码并 `py_compile` 自检；它们就绪后再跑真实冒烟：构造临时 A/B 目录（含多副本、同大小不同内容），embedded=False 启动窗口扫描，确认表格、缩略图、预览、右键、回收流程。
- [ ] 验证：`python -m py_compile dir_compare_gui.py`；`python dir_compare_gui.py` 可独立启动。

## WP4 目录内去重页（pi-dedupe）
- [ ] 读 design.md 页面契约与「去重页」小节；参照 `dedupe_media_gui.py`（只读）实现 `folder_dedupe_gui.py`。
- [ ] 调用 `duplicate_scan_core.find_internal_duplicates` / `recycle_duplicate`；缩略图与预览用 `media_thumbnail`；右键复用 `file_context_menu.py`。
- [ ] 保留策略下拉切换后提示需重新扫描（或用 `choose_keeper` 在已有结果上重算并重新逐字节确认——二选一，优先简单方案：提示重新扫描）。
- [ ] 同上的冒烟方式：临时目录含 3 个子目录各一份副本 + 同大小不同内容文件。
- [ ] 验证：`python -m py_compile folder_dedupe_gui.py`；`python folder_dedupe_gui.py` 可独立启动。

## 汇总门禁（主会话）
1. 4 个 WP 全部汇报完成 → 主会话跑 `python -m unittest tests.test_duplicate_scan_core -v`、`python -c "import unified_gui"`。
2. 派 trellis-check 全范围检查（重点：准确性不变量、契约一致性、线程安全、未越界修改文件）。
3. 用户实机验收 AC9–AC11。
4. 更新 spec（duplicate 校验契约）→ 提交（注意与 11-15 任务的未提交改动分开提交）。
