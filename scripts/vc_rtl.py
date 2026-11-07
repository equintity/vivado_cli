# -*- coding: utf-8 -*-
"""vc_rtl -- Verilog 开发辅助：模块/测试台模板生成、端口解析、启发式 lint、模块清单。

注意：lint 为启发式检查；真正的语法级检查用 `rtl lint --vivado`（调用 Vivado 自带
xvlog 编译器）。两者互补。
"""

import io
import os
import re
from datetime import date

from vc_util import error, info, run_cmd, warn

# ---------------------------------------------------------------- 端口规格

PORT_SPEC_RE = re.compile(r"^(\w+)(?:\[(\d+):(\d+)\])?:(in|out|inout)$")


def parse_port_spec(spec):
    """解析 'clk:in,sw[3:0]:in,led[3:0]:out' -> [(name, hi, lo, dir), ...]。

    width=1 时 hi=lo=None。
    """
    ports = []
    for tok in [t.strip() for t in spec.split(",") if t.strip()]:
        m = PORT_SPEC_RE.match(tok)
        if not m:
            raise RuntimeError("端口规格非法: %r（格式: name:dir 或 name[7:0]:dir，dir ∈ in/out/inout）" % tok)
        name, hi, lo, d = m.group(1), m.group(2), m.group(3), m.group(4)
        ports.append((name, int(hi) if hi is not None else None, int(lo) if lo is not None else None, d))
    return ports


def _norm_dir(d):
    """归一化方向词：in/input -> input, out/output -> output。"""
    return {"in": "input", "input": "input", "out": "output",
            "output": "output", "inout": "inout"}[d.lower()]


def _port_decl(name, hi, lo, d):
    kw = _norm_dir(d)
    rng = " [%d:0]" % hi if hi is not None else ""
    return "    %s%s %s" % (kw, rng, name)


def ports_dict_to_specs(ports):
    """把 parse_modules 的 {bitname: dir} 还原为 [(base, hi, None, dir)] 规格列表。

    同名多位总线取最大下标（led[0]..led[3] -> ('led', 3, None, d)）。
    """
    grouped = {}
    order = []
    for bitname, d in ports.items():
        m = re.match(r"^(\w+)\[(\d+)\]$", bitname)
        if m:
            base, idx = m.group(1), int(m.group(2))
        else:
            base, idx = bitname, None
        if base not in grouped:
            grouped[base] = [None, d]
            order.append(base)
        if idx is not None:
            if grouped[base][0] is None or idx > grouped[base][0]:
                grouped[base][0] = idx
    return [(b, grouped[b][0], None, grouped[b][1]) for b in order]


# ---------------------------------------------------------------- 模板生成

MODULE_TEMPLATE = """\
// ============================================================
// {module}.v
// 功能: {desc}
// 由 vivado_cli rtl new-module 生成 ({today})，请完成实现
// ============================================================
`timescale 1ns / 1ps

module {module} #(
    // TODO: 可选参数，例如
    // parameter integer COUNTER_W = 8
)(
{ports}
);

    // ------------------------------------------------------------
    // 内部信号
    // ------------------------------------------------------------
{signals}
    // ------------------------------------------------------------
    // TODO: 功能实现
    // 时序逻辑统一使用同步复位风格（与 Xilinx FPGA 推荐一致）:
    //   always @(posedge clk) begin
    //       if (!rst_n) begin
    //           /* 复位 */
    //       end else begin
    //           /* 逻辑 */
    //       end
    //   end
    // ------------------------------------------------------------

endmodule
"""

TB_TEMPLATE = """\
// ============================================================
// tb_{module}.v -- {module} 的测试台
// 由 vivado_cli rtl new-tb 生成 ({today})
// 用法: 将本文件加入 Vivado 工程 sim_1 fileset，
//       set as top 后 Run Simulation（vivado_cli 不代跑仿真器）
// ============================================================
`timescale 1ns / 1ps

module tb_{module};

    localparam CLK_PERIOD = 10; // ns -> 100 MHz

{dut_regs}
{dut_wires}
    // 被测模块
    {module} u_dut (
{dut_conns}
    );

    // 时钟生成
    initial clk = 1'b0;
    always #(CLK_PERIOD/2) clk = ~clk;

    // 复位与激励
    initial begin
        rst_n = 1'b0;
{init_stims}
        #100;
        rst_n = 1'b1;

        // TODO: 按 DUT 协议编写激励

        #1000;
        $display("SIM_DONE: tb_{module} finished at %0t", $time);
        $finish;
    end

endmodule
"""


