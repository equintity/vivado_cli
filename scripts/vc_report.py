# -*- coding: utf-8 -*-
"""vc_report -- Vivado 报告与日志解析：日志摘要、时序报告、利用率报告、时序优化建议。

支持的输入（均为 Vivado 2018.2 文本报告格式）:
  * vivado.log / runme.log          -> 日志摘要（ERROR/CRITICAL WARNING/WARNING 统计）
  * report_timing_summary 输出      -> WNS/TNS/WHS/THS、逐时钟、违例路径
  * report_utilization 输出         -> 关键资源利用
"""

import io
import os
import re

from vc_util import info

# ---------------------------------------------------------------- 日志摘要

_LOG_LEVEL_RE = re.compile(r"^(ERROR|CRITICAL WARNING|WARNING):\s*(.*)$")
_DIGITS_RE = re.compile(r"\d+")


def parse_log(path, max_samples=10):
    """解析 Vivado 日志，返回 dict:
    {counts: {...}, samples: {level: [(lineno, msg), ...]}, errors_tail: [...]}
    """
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    counts = {"ERROR": 0, "CRITICAL WARNING": 0, "WARNING": 0}
    seen = {}
    samples = {"ERROR": [], "CRITICAL WARNING": [], "WARNING": []}
    errors_all = []
    for i, line in enumerate(lines, 1):
        m = _LOG_LEVEL_RE.match(line.strip())
        if not m:
            continue
        level, msg = m.group(1), m.group(2).strip()
        counts[level] += 1
        key = (level, _DIGITS_RE.sub("N", msg))
        if key not in seen:
            seen[key] = 1
            if len(samples[level]) < max_samples:
                samples[level].append((i, msg))
        else:
            seen[key] += 1
        if level == "ERROR":
            errors_all.append((i, msg))
    return {
        "counts": counts,
        "samples": samples,
        "errors_tail": errors_all[-max_samples:],
    }


def format_log_summary(parsed):
    c = parsed["counts"]
    out = ["日志统计: ERROR=%d, CRITICAL WARNING=%d, WARNING=%d" % (c["ERROR"], c["CRITICAL WARNING"], c["WARNING"])]
    for lvl in ("ERROR", "CRITICAL WARNING"):
        if parsed["samples"][lvl]:
            out.append("%s 样例:" % lvl)
            for lineno, msg in parsed["samples"][lvl]:
                out.append("  L%d: %s" % (lineno, msg[:160]))
    return "\n".join(out)


# ---------------------------------------------------------------- 时序报告

_NUM = r"[-+]?\d+\.?\d*"


def _to_float(tok):
    try:
        return float(tok)
    except (TypeError, ValueError):
        return None


def parse_timing_summary(path):
    """解析 report_timing_summary 输出。

    返回 dict:
      wns, tns, whs, ths          -- Design Timing Summary 总体指标
      per_clock: [(clk, wns, tns, whs)]  -- Intra Clock Table 逐时钟
      violated_paths: [(slack, source, src_clk, dest, dst_clk, data_delay, levels)]
    """
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    res = {"wns": None, "tns": None, "whs": None, "ths": None, "per_clock": [], "violated_paths": []}

    # --- Design Timing Summary 总表
    for i, line in enumerate(lines):
        if "Design Timing Summary" in line:
            # 表头可能在接下来几行；找以 WNS 开头的头，然后取其后的数值行
            for j in range(i + 1, min(i + 8, len(lines))):
                if lines[j].strip().startswith("WNS"):
                    for k in range(j + 1, min(j + 4, len(lines))):
                        toks = lines[k].split()
                        if toks and _to_float(toks[0]) is not None:
                            res["wns"] = _to_float(toks[0])
                            res["tns"] = _to_float(toks[1]) if len(toks) > 1 else None
                            res["whs"] = _to_float(toks[4]) if len(toks) > 4 else None
                            res["ths"] = _to_float(toks[5]) if len(toks) > 5 else None
                            break
                    break
            break

    # --- Intra Clock Table 逐时钟
    for i, line in enumerate(lines):
        if "Intra Clock Table" in line:
            for j in range(i + 1, min(i + 12, len(lines))):
                toks = lines[j].split()
                if len(toks) >= 11 and _to_float(toks[1]) is not None:
                    res["per_clock"].append((toks[0], _to_float(toks[1]), _to_float(toks[2]),
                                             _to_float(toks[5]) if len(toks) > 5 else None))
                elif res["per_clock"] and (not toks or _to_float(toks[1] if len(toks) > 1 else "") is None):
                    break
            break

    # --- 违例/关键路径（Slack 块）
    i = 0
    while i < len(lines):
        m = re.match(r"\s*Slack\s*\((MET|VIOLATED)\)\s*:\s*(" + _NUM + r")ns", lines[i])
        if m:
            block = {"slack": float(m.group(2)), "violated": m.group(1) == "VIOLATED",
                     "source": "", "src_clk": "", "dest": "", "dst_clk": "",
                     "data_delay": "", "levels": ""}
            for j in range(i + 1, min(i + 20, len(lines))):
                l2 = lines[j]
                m2 = re.match(r"\s*Source:\s*(.*)", l2)
                if m2:
                    block["source"] = m2.group(1).strip()
                m2 = re.match(r"\s*Destination:\s*(.*)", l2)
                if m2:
                    block["dest"] = m2.group(1).strip()
                m2 = re.match(r"\s*Source Clock:\s*(.*)", l2)
                if m2:
                    block["src_clk"] = m2.group(1).split("(")[0].strip()
                m2 = re.match(r"\s*Destination Clock:\s*(.*)", l2)
                if m2:
                    block["dst_clk"] = m2.group(1).split("(")[0].strip()
                m2 = re.match(r"\s*Data Path Delay:\s*([^\s(]+)", l2)
                if m2:
                    block["data_delay"] = m2.group(1)
                m2 = re.match(r"\s*Logic Levels:\s*(\d+)", l2)
                if m2:
                    block["levels"] = m2.group(1)
                    break
            res["violated_paths"].append(block)
        i += 1
    return res


