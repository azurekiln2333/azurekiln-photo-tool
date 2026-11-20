# v1.2.4 从 main 发布记录

日期：2026-11-21（Asia/Shanghai）。工作提交：b0d4335d8e6a291ffa79ab097fd2ccc70dc26f97。

## 分支整合与修复

- 首次 cdf4176 在 tag CI 成功、branch CI 失败；未将偶发通过当作完成。独立复现定位测试先于真实 UI drain 读取行，pA 使用真实 timer 信号门禁加强回归，未改产品安全逻辑、未删原断言。
- 完整环境201项通过，无skip；C盘TEMP/无外部工具201项，0失败/错误，3个既有ffmpeg样片skip。
- main 从2f8b006完整fast-forward至b0d4335，包含三个现有子分支及其完整依赖链；本地/远端main和feature均已核对。分支未删除，无force/reset/cherry-pick。
- main CI 44836184819、feature CI 44836184833：均completed/success，含测试、版本、PyInstaller、bundle验证、便携包/安装包及上传。分支CI的Release步骤按设计跳过。
- 新annotated v1.2.4从main的b0d4335创建并推送，peeled commit一致。已存在v1.2.3保持原样。

## 正式发布

tag run44836626184已completed/success；测试、版本、bundle自检、portable/installer、上传及Publish GitHub Release均success。Release id453280760，tag=v1.2.4，published_at=2026-11-20T23:27:25Z（北京时间2026-11-21 07:27:25）。

三资产均uploaded且非零：

| 资产后缀（共同前缀AzureKilnPhotoTool-1.2.4-20261120-windows-x64） | 字节数 |
| --- | ---: |
| -portable.zip | 84,214,797 |
| -portable.sha256.txt | 90 |
| -setup.exe | 86,067,198 |

文件名日期来自CI的UTC日期，不是本地发布日。完整API证据见v124-release-assets.json、v124-tag-final-status.json和v124-tag-ci-jobs.json。

pB已完成真实下载核验：ZIP、checksum文本、setup大小与SHA-256均匹配GitHub API；ZIP完整性通过，包内EXE哈希匹配checksum，包内/包外checksum逐字节一致。未执行下载EXE，未声称安装/真实OneDrive端到端已验证。完整证据见pi-release-verification.md。root另外GET releases/latest确认最新正式版本为v1.2.4（同Release id453280760）。
