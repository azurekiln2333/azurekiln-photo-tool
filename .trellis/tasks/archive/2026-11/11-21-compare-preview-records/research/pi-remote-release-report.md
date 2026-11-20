# v1.2.2 远端发布核验（只读）

核验对象：tag run `44808571694`、Release `/releases/tags/v1.2.2`。
本文严格区分「GitHub API 观察」与「真实下载验证」；未运行 EXE、未改代码/版本/tag、未重跑发布。

## 1. Run 与 tag 对齐（API 观察）

| 项目 | 值 |
| --- | --- |
| Run ID | `44808571694`（Build，event=push，attempt=1） |
| head_branch | `v1.2.2` |
| head_sha | `a594841fe4a24c9b1b65fd76b0726e4aa9119470` |
| 创建 / 完成 | 2026-11-20T20:08:04Z / 2026-11-20T20:12:10Z |
| 结论 | **success**（全部 20 个 step success，含 `Run unit tests`、`Verify bundle contents`、`Publish GitHub Release`） |
| Annotated tag | `refs/tags/v1.2.2` → tag object `37f36b6f6df00c75690abe99150f3c57c1aaf493` |
| Peeled target | commit **`a594841fe4a24c9b1b65fd76b0726e4aa9119470`**（与 run head_sha 一致，`TARGET_MATCHES=True`） |

## 2. Release 资产（API 观察）

`GET /repos/azurekiln2333/azurekiln-photo-tool/releases/tags/v1.2.2`
→ id `453134507`，name `AzureKiln Photo Tool v1.2.2`，draft=false，prerelease=false，
published_at `2026-11-20T20:11:58Z`。

| 资产 | size（字节） | state | API digest |
| --- | --- | --- | --- |
| `AzureKilnPhotoTool-1.2.2-20261120-windows-x64-portable.zip` | 84,203,502 | uploaded | `sha256:68bc5b681503c18cb3e3451340a73a4f08f029ff19edf51f7a464fa720ed3d59` |
| `AzureKilnPhotoTool-1.2.2-20261120-windows-x64-portable.sha256.txt` | 90 | uploaded | `sha256:01387d5444f8c1baa5cab51c5c6900c2afe6686e835e236d6cb5c874baa16387` |
| `AzureKilnPhotoTool-1.2.2-20261120-windows-x64-setup.exe` | 86,056,519 | uploaded | `sha256:d379db08eb0930dc313f0f631603479cadaed2bdfbb3777ec9cc5bdf5db66d06` |

三类资产均存在且 size > 0。

## 3. 真实下载验证（不是 API 推断）

临时目录：`%TEMP%\azurekiln-release-verify-*\`（独立目录，仅下载/解压，不运行 EXE）。

1. **下载 checksum 文本**：`curl.exe -fsSL` exit `0`；文件 90 字节，内容逐字节为：
   ```
   d6c3d950f222d16387b4cb02d114532c14a8feb3821f146dd09bada36f9b30ac  AzureKilnPhotoTool.exe\r\n
   ```
   按打包约定，该文本记录的是**zip 内 `AzureKilnPhotoTool.exe` 的哈希**，不是 zip 自身哈希。
2. **下载 portable zip**：exit `0`；实际大小 `84,203,502` 字节，与 API size 一致；
   实际 SHA-256 `68bc5b681503c18cb3e3451340a73a4f08f029ff19edf51f7a464fa720ed3d59`，
   与 GitHub 资产 digest **一致**。
3. **解包核对**：zip 内含 `AzureKilnPhotoTool.exe`（84,734,741 字节）与同名
   `...portable.sha256.txt`（90 字节）。解出的 exe SHA-256
   `d6c3d950f222d16387b4cb02d114532c14a8feb3821f146dd09bada36f9b30ac`
   与 checksum 文本记录值 **一致（`EXE_HASH_MATCH=True`）**；zip 内 checksum 文件与下载的
   checksum 文件内容**逐字节一致（`EMBEDDED_CHECKSUM_IDENTICAL=True`）**。
4. setup.exe 仅做 API 存在性/size/digest 核验（按指示不下载、不运行）。

说明：zip 文件自身的 SHA-256（`68bc…`）与 checksum 文本中的 exe 哈希（`d6c3…`）不同是
**设计如此**（文本只记录 exe），不构成不一致；两者分别与 API digest / zip 内 exe 实测值对齐。

## 4. 结论

- 远端 tag run 全流程 success；tag 指向 `a594841` 与 run head 一致。
- Release 三类资产存在且 size>0；真实下载的 zip digest 与 API 一致，zip 内 exe 实测哈希
  与 checksum 文本一致，zip 内 checksum 与远端 checksum 逐字节一致。
- 未发现发布阻塞问题。未验证项：未运行 setup.exe / portable exe（按只读核验约束）。
