# -*- coding: utf-8 -*-
"""vc_flow -- Vivado 批处理流程编排：工程创建/源管理/综合/实现/烧写/HDF 导出/BD 生成。

执行模型：每阶段生成一个驱动 Tcl（写入工程目录 vc_work/），以
`vivado.bat -mode batch` 调用；工程状态由 Vivado project mode 的 .xpr 持久化，
因此各阶段可独立重入。阶段结果通过 `VC_XXX:` 标记行回传给 Python。
"""

import glob
import io
import os

import vc_report
from vc_util import (error, guard_writable_dir, info, parse_markers,
                     run_cmd, safe_tcl_value, to_tcl_path, tail, warn)

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TCL_ROOT = to_tcl_path(os.path.join(SKILL_ROOT, "tcl"))

# 阶段 -> Tcl 脚本（相对 tcl/ 根）
STAGE_TCL = {
    "create_project": "flow/create_project.tcl",
    "add_sources": "flow/add_sources.tcl",
    "open_project": "flow/open_project.tcl",
    "run_synth": "flow/run_synth.tcl",
    "run_impl": "flow/run_impl.tcl",
    "export_hwdef": "flow/export_hwdef.tcl",
    "program": "flow/program.tcl",
    "bd_zynq": "ps/zynq7000_ps7.tcl",
    "pin_check": "pins/pin_vivado_check.tcl",
}

STAGE_TIMEOUT = {
    "create_project": 600, "add_sources": 600, "open_project": 600,
    "run_synth": 7200, "run_impl": 14400, "export_hwdef": 1800,
    "program": 900, "bd_zynq": 1800, "pin_check": 900,
}


def vivado_bin(env):
    home = env.get("vivado_home")
    if not home:
        raise RuntimeError("未配置 Vivado。先运行: python scripts/vivado_cli.py env set --vivado-home <目录>")
    bat = os.path.join(home, "bin", "vivado.bat")
    if not os.path.isfile(bat):
        raise RuntimeError("vivado.bat 不存在: %s" % bat)
    return bat