def gen_module(name, ports, desc="", out=None):
    """生成 Verilog 模块文本并（可选）写出文件。返回文本。"""
    ports_txt = ",\n".join(_port_decl(n, hi, lo, d) for n, hi, lo, d in ports) or "    // TODO: 端口"
    signals = []
    for n, hi, lo, d in ports:
        d = _norm_dir(d)
        if d == "output":
            rng = " [%d:0]" % hi if hi is not None else ""
            signals.append("    reg%s r_%s;" % (rng, n))
        elif d == "inout":
            rng = " [%d:0]" % hi if hi is not None else ""
            signals.append("    wire%s io_%s;" % (rng, n))
    text = MODULE_TEMPLATE.format(
        module=name, desc=desc or "(TODO: 描述功能)", today=date.today().isoformat(),
        ports=ports_txt, signals="\n".join(signals) or "    // TODO: 内部信号声明\n",
    )
    if out:
        _write(out, text)
    return text


def gen_tb(module, ports, out=None):
    """根据模块端口生成 testbench 文本并（可选）写出。"""
    regs, wires, conns, inits = [], [], [], []
    for n, hi, lo, d in ports:
        d = _norm_dir(d)
        rng = "[%d:0] " % hi if hi is not None else ""
        if d == "input":
            regs.append("    reg  %s%s;" % (rng, n))
            conns.append("        .%s(%s)" % (n, n))
            init_val = "{%d{1'b0}}" % (hi + 1) if hi is not None else "1'b0"
            inits.append("        %s = %s;" % (n, init_val))
        else:
            wires.append("    wire %s%s;" % (rng, n))
            conns.append("        .%s(%s)" % (n, n))
    text = TB_TEMPLATE.format(
        module=module, today=date.today().isoformat(),
        dut_regs="\n".join(regs), dut_wires="\n".join(wires),
        dut_conns=",\n".join(conns),
        init_stims="\n".join(inits) or "        // TODO",
    )
    if out:
        _write(out, text)
    return text


def _write(path, text):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)
    info("已生成: %s" % path)


# ---------------------------------------------------------------- 端口解析

