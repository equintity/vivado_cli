# -*- coding: utf-8 -*-
"""vc_env -- Vivado 环境探测与配置。

状态文件 `vivado_cli_env.json` 保存在工程目录（CWD），内容示例::

    {
      "vivado_home": "D:/FPGA/vivado/Xilinux/Vivado/2018.2",
      "vivado_version": "2018.2",
      "part": "xc7a35tcpg236-1",
      "project": {"name": "...", "dir": "...", "xpr": "..."}
    }

优先级：--vivado-home 参数 > CWD 状态文件 > 环境变量 VIVADO_CLI_VIVADO_HOME > 自动探测。
"""

import glob
import json
import os
import re

from vc_util import error, guard_writable_dir, info, run_cmd, warn

ENV_FILE = "vivado_cli_env.json"
ENV_VAR = "VIVADO_CLI_VIVADO_HOME"
VIVADO_BAT = os.path.join("bin", "vivado.bat")

# 面向版本：2018.x（Xilinx 时代、SDK 时代）
TARGET_SERIES = "2018"


# ---------------------------------------------------------------- 状态文件

def env_path(cwd):
    return os.path.join(cwd, ENV_FILE)


def load_env(cwd):
    p = env_path(cwd)
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            warn("状态文件解析失败（将忽略）: %s (%s)" % (p, e))
    return {}


def save_env(cwd, data):
    p = env_path(cwd)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return p


# ---------------------------------------------------------------- 探测

def _glob_candidates():
    """在常见安装根下扫描 Vivado 安装（兼容 C:/D:/E:/F: 盘与自定义父目录）。"""
    roots = [r"C:\\", r"D:\\", r"E:\\", r"F:\\"]
    pats = []
    for root in roots:
        for depth in range(0, 4):
            star = os.path.join(*(["*"] * depth)) if depth else ""
            pats.append(os.path.join(root, star, "Xilinx", "Vivado", "*", VIVADO_BAT))
            pats.append(os.path.join(root, star, "Vivado", "*", VIVADO_BAT))
    found = set()
    for pat in pats:
        for hit in glob.glob(pat):
            found.add(os.path.normpath(os.path.dirname(os.path.dirname(hit))))
    return sorted(found)


def detect_installs():
    """返回候选 Vivado home 目录列表（不含校验）。"""
    cands = []
    env_home = os.environ.get(ENV_VAR)
    if env_home and os.path.isdir(env_home):
        cands.append(os.path.normpath(env_home))
    cands.extend(_glob_candidates())
    seen, out = set(), []
    for c in cands:
        if c.upper() not in seen:
            seen.add(c.upper())
            out.append(c)
    return out


_VERSION_RE = re.compile(r"Vivado\s+v(\d{4}\.\d+)", re.IGNORECASE)


def verify(vivado_home, timeout=180):
    """校验 vivado_home 可用并返回 (ok, version or None, message)。"""
    bat = os.path.join(vivado_home, VIVADO_BAT)
    if not os.path.isfile(bat):
        return False, None, "未找到 %s" % bat
    rc, out, errout = run_cmd([bat, "-version"], timeout=timeout)
    text = out + errout
    m = _VERSION_RE.search(text)
    if rc != 0 and not m:
        return False, None, "vivado -version 执行失败 (rc=%s): %s" % (rc, text.strip()[:300])
    ver = m.group(1) if m else None
    return True, ver, bat


# ---------------------------------------------------------------- 命令

def cmd_detect(args):
    cands = detect_installs()
    if not cands:
        error("未自动发现任何 Vivado 安装。请用 `env set --vivado-home <目录>` 手工指定。")
        return 2
    info("发现 %d 个候选安装，逐一验证：" % len(cands))
    for c in cands:
        ok, ver, msg = verify(c)
        if ok:
            info("  [可用] %-60s 版本 %s" % (c, ver))
        else:
            warn("  [无效] %-60s (%s)" % (c, msg))
    return 0


def cmd_set(args):
    guard_writable_dir(args.cwd, allow_system_drive=False)  # 状态文件同样禁止写系统盘
    home = os.path.abspath(args.vivado_home)
    ok, ver, msg = verify(home)
    if not ok:
        error("该目录不是有效的 Vivado 安装: %s" % msg)
        return 2
    data = load_env(args.cwd)
    data["vivado_home"] = home.replace("\\", "/")
    data["vivado_version"] = ver
    p = save_env(args.cwd, data)
    info("已写入 %s: vivado_home=%s (v%s)" % (p, data["vivado_home"], ver))
    if ver and not ver.startswith(TARGET_SERIES + "."):
        warn("本 skill 面向 Vivado %s.x（Tcl 脚本按 2018 API 编写），当前为 %s，"
             "部分命令/属性名可能不兼容，详见 docs/vivado2018_notes.md。" % (TARGET_SERIES, ver))
    return 0


