"""ExifTool 定位与调用解析器。

背景
----
Windows 版 ExifTool 由两部分组成：

1. ``exiftool.exe`` —— 约 58KB 的启动器（stub），本身不是 ExifTool；
2. ``exiftool_files/`` —— 真正的 Perl 运行时 + ``exiftool.pl`` 脚本。

该 stub 依赖「相对自身位置」推导 ``exiftool_files`` 目录。当程序被打包成
PyInstaller onefile 后，文件被解压到 ``%TEMP%/_MEIxxxxxx``，stub 的自定位
会失败，表现为 Perl 的 ``@INC`` 为空：

    Can't locate strict.pm in @INC (@INC contains:) at .../exiftool_files/exiftool.pl line 10

此时 ``exiftool.exe -ver`` 返回 255，即便 ``exiftool_files`` 完整存在。

解决方案
--------
直接绕过 stub，改用 ``exiftool_files/perl.exe -I<lib> exiftool.pl`` 调用，
把库路径显式传给 Perl，不依赖 stub 的自定位。

``resolve_exiftool()`` 返回一个 :class:`ExifToolCommand`，它对上层暴露统一的
``exiftool_path`` / ``extra_args`` / ``cwd``，调用方按
``[exiftool_path, *extra_args, *用户参数]`` 组装命令即可，无需关心底层差异。
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ExifToolCommand",
    "resolve_exiftool",
    "build_exiftool_command",
    "run_exiftool",
    "get_startupinfo",
    "describe_resolution",
]


def get_startupinfo():
    """隐藏子进程控制台窗口。"""
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


@dataclass
class ExifToolCommand:
    """一次可用的 ExifTool 调用方式。"""

    #: 实际要执行的可执行文件（可能是 exiftool.exe，也可能是 perl.exe）
    exiftool_path: str
    #: 必须前置的参数（perl 模式下为 -I<lib> 与 exiftool.pl 的绝对路径）
    extra_args: list[str] = field(default_factory=list)
    #: 子进程工作目录；None 表示继承当前目录
    cwd: str | None = None
    #: 人类可读的来源说明，便于诊断
    source: str = ""

    def command(self, args: list[str] | None = None) -> list[str]:
        """组装完整命令：``可执行文件 + 前置参数 + 用户参数``。

        注意：perl 直调模式下 :attr:`cwd` 指向 ``exiftool_files``，
        因此调用方传入的**文件路径必须是绝对路径**，否则会相对于该目录解析。
        """
        return [self.exiftool_path, *self.extra_args, *(args or [])]

    def describe(self) -> str:
        return self.source or self.exiftool_path


def _perl_mode_candidate(exiftool_files_dir: Path, source: str) -> ExifToolCommand | None:
    """尝试构造 ``perl.exe -Ilib exiftool.pl`` 调用。

    :param exiftool_files_dir: ExifTool 的 ``exiftool_files`` 目录
    :param source: 来源描述（用于诊断信息）
    """
    perl = exiftool_files_dir / "perl.exe"
    script = exiftool_files_dir / "exiftool.pl"
    lib = exiftool_files_dir / "lib"

    if os.name != "nt":
        # 非 Windows 一般是原生 perl 脚本，不适用此模式
        return None
    if not (perl.exists() and script.exists()):
        return None

    extra: list[str] = []
    if lib.is_dir():
        # 显式指定库路径，避免 stub/自定位问题导致 @INC 为空
        extra.extend([f"-I{lib}"])
    extra.append(str(script))

    return ExifToolCommand(
        exiftool_path=str(perl),
        extra_args=extra,
        cwd=str(exiftool_files_dir),
        source=f"perl 直调模式（{source}）",
    )


def _stub_candidate(exe_path: Path, source: str) -> ExifToolCommand:
    """传统的 ``exiftool.exe`` 直接调用方式。"""
    return ExifToolCommand(
        exiftool_path=str(exe_path),
        extra_args=[],
        cwd=str(exe_path.parent),
        source=f"stub 直调模式（{source}）",
    )


def _dir_candidates(exiftool_dir: Path, source: str) -> list[ExifToolCommand]:
    """给定包含 ``exiftool.exe`` / ``exiftool_files`` 的目录，按优先级返回候选调用方式。

    顺序：

    1. **perl 直调** —— 绕过 stub 自定位，PyInstaller onefile 下唯一可靠的方式；
    2. **stub 直调** —— 源码运行、或 exiftool.exe 能正确定位自身时使用。

    返回列表交由 :func:`_probe` 逐个验证，第一个可用的胜出。
    """
    out: list[ExifToolCommand] = []
    exiftool_files = exiftool_dir / "exiftool_files"

    if exiftool_files.is_dir():
        perl_cmd = _perl_mode_candidate(exiftool_files, source)
        if perl_cmd is not None:
            out.append(perl_cmd)

    for name in ("exiftool.exe", "exiftool"):
        exe = exiftool_dir / name
        if exe.exists():
            out.append(_stub_candidate(exe, source))
            break

    return out


def _probe(cmd: ExifToolCommand, timeout: float = 20.0) -> bool:
    """实际执行 ``-ver`` 验证该调用方式可用。"""
    try:
        result = subprocess.run(
            cmd.command(["-ver"]),
            capture_output=True,
            timeout=timeout,
            cwd=cmd.cwd,
            startupinfo=get_startupinfo(),
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    # 正常情况下 stdout 是版本号，如 b"13.58"
    out = (result.stdout or b"").strip()
    return bool(out)


def _candidate_dirs() -> list[tuple[Path, str]]:
    """按优先级列出所有可能的 ExifTool 目录。"""
    dirs: list[tuple[Path, str]] = []

    exiftool_dir_env = os.environ.get("EXIFTOOL_DIR")
    if exiftool_dir_env:
        dirs.append((Path(exiftool_dir_env), "EXIFTOOL_DIR 环境变量"))

    # 打包后：PyInstaller 解压目录
    if hasattr(sys, "_MEIPASS"):
        mei = Path(sys._MEIPASS)
        dirs.append((mei, "打包解压目录"))
        dirs.append((mei / "exiftool", "打包解压目录/exiftool"))

    # 源码运行：相对本文件所在目录
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for rel in ("vendor/exiftool", "exiftool", "bin"):
        dirs.append((base_dir / rel, f"程序目录/{rel}"))

    exe_dir = Path(sys.executable).resolve().parent
    for rel in ("vendor/exiftool", "exiftool", "bin"):
        dirs.append((exe_dir / rel, f"可执行文件目录/{rel}"))
    dirs.append((exe_dir, "可执行文件目录"))

    return dirs


_CACHED: ExifToolCommand | None = None
_CACHE_DONE = False


def resolve_exiftool() -> ExifToolCommand | None:
    """定位一个可用的 ExifTool，返回可直接拼装命令的对象。

    返回 ``None`` 表示未找到任何可用实例。结果会被缓存，避免重复探测。
    """
    global _CACHED, _CACHE_DONE
    if _CACHE_DONE:
        return _CACHED

    # 1) EXIFTOOL_PATH 显式指向可执行文件
    env_path = os.environ.get("EXIFTOOL_PATH")
    if env_path and Path(env_path).exists():
        # EXIFTOOL_PATH 可能指向 exiftool.exe，也可能指向 exiftool_files 目录
        p = Path(env_path)
        search_dirs = []
        if p.is_dir():
            search_dirs.append((p, "EXIFTOOL_PATH 目录"))
            search_dirs.append((p.parent, "EXIFTOOL_PATH 上级目录"))
        else:
            search_dirs.append((p.parent, "EXIFTOOL_PATH"))
        for directory, src in search_dirs:
            for cand in _dir_candidates(directory, src):
                if _probe(cand):
                    _CACHED, _CACHE_DONE = cand, True
                    return _CACHED

    # 2) 依次探测各个目录
    for directory, source in _candidate_dirs():
        try:
            if not directory.is_dir():
                continue
            for cand in _dir_candidates(directory, source):
                if _probe(cand):
                    _CACHED, _CACHE_DONE = cand, True
                    return _CACHED
        except Exception:
            continue

    # 3) 回退到系统 PATH
    try:
        result = subprocess.run(
            ["exiftool", "-ver"],
            capture_output=True,
            timeout=20.0,
            startupinfo=get_startupinfo(),
        )
        if result.returncode == 0:
            _CACHED = ExifToolCommand(exiftool_path="exiftool", source="系统 PATH")
            _CACHE_DONE = True
            return _CACHED
    except Exception:
        pass

    _CACHED, _CACHE_DONE = None, True
    return None


def build_exiftool_command(args: list[str]) -> list[str] | None:
    """便捷函数：返回完整命令列表，未找到 ExifTool 时返回 ``None``。"""
    cmd = resolve_exiftool()
    if cmd is None:
        return None
    return cmd.command(args)


def run_exiftool(
    args: list[str],
    *,
    cwd: str | None = None,
    text: bool = False,
    encoding: str | None = None,
    errors: str | None = None,
    stdout=None,
    stderr=None,
    timeout: float | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess | None:
    """按标准方式调用 ExifTool；未找到时返回 ``None``。"""
    resolved = resolve_exiftool()
    if resolved is None:
        return None

    kwargs: dict = {
        "capture_output": stdout is None and stderr is None,
        "startupinfo": get_startupinfo(),
    }
    if stdout is not None or stderr is not None:
        kwargs = {"startupinfo": get_startupinfo()}
        if stdout is not None:
            kwargs["stdout"] = stdout
        if stderr is not None:
            kwargs["stderr"] = stderr
    if text:
        kwargs["text"] = True
    if encoding:
        kwargs["encoding"] = encoding
    if errors:
        kwargs["errors"] = errors
    if timeout is not None:
        kwargs["timeout"] = timeout
    # 调用方显式传入的 cwd 优先，否则用解析出的工作目录
    kwargs["cwd"] = cwd if cwd is not None else resolved.cwd
    if check:
        kwargs["check"] = True

    return subprocess.run(resolved.command(args), **kwargs)


def describe_resolution() -> str:
    """返回当前解析结果的可读描述，便于诊断。"""
    cmd = resolve_exiftool()
    if cmd is None:
        return "未找到可用的 ExifTool"
    return f"{cmd.source} | exe={cmd.exiftool_path} | cwd={cmd.cwd}"