def format_timing(res, max_paths=8):
    out = []
    if res["wns"] is None:
        out.append("未能解析出 Design Timing Summary（报告可能不含该表或格式变化）")
    else:
        out.append("WNS=%.3fns  TNS=%.3fns  WHS=%.3fns  THS=%.3fns  => %s" % (
            res["wns"], res["tns"] or 0.0, res["whs"] or 0.0, res["ths"] or 0.0,
            "时序收敛" if (res["wns"] >= 0 and (res["whs"] or 0) >= 0) else "存在违例"))
    if res["per_clock"]:
        out.append("逐时钟 WNS:")
        for clk, wns, tns, whs in res["per_clock"]:
            out.append("  %-16s WNS=%s TNS=%s WHS=%s" % (clk, wns, tns, whs))
    viol = [p for p in res["violated_paths"] if p["violated"]]
    if viol:
        out.append("违例路径 %d 条（最多显示 %d）:" % (len(viol), max_paths))
        for p in viol[:max_paths]:
            out.append("  slack=%sns  %s [%s] -> %s [%s]  逻辑级=%s  数据延迟=%s" % (
                p["slack"], p["source"][:40], p["src_clk"] or "?", p["dest"][:40],
                p["dst_clk"] or "?", p["levels"] or "?", p["data_delay"] or "?"))
    return "\n".join(out)


# ---------------------------------------------------------------- 利用率报告

_UTIL_RE = re.compile(r"^\s*(Slice LUTs[^\|]*|CLB LUTs|Slice Registers[^\|]*|Block RAM Tile|RAMB36[^\|]*|RAMB18[^\|]*|DSPs|Bonded IOB|BUFGCTRL|MMCM[^\|]*|PLL[^\|]*|LUT as Logic|LUT as Memory)\s*\|\s*(" + _NUM + r")\s*\|?\s*(" + _NUM + r")?\s*\|?\s*(" + _NUM + r")?")


def parse_utilization(path):
    """解析 report_utilization 输出 -> [(resource, used, total_or_None), ...]"""
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    rows = []
    for line in lines:
        m = _UTIL_RE.match(line)
        if m:
            rows.append((m.group(1).strip(), _to_float(m.group(2)),
                         _to_float(m.group(3)) if m.group(3) else None))
    return rows


def format_utilization(rows):
    if not rows:
        return "未解析到资源表（报告可能为空或格式不同）"
    out = ["资源利用率:"]
    for name, used, total in rows:
        pct = (" (%.1f%%)" % (used / total * 100)) if total else ""
        out.append("  %-20s %s%s" % (name, used, "/%s" % total if total else ""))
    return "\n".join(out)


# ---------------------------------------------------------------- 优化建议引擎