def cmd_check(args):
    data = load_env(args.cwd)
    home = args.vivado_home or data.get("vivado_home") or os.environ.get(ENV_VAR)
    if not home:
        cands = detect_installs()
        if not cands:
            error("未配置 Vivado。请先运行: env set --vivado-home <Vivado安装目录>")
            return 2
        if len(cands) > 1:
            warn("发现多个安装，请用 env set 显式选择其一: %s" % cands)
        home = cands[0]
    ok, ver, msg = verify(home)
    if not ok:
        error("Vivado 环境不可用: %s" % msg)
        return 1
    info("Vivado 环境正常: %s (v%s)" % (home, ver))
    if args.save:
        data["vivado_home"] = os.path.abspath(home).replace("\\", "/")
        data["vivado_version"] = ver
        save_env(args.cwd, data)
        info("已保存到 %s" % env_path(args.cwd))
    if ver and not ver.startswith(TARGET_SERIES + "."):
        warn("检测到版本 %s；本 skill 的 Tcl 按 %s.x API 编写，存在兼容风险。"
             % (ver, TARGET_SERIES))
    return 0


# ---------------------------------------------------------------- Win11 综合崩溃修复

# Windows 11 (24H2+) 上老版 Vivado 综合阶段崩溃/挂起：
# libPortability.dll 枚举网络共享在新系统上失败。官方修复思路（NI KB）是用
# 随附的无共享枚举变体 libPortabilityNOSH.dll 替换。见 docs/vivado2018_notes.md 第 8 节。
_PORT_DIR = os.path.join("ids_lite", "ISE", "lib", "nt64")
_DLL = "libPortability.dll"
_NOSH = "libPortabilityNOSH.dll"
_BAK_SUFFIX = ".bak_vivado_cli"


def _portability_paths(vivado_home):
    d = os.path.join(vivado_home, _PORT_DIR)
    return {
        "dir": d,
        "dll": os.path.join(d, _DLL),
        "nosh": os.path.join(d, _NOSH),
        "bak": os.path.join(d, _DLL + _BAK_SUFFIX),
    }


def fix_win11_status(vivado_home):
    p = _portability_paths(vivado_home)
    if not os.path.isfile(p["dll"]):
        return "missing", "未找到 %s" % p["dll"]
    if os.path.isfile(p["bak"]):
        return "patched", "已替换为 NOSH 变体（备份 %s）" % p["bak"]
    if os.path.isfile(p["nosh"]):
        with open(p["dll"], "rb") as f1, open(p["nosh"], "rb") as f2:
            if f1.read() == f2.read():
                return "patched", "libPortability.dll 已是 NOSH 变体（内容一致）"
    return "original", "原始 libPortability.dll —— Windows 11 上综合可能崩溃"
    # 崩溃特征: "TclStackFree: incorrect freePtr. Call out of sequence?"


def _resolve_home(args):
    data = load_env(args.cwd)
    home = args.vivado_home or data.get("vivado_home") or os.environ.get(ENV_VAR)
    if not home or not os.path.isdir(home):
        raise RuntimeError("未定位 Vivado 安装目录，请先 env set 或传 --vivado-home")
    return home


def cmd_fix_win11(args):
    home = _resolve_home(args)
    p = _portability_paths(home)
    status, msg = fix_win11_status(home)
    if args.fix_action == "status":
        info("libPortability 状态: %s —— %s" % (status, msg))
        return 0
    if args.fix_action == "apply":
        if status == "patched":
            info("无需修复: %s" % msg)
            return 0
        if status == "missing" or not os.path.isfile(p["nosh"]):
            error("缺少 %s，无法修复" % p["nosh"])
            return 1
        import shutil
        shutil.copy2(p["dll"], p["bak"])
        shutil.copy2(p["nosh"], p["dll"])
        info("已修复: %s -> NOSH 变体（备份: %s）" % (p["dll"], p["bak"]))
        info("还原命令: env fix-win11 revert")
        return 0
    if args.fix_action == "revert":
        if not os.path.isfile(p["bak"]):
            info("无备份可还原（当前状态: %s）" % msg)
            return 0
        import shutil
        shutil.copy2(p["bak"], p["dll"])
        os.remove(p["bak"])
        info("已还原原始 libPortability.dll")
        return 0
    return 2


def register(sub):
    p = sub.add_parser("env", help="Vivado 环境探测与配置")
    sp = p.add_subparsers(dest="action", required=True)

    d = sp.add_parser("detect", help="扫描常见路径，列出可用 Vivado 安装")
    d.set_defaults(func=cmd_detect)

    s = sp.add_parser("set", help="指定 Vivado 安装目录并写入 CWD/vivado_cli_env.json")
    s.add_argument("--vivado-home", required=True, help="Vivado 安装根目录（含 bin/vivado.bat）")
    s.set_defaults(func=cmd_set)

    c = sp.add_parser("check", help="校验当前环境可用性")
    c.add_argument("--vivado-home", default=None, help="临时指定安装目录（优先于状态文件）")
    c.add_argument("--save", action="store_true", help="校验通过后写入状态文件")
    c.set_defaults(func=cmd_check)

    f = sp.add_parser("fix-win11", help="Windows 11 综合崩溃（TclStackFree）诊断与修复")
    fp = f.add_subparsers(dest="fix_action", required=True)
    fs = fp.add_parser("status", help="查看 libPortability.dll 状态")
    fs.add_argument("--vivado-home", default=None)
    fs.set_defaults(func=cmd_fix_win11)
    fa = fp.add_parser("apply", help="备份并用 libPortabilityNOSH.dll 替换（可 revert）")
    fa.add_argument("--vivado-home", default=None)
    fa.set_defaults(func=cmd_fix_win11)
    fr = fp.add_parser("revert", help="从备份还原原始 DLL")
    fr.add_argument("--vivado-home", default=None)
    fr.set_defaults(func=cmd_fix_win11)
