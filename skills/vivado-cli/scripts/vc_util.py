# -*- coding: utf-8 -*-
"""vc_util -- vivado_cli 公共工具：控制台输出、路径防护、子进程执行。

所有模块共用；不依赖任何第三方库。
"""

import os
import re
import subprocess
import sys


# ---------------------------------------------------------------- 控制台输出

def _setup_streams():
    """防止中文 Windows 控制台（GBK）在输出 Vivado 日志字符时崩溃。"""
    try:
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(errors="replace")
    except Exception:
        pass


_setup_streams()


def info(msg):
    print("[vivado_cli] %s" % msg)


def warn(msg):
    print("[vivado_cli][警告] %s" % msg, file=sys.stderr)


def error(msg):
    print("[vivado_cli][错误] %s" % msg, file=sys.stderr)


# ---------------------------------------------------------------- 路径防护

def system_drive():
    """返回 Windows 系统盘符，如 'C:'。"""
    return (os.environ.get("SystemDrive") or "C:").rstrip("\\/") or "C:"


def guard_writable_dir(path, allow_system_drive=False):
    """确保要写入的目录位于非系统盘（本 skill 的硬性安全约束）。

    返回规范化后的绝对路径；违规时抛出 RuntimeError。
    """
    abspath = os.path.abspath(path)
    drive, _ = os.path.splitdrive(abspath)
    if not allow_system_drive and drive.upper() == system_drive().upper():
        raise RuntimeError(
            "拒绝写入系统盘: %s\n"
            "vivado_cli 要求所有工程/输出文件放在非系统盘（例如 D:\\），避免污染 C 盘。\n"
            "如确需覆盖该约束，请显式加 --allow-system-drive 参数。" % abspath
        )
    return abspath


def to_tcl_path(path):
    """转成 Tcl 友好的正斜杠绝对路径。"""
    return os.path.abspath(path).replace("\\", "/")


def safe_tcl_value(value):
    """校验可安全嵌入 Tcl `set x {value}` 的字符串值。"""
    bad = set("{}\n\r")
    if any(ch in bad for ch in value):
        raise RuntimeError("Tcl 参数包含非法字符 {} 或换行: %r" % value)
    return value


# ---------------------------------------------------------------- 子进程

def run_cmd(cmd, cwd=None, timeout=600, env_extra=None):
    """执行外部命令，返回 (returncode, stdout, stderr)，统一 UTF-8 容错解码。"""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, timeout=timeout, env=env
        )
        rc = proc.returncode
        out = (proc.stdout or b"").decode("utf-8", errors="replace")
        errout = (proc.stderr or b"").decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b"").decode("utf-8", errors="replace") if e.stdout else "", \
               "TIMEOUT after %ss: %s" % (timeout, " ".join(cmd))
    return rc, out, errout


def tail(text, n=60):
    """取文本最后 n 行（失败诊断用）。"""
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[-n:])


# ---------------------------------------------------------------- 报告标记

MARKER_RE = re.compile(r"^VC_([A-Z_]+):\s*(.*)$")


def parse_markers(text):
    """从 Vivado 输出/日志中解析 `VC_XXX: value` 结构化标记。

    返回 [(tag, value), ...]（保持出现顺序）。
    """
    found = []
    for line in text.splitlines():
        m = MARKER_RE.match(line.strip())
        if m:
            found.append((m.group(1), m.group(2).strip()))
    return found
