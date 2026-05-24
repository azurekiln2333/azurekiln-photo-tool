# Web 版本上下文记录

本文记录本次为项目增加 Web 版本时的重要决策、当前实现状态和后续维护注意点，方便之后继续开发时快速恢复上下文。

## 背景

当前项目的 `unified_gui.py` 已经是较完整的 PyQt6 / Fluent 桌面统一入口。它本质上是一个桌面容器，内部嵌入三个已有窗口：

- `merge_live_photo_gui.py`：LivePhoto 合并
- `split_huawei_live_photo_gui.py`：华为 LivePhoto 拆分
- `main_gui.py`：Flyme LivePhoto 修复

这些 GUI 文件不适合直接搬到浏览器里运行，因为它们依赖 PyQt 窗口、控件、线程和本地目录选择器。Web 版应该复用核心处理逻辑，而不是复用桌面 GUI。

## 仓库组织决策

当前不建议 Windows 桌面版和 Web 版分仓库。

原因：

- 桌面版和 Web 版都依赖同一批核心处理逻辑。
- 分仓库会导致修 bug、改算法、更新兼容规则时需要双端同步。
- 当前 Web 版仍是本项目的另一种入口，不是独立产品或独立服务。

推荐继续使用单仓库：

```text
LivePhotosSpilt/
  unified_gui.py
  main_gui.py
  merge_live_photo_gui.py
  split_huawei_live_photo_gui.py

  merge_live_photo.py
  split_huawei_live_photo.py
  flyme_livephoto_fix_core.py
  main_gui_logic.py

  web/
    server.py
    static/
    README.md
```

未来如果 Web 版变成长期线上服务，有独立 Docker、CI/CD、域名、用户系统，或者核心逻辑被抽成单独 Python 包，再考虑分仓库。

## Web 版实现位置

新增目录：

```text
web/
  server.py
  README.md
  .gitignore
  static/
    index.html
    styles.css
    app.js
    README.md
```

`web/.gitignore` 已排除：

```text
.jobs/
```

`.jobs/` 是 Web 服务运行时的上传缓存、处理输出和下载 ZIP 目录，不应提交。

## Web 版架构

Web 版采用 Python 标准库 `http.server` 实现，没有新增 Flask/FastAPI 等额外后端依赖。

启动入口：

```powershell
python .\web\server.py
```

默认地址：

```text
http://127.0.0.1:8765
```

可通过环境变量指定监听地址和端口：

```powershell
$env:AZUREKILN_WEB_HOST="127.0.0.1"
$env:AZUREKILN_WEB_PORT="9000"
python .\web\server.py
```

Linux 示例：

```bash
export AZUREKILN_WEB_HOST=127.0.0.1
export AZUREKILN_WEB_PORT=8765
python web/server.py
```

## 浏览器工作流限制

桌面 GUI 可以直接读写用户选择的本地目录。浏览器出于安全限制，不能随意写用户电脑上的任意路径。

因此 Web 版采用：

```text
上传文件 -> 本地 Python 后端处理 -> 下载 ZIP 结果
```

这和桌面版的目录输入/目录输出不同，但更符合浏览器安全模型，也方便以后部署到 Linux 服务器。

## 当前 Web 功能

Web 首页是单页工具，三个标签页对应：

- LivePhoto 合并
- 华为 LivePhoto 拆分
- Flyme LivePhoto 修复

### LivePhoto 合并

前端上传同名文件：

```text
IMG_001.jpg
IMG_001.mp4
```

后端按 stem 匹配同名图片和视频，调用：

```python
merge_live_photo.make_live_photo()
```

输出 Motion Photo JPG，并打包 ZIP 下载。

当前支持上传扩展名：

```text
.jpg .jpeg .mp4 .mov
```

注意：当前后端实际复用的是 `merge_live_photo.py`，它主要按 JPG/JPEG 处理。桌面 GUI 中更完整的 HEIC/HEIF 逻辑在 `merge_live_photo_gui.py`，后续如需 Web 支持 HEIC，应把 GUI 中的非界面处理逻辑进一步抽到共享 core。

### 华为 LivePhoto 拆分

上传华为内嵌 LivePhoto JPG/JPEG，后端调用：

```python
split_huawei_live_photo.is_huawei_live_photo()
split_huawei_live_photo.split_live_photo()
```

输出：

```text
原名.jpg
原名.mp4
```

并打包 ZIP 下载。

### Flyme LivePhoto 修复

上传 Flyme LivePhoto JPG/JPEG，后端调用：

```python
flyme_livephoto_fix_core.check_photo_type()
flyme_livephoto_fix_core.LivePhotoFixTool.fix_photo()
```

输出修复后的 JPG，并打包 ZIP 下载。

Flyme 修复依赖 ExifTool；合并和华为拆分不依赖 ExifTool。

## ExifTool 跨平台处理

