# pi-readme 实施报告：media_readme_core.py

范围：仅 `media_readme_core.py` 与本报告。未触碰其他模块、任务文档、README 或真实 OneDrive 文件。

## 交付内容

`media_readme_core.py`（纯标准库，零新增依赖，不导入 PyQt）。严格实现 `research/parallel-contract.md` 固定接口：

```python
MAX_README_BYTES = 2 * 1024 * 1024

@dataclass(frozen=True) class ReadmeDocument: path, text, encoding, bom, newline, baseline, mtime_ns
@dataclass(frozen=True) class ReadmeResult:   status, document=None, error="", path=None

def load_readme(directory: Path) -> ReadmeResult
def save_readme(document: ReadmeDocument, text: str) -> ReadmeResult
```

附加便利（不改变契约）：状态常量 `STATUS_READY/MISSING/TOO_LARGE/ERROR/CONFLICT/SAVED`、
`README_NAME`、`find_readme(directory)`、`ReadmeDocument.size`/`editor_text`、`ReadmeResult.ok`。

契约字段已用 `__dataclass_fields__` 逐项核对一致，GUI 可按位置或关键字构造。

## 修订记录（v2，协调者复审后）

### 修订 1：枚举/类型失败不再误报 missing（原缺陷已修复）

原实现有两处会把握手失败降级成 `missing`：

1. `find_readme` 把所有 `OSError` 都 `return None`，包括 `with os.scandir(...)` 期间**迭代中**抛出的 `FindNextFileW` 失败；
2. `load_readme` 在 `find_readme` 返回 None 后再开一次 `with os.scandir(folder): pass`，而该语句**不消费迭代器**，所以迭代期错误根本不会再次暴露，只能看到“打开成功”；
3. 同名 `readme.txt` 条目的 `is_file()` 抛 `PermissionError` 时被 `except OSError: continue` 吞掉，直接落到“没有说明文件”。

重构：新增内部 `_locate_readme(directory) -> ReadmeResult`，作为**唯一权威枚举入口**，`load_readme` 不再二次遍历（测试断言 `os.scandir` 恰好调用 1 次）。返回类型与状态严格三分：

- `ready` + `path`：命中，`path` 为磁盘真实大小写路径；
- `missing`：目录**完整枚举成功**且确实无 `readme.txt`；
- `error`：目录不存在/不是目录/不可访问/构造失败/**迭代中途失败**/同名项 `is_symlink`·`is_junction`·`is_file` 判定失败，`error` 附原因，`path` 指向目录（枚举失败）或该条目（类型判定失败）。

`find_readme` 保留为便利函数，仅 `ready` 时返回路径，其余返回 `None`（docstring 明确指路 `load_readme` 获取失败细节）。同名但不是普通文件（如名为 `readme.txt` 的目录）仍视为“没有可编辑说明”，不是失败。

### 修订 2：保存也强制 2 MiB 上限

原实现只限制读取，编辑器可以把文件写到 >2 MiB，导致保存成功但下次无法重新打开。现在在严格编码后、基线检查与写临时文件之前比较 `len(payload) > MAX_README_BYTES`，超限返回 `STATUS_TOO_LARGE`：不写盘、不建临时文件、原文件字节不变、`document`（草稿基线）保留给 GUI 显示失败。恰好 2 MiB 仍可保存且可重新加载；UTF-16 按**落盘字节**计而非字符数。
- 状态选 `too_large` 而非 `error`：语义与读取侧一致，GUI 已按“通用失败”处理（保留草稿、恢复编辑器可编辑）。
- 该检查先于基线检查，故“外部已修改 + 草稿超限”时也不会误写（测试覆盖）。

## 关键行为决策

