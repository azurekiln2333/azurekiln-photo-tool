# 媒体统计与目录说明契约

## 1. 范围与触发条件

适用于 `media_statistics_core.py`、`media_readme_core.py`、`media_statistics_gui.py`
和统一窗口接入。目录统计只看名称/目录项类型；只有用户选中目录后才读取其中已有的
`readme.txt`。不得把缩略图、EXIF、哈希或创建说明文件混入统计流程。

## 2. 接口签名

```python
scan_folders(root, image_suffixes, video_suffixes, *, stop_event=None, on_batch=None) -> ScanOutcome
load_readme(directory: Path | str) -> ReadmeResult
save_readme(document: ReadmeDocument, text: str) -> ReadmeResult

# GUI：独立窗口与 unified 共用
MainWindow(parent=None, embedded=False)
window.set_root_folder(path)
window.scan_files()
window.request_close(on_ready) -> bool
```

## 3. 数据与行为契约

- `FolderSnapshot`：`path, parent_path, name, direct_image_count, direct_video_count,
  image_count, video_count, complete, issue_count`；`total = image_count + video_count`。
  父目录统计包含直属文件和全部后代；空目录保留。路径为绝对路径，不解析链接目标。
- `ScanOutcome`：`root, folders, errors, cancelled`；错误项为 `ScanIssue(path, message)`。
  未取消且无错误才是完整结果；失败/中断保留已枚举计数并标记相关祖先不完整。
- `on_batch` 接收目录快照列表，父目录先出现；同路径的后续快照是覆盖值，不可累加。
  GUI 按请求代号过滤，排队后每轮最多处理 120 行；最终结果等队列处理完再显示。
- 格式集合由 GUI 从 `timestamp_fix_gui` 的 `IMAGE_SUFFIXES/VIDEO_SUFFIXES` 传入；
  大小写不敏感。先判断目录/文件类型再看扩展名，`album.JPG/` 仍应递归扫描。
- 用 `os.scandir` 流式枚举，每条目检查停止标志。只排除真实 symlink/junction，
  不能仅凭 `REPARSE_POINT/OFFLINE/UNPINNED` 排除 OneDrive 媒体占位项。
- `ReadmeDocument`：`path, text, encoding, bom, newline, baseline, mtime_ns`。
  `text` 统一 LF 供编辑；保存恢复原编码/BOM/主要换行风格（混合换行会规范化）。
  编码支持 UTF-8、UTF-8 BOM、UTF-16 LE/BE BOM、GB18030；严格解码/编码。
- `ReadmeResult`：`status, document, error, path`。读取和编码后的保存字节均不超过
  `MAX_README_BYTES = 2 * 1024 * 1024`。不存在时不创建，不继承上级说明。
- 保存前及替换前比较原始字节基线；同目录唯一临时文件完整写入、flush/fsync 后
  `os.replace`。失败只清理本次创建的临时文件。基线校验尽力防止外部修改，非同步锁。
- GUI 只保留一个活跃说明 I/O；草稿在切目录、换根、重扫、重载、关闭前提供
  保存/放弃/取消。I/O 忙时延后动作并重新检查草稿；旧请求不能覆盖新选择。
- `request_close` 返回 `True` 代表已安全；`False` 代表页面接管等待/草稿决策。
  成功收尾后调用 `on_ready`；取消或保存失败撤销关闭意图，保留草稿并恢复编辑。
  不在主线程 `wait()` 或 `terminate()`。
- 验证设置 `QT_QPA_PLATFORM=offscreen` 与临时 `APPDATA`；不改用户真实配置。

## 4. 验证与错误矩阵

| 条件 | 核心结果 | 界面行为 |
|---|---|---|
| 目录正常且无媒体 | 完整，total=0 | 保留空目录行 |
| 枚举/类型判断失败或目录消失 | errors + partial | 保留计数并提示不完整 |
| 协作式停止 | cancelled=True | 标记已停止，不宣称完整 |
| 成功枚举但没有直接 readme.txt | missing | 清空旧文本，禁用编辑 |
| 枚举/读取失败、无法解码 | error | 显示错误，不冒充 missing |
| 读取或保存字节超限 | too_large | 禁止读取或保留保存草稿，原文件不动 |
| 已加载/保存成功 | ready/saved + document | 更新文本/基线，清除脏状态 |
| 原说明被修改/删除 | conflict | 保留草稿与磁盘内容，取消续操作 |
| 无写权限/替换/编码失败 | error | 保留草稿与原文件，允许重试 |

## 5. 正常、基本与异常用例

- 正常：`2026/2026-11` 有 `A.JPG`、`B.MOV`、`readme.txt`，显示 1 图、1 视频、2 项；
  上级累计这 2 项，选择月份才加载说明，保存不改变媒体计数。
- 基本：空目录显示 0/0/0；只有 `notes.txt` 的目录同样为 0，编辑区显示无说明。
- 异常：云目录枚举中断时保留先前计数，祖先显示不完整；仅联机说明读取失败不影响统计。

## 6. 必要验证与断言

1. 所有现有扩展名、大小写、嵌套、空目录、后缀名目录、无关文件；逐层验证总计。
2. 拦截文件内容打开操作，扫描期间调用数为零；模拟非链接云属性与真实临时 junction。
3. 单条目失败、迭代中途失败、取消：保留前面已见媒体，完整标志及祖先计数正确。
4. 编码/BOM/CRLF/LF 往返、空文件、大小写 README、2 MiB 边界；外部修改/删除、
   权限失败、编码失败、替换失败后原文件字节与草稿不变。
5. 用真实按钮点击和选择信号验证保存/放弃/取消；捕获所有 Qt 槽异常并判失败。
6. 人为延迟工作线程，验证快速换根/切目录、保存后续动作、关闭时仍保留所有线程引用；
   旧线程 finished 不得清空新任务引用，最后无活跃线程且进程退出 0。
7. 独立/内嵌、中英、最小与默认窗口、长路径；检查实际尺寸及数字列布局，不能只看 grab 非空。
8. 用户真实 OneDrive 仅作只读统计对照；说明写回只使用临时目录。明确记录真实仅联机
   说明下载/离线行为是否测过，不能用本地模拟冒充云服务端到端验证。

## 7. 错误与正确实现

```python
# 错误：云占位也可能是 reparse；会漏计尚未下载的图片
if entry.stat().st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT:
    continue

# 正确：只排除会跳到其他路径/形成循环的实际链接，媒体内容不打开
if entry.is_symlink() or entry.is_junction():
    continue
if entry.is_dir(follow_symlinks=False):
    queue_directory(entry.path)
elif entry.is_file(follow_symlinks=False):
    count_by_suffix(entry.name)
```

目录项操作抛出 `OSError` 时应记录问题并标记不完整，不可捕获后伪装成非媒体文件。
