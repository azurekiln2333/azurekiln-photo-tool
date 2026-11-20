# v1.2.4 远端发布与真实下载核验

## 结论

**PASS：main / feature / tag CI 均 success，v1.2.4 三资产完整，真实下载与哈希核验一致。**
本批仅认证 REST GET、下载/只读解包并写本文；未改 GitHub、源码、spec、任务状态或版本，未 commit/push/tag、重跑发布或构建，未执行任何 EXE。v1.2.3 的暂停核验不混入本报告。

## 1. 版本、提交与 CI（API 观察）

期望提交：`b0d4335d8e6a291ffa79ab097fd2ccc70dc26f97`。
通过同 SHA 的 Actions runs 查询确认如下，均为 push、attempt=1、head_sha 精确匹配：

| Run ID | head_branch | 结果 | API 最终 updated_at（UTC） |
| --- | --- | --- | --- |
| `44836184819` | `main` | **success** | 2026-11-20T23:24:17Z |
| `44836184833` | `feat/dedupe-groups-keeper` | **success** | 2026-11-20T23:24:33Z |
| `44836626184` | `v1.2.4` | **success** | 2026-11-20T23:27:30Z |

- tag run 创建于 `2026-11-20T23:24:57Z`。本 Pi 在 `23:26:35Z` 观察构建中，在 `23:27:39Z` 观察完成；两次轮询相隔超过 45 秒。
- 必需步骤均成功：离屏/隔离配置单测、版本检查、构建、自检、portable、安装包、上传与 Publish GitHub Release。`Download ExifTool` 因缓存命中 skipped，随后 Configure ExifTool 成功；不将该条件跳过误报为失败或称每步均执行。
- annotated `v1.2.4` tag object：`4c1a22836b3f21986b1a21a50cee9fc69c5a4de2`；peeled commit 精确为期望提交。`2026-11-20T23:28:01Z` API 观察 main 同样位于该提交。
- 认证使用关闭交互的 `git credential fill`，凭证仅内存解析并作为 REST Bearer；未打印/保存凭证输出或 token，重定向时移除 Authorization，未安装 gh。

## 2. Release 与资产（API 观察）

`GET /repos/azurekiln2333/azurekiln-photo-tool/releases/tags/v1.2.4`：

- Release ID：`453280760`；名称：`AzureKiln Photo Tool v1.2.4`。
- published_at：`2026-11-20T23:27:25Z`；draft=false，prerelease=false。
- 下列三资产均 `uploaded` 且 size>0，名称均含 **1.2.4**。文件日期 `20261120` 来自构建 UTC 日期；本地 +08:00 核验时间已是 2026-11-21，不是混入旧版本。

| 资产名称 | ID | API size（字节） |
| --- | --- | --- |
| `AzureKilnPhotoTool-1.2.4-20261120-windows-x64-portable.zip` | 773717602 | **84,214,797** |
| `AzureKilnPhotoTool-1.2.4-20261120-windows-x64-portable.sha256.txt` | 773717599 | **90** |
| `AzureKilnPhotoTool-1.2.4-20261120-windows-x64-setup.exe` | 773717601 | **86,067,198** |

## 3. 真实下载核验（不是 API 存在性推断）

使用本轮唯一系统临时目录：
`D:\AppData\Local\Temp\azurekiln-v124-verify-7bac8a9448904daeac177adbd4b58b63\`。

三资产均实际下载，仅解包已确认名称的 portable EXE，不执行。下载文件大小全部与 API 一致；`2026-11-20T23:29:14Z` 完成校验，脚本进程 **exit 0**。

| 实际下载文件 | 实测 SHA-256（与 GitHub asset digest 均一致） |
| --- | --- |
| portable ZIP | `9add6b640b6bd55bd65f75ea882953e076b7768be26a341bf3bd04eb36da56dc` |
| portable checksum 文本 | `47af9ef0dfd5d6ef36f57c90f2c9e6afc7ae4cc9dfb9625cf9b9ca2331106ae9` |
| setup EXE | `ef52484158fa814bd01ca5103ff460501abe7eb8a3654545b237ff546cbd4ff9` |

### ZIP 内部与 checksum

- ZIP CRC 完整性检查 `testzip()`：**PASS**。
- ZIP 精确包含 `AzureKilnPhotoTool.exe` 与 `AzureKilnPhotoTool-1.2.4-20261120-windows-x64-portable.sha256.txt`，无其它版本资产。
- 包内 checksum 与独立下载的 90 字节文本**逐字节相同**。
- checksum 内容（末尾为真实 CRLF，下面转义展示）：

```text
7153c6e92782dcbed39fdda78bb10cd0bc15517f862d0e72547c4b0fde9b3ba3  AzureKilnPhotoTool.exe\r\n
```

- 解包 EXE 大小：**84,745,665 字节**。
- 解包 EXE 实测 SHA-256：`7153c6e92782dcbed39fdda78bb10cd0bc15517f862d0e72547c4b0fde9b3ba3`，与 checksum 记录值**完全一致**。
- checksum 记录的是 **EXE** 哈希，不是 ZIP。ZIP 自身摘要独立对照 GitHub asset digest，两个层级均核验通过。
- setup EXE 本次也真实下载并核对其 asset digest；**未运行安装包，也未运行 portable EXE**。

## 4. 原始证据与边界

上述独立临时目录保留公开核验事实：`status-observations.jsonl`、`runs-current.json`、`release-v124.json`、`downloads-v124.json` 及实际下载文件。不保存凭证，不将二进制/临时目录提交进仓库。

本报告完成远端 CI、tag/main 对齐、三资产上传及真实下载内容完整性核验；不代表安装体验、SmartScreen、真实相册/OneDrive 运行或 EXE 功能端到端已验证。

**本报告写入并回读后停笔，停止文件写入与额外 API 请求；后续提交、归档和发布说明由 root 处理。**