- **查找**：仅 `os.scandir` 所选目录直接子项，`name.casefold() == "readme.txt"`，保留磁盘真实大小写路径；`is_symlink()`/`is_junction()` 或非普通文件的同名项跳过；云占位文件照常可读。不创建文件、不查上级目录。**单次枚举**，枚举/类型判定失败返回 `error` 并给出行定位信息。
- **missing 与 error 严格区分**：只有“目录完整枚举成功且确实无同名文件”才 `missing`；目录不存在/不是目录/不可访问/**迭代中途失败**/同名项类型判定失败/打开失败/无法解码一律 `error`，并把真实路径与原因写入 `error`，绝不把失败伪装成 missing。
- **编码识别顺序**：UTF-8 BOM → UTF-16 LE/BE BOM → 严格 UTF-8 → GB18030。无 BOM 但含 NUL 字节不猜 UTF-16（返回 error），避免以替代字符掩盖。UTF-16 奇数长度同样判为 error。全程 `errors="strict"`，未使用 ignore/replace。
- **BOM 保留**：`bom` 字段存原 BOM 字节，保存时原样前置；无 BOM 保持无 BOM。
- **换行**：读入时探测主要风格（CRLF/LF/CR，取前 64K 字符内最多者，默认 LF），`document.text` 统一为 LF 供编辑器使用；保存时 `_restore_newlines` 还原原风格。混合换行采用原主要风格。
- **2 MiB 上限（读与写双向）**：读取时以 `read(limit+1)` 探测，超限返回 `too_large` 且不整体载入；恰好 2097152 字节可正常编辑；同时用 `st_size` 复核，防止读取期间增长。保存时对**编码后的落盘字节**再次校验，超限返回 `too_large`，保证“能保存的文件一定能重新打开”。
- **只读/权限安全**：不做 chmod/chown，不绕过 Windows 只读属性或 ACL；无写权限时返回 `error`，原文件字节不变。
- **基线冲突**：`_check_baseline` 比较"文件存在 + 大小 + 完整字节"（先比大小避免大读）。保存流程中检查两次——写临时文件前、`os.replace` 前——可捕获两次检查之间的竞态。外部修改或删除返回 `conflict`，`document` 仍为原文档（草稿由 GUI 侧持有），绝不重建被删除的文件。
- **原子替换**：`tempfile.mkstemp(prefix=".<name>.", suffix=".tmp", dir=原目录)` → 写入 → `flush` → `os.fsync` → 关闭 → 基线复核 → `os.replace`。全程不截断原文件；任何异常（写入、编码、权限、替换）只 `_safe_unlink` 本次确知创建的临时路径，并在替换成功后把 `temp_path` 置 None 以免误删新文件。
- **内容未变化**：若编码后字节与基线完全相同，直接返回 `saved` 且不重写磁盘（mtime 不变），避免无意义写与云同步触发。
- **成功后基线**：返回 **新的** `ReadmeDocument`（`baseline=payload`、`mtime_ns` 取落盘后 `stat()`），GUI 以此清除 dirty，重新加载与磁盘一致。
- **不可编码**：GB18030/UTF-8 编码失败返回 `error`（不做自动换编码），`document` 保留以便 GUI 保留草稿，原文件不受损。

## 验证结果

`compileall`：`.venv/Scripts/python.exe -m compileall -q media_readme_core.py` → 通过。

### v1 行为验证（60 项断言，全 PASS）

临时脚本（已删除）+ `tempfile.mkdtemp()` 独立夹具 + `unittest.mock`：

- 编码/换行往返：UTF-8 CRLF、UTF-8 BOM（大写 `README.TXT`）、UTF-16 LE/BE BOM、GB18030、LF/CRLF/CR 三种风格；保存后逐字节比对磁盘内容与 BOM。
- 空文件：`ready` 且可编辑、可写回。
- 缺失：`missing` 且不创建文件；不存在目录 → `error`。
- 超限：2 MiB+1 → `too_large` 无 document；恰好 2 MiB → `ready`。
- 不可解码：UTF-16 孤立代理 → `error`（非 missing）。
- 外部修改 / 外部删除 → `conflict`，原字节保留、被删文件不重建、无残留临时文件。
- 只读文件属性 → `error`/`conflict`，字节不变。
- `os.replace` 抛 `OSError` → `error`，原字节 `keep me\n` 保留，目录内无 `.tmp` 残留。
- `os.fsync` 抛 `OSError`（写入中途失败）→ `error`，原字节保留，临时文件已清理。
- 保存前二次基线检查失败（模拟另一写入者）→ `conflict`，另一写入者内容完整保留，无临时残留。
- 内容未变 → `saved` 且 mtime 未变。
- 符号链接说明 → 被忽略（`missing`）。
- 导入 `media_readme_core` 后 `sys.modules` 无 PyQt6；无任何新依赖。

