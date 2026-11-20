# Root 真实按钮/线程链路验证

独立临时目录 `D:/AppData/Local/Temp/dedupe-root-flow-iyx_wx6n`，offscreen，隔离 APPDATA/LOCALAPPDATA，标准 unittest.mock；退出码 0，Qt 槽异常 0。

1. 照片/视频/其他各写 a/b/c 三副本；点击扫描按钮，等待真实扫描 QThread finished、busy 清空，得到 3 组。
2. 分别点三类按钮和“全不选”，再进入照片选 B，真实点击“设为保留”：B keeper/unchecked，A duplicate/pending/checked。
3. 真实点击导出按钮（仅文件选择器替身），等待记录线程结束；再真实点击导入，等待线程结束。新的 keeper B 正确保留，`_record_imported=True`。
4. 主动取消 UI 的 byte_verify 选项，点击回收按钮；仅确认对话框替身返回 Yes，`recycle_duplicate` 使用 wraps 调实际共用核心，只有 `send2trash` mock。
5. 真实回收线程仅处理照片 A，所有参数确认 keeper=B、byte_verify=True；send2trash 恰调用 1 次且目标是 A，未触碰 B。所有媒体均为临时测试字节。
6. 正常关闭、DeferredDelete 后无 Qt 异常。记录保存在上述临时目录的 record.json，不提交媒体或临时配置。

此为 root 的独立集成验证，不代替 pA 的持久化回归套件和最终全量结果。
