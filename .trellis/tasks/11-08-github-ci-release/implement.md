# Implement Plan

## Checklist

1. [ ] `requirements.txt` / `requirements-build.txt`（版本取自本地 `.venv` pip freeze，仅保留实际用到的包）
2. [ ] `.gitignore` 放行 `AzureKilnPhotoTool_onefile.spec`；spec 加 CI 下 ExifTool 缺失即失败
3. [ ] `scripts/ci/`：`get_version.py`（读 APP_VERSION / 校验 tag）、`verify_bundle.py`（自检）、`package_portable.py`（zip+sha256）
4. [ ] `installer/AzureKilnPhotoTool.iss`（新 AppId GUID）
5. [ ] `.github/workflows/build.yml`（下载 ExifTool 并固定 SHA256——实现时下载一次计算）
6. [ ] `unified_gui.py` `APP_VERSION = "1.1.0"`
7. [ ] README ×3 打包章节 + `.trellis/spec/python/packaging.md`

## Local Validation

- `.venv/Scripts/python.exe scripts/ci/get_version.py` → `1.1.0`；用 `v1.0.9` 模拟 tag 校验应失败。
- 本地 `.venv` 跑 PyInstaller，再跑 `verify_bundle.py` 与 `package_portable.py`，核对命名与 sha256 格式（90 字节）。
- 若本地装有 Inno Setup 则编译一次 `.iss`；否则依赖 CI 验证。
- `actionlint`（若可用）或人工审 workflow YAML。

## Remote Validation（需用户确认后才执行，属对外操作）

1. commit → push 到分支 → 观察 Actions 构建通过、artifact 可下载。
2. 用户确认后打 `v1.1.0` tag 并 push → 检查 Release 内容、哈希。
3. 下载 Release exe 打开一张 HEIC 验证。

## Rollback Points

- 步骤 1–7 均为新增/小改，`git revert` 即可。
- 错误 Release：删除 Release + 远端 tag 后重推。