def run_stage(env, stage, variables, cwd, timeout=None, quiet=False):
    """执行一个 Vivado 批处理阶段。

    variables: {k: v}，将生成 `set vc_<k> {v}`。
    返回 dict: {rc, markers(tag->first value), marker_list, log, tail}
    """
    workdir = os.path.join(cwd, "vc_work")
    os.makedirs(workdir, exist_ok=True)
    driver = os.path.join(workdir, "%s.tcl" % stage)
    lines = ["# 由 vivado_cli 生成: stage=%s" % stage]
    for k, v in sorted(variables.items()):
        v = str(v)
        safe_tcl_value(v)
        lines.append("set vc_%s {%s}" % (k, v))
    lines.append("set vc_tcl_root {%s}" % TCL_ROOT)
    lines.append("source [file join $vc_tcl_root lib common.tcl]")
    lines.append("source [file join $vc_tcl_root %s]" % STAGE_TCL[stage].replace("/", " "))
    with io.open(driver, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    log = os.path.join(workdir, "%s.log" % stage)
    jou = os.path.join(workdir, "%s.jou" % stage)
    cmd = [vivado_bin(env), "-mode", "batch", "-source", to_tcl_path(driver),
           "-notrace", "-log", to_tcl_path(log), "-journal", to_tcl_path(jou)]
    if not quiet:
        info("执行阶段 %s（批处理，超时 %ss）..." % (stage, timeout or STAGE_TIMEOUT.get(stage, 3600)))
    rc, out, errout = run_cmd(cmd, cwd=cwd, timeout=timeout or STAGE_TIMEOUT.get(stage, 3600))
    log_text = ""
    if os.path.isfile(log):
        with io.open(log, "r", encoding="utf-8", errors="replace") as f:
            log_text = f.read()
    combined = log_text + "\n" + out + "\n" + errout
    marker_list = parse_markers(combined)
    markers = {}
    for tag, val in marker_list:
        markers.setdefault(tag, val)
    return {"rc": rc, "markers": markers, "marker_list": marker_list,
            "log": log, "tail": tail(combined, 40), "output": combined}


def fail_stage(stage, result, hints=None):
    error("阶段 %s 失败 (rc=%s)" % (stage, result["rc"]))
    for tag, val in result["marker_list"]:
        if tag == "ERROR":
            error("Vivado: %s" % val)
    parsed = vc_report.parse_log(result["log"]) if os.path.isfile(result["log"]) else None
    if parsed:
        print(vc_report.format_log_summary(parsed))
    if hints:
        for h in hints:
            info("提示: %s" % h)
    info("完整日志: %s" % result["log"])


# ================================================================ env helpers

def load_env_or_fail(cwd):
    import vc_env
    data = vc_env.load_env(cwd)
    if not data.get("vivado_home"):
        raise RuntimeError("未配置 Vivado。先运行: env set --vivado-home <Vivado安装目录>")
    return data


def save_project_state(cwd, name, proj_dir, xpr, part=None):
    import vc_env
    data = vc_env.load_env(cwd)
    data["project"] = {"name": name, "dir": os.path.abspath(proj_dir).replace("\\", "/"),
                       "xpr": os.path.abspath(xpr).replace("\\", "/")}
    if part:
        data.setdefault("part", part)
    vc_env.save_env(cwd, data)


def get_project(cwd, args_project=None):
    """返回 (xpr_path, env_data)；args_project 优先，其次状态文件。"""
    env = load_env_or_fail(cwd)
    xpr = args_project or (env.get("project") or {}).get("xpr")
    if not xpr or not os.path.isfile(xpr):
        raise RuntimeError("未找到工程 .xpr（用 project create 创建或 --project 显式指定）")
    return xpr, env


# ================================================================ project

def cmd_project_create(args):
    proj_dir = guard_writable_dir(args.dir, args.allow_system_drive)
    os.makedirs(proj_dir, exist_ok=True)
    xpr_expected = os.path.join(proj_dir, args.name + ".xpr")
    if os.path.isfile(xpr_expected) and not args.overwrite:
        error("工程已存在: %s（确认覆盖用 --overwrite）" % xpr_expected)
        return 2
    env = load_env_or_fail(args.cwd)
    part = args.part or env.get("part")
    if not part and not args.board:
        error("必须提供 --part <器件>（或 --board <板卡>），例如 --part xc7a35tcpg236-1")
        return 2
    res = run_stage(env, "create_project",
                    {"name": args.name, "dir": to_tcl_path(proj_dir),
                     "part": part or "", "board": args.board or ""},
                    cwd=proj_dir, timeout=args.timeout)
    if res["rc"] != 0 or "XPR_PATH" not in res["markers"]:
        fail_stage("create_project", res, ["检查器件名是否为 2018.2 支持的 part（如 xc7a35tcpg236-1）",
                                           "检查磁盘空间与目录权限"])
        return 1
    xpr = res["markers"]["XPR_PATH"]
    save_project_state(args.cwd, args.name, proj_dir, xpr, part)
    info("工程创建成功: %s" % xpr)
    info("下一步: project add-src 添加 RTL，pins new/apply 添加引脚约束，synth run 综合")
    return 0


def cmd_project_add_src(args):
    xpr, env = get_project(args.cwd, args.project)
    proj_dir = os.path.dirname(xpr)
    files = []
    for pat in args.files:
        hits = sorted(glob.glob(pat)) if any(ch in pat for ch in "*?") else [pat]
        for h in hits:
            if not os.path.isfile(os.path.abspath(h)):
                error("文件不存在: %s" % h)
                return 2
            files.append(to_tcl_path(h))
    if not files:
        error("未提供任何源文件")
        return 2
    res = run_stage(env, "add_sources",
                    {"xpr": to_tcl_path(xpr), "files": "|".join(files),
                     "fileset": args.fileset, "top": args.top or ""},
                    cwd=proj_dir, timeout=args.timeout)
    if res["rc"] != 0:
        fail_stage("add_sources", res)
        return 1
    info("已添加 %d 个文件到 %s%s" % (len(files), args.fileset, "，top=%s" % args.top if args.top else ""))
    return 0


def cmd_project_open(args):
    xpr = os.path.abspath(args.xpr)
    if not os.path.isfile(xpr):
        error(".xpr 不存在: %s" % xpr)
        return 2
    name = os.path.splitext(os.path.basename(xpr))[0]
    save_project_state(args.cwd, name, os.path.dirname(xpr), xpr)
    info("已登记当前工程: %s" % xpr)
    info("后续命令（synth/impl/...）默认作用于该工程。")
    return 0


def cmd_project_status(args):
    xpr, env = get_project(args.cwd, args.project)
    proj_dir = os.path.dirname(xpr)
    info("工程: %s" % xpr)
    runs_dir = os.path.join(proj_dir, os.path.splitext(os.path.basename(xpr))[0] + ".runs")
    synth_dir = os.path.join(runs_dir, "synth_1")
    impl_dir = os.path.join(runs_dir, "impl_1")
    def mark(path):
        return "OK " if os.path.exists(path) else "-- "
    info("  综合  [{}] synth_1/runme.log".format(mark(os.path.join(synth_dir, "runme.log"))))
    info("  实现  [{}] impl_1/runme.log".format(mark(os.path.join(impl_dir, "runme.log"))))
    bits = sorted(glob.glob(os.path.join(impl_dir, "*.bit")))
    info("  比特流 %s" % (", ".join(os.path.basename(b) for b in bits) if bits else "(无)"))
    hdf = sorted(glob.glob(os.path.join(proj_dir, "**", "*.hdf"), recursive=True))
    if hdf:
        info("  HDF   %s" % ", ".join(os.path.basename(h) for h in hdf))
    rpt_dir = os.path.join(proj_dir, "vc_reports")
    if os.path.isdir(rpt_dir):
        info("  报告  %s" % ", ".join(sorted(os.listdir(rpt_dir))))
    vlog = os.path.join(proj_dir, "vc_work")
    if os.path.isdir(vlog):
        logs = sorted(os.listdir(vlog))
        if logs:
            info("  阶段日志 %s" % ", ".join(logs))
    return 0


# ================================================================ synth / impl / timing

def cmd_synth_run(args):
    xpr, env = get_project(args.cwd, args.project)
    proj_dir = os.path.dirname(xpr)
    res = run_stage(env, "run_synth",
                    {"xpr": to_tcl_path(xpr), "jobs": args.jobs,
                     "strategy": args.strategy or "", "retiming": "1" if args.retiming else "0",
                     "write_dcp": "1" if args.write_dcp else "0",
                     "rpt_dir": to_tcl_path(os.path.join(proj_dir, "vc_reports"))},
                    cwd=proj_dir, timeout=args.timeout)
    if res["rc"] != 0 or res["markers"].get("SYNTH_STATUS", "") == "":
        fail_stage("run_synth", res, ["用 report summary --log vc_work/run_synth.log 查看详细错误",
                                      "确认约束文件语法（xdc）与 RTL 顶层设置"])
        return 1
    info("综合完成: %s" % res["markers"].get("SYNTH_STATUS"))
    rpt = os.path.join(proj_dir, "vc_reports", "timing_summary_synth.rpt")
    if os.path.isfile(rpt):
        res2 = vc_report.parse_timing_summary(rpt)
        print(vc_report.format_timing(res2))
        print("\n优化建议:")
        for t in vc_report.suggest_timing(res2):
            print(t)
        info("时序门限检查: 若 WNS<0，建议先 timing 优化循环，再进入 impl。")
    return 0


def cmd_impl_run(args):
    xpr, env = get_project(args.cwd, args.project)
    proj_dir = os.path.dirname(xpr)
    res = run_stage(env, "run_impl",
                    {"xpr": to_tcl_path(xpr), "jobs": args.jobs,
                     "bitstream": "1" if args.to_bitstream else "0",
                     "strategy": args.strategy or "",
                     "phys_opt": "1" if args.phys_opt else "0",
                     "rpt_dir": to_tcl_path(os.path.join(proj_dir, "vc_reports"))},
                    cwd=proj_dir, timeout=args.timeout)
    if res["rc"] != 0:
        fail_stage("run_impl", res, ["先确认综合已完成（synth run）",
                                     "时序违例时可尝试 --phys-opt 或 Performance 系列策略"])
        return 1
    info("实现完成: %s" % res["markers"].get("IMPL_STATUS", ""))
    if "BIT_PATH" in res["markers"]:
        info("比特流: %s" % res["markers"]["BIT_PATH"])
    rpt = os.path.join(proj_dir, "vc_reports", "timing_summary_impl.rpt")
    if os.path.isfile(rpt):
        res2 = vc_report.parse_timing_summary(rpt)
        print(vc_report.format_timing(res2))
        print("\n优化建议:")
        for t in vc_report.suggest_timing(res2):
            print(t)
    util = os.path.join(proj_dir, "vc_reports", "utilization_impl.rpt")
    if os.path.isfile(util):
        print(vc_report.format_utilization(vc_report.parse_utilization(util)))
    return 0


# ================================================================ hwdef / program

def cmd_hwdef_export(args):
    xpr, env = get_project(args.cwd, args.project)
    proj_dir = os.path.dirname(xpr)
    out = args.out or os.path.join(proj_dir, os.path.splitext(os.path.basename(xpr))[0] + ".hdf")
    res = run_stage(env, "export_hwdef",
                    {"xpr": to_tcl_path(xpr), "out": to_tcl_path(out),
                     "include_bit": "1" if args.include_bit else "0"},
                    cwd=proj_dir, timeout=args.timeout)
    if res["rc"] != 0 or "HDF_PATH" not in res["markers"]:
        fail_stage("export_hwdef", res, ["HDF 导出面向 Zynq（PS+PL）设计；纯 PL 工程直接用 .bit",
                                         "确认已运行 synth（或 impl）且设计包含 PS7"])
        return 1
    info("HDF 导出成功: %s" % res["markers"]["HDF_PATH"])
    info("2018.2 流程: 在 Xilinx SDK 中 File->New->Board Support/Application 从该 HDF 建板级包。")
    return 0


def cmd_hw_program(args):
    xpr, env = get_project(args.cwd, args.project) if args.project else (None, load_env_or_fail(args.cwd))
    bit = args.bit
    if not bit and xpr:
        proj_dir = os.path.dirname(xpr)
        hits = sorted(glob.glob(os.path.join(proj_dir, "*.runs", "impl_1", "*.bit")))
        if hits:
            bit = hits[-1]
    if not bit or not os.path.isfile(bit):
        error("未找到比特流。请 --bit 指定或先 impl run --to-bitstream")
        return 2
    proj_dir = os.path.dirname(xpr) if xpr else args.cwd
    res = run_stage(env, "program",
                    {"bit": to_tcl_path(bit), "device": args.device or ""},
                    cwd=proj_dir, timeout=args.timeout)
    if res["rc"] != 0 or "PROGRAMMED" not in res["markers"]:
        fail_stage("program", res, ["确认开发板已上电、JTAG 已连接、hw_server 可访问",
                                    "用 hw list-targets 查看在线器件"])
        return 1
    info("烧写成功: %s <= %s" % (res["markers"].get("DEVICE", ""), bit))
    return 0


def cmd_hw_targets(args):
    xpr, env = get_project(args.cwd, args.project) if args.project else (None, load_env_or_fail(args.cwd))
    res = run_stage(env, "program",
                    {"bit": "", "device": "", "list_only": "1"},
                    cwd=args.cwd, timeout=300)
    if res["rc"] != 0:
        fail_stage("list_targets", res, ["确认 hw_server 已随 Vivado 安装并运行（或插板后自动启动）"])
        return 1
    return 0


# ================================================================ PL/PS

def cmd_pl_bd_zynq(args):
    xpr, env = get_project(args.cwd, args.project)
    proj_dir = os.path.dirname(xpr)
    if args.ps_config and ("{" in args.ps_config or "}" in args.ps_config):
        error("--ps-config 含非法字符 { }（会破坏 Tcl 花括号包裹）")
        return 2
    res = run_stage(env, "bd_zynq",
                    {"xpr": to_tcl_path(xpr), "bd_name": args.bd_name,
                     "ps_config": args.ps_config or "", "ext_fclk": "1" if args.ext_fclk else "0"},
                    cwd=proj_dir, timeout=args.timeout)
    warns = [v for tag, v in res["marker_list"] if tag == "WARN"]
    for w in warns:
        warn("BD: %s" % w)
    if res["rc"] != 0 or "BD_WRAPPER" not in res["markers"]:
        fail_stage("bd_zynq", res, ["CONFIG.PCW_* 属性名请参考 2018.2 processing_system7 IP 手册",
                                    "若 BD 已存在，换 --bd-name 或先在工程中删除"])
        return 1
    info("Zynq-7000 BD 创建成功: %s（wrapper 已设为 top）" % res["markers"]["BD_WRAPPER"])
    info("下一步: 把自定义 RTL 以 AXI-Lite/普通端口挂接 BD，或直接 add-src 后 synth。")
    return 0


# ================================================================ pins (vivado-backed)

def cmd_pins_vivado_check(args):
    import vc_pins
    rows = vc_pins.read_csv(args.csv)
    local_errors = vc_pins.validate(rows)
    if local_errors:
        for e in local_errors:
            error(e)
        return 2
    env = load_env_or_fail(args.cwd)
    part = args.part or env.get("part")
    if not part:
        error("需要目标器件：传 --part <器件名> 或先用 project create 登记")
        return 2
    # 2018.2 的 get_package_pins 需设计上下文；本阶段在全新会话
    # link_design -part 建立空网表上下文，不需要 .xpr，也不启动综合引擎。
    res = run_stage(env, "pin_check",
                    {"part": part, "pairs": ";".join("%s=%s" % (r.name, r.pin) for r in rows)},
                    cwd=args.cwd, timeout=args.timeout)
    missing = [v for tag, v in res["marker_list"] if tag == "PIN_MISSING"]
    for m in missing:
        error("器件封装 %s 中不存在引脚: %s" % (part, m))
    if res["rc"] != 0:
        fail_stage("pin_check", res, ["确认器件名完整（如 xc7a35tcpg236-1）"])
        return 1
    info("器件封装校验通过: %s 上 %d 个引脚均存在" % (part, len(rows)))
    return 0


# ================================================================ workflow

def cmd_workflow_full(args):
    if args.create and not (args.name and args.dir and (args.part or args.board)):
        error("--create 模式必须提供 --name、--dir 和 --part（或 --board）")
        return 2
    rc = cmd_project_create(args) if args.create else 0
    if rc != 0:
        return rc
    rc = cmd_synth_run(args)
    if rc != 0:
        return rc
    xpr, _ = get_project(args.cwd, args.project)
    rpt = os.path.join(os.path.dirname(xpr), "vc_reports", "timing_summary_synth.rpt")
    if os.path.isfile(rpt) and not args.no_timing_gate:
        res2 = vc_report.parse_timing_summary(rpt)
        if res2["wns"] is not None and res2["wns"] < args.wns_threshold:
            if not args.continue_on_fail:
                error("WNS=%.3f 低于阈值 %.2f：已停止进入实现阶段。"
                      "优化时序后重试，或加 --continue-on-fail 忽略。" % (res2["wns"], args.wns_threshold))
                return 1
            warn("时序未达标，但按 --continue-on-fail 继续。")
    rc = cmd_impl_run(args)
    if rc != 0:
        return rc
    info("一键全流程完成。工程状态: project status")
    return 0


def register(sub):
    p = sub.add_parser("project", help="工程生命周期")
    sp = p.add_subparsers(dest="action", required=True)

    c = sp.add_parser("create", help="创建 Vivado 工程（project mode）")
    c.add_argument("--name", required=True)
    c.add_argument("--dir", required=True, help="工程目录（必须位于非系统盘）")
    c.add_argument("--part", default=None, help="器件全名，如 xc7a35tcpg236-1")
    c.add_argument("--board", default=None, help="板卡名（如 zc702/zed/ac701，与 --part 二选一）")
    c.add_argument("--overwrite", action="store_true")
    c.add_argument("--timeout", type=int, default=600)
    c.set_defaults(func=cmd_project_create, create=True)

    a = sp.add_parser("add-src", help="添加源/仿真/约束文件")
    a.add_argument("--files", nargs="+", required=True, help="文件或通配符（可多个）")
    a.add_argument("--fileset", default="sources_1", choices=["sources_1", "sim_1", "constrs_1"])
    a.add_argument("--top", default=None, help="设为该 fileset 的 top 模块名")
    a.add_argument("--project", default=None, help="xpr 路径（默认取状态文件）")
    a.add_argument("--timeout", type=int, default=600)
    a.set_defaults(func=cmd_project_add_src)

    o = sp.add_parser("open", help="登记既有工程为当前工程（写入状态文件）")
    o.add_argument("--xpr", required=True)
    o.set_defaults(func=cmd_project_open)

    s = sp.add_parser("status", help="工程进度概览（文件级，秒回）")
    s.add_argument("--project", default=None)
    s.set_defaults(func=cmd_project_status)

    # synth
    p = sub.add_parser("synth", help="综合")
    sp = p.add_subparsers(dest="action", required=True)
    r = sp.add_parser("run", help="运行综合并产出时序/利用率报告")
    r.add_argument("--project", default=None)
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--strategy", default=None, help="如 Flow_PerfOptimized_high")
    r.add_argument("--retiming", action="store_true", help="开启 STEPS.SYNTH_DESIGN.ARGS.RETIMING")
    r.add_argument("--write-dcp", action="store_true", help="保存综合后检查点 vc_reports/synth.dcp")
    r.add_argument("--timeout", type=int, default=7200)
    r.set_defaults(func=cmd_synth_run, create=False, no_timing_gate=True, wns_threshold=0.0,
                   continue_on_fail=False)

    # impl
    p = sub.add_parser("impl", help="实现（布局布线）与比特流")
    sp = p.add_subparsers(dest="action", required=True)
    r = sp.add_parser("run", help="运行实现（默认到 write_bitstream）")
    r.add_argument("--project", default=None)
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--to-bitstream", action="store_true", default=True)
    r.add_argument("--strategy", default=None, help="如 Performance_ExplorePostRoutePhysOpt")
    r.add_argument("--phys-opt", action="store_true", help="启用后布线 phys_opt 步骤")
    r.add_argument("--timeout", type=int, default=14400)
    r.set_defaults(func=cmd_impl_run)

    # hwdef
    p = sub.add_parser("hwdef", help="硬件描述导出（2018: HDF，供 Xilinx SDK 使用）")
    sp = p.add_subparsers(dest="action", required=True)
    e = sp.add_parser("export", help="导出 HDF（Zynq 设计）")
    e.add_argument("--project", default=None)
    e.add_argument("--out", default=None, help="输出 .hdf 路径（默认 <工程名>.hdf）")
    e.add_argument("--include-bit", action="store_true", help="打包比特流进 HDF（write_sysdef）")
    e.add_argument("--timeout", type=int, default=1800)
    e.set_defaults(func=cmd_hwdef_export)

    # hw
    p = sub.add_parser("hw", help="板级操作（Hardware Manager）")
    sp = p.add_subparsers(dest="action", required=True)
    g = sp.add_parser("program", help="JTAG 烧写比特流")
    g.add_argument("--bit", default=None, help="比特流路径（默认取 impl_1 最新 .bit）")
    g.add_argument("--device", default=None, help="器件名（默认取第一个）")
    g.add_argument("--project", default=None)
    g.add_argument("--timeout", type=int, default=900)
    g.set_defaults(func=cmd_hw_program)
    l = sp.add_parser("list-targets", help="列出 JTAG 链上器件")
    l.add_argument("--project", default=None)
    l.set_defaults(func=cmd_hw_targets)

    # pl
    p = sub.add_parser("pl", help="PL/PS（Zynq）设计")
    sp = p.add_subparsers(dest="action", required=True)
    b = sp.add_parser("bd-zynq", help="创建含 Zynq-7000 PS7 的 Block Design")
    b.add_argument("--bd-name", default="system")
    b.add_argument("--ps-config", default="", help="分号分隔的 CONFIG 键值，如 'PCW_UART1_PERIPHERAL_ENABLE=1;PCW_FPGA0_PERIPHERAL_FREQMHZ=100'")
    b.add_argument("--ext-fclk", action="store_true", help="把 FCLK_CLK0 引出为外部端口")
    b.add_argument("--project", default=None)
    b.add_argument("--timeout", type=int, default=1800)
    b.set_defaults(func=cmd_pl_bd_zynq)

    # pins (vivado 校验部分)
    p = sub.add_parser("pins-vivado", help="引脚约束的 Vivado 端校验")
    sp = p.add_subparsers(dest="action", required=True)
    v = sp.add_parser("check", help="校验 CSV 引脚是否存在于目标封装（无需工程，需 --part 或已登记器件）")
    v.add_argument("--csv", required=True)
    v.add_argument("--part", default=None, help="目标器件名（如 xc7a35tcpg236-1）")
    v.add_argument("--timeout", type=int, default=900)
    v.set_defaults(func=cmd_pins_vivado_check)

    # workflow
    p = sub.add_parser("workflow", help="一键组合流程")
    sp = p.add_subparsers(dest="action", required=True)
    f = sp.add_parser("full", help="创建工程(可选) -> 综合 -> 时序门限 -> 实现到比特流")
    f.add_argument("--create", action="store_true", help="先创建工程（需 --name/--dir/--part）")
    f.add_argument("--name", default=None)
    f.add_argument("--dir", default=None)
    f.add_argument("--part", default=None)
    f.add_argument("--board", default=None)
    f.add_argument("--allow-system-drive", action="store_true")
    f.add_argument("--overwrite", action="store_true")
    f.add_argument("--project", default=None)
    f.add_argument("--jobs", type=int, default=4)
    f.add_argument("--strategy", default=None)
    f.add_argument("--retiming", action="store_true")
    f.add_argument("--write-dcp", action="store_true")
    f.add_argument("--phys-opt", action="store_true")
    f.add_argument("--to-bitstream", action="store_true", default=True)
    f.add_argument("--wns-threshold", type=float, default=0.0)
    f.add_argument("--no-timing-gate", action="store_true")
    f.add_argument("--continue-on-fail", action="store_true")
    f.add_argument("--timeout", type=int, default=14400)
    f.set_defaults(func=cmd_workflow_full)
