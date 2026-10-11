# 日志约定

> 记录本项目**实际的**日志现状。

---

## 现状：没有结构化日志框架

本项目**没有** `logging` 模块配置、没有日志文件、没有日志级别。
这是桌面 GUI 工具的现状，不要为了「规范」而引入日志框架（会增加打包体积与复杂度）。

错误信息的实际呈现渠道有 3 种：

### 1. 用户可见的状态栏 / 提示条（主要渠道）

```python
# 状态栏文本，走翻译键
self.status.setText(self.tr(key, **kwargs))

# 右下角 InfoBar 提示（成功/错误）
self._notify(title, content, is_error=True)   # -> InfoBar.error(...)
self._notify(title, content)                  # -> InfoBar.success(...)
```

- 面向用户的反馈一律走 `InfoBar` 或页面内嵌提示。
- 文案必须走翻译键（zh/en），不要硬编码中文串。

### 2. 每行的处理状态（批处理结果）

处理结果记录在 `file_list` 每项的 `status` 字段，格式约定：

- `status_static_failed|<error>` / `status_merge_failed|<error>` / `status_other_failed|<error>`
- 用 `|` 分隔「状态键」与「错误详情」，展示前经 `_display_status()` 翻译。

### 3. stderr（开发期排查）

PyQt 事件处理里的未捕获异常只会打到 stderr，窗口里看不到。
因此**不要把关键错误只留给 stderr**——那会导致「静默失效」。

---

## 约定

- 面向用户的错误 → `_notify(..., is_error=True)` + 中文可操作提示。
- 批处理单文件失败 → 写入该行 `status`，继续处理下一个。
- 开发调试信息：临时用 `print()` 即可，**提交前删除**。
- 不要新增 `logging` 配置；若未来确需落盘日志，属于架构变更，另开任务讨论。

---

## 禁止事项

- ❌ 不要用 `print()` 输出面向用户的信息。
- ❌ 不要让用户只能通过 stderr 发现错误。
- ❌ 不要在没有翻译键的情况下直接显示原始 `status_*`（除错误详情本身）。
