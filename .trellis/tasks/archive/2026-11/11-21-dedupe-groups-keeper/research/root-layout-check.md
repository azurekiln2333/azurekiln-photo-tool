# Root 布局与核心基线验证

- 当前核心原有定向回归：`unittest discover -s tests -p test_duplicate_scan_core.py -q`，81 tests，OK，exit 0。新增 helper 的专项测试仍由 p4 补充，不能把此结果当作全部新增覆盖。
- 使用临时目录真实三副本 JPG、视频/其他占位组构造结果；没有触碰真实相册、没有执行回收。
- 当前 offscreen 环境 `QFontDatabase.families()` 为 0。初次截图文字方框不构成有效文字布局证据；随后仅在 QA 进程注册 Windows `C:/Windows/Fonts/msyh.ttc`，使用 Microsoft YaHei UI 9pt 重测，未修改产品字体。
- 独立/EmbeddedPage × zh/en 共四种 1360×880 布局：三个分类按钮、全选、取消、反选、设为保留全部可见且几何位于页面内；所选 pending 副本的设为保留按钮 enabled。关闭并处理 DeferredDelete 后 Qt 槽异常为 0，进程 exit 0。
- 已实际查看独立中文、内嵌英文的渲染图：三类数量各 1 组/3 文件，底部批量按钮清晰，右侧两槽等宽，长路径换行，没有新增控件遮挡。
- 临时截图目录：`D:/AppData/Local/Temp/dedupe-ui-qa-kk26h7g1/`，有效图为 `standalone-zh-fonts.png`、`standalone-en-fonts.png`、`embedded-zh-fonts.png`、`embedded-en-fonts.png`。不提交临时媒体/图片。
- 本证据针对布局和既有核心基线；新 keeper 实际 worker、记录往返和全量结果以后续最终测试为准。
