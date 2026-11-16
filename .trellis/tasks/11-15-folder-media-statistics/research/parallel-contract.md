# 四个 Pi 的文件所有权与固定接口

用户已批准实施并明确要求 4 个 Pi 同工作区并行。除主会话之外只启动以下四个 Pi，均使用本机默认模型配置；不建立 worktree、不互相回退编辑、不提交代码。

## 所有权

- pi-scan：media_statistics_core.py，research/pi-scan-report.md。
- pi-readme：media_readme_core.py，research/pi-readme-report.md。
- pi-gui：media_statistics_gui.py，research/pi-gui-report.md。
- pi-integrate：unified_gui.py、README.md、docs/README.en.md、docs/README.zh-TW.md，research/pi-integrate-report.md；静态 import 正常则不改 spec。
- 主会话：任务文档、最终规格更新、联调验证、提交收尾；接口改变必须先协调。

## media_statistics_core.py 公共接口

标准库模块，不导入 Qt。dataclass 字段如下（额外内部字段可以增加，以下字段须保持）：

```python
@dataclass(frozen=True)
class ScanIssue:
    path: Path
    message: str

@dataclass(frozen=True)
class FolderSnapshot:
    path: Path
    parent_path: Path | None
    name: str
    direct_image_count: int
    direct_video_count: int
    image_count: int
    video_count: int
    complete: bool
    issue_count: int
    # total 属性 = image_count + video_count

@dataclass(frozen=True)
class ScanOutcome:
    root: Path
    folders: tuple[FolderSnapshot, ...]
    errors: tuple[ScanIssue, ...]
    cancelled: bool
    # complete 属性 = not cancelled and not errors（所有目录枚举成功）

def scan_folders(root: Path, image_suffixes, video_suffixes, *,
                 stop_event=None, on_batch=None) -> ScanOutcome: ...
```

on_batch(list[FolderSnapshot]) 传递绝对快照，可先发父节点再发更新，按路径更新不可累加旧通知。结果 folders 含根及全部已发现目录，确保父节点可先插入。目录异常不外抛，返回 partial + errors。扩展名由 GUI 从 timestamp_fix_gui 导入后传入。

## media_readme_core.py 公共接口

```python
MAX_README_BYTES = 2 * 1024 * 1024

@dataclass(frozen=True)
class ReadmeDocument:
    path: Path
    text: str
    encoding: str
    bom: bytes
    newline: str
    baseline: bytes
    mtime_ns: int

@dataclass(frozen=True)
class ReadmeResult:
    status: str  # ready/missing/too_large/error/conflict/saved
    document: ReadmeDocument | None = None
    error: str = ""
    path: Path | None = None

def load_readme(directory: Path) -> ReadmeResult: ...
def save_readme(document: ReadmeDocument, text: str) -> ReadmeResult: ...
```

返回状态须遵守以上名称，成功保存返回新 document。不新增不存在的 readme；只读/错误/冲突不写原文件。UTF-8/UTF-8 BOM/UTF-16 BOM/GB18030 严格编码，保留换行，临时文件+替换。无需读取真实用户说明来测试。

## media_statistics_gui.py 对统一入口和验证的接口

```python
class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False): ...
    def _apply_language(self): ...  # 同现有页面，使用 self.lang
    def set_root_folder(self, path: str | Path): ...  # 经草稿守卫后设置根并开始扫描
    def scan_files(self): ...
    def request_close(self, on_ready) -> bool: ...
```

同时保留 lang、language_combo、tree（Fluent TreeView）、readme_edit（PlainTextEdit）、btn_save 属性，便于集成验证。

request_close 返回 True 表示现在可安全退出；否则显示草稿决策/等待后台清理，最终调用 on_ready。每次调用须幂等，不能重复开启保存。独立 closeEvent 与统一 closeEvent 均使用同一接口；统一窗口返回 False 时切换到媒体统计页以展示草稿提示，再 event.ignore()。不要在 Qt 主线程阻塞等待工作线程。

统一入口保存 self.media_statistics_window 与 self.media_statistics_page，新增路由名 media_statistics；保留原六页功能设置（只让其读取前六个窗口即可），语言覆盖七页。实际接入保持 `_feature_windows` 为原六页，统计页单独保存，显式同步语言并参与统一窗口关闭协调。

## 验证与工作方法

各 Pi 先读 PRD/design/implement、implement.jsonl 引用的相关规范及本契约，再直接实现；无需重新建任务或征求权限，不再派子代理。实现与局部验证完成后写各自 research/pi-*-report.md，并结束进程。主会话按进程结束/退出状态判定完成，随后协调交叉检查。

使用 .venv/Scripts/python.exe；GUI 测试先隔离 APPDATA 和 QT_QPA_PLATFORM=offscreen；不新增测试框架。临时行为测试可用标准库 unittest.mock/assertions。禁止更改真实 OneDrive 媒体或说明文件，禁止 git commit/push/merge。
