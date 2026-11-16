"""目录 readme.txt 的读取与安全保存（仅标准库，不依赖 PyQt）。

职责边界：
- 只读取所选目录“直接包含”的、名称不区分大小写等于 readme.txt 的已有文件；
  本模块不创建说明文件，也不递归查找上级说明。
- 严格识别编码（UTF-8 BOM / UTF-16 LE-BE BOM / UTF-8 / GB18030），
  禁用 errors="ignore"/"replace"；保存时仍用原编码，容不下新字符则报错且不改原文件。
- 保留原 BOM 与主要换行风格：读取时把文本统一为 LF 交给编辑器，
  保存时再还原为原始换行风格。
- 保存采用「同目录唯一临时文件 + flush + os.replace」，不先截断原文件；
  失败时只清理本次确知创建的临时文件。
- 保存前比较基线（原始字节长度 + 原始字节内容），发现外部修改或删除返回 conflict，
  由调用方保留草稿，绝不静默覆盖。ReadmeDocument.mtime_ns 仅作为元数据保留，
  不参与冲突判定（内容比对已覆盖同类场景，且避免 OneDrive 同步写回时间戳造成误报）。
- 所有失败都以明确的 ReadmeResult.status 返回（error/too_large/conflict），
  绝不会把读取失败伪装成 missing。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

# 编辑器最多加载 2 MiB，超出提示并禁止编辑，避免大文本拖慢页面
MAX_README_BYTES = 2 * 1024 * 1024

# 说明文件名（比较时用 casefold，不区分大小写）
README_NAME = "readme.txt"

# 状态常量：与 research/parallel-contract.md 保持一致
STATUS_READY = "ready"
STATUS_MISSING = "missing"
STATUS_TOO_LARGE = "too_large"
STATUS_ERROR = "error"
STATUS_CONFLICT = "conflict"
STATUS_SAVED = "saved"

_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"

_NEWLINE_CRLF = "\r\n"
_NEWLINE_LF = "\n"
_NEWLINE_CR = "\r"

_TEXT_ENCODINGS = ("utf-8", "gb18030", "utf-16-le", "utf-16-be")

# 用于检测换行风格的探测长度上限（只影响探测，不影响整体解码）
_NEWLINE_PROBE_CHARS = 65536


@dataclass(frozen=True)
class ReadmeDocument:
    """已成功加载的说明文件快照，保存时以它为基线做冲突检查。"""

    path: Path
    text: str  # 已统一为 LF 换行的编辑器文本
    encoding: str  # Python 编码名，例如 "utf-8" / "utf-16-le" / "gb18030"
    bom: bytes  # 原文件开头的 BOM（无 BOM 时为空字节串）
    newline: str  # 原主要换行风格："\r\n" / "\n" / "\r"
    baseline: bytes  # 读取时的完整原始字节
    mtime_ns: int  # 读取时的 mtime（纳秒）

    @property
    def size(self) -> int:
        return len(self.baseline)

    @property
    def editor_text(self) -> str:
        """编辑器使用的文本（统一 LF）。"""
        return self.text


@dataclass(frozen=True)
class ReadmeResult:
    """读写结果。status 为 ready/missing/too_large/error/conflict/saved。"""

    status: str
    document: ReadmeDocument | None = None
    error: str = ""
    path: Path | None = None

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_READY, STATUS_SAVED)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _as_directory(directory: Path | str) -> Path:
    """把输入统一成绝对路径（不解析链接，避免云占位路径被改写）。"""
    path = Path(directory)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _detect_newline(text: str) -> str:
    """检测主要换行风格；默认 LF。

    统计前若干字符内 CRLF / 单独 LF / 单独 CR 的出现次数，取最多者。
    """
    probe = text[:_NEWLINE_PROBE_CHARS]
    crlf = probe.count(_NEWLINE_CRLF)
    lf = probe.count(_NEWLINE_LF) - crlf
    cr = probe.count(_NEWLINE_CR) - crlf
    counts = ((_NEWLINE_CRLF, crlf), (_NEWLINE_LF, lf), (_NEWLINE_CR, cr))
    best_newline = _NEWLINE_LF
    best_count = 0
    for newline, count in counts:
        if count > best_count:
            best_newline, best_count = newline, count
    return best_newline


def _normalise_newlines(text: str) -> str:
    """把任意换行统一为 LF（先 CRLF 再裸 CR，避免重复替换）。"""
    return text.replace(_NEWLINE_CRLF, _NEWLINE_LF).replace(_NEWLINE_CR, _NEWLINE_LF)


def _restore_newlines(text: str, newline: str) -> str:
    """把 LF 文本还原为指定换行风格。"""
    if newline == _NEWLINE_LF:
        return text
    normalised = _normalise_newlines(text)
    if newline == _NEWLINE_CRLF:
        return normalised.replace(_NEWLINE_LF, _NEWLINE_CRLF)
    return normalised.replace(_NEWLINE_LF, _NEWLINE_CR)


def _decode_strict(raw: bytes) -> tuple[str, str, bytes] | None:
    """严格识别编码，返回 (文本, 编码名, BOM)；全部失败返回 None。

    顺序：UTF-8 BOM → UTF-16 LE/BE BOM → 严格 UTF-8 → GB18030。
    """
    if raw.startswith(_UTF8_BOM):
        body = raw[len(_UTF8_BOM):]
        try:
            return body.decode("utf-8"), "utf-8", _UTF8_BOM
        except UnicodeDecodeError:
            return None
    if raw.startswith(_UTF16_LE_BOM) or raw.startswith(_UTF16_BE_BOM):
        is_le = raw.startswith(_UTF16_LE_BOM)
        encoding = "utf-16-le" if is_le else "utf-16-be"
        body = raw[2:]
        if len(body) % 2:
            # 奇数长度不可能是完整 UTF-16 文本，不以替代字符掩盖
            return None
        try:
            return body.decode(encoding), encoding, raw[:2]
        except UnicodeDecodeError:
            return None
    # 无 BOM 且含空字节的多半是 UTF-16；无 BOM 的 UTF-16 不予猜测
    try:
        if b"\x00" in raw:
            return None
        return raw.decode("utf-8"), "utf-8", b""
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("gb18030"), "gb18030", b""
    except UnicodeDecodeError:
        return None


def _encode_strict(text: str, encoding: str, bom: bytes, newline: str) -> bytes | None:
    """按原编码/编码 BOM/换行风格严格编码；编码不下时返回 None。

    不使用 errors="replace"，也不自动更换编码。
    """
    restored = _restore_newlines(text, newline)
    if encoding in ("utf-8", "gb18030"):
        try:
            return bom + restored.encode(encoding)
        except UnicodeEncodeError:
            return None
    if encoding in ("utf-16-le", "utf-16-be"):
        try:
            body = restored.encode(encoding)
        except UnicodeEncodeError:
            return None
        # 保留原 BOM 形式：有 BOM 则补回，无 BOM 保持无 BOM
        return bom + body if bom else body
    return None


def _read_bytes_limited(path: Path, limit: int) -> tuple[bytes, bool]:
    """读取至多 limit 字节，返回 (字节, 是否超限)。"""
    with open(path, "rb") as handle:
        data = handle.read(limit + 1)
    return data[:limit], len(data) > limit


def _read_bytes_limited_fd(handle, limit: int) -> tuple[bytes, bool]:
    """从已打开的文件对象读取至多 limit 字节。"""
    data = handle.read(limit + 1)
    return data[:limit], len(data) > limit


def _locate_readme(directory: Path | str) -> ReadmeResult:
    """一次枚举目录，取得 readme.txt 的实际路径。

    这是唯一的枚举入口：返回值严格区分三种情况，绝不把失败伪装成 missing。
    - status == ready：命中，result.path 为实际路径（大小写与磁盘一致）
    - status == missing：目录可正常枚举，且确实没有 readme.txt
    - status == error：目录不存在/不是目录/不可枚举/迭代中出错，
      或同名项的链接/类型判定失败，result.path 与 error 给出行定位信息
    """
    folder = _as_directory(directory)
    expected = folder / README_NAME

    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.name.casefold() != README_NAME:
                    continue
                entry_path = Path(entry.path)
                try:
                    if entry.is_symlink() or entry.is_junction():
                        # 实际链接/联接说明不处理，避免写出目录
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        # 同名但不是普通文件（例如目录）：不是可编辑说明
                        continue
                except PermissionError as exc:
                    # 类型判定失败属于读取失败，不能当作“没有说明文件”
                    return ReadmeResult(
                        STATUS_ERROR, None, f"无法判断说明文件类型：{exc}", entry_path
                    )
                except OSError as exc:
                    return ReadmeResult(
                        STATUS_ERROR, None, f"无法判断说明文件类型：{exc}", entry_path
                    )
                return ReadmeResult(STATUS_READY, None, "", entry_path)
    except FileNotFoundError:
        return ReadmeResult(STATUS_ERROR, None, "目录不存在或已被删除", folder)
    except NotADirectoryError:
        return ReadmeResult(STATUS_ERROR, None, "路径不是目录", folder)
    except PermissionError as exc:
        return ReadmeResult(STATUS_ERROR, None, f"目录不可访问：{exc}", folder)
    except OSError as exc:
        # 含 FindNextFileW 失败、仅联机目录枚举失败等；一次遍历内即暴露
        return ReadmeResult(STATUS_ERROR, None, f"无法枚举目录：{exc}", folder)
    except Exception as exc:  # 防御：任何枚举异常都不能变成 missing
        return ReadmeResult(STATUS_ERROR, None, f"无法枚举目录：{exc}", folder)

    return ReadmeResult(STATUS_MISSING, None, "", expected)


def find_readme(directory: Path | str) -> Path | None:
    """便利函数：返回目录直接包含的 readme.txt 实际路径，无法确定时返回 None。

    需要区分「确实没有」与「读取/枚举失败」时，请直接使用 load_readme，
    它会返回 error 状态而不是 missing。
    """
    located = _locate_readme(directory)
    if located.status != STATUS_READY:
        return None
    return located.path


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------


def load_readme(directory: Path | str) -> ReadmeResult:
    """加载目录直接包含的 readme.txt（单次枚举，无二次遍历）。

    返回状态：
    - ready：成功加载（空文件也是可编辑的已加载文档）
    - missing：目录可正常枚举，且确实没有 readme.txt
    - too_large：超过 MAX_README_BYTES
    - error：目录不可访问、枚举/类型判定失败、打开失败、无法识别编码等其他失败
    """
    folder = _as_directory(directory)

    located = _locate_readme(folder)
    if located.status == STATUS_ERROR:
        return located
    if located.status == STATUS_MISSING:
        return located

    found = located.path
    expected = folder / README_NAME

    try:
        # 先按上限读取，避免把超大文件整体读入内存
        raw_head, over_limit = _read_bytes_limited(found, MAX_README_BYTES)
        if over_limit:
            return ReadmeResult(
                STATUS_TOO_LARGE,
                None,
                f"说明文件超过 {MAX_README_BYTES // (1024 * 1024)} MiB 上限，暂不支持编辑",
                found,
            )
        stat_result = found.stat()
        # 文件在读取期间可能增长，size 与实读不一致时以上限判断为准
        if stat_result.st_size > MAX_README_BYTES:
            return ReadmeResult(
                STATUS_TOO_LARGE,
                None,
                f"说明文件超过 {MAX_README_BYTES // (1024 * 1024)} MiB 上限，暂不支持编辑",
                found,
            )
        raw = raw_head
    except FileNotFoundError:
        return ReadmeResult(STATUS_ERROR, None, "说明文件在读取过程中被删除", found)
    except PermissionError as exc:
        return ReadmeResult(STATUS_ERROR, None, f"没有读取权限：{exc}", found)
    except OSError as exc:
        # 含仅联机文件离线不可读等云 I/O 失败，必须显示为错误
        return ReadmeResult(STATUS_ERROR, None, f"读取失败：{exc}", found)

    decoded = _decode_strict(raw)
    if decoded is None:
        return ReadmeResult(
            STATUS_ERROR,
            None,
            "无法识别说明文件编码（仅支持 UTF-8、UTF-8 BOM、UTF-16 BOM、GB18030）",
            found,
        )
    text, encoding, bom = decoded
    newline = _detect_newline(text)

    document = ReadmeDocument(
        path=found,
        text=_normalise_newlines(text),
        encoding=encoding,
        bom=bom,
        newline=newline,
        baseline=raw,
        mtime_ns=int(stat_result.st_mtime_ns),
    )
    return ReadmeResult(STATUS_READY, document, "", found)


def save_readme(document: ReadmeDocument, text: str) -> ReadmeResult:
    """把编辑器文本以原编码/BOM/换行风格写回原文件（原子替换）。

    失败时原文件保持不变：
    - conflict：文件被外部修改或删除（或基线读取失败）
    - too_large：编码后的字节超过 MAX_README_BYTES（保证保存后仍可重新加载）
    - error：编码不下、无写权限、替换失败等
    成功返回 STATUS_SAVED 与新 document（基线已更新为落盘字节）。
    """
    if document is None:
        return ReadmeResult(STATUS_ERROR, None, "缺少待保存的说明文档", None)

    path = document.path
    try:
        payload = _encode_strict(text, document.encoding, document.bom, document.newline)
    except Exception as exc:  # 防御：编码实现异常也要转成错误状态
        return ReadmeResult(STATUS_ERROR, document, f"编码失败：{exc}", path)
    if payload is None:
        return ReadmeResult(
            STATUS_ERROR,
            document,
            f"当前编码（{document.encoding}）无法表示新内容，已保留草稿与原文件",
            path,
        )

    # ---- 落盘字节上限 - 与读取上限一致，避免保存出一个自己也无法重新打开的说明 ----
    if len(payload) > MAX_README_BYTES:
        return ReadmeResult(
            STATUS_TOO_LARGE,
            document,
            (
                f"保存后的大小超过 {MAX_README_BYTES // (1024 * 1024)} MiB 上限，"
                "未写入任何内容，草稿已保留"
            ),
            path,
        )

    # ---- 保存前基线检查（减小外部变更竞争窗口，不是分布式锁） ----
    conflict = _check_baseline(document)
    if conflict is not None:
        return conflict

    if payload == document.baseline:
        # 内容没有实际变化：不重写文件，直接把当前状态视为已保存
        return ReadmeResult(STATUS_SAVED, document, "", path)

    temp_path: Path | None = None
    try:
        # 同目录唯一临时文件，保证 os.replace 同卷原子替换
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        temp_path = Path(temp_name)
        # 完整写入、flush、fsync 后再替换；句柄由 fdopen 托管并在 with 退出时关闭
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        # 替换前再次检查基线，进一步缩小竞争窗口
        conflict = _check_baseline(document)
        if conflict is not None:
            _safe_unlink(temp_path)
            temp_path = None
            return conflict

        os.replace(temp_path, path)
        temp_path = None  # 已被替换，不再清理
    except PermissionError as exc:
        _safe_unlink(temp_path)
        return ReadmeResult(STATUS_ERROR, document, f"没有写入权限：{exc}", path)
    except OSError as exc:
        _safe_unlink(temp_path)
        return ReadmeResult(STATUS_ERROR, document, f"保存失败：{exc}", path)
    except Exception as exc:  # 防御：任何异常都必须清理临时文件
        _safe_unlink(temp_path)
        return ReadmeResult(STATUS_ERROR, document, f"保存失败：{exc}", path)

    # 成功后以落盘内容建立新基线
    try:
        new_stat = path.stat()
        new_mtime_ns = int(new_stat.st_mtime_ns)
    except OSError:
        new_mtime_ns = document.mtime_ns

    saved_document = ReadmeDocument(
        path=path,
        text=_normalise_newlines(text),
        encoding=document.encoding,
        bom=document.bom,
        newline=document.newline,
        baseline=payload,
        mtime_ns=new_mtime_ns,
    )
    return ReadmeResult(STATUS_SAVED, saved_document, "", path)


def _check_baseline(document: ReadmeDocument) -> ReadmeResult | None:
    """基线检查：原文件存在且长度、原始字节均与基线一致则返回 None，否则返回 conflict。

    只比较长度与原始字节；document.mtime_ns 不参与判定（仅作元数据保留）。
    """
    path = document.path
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return ReadmeResult(STATUS_CONFLICT, document, "说明文件已被删除，未写入任何内容", path)
    except PermissionError as exc:
        return ReadmeResult(STATUS_CONFLICT, document, f"无法读取原文件状态：{exc}", path)
    except OSError as exc:
        return ReadmeResult(STATUS_CONFLICT, document, f"无法读取原文件状态：{exc}", path)

    if stat_result.st_size != len(document.baseline):
        return ReadmeResult(STATUS_CONFLICT, document, "说明文件已被外部修改，未覆盖磁盘内容", path)

    try:
        with open(path, "rb") as handle:
            current, over_limit = _read_bytes_limited_fd(handle, len(document.baseline))
    except PermissionError as exc:
        return ReadmeResult(STATUS_CONFLICT, document, f"无法读取原文件内容：{exc}", path)
    except OSError as exc:
        return ReadmeResult(STATUS_CONFLICT, document, f"无法读取原文件内容：{exc}", path)

    if over_limit or current != document.baseline:
        return ReadmeResult(STATUS_CONFLICT, document, "说明文件已被外部修改，未覆盖磁盘内容", path)
    return None


def _safe_unlink(temp_path: Path | None) -> None:
    """只清理本次确知创建的临时文件，失败忽略（不影响用户数据）。"""
    if temp_path is None:
        return
    try:
        os.unlink(temp_path)
    except OSError:
        pass
