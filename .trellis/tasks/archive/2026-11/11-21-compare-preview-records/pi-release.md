Active task: .trellis/tasks/11-21-compare-preview-records

你是实际 Pi CLI trellis-implement 发布集成worker。先读 implement.jsonl、prd/design/implement、python packaging spec 与 trellis-before-dev。

所有权仅 AzureKilnPhotoTool_onefile.spec、.github/workflows/build.yml、scripts/ci/verify_bundle.py、README.md、docs/README.en.md、docs/README.zh-TW.md，及任务 research/pi-release-report.md、research/integration_*.py。另三个Pi同工作区，别回滚覆盖别人代码。禁止commit/push/tag/branch/release，最终主会话操作。

先核对PyQt6.QtMultimedia和Qt FFmpeg插件/依赖当前是否会正确打包，preview worker稍后写 research/video-packaging-contract.md。保证发布包本身有视频首帧回退能力，不可只靠本机PATH。最小调整spec及产物自检（需要时加backend binary/plugin检查），避免无必要下载庞大外部ffmpeg。与preview通过任务文件协调；若依赖不清，先写文档/验证脚本继续独立工作，不频繁等待。CI需要有意义的测试门禁但不引入新测试框架或依赖；GUI测试需隔离APPDATA并设置QT_QPA_PLATFORM=offscreen。

README三语同步本轮等宽可拖预览、全选反选、JSON记录导入导出及历史复核、视频失败重试等真实行为。可新增任务research集成检查脚本，先不抢占其他worker测试文件。发布版本主会话设置1.2.1。验证用.venv，禁止PyInstaller --clean。不碰真相册，报告已完成与未验证边界。
