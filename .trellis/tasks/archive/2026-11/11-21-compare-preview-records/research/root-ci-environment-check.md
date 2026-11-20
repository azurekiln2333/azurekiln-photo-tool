# CI 无外部工具环境复验

PATH仅含Windows系统目录，EXIFTOOL_DIR/EXIFTOOL_PATH移除，flyme引擎的resolve_exiftool强制返回None；Qt offscreen，APPDATA/LOCALAPPDATA临时隔离。真实测试发现与执行，40秒faulthandler兜底未触发。

CI-like environment: tests=183, failures=0, errors=0, skipped=3, successful=True

3项跳过来自既有ffmpeg生成样片的条件，保持与无ffmpeg的CI一致；不跳过统一窗口关闭测试，不放宽任何原关闭断言。
