# 最终交付：v1.2.2

修复提交为`239874b`，CI环境修正提交为`55ed8fb`和`a594841`；最终annotated tag `v1.2.2`指向`a594841fe4a24c9b1b65fd76b0726e4aa9119470`，已推送。首次`v1.2.1`因CI测试隐式外部依赖挂起而取消构建，原tag保留不覆盖。

## 功能与安全验收

- A/B等宽预览、长路径任意换行、可拖分隔条、内部纵向滚动；独立/内嵌、中/英四组合真实Qt布局探针通过并检查截图。
- 两页全选/全不选/反选与Ctrl+A，仅合法待回收副本可选；取消/失效结果受保护。
- 异步JSON扫描记录导出/导入，版本/路径归属/角色/重复目标/保留项交集严格校验，原子保存；坏导入保留当前结果，使用扫描时根与选项快照。
- 导入历史后回收强制逐字节复核；修改（同大小同mtime）或删除目标均被跳过。模拟同大小同哈希而内容不同的真实BMP，重复组被拒绝、回收零调用；这是模拟碰撞，不是发现真实SHA256碰撞。
- 视频Shell失败后的QtMultimedia首帧回退、超时/有限重试/失败提示；本地真实H.264/HEVC后台解码验证通过，发布包QtMultimedia/QtNetwork与FFmpeg依赖检查通过。
- 记录/扫描/回收直到finished清理前保持忙态；统一窗口等待后台保存收尾，关闭与DeferredDelete无槽异常。

## 测试与发布证据

本地正常全量183项通过；实际C盘TEMP/D盘repo、无ExifTool/ffmpeg PATH、隔离APPDATA/LOCALAPPDATA的CI复验共183项，0失败、0错误、3项既有ffmpeg样片生成条件跳过，7.720秒，cwd恢复且临时目录清理。CI两处fixture环境问题均按真实日志修正，未跳过测试或放宽断言；独立复核PASS。

分支Actions run `44808199635`及标签发布run `44808571694`均success。正式Release id`453134507`，三类资产齐全且uploaded：便携ZIP、SHA256文本、setup安装包。Pi真实下载的ZIP哈希与GitHub digest一致，包内EXE哈希与发布校验文本一致，包内外校验文本逐字节一致；具体命令、资产大小与完整摘要见`pi-remote-release-report.md`，API读回见`release-ci-status.json`、`release-tag-status.json`和`release-assets.json`。

## 未声称验证的边界

真实OneDrive仅联机/按需下载视频未做端到端实测；未运行或安装发布EXE/安装包。所有回收测试使用临时样例与mock，没有回收真实用户媒体。无已配置静态类型检查器，compileall不代称类型检查。