### v2 增量行为验证（42 项断言，全 PASS）

修复缺陷的针对性用例（均基于真实临时目录 + `mock.patch.object(m.os, "scandir")` 注入故障）：

- **迭代中途失败**：自定义 `scandir` 包装器首次 `__next__` 抛 `OSError(22)` → `load_readme` 返回 `error`、`error` 含“枚举”、`path` 为目录；同场景 `find_readme` 返回 `None`。
- **迭代后期失败**：先正常产出若干项再抛 `OSError` → 绝不 `missing`。
- **同名项 `is_file()` 抛 `PermissionError`** → `error`（非 missing），`path` 指向该 `readme.txt` 条目，`error` 含“类型”。
- **`is_symlink()` 抛 `PermissionError`** → `error`（非 missing）。
- **单次枚举**：`ready` 与 `missing` 两种路径下 `os.scandir` 均**恰好调用 1 次**（计数器断言，防回归到二次遍历）。
- **真正的 missing 仍为 missing**：空目录 → `missing`；`find_readme` → `None`；命中时返回真实路径。
- **名为 `readme.txt` 的目录** → `missing`（不是可编辑说明，也不是错误）。
- **保存超限**：编码后 >2 MiB → `too_large`，原字节不变、`document` 保留、目录内无临时文件、`error` 含“上限”。
- **保存恰好 2 MiB** → `saved`，落盘大小精确为 2097152，且随后 `load_readme` 为 `ready`（闭合“保存后仍可重新打开”）。
- **UTF-16 按落盘字节计**：字符数仅为一半但字节 >2 MiB → `too_large`，原字节不变。
- **超限 + 外部已修改**：返回 `too_large`/`conflict`，外部内容完整保留。
- **回归**：UTF-8 BOM + 大写文件名 + CRLF 往返、外部修改冲突、只读保护、`os.replace` 失败清理与字节保留均保持 PASS。
- 额外核对：两个 dataclass 字段列表与契约完全一致；5 种编码/ BOM 组合往返字节精确；缺失不建文件；无 PyQt 导入。

未写真实用户说明文件；全部写测试在临时目录完成并已删除。

## 真实云环境边界（沿用 evidence.md）

- OneDrive 仅联机 readme.txt 的实际下载/离线失败路径未在用户目录实测；代码把这类 `OSError` 明确转为 `error` 并返回路径，不会显示为 missing。
- 基线检查是尽力减少覆盖窗口，不提供跨设备/跨进程的分布式锁；OneDrive 同步冲突仍需用户在客户端处理。
- 无 BOM 文本编码存在固有歧义，采用 UTF-8 → GB18030 有限策略，不承诺任意 ANSI 文本都能准确识别。

## 交接要点（供 pi-gui / 主会话）

- 每次选择目录：`load_readme(dir)`；`ready` → 填充编辑器并用返回的 `document` 作为基线；`missing` → 清空并禁用编辑区，文案"此目录没有 readme.txt"；`too_large`/`error` → 清空、只读、显示 `result.error`，并展示 `result.path`。
- `document.text` 已是 LF；dirty 判断请比较 `editor.toPlainText() != document.text`（不要与磁盘原始 CRLF 字节比较）。
- 保存：`save_readme(document, editor_text)`；`saved` → 用 `result.document` 替换当前基线并清除 dirty；`conflict`/`error` → 保留草稿、恢复编辑器可编辑、显示 `result.error`。
- `result.path` 在 `missing` 时为“预期路径”，在 `error/conflict/too_large` 时为真实文件路径（枚举失败时为目录路径，类型判定失败时为该同名条目路径），可直接用于界面显示。
- 保存可能返回 `too_large`（草稿编码后 >2 MiB）。GUI 的通用失败分支即可处理：保留草稿、恢复编辑器可编辑、显示 `result.error`。如需更精确提示，可单列 `STATUS_TOO_LARGE` 文案。
- 本模块无锁、无线程；请确保同一时刻只有一个说明 I/O worker（契约已要求 request_id 单活跃）。
