# 多语言文案约定

> 全应用中英双语。这里的规则**必须**遵守，否则界面会显示原始 key。

---

## 翻译机制

每个功能页有独立翻译模块或内联字典：

| 页面 | 翻译来源 |
|------|----------|
| LivePhoto 合并 | `merge_live_photo_translations.py`（`DEFAULT_LANGUAGE` / `SUPPORTED_LANGUAGES` / `TRANSLATIONS`）+ `merge_live_photo_gui.py` 内联 `EXTRA_TRANSLATIONS` |
| 华为分离 | `split_huawei_live_photo_translations.py` + 页面内联 `EXTRA_TRANSLATIONS` |
| 其他页 | 各页文件内联 `TRANSLATIONS` 字典 |
| 统一 GUI | `unified_gui.py` 内联 `TRANSLATIONS` |
| 共用 | `ui_translations.py` |

结构统一为：

```python
DEFAULT_LANGUAGE = "zh"
TRANSLATIONS = {
    "zh": { "some_key": "中文文案", ... },
    "en": { "some_key": "English text", ... },
}
SUPPORTED_LANGUAGES = frozenset(TRANSLATIONS)
```

---

## 取值：`self.tr(key, **kwargs)`

```python
def tr(self, key: str, **kwargs) -> str:
    text = EXTRA_TRANSLATIONS.get(self.lang, {}).get(
        key,
        TRANSLATIONS.get(self.lang, TRANSLATIONS["zh"]).get(key, key),   # 找不到就返回 key 本身
    )
    return text.format(**kwargs) if kwargs else text
```

- **查找顺序**：`EXTRA_TRANSLATIONS` 优先，再回退主 `TRANSLATIONS`。
- 找不到键时**返回 key 原文**（所以界面会显示 `some_key` —— 这是漏配翻译的明显信号）。
- 支持 `{name}` 占位：`self.tr("drop_added", added=3, count=10)`。

---

## 硬性规则

### 1. 新增文案必须补 zh + en 两个键

否则界面直接显示原始 key。这是本项目最常见的问题。

### 2. kebab/下划线风格：`snake_case`

```python
"drop_added": "已拖拽添加 {added} 个文件，当前共 {count} 项",   # ✅
"dropAdded": ...                                              # ❌
```

### 3. 语言切换要刷新

每页有 `_on_language_changed` → `_apply_language()`：

```python
def _apply_language(self):
    self.setWindowTitle(self.tr("app_title"))
    self.title_label.setText(self.tr("header_title"))
    ...
    self.elevation_hint.set_language(self.lang)    # 新控件也要刷新
```

**新增任何带文案的控件，都要在 `_apply_language()` 里补一行刷新。**

### 4. 统一 GUI 的语言由 settings 页驱动

`unified_gui.py` 的 settings 页遍历所有功能页，调用其 `_apply_language`：

```python
def _apply_feature_language(self, feature_window, lang):
    feature_window.lang = lang
    combo = getattr(feature_window, "language_combo", None)
    if combo:  # 同步下拉框，但 blockSignals 防重入
        combo.blockSignals(True)
        ...
    apply_language = getattr(feature_window, "_apply_language", None)
    if callable(apply_language):
        apply_language()
```

功能页嵌入后，语言由统一 GUI 控制，页面自己的语言下拉会被隐藏（`if not self._embedded`）。

### 5. 动态状态也走翻译

处理行的状态用 `|` 分隔错误详情：

```python
"status_merge_failed|<error>"  ->  self.tr("status_merge_failed", error=<error>)
```

`_display_status()` 负责识别前缀并翻译。

---

## 主题 / 语言常量

- 默认语言：`zh`。
- 支持语言：`frozenset(TRANSLATIONS)` → 目前 `{"zh", "en"}`。
- 设置持久化在 `%APPDATA%\<APP_NAME>\settings.json` 的 `language` 字段。

---

## 禁止事项

- ❌ 新增文案只写中文不写英文（或反之）。
- ❌ 在控件里硬编码文案，绕过 `self.tr()`。
- ❌ 新增带文案的控件但忘了在 `_apply_language()` 刷新。
- ❌ 用不存在的键（会直接显示 key），提交前搜索确认。