_MOD_RE = re.compile(r"\bmodule\s+(\w+)\s*(?:#\((.*?)\))?\s*\((.*?)\)\s*;", re.DOTALL)
_ITEM_RE = re.compile(
    r"^\s*(input|output|inout)\b\s*(?:wire|reg|logic)?\s*(?:\[(\d+)\s*:\s*(\d+)\])?\s*(\w+)\s*$",
    re.IGNORECASE,
)
BODY_ITEM_RE = re.compile(
    r"^\s*(input|output|inout)\s+(?:wire|reg|logic)?\s*(?:\[(\d+)\s*:\s*(\d+)\])?\s*(\w+)\s*;",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_comments(text):
    text = re.sub(r"//[^\n]*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def _add_bits(ports, direction, hi, lo, base):
    if hi is not None:
        h, l = int(hi), int(lo)
        step = 1 if h >= l else -1
        for b in range(l, h + step, step):
            ports["%s[%d]" % (base, b)] = direction
    else:
        ports[base] = direction


def parse_modules(path):
    """解析 Verilog 文件，返回 [(module_name, {bitname: direction}), ...]。

    bitname: 总线逐位展开为 led[0]..；宽度 1 为裸名。支持 ANSI 头端口；
    非 ANSI（module 体内另写 input/output）按 best-effort 解析。
    """
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        text = _strip_comments(f.read())
    result = []
    for m in _MOD_RE.finditer(text):
        name = m.group(1)
        decl = m.group(3) or ""
        body = text[m.end():]
        ports = {}
        # ANSI 头：按顶层逗号切分
        for item in re.split(r",(?![^()]*\))", decl):
            im = _ITEM_RE.match(item.strip())
            if im:
                _add_bits(ports, im.group(1).lower(), im.group(2), im.group(3), im.group(4))
        # 非 ANSI 体声明
        for bm in BODY_ITEM_RE.finditer(body):
            _add_bits(ports, bm.group(1).lower(), bm.group(2), bm.group(3), bm.group(4))
        result.append((name, ports))
    return result


def parse_ports_of_top(path, top=None):
    """返回 (top_name, {bitname: direction})；文件含多个模块时取第一个或指定 top。"""
    mods = parse_modules(path)
    if not mods:
        raise RuntimeError("文件中未找到 module 声明: %s" % path)
    if top:
        for name, ports in mods:
            if name == top:
                return name, ports
        raise RuntimeError("未找到模块 %s 于 %s" % (top, path))
    return mods[0]


# ---------------------------------------------------------------- 启发式 lint

_BLOCK_ASSIGN_RE = re.compile(r"(?<![<>=!])=(?!=)")


def lint_file(path):
    """启发式 lint，返回 [(severity, lineno, msg), ...]。severity: ERROR/WARN/INFO。

    检查项（保守，避免误报）：
      * module/endmodule 配对、数量
      * 模块名与文件名一致性
      * 时序块中的阻塞赋值
      * always 时序块缺少复位分支（INFO）
      * begin/end 粗配对
    """
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    issues = []
    text = _strip_comments(raw)
    lines = text.splitlines()

    fname = os.path.splitext(os.path.basename(path))[0]
    n_mod = len(re.findall(r"\bmodule\b", text))
    n_endmod = len(re.findall(r"\bendmodule\b", text))
    if n_mod == 0:
        issues.append(("WARN", 0, "未找到 module 声明"))
    else:
        if n_mod != n_endmod:
            issues.append(("ERROR", 0, "module(%d)/endmodule(%d) 数量不配对" % (n_mod, n_endmod)))
        mods = re.findall(r"\bmodule\s+(\w+)", text)
        if len(mods) > 1:
            issues.append(("INFO", 0, "一个文件包含多个模块: %s（建议一文件一模块）" % ",".join(mods)))
        if mods and mods[0].lower() != fname.lower():
            issues.append(("WARN", 0, "模块名 %s 与文件名 %s 不一致" % (mods[0], fname)))

    in_seq = False
    block_txt = ""
    n_begin = len(re.findall(r"\bbegin\b", text))
    # end 数量：排除 endcase/endmodule/endfunction/endtask 关键字前缀
    n_end = len(re.findall(r"\bend\b", text))
    if n_begin > 0 and n_end < n_begin:
        issues.append(("WARN", 0, "begin(%d)/end(%d) 数量不匹配，请人工确认" % (n_begin, n_end)))

    for i, line in enumerate(lines, 1):
        low = line.lower()
        if re.search(r"always\s*@\s*\(\s*(posedge|negedge)", low):
            in_seq = True
            block_txt = line
            continue
        if re.search(r"always\s*@\s*\(\s*\*", low):
            in_seq = False
            continue
        if in_seq:
            block_txt += " " + line
            if re.search(r"\bend\b", low):
                if not re.search(r"rst|reset|clr|clear", block_txt.lower()):
                    issues.append(("INFO", i, "时序块内未发现 rst/reset 信号（若无复位需求可忽略）"))
                in_seq = False
                block_txt = ""
            elif _BLOCK_ASSIGN_RE.search(line) and not re.search(r"\bfor\b\s*\(", low):
                issues.append(("ERROR", i, "时序块中出现阻塞赋值 '='（应使用 '<='）: %s" % line.strip()[:60]))
    return issues


def list_modules(paths):
    """枚举多个文件中的模块: [(file, module, port_count), ...]"""
    out = []
    for p in paths:
        try:
            for name, ports in parse_modules(p):
                out.append((p, name, len(ports)))
        except Exception as e:
            warn("解析失败 %s: %s" % (p, e))
    return out


def xvlog_check(vivado_home, files):
    """调用 Vivado 自带 xvlog 做真实语法检查。返回 (ok, output)。"""
    xvlog = os.path.join(vivado_home, "bin", "xvlog.bat")
    if not os.path.isfile(xvlog):
        return False, "未找到 %s" % xvlog
    rc, out, errout = run_cmd([xvlog, "-sv"] + list(files), timeout=300)
    return rc == 0, out + errout