def suggest_timing(res, wnsthreshold=0.0):
    """基于解析结果给出可操作的优化建议（规则引擎，返回 [str]）。"""
    tips = []
    wns = res["wns"]
    if wns is None:
        tips.append("未获得 WNS，请确认已生成 timing_summary 报告。")
        return tips
    viol = [p for p in res["violated_paths"] if p["violated"]]
    if wns < wnsthreshold:
        tips.append("WNS=%.3fns < 阈值 %.2fns：时序未收敛。" % (wns, wnsthreshold))
        inter = [p for p in viol if p["src_clk"] and p["dst_clk"] and p["src_clk"] != p["dst_clk"]]
        io_paths = [p for p in viol if "(port" in p["source"].lower() or "(port" in p["dest"].lower()]
        deep = [p for p in viol if p["levels"] and int(p["levels"]) >= 8]
        netheavy = [p for p in viol if p["data_delay"] and p["levels"] and int(p["levels"]) <= 4]
        if inter:
            tips.append("  [跨时钟域] %d 条违例路径跨时钟（如 %s -> %s）：确认是真实路径还是伪路径；"
                        "异步单比特用两级同步器，多比特总线用握手/异步 FIFO；"
                        "确认无路径约束用 set_clock_groups -asynchronous 或 set_false_path。" %
                        (len(inter), inter[0]["src_clk"], inter[0]["dst_clk"]))
        if io_paths:
            tips.append("  [IO 路径] %d 条违例涉及顶层端口：核对 set_input_delay/set_output_delay 是否"
                        "按真实板级时序设置（可先放宽验证内部时序后再收紧）。" % len(io_paths))
        if deep:
            tips.append("  [深组合逻辑] %d 条路径逻辑级 >= 8（如 %s，%s 级）：优先插入流水线寄存器"
                        "拆分组合路径；也可尝试综合 retiming。" %
                        (len(deep), deep[0]["source"][:50], deep[0]["levels"]))
        if netheavy:
            tips.append("  [布线主导] %d 条路径逻辑级 <= 4 但数据延迟大（如 %s）：多为高扇出/长布线，"
                        "考虑寄存器复制（set_property MAX_FANOUT N）或实现阶段 NetDelay 策略。" %
                        (len(netheavy), netheavy[0]["source"][:50]))
        if not (inter or io_paths or deep or netheavy):
            tips.append("  未命中细分规则：可打开 timing_summary 报告查看 Path/Source 属性后人工定位。")
        tips.append("  [策略] 可先尝试更激进的实现策略（无需改 RTL）:")
        tips.append("    impl run --strategy Performance_ExplorePostRoutePhysOpt --project <xpr>")
        tips.append("  [综合级] retiming + 高性能综合策略:")
        tips.append("    synth run --strategy Flow_PerfOptimized_high --retiming --project <xpr>")
    else:
        tips.append("WNS=%.3fns 达标。若需更大裕量，仍可评估关键路径（见 timing report 输出的最差路径）。" % wns)
    if res["whs"] is not None and res["whs"] < 0:
        tips.append("  [保持时间] WHS=%.3fns < 0：优先用实现策略修正（Performance_WLBlockPlacement），"
                    "并检查跨域路径是否误设了过紧的约束。" % res["whs"])
    return tips


# ---------------------------------------------------------------- 命令实现

def cmd_summary(args):
    if not os.path.isfile(args.log):
        error("日志不存在: %s" % args.log)
        return 2
    parsed = parse_log(args.log)
    print(format_log_summary(parsed))
    # 同步解析 vivado_cli 阶段标记
    return 0


def cmd_timing_parse(args):
    if not os.path.isfile(args.rpt):
        error("报告不存在: %s" % args.rpt)
        return 2
    res = parse_timing_summary(args.rpt)
    print(format_timing(res))
    if args.suggest:
        print("\n优化建议:")
        for t in suggest_timing(res, args.wns_threshold):
            print(t)
    return 0


def cmd_util(args):
    if not os.path.isfile(args.rpt):
        error("报告不存在: %s" % args.rpt)
        return 2
    print(format_utilization(parse_utilization(args.rpt)))
    return 0


def register(sub):
    p = sub.add_parser("report", help="日志/报告解析")
    sp = p.add_subparsers(dest="action", required=True)

    s = sp.add_parser("summary", help="统计 vivado.log / runme.log 的错误与警告")
    s.add_argument("--log", required=True)
    s.set_defaults(func=cmd_summary)

    t = sp.add_parser("timing", help="解析 report_timing_summary 输出（可附建议）")
    t.add_argument("--rpt", required=True, help="timing_summary_*.rpt 路径")
    t.add_argument("--suggest", action="store_true", help="附带优化建议")
    t.add_argument("--wns-threshold", type=float, default=0.0, help="WNS 阈值（默认 0）")
    t.set_defaults(func=cmd_timing_parse)

    u = sp.add_parser("util", help="解析 report_utilization 输出")
    u.add_argument("--rpt", required=True)
    u.set_defaults(func=cmd_util)