之前核心逻辑偏 Windows，只优先找 `exiftool.exe`。这对 Linux 服务器不合适。

已修改 `flyme_livephoto_fix_core.py` 的查找逻辑，顺序包括：

1. `EXIFTOOL_PATH` 环境变量
2. PyInstaller 打包目录中的 `exiftool.exe`
3. PyInstaller 打包目录中的 `exiftool`
4. 项目内 `vendor/exiftool/exiftool.exe`
5. 项目内 `vendor/exiftool/exiftool`
6. 项目内 `exiftool/exiftool.exe`
7. 项目内 `exiftool/exiftool`
8. 项目内 `bin/exiftool.exe`
9. 项目内 `bin/exiftool`
10. 系统 PATH 中的 `exiftool`

Linux 上安装 ExifTool 示例：

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y libimage-exiftool-perl

# Fedora / RHEL
sudo dnf install -y perl-Image-ExifTool

# Arch Linux
sudo pacman -S perl-image-exiftool
```

验证：

```bash
exiftool -ver
```

如果 ExifTool 不在 PATH：

```bash
export EXIFTOOL_PATH=/opt/exiftool/exiftool
python web/server.py
```

## 安全和部署注意点

当前 Web 服务适合作为本地工具或受控内网工具。

已经做的基础防护：

- 上传处理使用独立 job 目录。
- 输出结果打包为 ZIP。
- 静态文件和 ZIP 下载路径做了目录边界校验，避免基础路径穿越。
- 上传大小默认限制为 `MAX_UPLOAD_BYTES = 1024 * 1024 * 1024`。
- `.jobs/` 旧任务会按 TTL 清理，当前 `JOB_TTL_SECONDS = 12 * 60 * 60`。

如果部署到公网，需要继续补：

- 用户认证
- HTTPS
- 反向代理上传大小限制
- 更严格的文件类型和内容校验
- 后台任务队列
- 并发和资源限制
- 定期清理任务
- 日志和错误追踪

## 已做验证

执行过语法检查：

```powershell
.\.venv\Scripts\python.exe -m py_compile .\flyme_livephoto_fix_core.py .\web\server.py
node --check .\web\static\app.js
```

用 sample 验证过华为拆分链路：

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from web.server import UploadFile, MultipartData, _process_request; p=Path('sample/HarmonyOS4/Source/IMG_20260515_230101.jpg'); r=_process_request(MultipartData(fields={'mode':'split'}, files=[UploadFile('files', p.name, p.read_bytes())])); print(r['ok'], r['summary'], r['zip'])"
```

结果摘要：

```text
True {'mode': 'split', 'split': 1, 'failed': 0, 'skipped': 0, 'uploaded': 1}
ZIP preview: IMG_20260515_230101.jpg, IMG_20260515_230101.mp4
```

用 sample 验证过合并链路：

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from web.server import UploadFile, MultipartData, _process_request; files=[]; paths=[Path('sample/HarmonyOS4/SplitOutput/IMG_20260515_230101.jpg'), Path('sample/HarmonyOS4/SplitOutput/IMG_20260515_230101.mp4')]; [files.append(UploadFile('files', p.name, p.read_bytes())) for p in paths]; r=_process_request(MultipartData(fields={'mode':'merge'}, files=files)); print(r['ok'], r['summary'], r['zip'])"
```

结果摘要：

```text
True {'mode': 'merge', 'merged': 1, 'failed': 0, 'skipped': 0, 'uploaded': 2}
ZIP preview: IMG_20260515_230101.jpg
```

启动服务并访问首页验证过：

```powershell
$env:AZUREKILN_WEB_PORT='8765'
python .\web\server.py
```

首页返回 HTTP 200。

## 当前未覆盖或待改进

- Web 版未完整复刻桌面 GUI 的所有选项，例如复杂的冲突策略、目录递归扫描、分类导出等。
- 浏览器目前以文件上传为主，没有目录上传的完整相对路径保留逻辑。
- HEIC/HEIF 合并支持需要进一步从 `merge_live_photo_gui.py` 抽离到共享 core。
- Flyme 修复链路尚未用真实 Flyme 样本在 Web 后端跑完整验证。
- 当前 Web 后端适合本地使用；公网部署需要认证、反代和资源限制。

## 后续建议

短期：

1. 继续保持单仓库。
2. 把 Web 版当作新的入口维护在 `web/`。
3. 为 `web/server.py` 增加更系统的单元测试。
4. 补一个 Linux 部署脚本或 Dockerfile。

中期：

1. 新建 `core/` 或 `azurekiln_photo_core/`。
2. 把三个功能的纯处理逻辑从 GUI 文件中抽出来。
3. 桌面 GUI 和 Web 后端都只调用 core。

长期：

1. 如果 Web 版变成独立服务，再考虑分仓库。
2. 可以把 core 发布为内部 Python 包，桌面仓库和 Web 仓库都依赖它。
