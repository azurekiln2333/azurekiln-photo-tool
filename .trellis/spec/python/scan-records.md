# 扫描记录与历史恢复

## 1. 适用范围

`scan_record_core.py` 是目录比对、目录内去重两页共用的无 Qt 记录边界。记录是用户可编辑的不可信 JSON，只保存扫描结果和行状态，不嵌入媒体、不执行回收、不读取媒体内容。

## 2. 接口

```python
@dataclass
class ScanRecord:
    mode: str
    root_a: Path
    root_b: Path | None
    scope: str
    keep_strategy: str
    result: ScanResult
    row_states: dict[str, dict]
    created_at: str = ''
    stale: bool = False

def save_record(path: Path, record: ScanRecord) -> None: ...
def load_record(path: Path, *, expected_mode: str | None = None) -> ScanRecord: ...
```

文件/权限错误抛 `OSError`，无效类型、格式或安全约束抛 `ValueError`。GUI 后台线程负责调用，主线程只在完整成功后替换显示。

## 3. 格式与跨层契约

- UTF-8、`schema_version=1`，顶层字段：`schema_version/mode/created_at/roots/options/result/row_states/stale`。未知或缺少字段、重复 JSON 键均拒绝。
- `mode` 为 `compare` 或 `internal`；`roots={a:绝对路径,b:绝对路径或null}`；internal 的 b 必须为 null。
- `options={scope:'all'|'media', keep_strategy:'shallowest'|'oldest'|'newest'}`。
- `result` 保留核心 `ScanResult` 的 groups、mismatches、issues、scanned_files、hashed_files、hashed_bytes、cancelled；条目保留 path、root、size、mtime_ns、file_id，组保留完整 SHA-256。
- `row_states` 键为结果中的绝对路径，值仅 `{'checked': bool, 'status': str}`。角色来自核心分组，不能由导入状态反过来改变；只有合法待回收目标可勾选。
- 保存使用同目录临时文件、flush/fsync 后 `os.replace`。替换失败保留旧目标并清理临时文件。输入有 64 MiB 文件上限及集合/文本边界。
- 路径允许已经删除，供历史展示；现存链接仍按真实路径检查根归属，不能退回词法路径放行无法确认的解析。
- GUI 导出使用扫描时的根/选项快照和最新处理状态，不能读取后来改过的目录输入框冒充原扫描参数。导入标记 `_record_imported=True`，回收强制 `byte_verify=True`；取消、失效记录不可回收。

### 目录内去重重选 keeper（schema v1 不变）

- 新 keeper 关系直接保存在更新后的 `result.groups`，不增加平行角色字段、不升级 schema；旧 v1 记录仍按原 validator 读取。类型分类/当前筛选是展示派生值，不必写入记录。
- 页面必须先同步实际 group 和所有同组行的角色/keeper 引用，再按绝对路径生成 `row_states`：新 keeper 为 `status_keep`、未勾选；旧 keeper 转为 `status_pending` 目标并默认勾选；其它目标保留原合法勾选状态。只改表格文案不会改变记录角色，属于错误实现。
- `row_states` 不能反过来授权 keeper 变 target；已处理组不许通过重选变回 pending，导入仍强制逐字节复核。目录比对模式的 A/B 约束不变，不能借 internal 功能放宽 compare 角色验证。
- 兼容边界包括既有合法 internal 单 keeper 组（`duplicates=[]`）：记录 validator 已允许，展示分类不得因无副本抛错或使整份旧记录导入失败；它没有可切换目标，也不能获得回收资格。

## 4. 校验与错误矩阵

| 条件 | 处理 |
|---|---|
| 错误版本、expected_mode 不匹配、布尔冒充整数 | `ValueError`，当前显示不变 |
| 相同/嵌套 A/B 根、越界路径、错误 keeper/target 角色 | 整份拒绝 |
| 重复 target、keeper/target 相交、未知状态行 | 整份拒绝 |
| 非 pending 目标或非目标行声称 checked | 不能变成可回收目标 |
| 记录中的路径已被删除 | 可展示历史，实际回收时跳过 |
| 文件修改，甚至大小/mtime 相同 | 导入后的逐字节重验返回 `content_differs`，不调用 send2trash |
| 保存途中写入/替换失败 | 旧记录完整保留，错误交给 UI 提示 |

## 5. 正常、基线与异常示例

- 正常：compare 中 A 有一份、B 有多份，往返后全部 B 副本、指纹和 pending 勾选仍对应原分组。
- 基线：空扫描结果可保存、已回收行可恢复为只读历史，stale/cancelled 标记不丢失。
- 异常：把某个 keeper 在 row_states 中改成 pending，不能获得回收资格；坏记录不得先清空原表再报错。

## 6. 必需测试

`tests/test_scan_record_core.py`：两模式往返、严格类型/版本/模式、根路径和链接越界、错误角色、重复目标、keeper/target 相交、JSON 重复键/非法数字/大小、原子保存失败保留旧记录、stale、已删除历史，以及导入后修改/删除文件不触发回收。

页面测试应从按钮启动异步导入/导出，验证坏导入保留结果、扫描快照与编辑控件隔离、导入强制逐字节、取消/失效记录锁定；记录线程必须进入忙状态和独立/内嵌关闭协议。
目录内重选后须以真实按钮导出/导入验证新 keeper、旧 keeper 的目标资格、其它副本逐路径 checked/status；真实回收 worker 必须收到新 keeper 和 imported 强制 `byte_verify=True`。保留旧 v1（含无副本 keeper 组）导入用例，不可用收紧格式或新增 skip 绕过兼容回归。

## 7. 错误与正确写法

```python
# 错：信任导入状态，直接回收路径。
send2trash(imported_path)

# 对：行角色来自受校验结果，执行仍走共用核心并强制完整复核。
record = load_record(path, expected_mode='compare')
outcome = recycle_duplicate(target, keeper, byte_verify=True)
```
