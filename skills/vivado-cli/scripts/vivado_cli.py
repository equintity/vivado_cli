#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""vivado_cli -- Vivado 2018 全工作流 CLI skill 的统一入口。

用法:
    python scripts/vivado_cli.py <模块> <动作> [参数]

模块: env / project / pins / rtl / synth / impl / hwdef / hw / pl / report / workflow
详见 SKILL.md 与 README.md。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vc_env      # noqa: E402
import vc_flow     # noqa: E402
import vc_pins     # noqa: E402
import vc_report   # noqa: E402
import vc_rtl      # noqa: E402
from vc_util import error  # noqa: E402


def cwd_of(args):
    return os.path.abspath(args.cwd)


# ---------------------------------------------------------------- pins 命令

def cmd_pins_new(args):
    path = os.path.abspath(args.out)
    if os.path.isfile(path) and not args.force:
        error("文件已存在: %s（覆盖用 --force）" % path)
        return 2
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(vc_pins.HEADER) + "\n")
    print("[vivado_cli] 已生成引脚表模板: %s" % path)
    print("[vivado_cli] 填写规范: name 可为 led 或 led[3]（逐位）；pin 如 P17；"
          "iostandard 如 LVCMOS33。详见 SKILL.md 引脚表规范章节。")
    return 0


def cmd_pins_apply(args):
    rows = vc_pins.read_csv(args.csv)
    errors = vc_pins.validate(rows)
    if errors:
        for e in errors:
            error(e)
        error("引脚表校验未通过，未生成 XDC。")
        return 2
    xdc = vc_pins.gen_xdc(rows, part=args.part, note=args.note or "")
    out = os.path.abspath(args.out)
    if os.path.isfile(out) and not args.force:
        error("XDC 已存在: %s（覆盖用 --force）" % out)
        return 2
    with open(out, "w", encoding="utf-8") as f:
        f.write(xdc)
    print("[vivado_cli] 已生成 XDC: %s（%d 个端口位）" % (out, len(rows)))
    print("[vivado_cli] 下一步: project add-src --files %s --fileset constrs_1" % out)
    return 0


def cmd_pins_import(args):
    rows = vc_pins.import_xdc(args.xdc)
    out = vc_pins.write_csv(os.path.abspath(args.out), rows)
    print("[vivado_cli] 已从 XDC 导入 %d 个引脚位到 %s" % (len(rows), out))
    return 0


def cmd_pins_check(args):
    rows = vc_pins.read_csv(args.csv)
    errors = vc_pins.validate(rows)
    if errors:
        for e in errors:
            error(e)
        return 1
    print("[vivado_cli] 引脚表静态校验通过: %d 个端口位，无重复引脚/端口。" % len(rows))
    print("[vivado_cli] 若需校验引脚是否存在于器件封装，运行: pins-vivado check --part <器件名>。")
    return 0


def cmd_pins_crosscheck(args):
    rows = vc_pins.read_csv(args.csv)
    top, ports = vc_rtl.parse_ports_of_top(os.path.abspath(args.top_rtl), top=args.top)
    missing_in_csv, missing_in_rtl = vc_pins.crosscheck(rows, ports)
    print("[vivado_cli] 交叉校验: top=%s，CSV 位=%d，RTL 端口位=%d" % (top, len(rows), len(ports)))
    ok = True
    if missing_in_csv:
        ok = False
        for b in missing_in_csv:
            error("RTL 端口 %s 未分配引脚（CSV 缺行）" % b)
    if missing_in_rtl:
        ok = False
        for b in missing_in_rtl:
            error("CSV 分配了引脚但 RTL 无此端口: %s" % b)
    if ok:
        print("[vivado_cli] 交叉校验通过: CSV 与 RTL 端口完全对应。")
        return 0
    return 1


# ---------------------------------------------------------------- rtl 命令

def cmd_rtl_new_module(args):
    ports = vc_rtl.parse_port_spec(args.ports)
    text = vc_rtl.gen_module(args.name, ports, desc=args.desc or "",
                             out=os.path.abspath(args.out) if args.out else None)
    if not args.out:
        print(text)
    return 0


def cmd_rtl_new_tb(args):
    ports_path = os.path.abspath(args.from_rtl) if args.from_rtl else None
    if ports_path:
        _, ports_dict = vc_rtl.parse_ports_of_top(ports_path, top=args.module)
        specs = vc_rtl.ports_dict_to_specs(ports_dict)
    else:
        specs = vc_rtl.parse_port_spec(args.ports) if args.ports else []
        if not specs:
            error("需提供 --from-rtl <模块文件> 或 --ports 规格串")
            return 2
    vc_rtl.gen_tb(args.module, specs, out=os.path.abspath(args.out) if args.out else None)
    return 0


def _expand(files):
    import glob as _g
    out = []
    for f in files:
        if any(ch in f for ch in "*?"):
            out.extend(sorted(_g.glob(f)))
        else:
            out.append(f)
    return out


