# 错误处理约定

> 记录本项目**实际的**异常处理方式。

---

## 核心原则：尽力读取，失败降级为 None

这是一个批处理媒体工具。单个文件的元数据读取失败**不应该中断整批处理**。
因此「读取类」函数统一采用**宽泛捕获 + 返回中性值**：

```python
# timestamp_fix_gui.py — 典型「读取降级」模式
try:
    ...
    return ts
except Exception:
    return None
```

```python
# timestamp_fix_gui.py — 窄捕获时也只返回中性值
def _is_placeholder_timestamp(timestamp: float | None) -> bool:
    if timestamp is None:
        return True
    try:
        dt = datetime.fromtimestamp(timestamp)
    except (OSError, OverflowError, ValueError):
        return True
    return (dt.year, ...) in PLACEHOLDER_EXIF_TIMES
```

**约定：**
- 读取/解析工具函数：捕获异常后返回 `None`（或 `False` / 空容器），**不向外抛**。
- 可以窄捕获时优先窄捕获（`(OSError, OverflowError, ValueError)`），
  但**媒体元数据解析**这类「格式千奇百怪」的场景允许直接 `except Exception`。
- 返回 `None` 表示「读不到 / 不可信」，调用方必须能处理 `None`。

---

## 环境缺失：明确抛错，且带可操作提示

当依赖的外部工具（ExifTool / ffprobe）找不到了，属于**环境错误**，此时明确抛出，
并给出「怎么修」的中文提示：

```python
# flyme_livephoto_fix_core.py
def _check_exiftool(self):
    try:
        self._run_exiftool(['-ver'])
    except Exception:
        raise FileNotFoundError(
            "未找到 exiftool！请确保 exiftool/exiftool.exe 在当前目录、"
            "EXIFTOOL_DIR、EXIFTOOL_PATH 或系统 PATH 中。"
        )
```

```python
# exiftool_resolver.py — 找不到新依赖时明确说明是环境问题
raise ImportError("qfluentwidgets is not installed.") from last_exc
```

**约定：**
- 环境/依赖缺失 → 抛异常，异常信息用**中文**、说明「需要什么」+「怎么解决」。
- 用 `raise ... from last_exc` 保留原始异常链，便于排查。

---

## GUI 线程边界：绝不让异常穿透到 Qt 事件循环

- 后台 worker（`QThread` + `*Worker(QObject)`）内部处理单个任务时用 try/except 包住，
  把失败记录成该行的状态（如 `status_static_failed|...`），而不是让线程崩掉。
- `eventFilter` / 事件处理函数里出错会被 PyQt 吞掉（只在 stderr 打印），导致「静默失效」。
  因此事件处理**必须保持简单**，复杂逻辑交给 worker，并显式检查守卫条件
  （例如 `_is_busy()`），必要时给用户提示而不是静默 return。

---

## 配置读写：静默失败即可

设置持久化（`%APPDATA%\<APP_NAME>\settings.json`）失败不影响功能，直接忽略：

```python
def _save_global_settings(self):
    try:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(json.dumps(...), encoding="utf-8")
    except Exception:
        pass
```

---

## 禁止事项

- ❌ 不要用裸 `except:`（无类型），一律 `except Exception:`。
- ❌ 不要在读取类函数里把异常往上抛，让整批处理中断。
- ❌ 不要吞掉异常后**静默改变用户可见状态**（如「拖拽没反应」）——要么不吞，要么给提示。
- ❌ 不要在环境缺失时返回 `None` 假装成功；那属于必须让用户知道的错误。