def cmd_rtl_lint(args):
    files = _expand(args.files)
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        for f in missing:
            error("文件不存在: %s" % f)
        return 2
    if not files:
        error("未找到任何文件")
        return 2
    rc = 0
    for f in files:
        issues = vc_rtl.lint_file(f)
        if issues:
            print("[lint] %s" % f)
            for sev, ln, msg in issues:
                print("  [%s] L%s: %s" % (sev, ln if ln else "-", msg))
                if sev == "ERROR":
                    rc = 1
        else:
            print("[lint] %s: 通过" % f)
    if args.vivado:
        env = vc_env.load_env(cwd_of(args))
        home = args.vivado_home or env.get("vivado_home")
        if not home:
            error("需要 Vivado 环境（env set）或 --vivado-home 来调用 xvlog")
            return 2
        ok, output = vc_rtl.xvlog_check(home, files)
        print(output)
        if not ok:
            rc = 1
    return rc


def cmd_rtl_list(args):
    rows = vc_rtl.list_modules(_expand(args.files))
    for f, name, nports in rows:
        print("%-40s %-30s ports=%d" % (f, name, nports))
    if not rows:
        print("[vivado_cli] 未解析到模块。")
    return 0


# ---------------------------------------------------------------- 主入口

def build_parser():
    ap = argparse.ArgumentParser(
        prog="vivado_cli",
        description="Vivado 2018 全工作流 CLI skill（工程/引脚/RTL/综合/时序/实现/烧写）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cwd", default=".", help="工程/状态目录（默认当前目录；所有输出强制非系统盘）")
    ap.add_argument("--allow-system-drive", action="store_true",
                    help="允许写入系统盘（默认禁止，防止污染 C 盘）")
    sub = ap.add_subparsers(dest="module", required=True)

    vc_env.register(sub)

    p = sub.add_parser("pins", help="引脚映射管理（CSV <-> XDC，纯本地）")
    sp = p.add_subparsers(dest="action", required=True)
    n = sp.add_parser("new", help="生成引脚表 CSV 模板")
    n.add_argument("--out", default="pins.csv")
    n.add_argument("--force", action="store_true")
    n.set_defaults(func=cmd_pins_new)
    a = sp.add_parser("apply", help="校验 CSV 并生成 XDC")
    a.add_argument("--csv", required=True)
    a.add_argument("--out", default="pins.xdc")
    a.add_argument("--part", default=None, help="仅写入注释")
    a.add_argument("--note", default=None)
    a.add_argument("--force", action="store_true")
    a.set_defaults(func=cmd_pins_apply)
    i = sp.add_parser("import", help="从既有 XDC 反向导入 CSV")
    i.add_argument("--xdc", required=True)
    i.add_argument("--out", default="pins.csv")
    i.set_defaults(func=cmd_pins_import)
    c = sp.add_parser("check", help="CSV 静态校验（重复引脚/端口、iostandard 等）")
    c.add_argument("--csv", required=True)
    c.set_defaults(func=cmd_pins_check)
    x = sp.add_parser("crosscheck", help="CSV 与 RTL 顶层端口交叉校验")
    x.add_argument("--csv", required=True)
    x.add_argument("--top-rtl", required=True, help="顶层模块 .v 文件")
    x.add_argument("--top", default=None, help="模块名（文件含多模块时）")
    x.set_defaults(func=cmd_pins_crosscheck)

    p = sub.add_parser("rtl", help="Verilog 开发辅助")
    sp = p.add_subparsers(dest="action", required=True)
    m = sp.add_parser("new-module", help="生成模块模板")
    m.add_argument("--name", required=True)
    m.add_argument("--ports", required=True, help="如 'clk:in,rst_n:in,sw[3:0]:in,led[3:0]:out'")
    m.add_argument("--desc", default="")
    m.add_argument("--out", default=None)
    m.set_defaults(func=cmd_rtl_new_module)
    t = sp.add_parser("new-tb", help="生成 testbench 模板")
    t.add_argument("--module", required=True)
    t.add_argument("--from-rtl", default=None, help="从模块文件解析端口")
    t.add_argument("--ports", default=None, help="或直接给端口规格")
    t.add_argument("--out", required=True)
    t.set_defaults(func=cmd_rtl_new_tb)
    l = sp.add_parser("lint", help="启发式 lint（可选 --vivado 调 xvlog 真实编译）")
    l.add_argument("--files", nargs="+", required=True)
    l.add_argument("--vivado", action="store_true")
    l.add_argument("--vivado-home", default=None)
    l.set_defaults(func=cmd_rtl_lint)
    ls = sp.add_parser("list", help="列出文件中的模块与端口数")
    ls.add_argument("--files", nargs="+", required=True)
    ls.set_defaults(func=cmd_rtl_list)

    vc_flow.register(sub)
    vc_report.register(sub)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    args.cwd = cwd_of(args)
    try:
        return args.func(args)
    except RuntimeError as e:
        error(str(e))
        return 2
    except KeyboardInterrupt:
        error("用户中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())
