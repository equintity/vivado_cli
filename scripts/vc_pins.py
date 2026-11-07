# -*- coding: utf-8 -*-
"""vc_pins -- 引脚映射关系管理（纯本地逻辑，不依赖 Vivado）。

CSV 规范（UTF-8，表头固定 8 列）::

    name,width,pin,iostandard,drive,slew,pulltype,comment
    clk,1,P17,LVCMOS33,,,,系统时钟
    led[0],4,P15,LVCMOS33,8,FAST,,

规则：
  * 每行代表一个端口位。宽度 1 的端口 name 不带下标；总线用 led[0]..led[N-1] 每位一行，
    width 列一律填总线总宽度 N，下标必须 < N。
  * pin 为封装引脚名（如 P17、AA3，统一大写）。
  * 差分对用两行（P/N 各一行），iostandard 填差分电平（如 LVDS_25）。
"""

import csv
import io
import os
import re
import sys

from vc_util import error, info, warn

HEADER = ["name", "width", "pin", "iostandard", "drive", "slew", "pulltype", "comment"]

PIN_NAME_RE = re.compile(r"^[A-Z]{1,2}[0-9]{1,2}$")
PORT_RE = re.compile(r"^(\w+)(?:\[(\d+)\])?$")

KNOWN_IOSTANDARD = {
    "LVCMOS12", "LVCMOS15", "LVCMOS18", "LVCMOS25", "LVCMOS33",
    "SSTL15", "SSTL15_R", "SSTL135", "SSTL135_R", "SSTL12",
    "LVDS", "LVDS_25", "LVDS_15", "MINI_LVDS_25",
    "DIFF_SSTL15", "DIFF_SSTL15_R", "DIFF_SSTL135", "DIFF_HSTL_I_18",
    "TMDS_33", "HSUL_12", "MOBILE_DDR", "HSTL_I", "HSTL_I_18",
}


class PinRow(object):
    __slots__ = ("name", "width", "pin", "iostandard", "drive", "slew", "pulltype", "comment", "line_no")

    def __init__(self, line_no, name, width, pin, iostandard, drive="", slew="", pulltype="", comment=""):
        self.line_no = line_no
        self.name = name.strip()
        self.width = int(width) if str(width).strip() else 1
        self.pin = pin.strip().upper()
        self.iostandard = iostandard.strip().upper()
        self.drive = drive.strip()
        self.slew = slew.strip().upper()
        self.pulltype = pulltype.strip().upper()
        self.comment = comment.strip()


# ---------------------------------------------------------------- CSV 读写

def read_csv(path):
    if not os.path.isfile(path):
        raise RuntimeError("引脚表不存在: %s" % path)
    rows = []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for i, record in enumerate(reader):
            if i == 0:
                head = [c.strip().lower() for c in record]
                if head[:4] != HEADER[:4]:
                    raise RuntimeError("引脚表表头不符合规范，期望以 %s 开头，实际: %s" % (",".join(HEADER), ",".join(record)))
                continue
            if not record or not any(c.strip() for c in record):
                continue
            record = list(record) + [""] * (len(HEADER) - len(record))
            rows.append(PinRow(i + 1, record[0], record[1], record[2], record[3],
                               record[4], record[5], record[6], record[7]))
    if not rows:
        raise RuntimeError("引脚表没有任何数据行: %s" % path)
    return rows


def write_csv(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for r in rows:
            w.writerow([r.name, r.width, r.pin, r.iostandard, r.drive, r.slew, r.pulltype, r.comment])
    return path


# ---------------------------------------------------------------- 校验

def validate(rows):
    """静态校验，返回错误列表（空列表 = 通过）。"""
    errors = []
    seen_port_bit = {}
    seen_pin = {}
    for r in rows:
        loc = "第%d行[%s]" % (r.line_no, r.name)
        m = PORT_RE.match(r.name)
        if not m:
            errors.append("%s: 端口名非法（应为 foo 或 foo[3]）" % loc)
            continue
        base, bit = m.group(1), m.group(2)
        if r.width < 1:
            errors.append("%s: width 必须 >= 1" % loc)
        if bit is None and r.width > 1:
            errors.append("%s: 宽度 %d 的总线必须逐位列出（如 %s[0]..%s[%d]）" % (loc, r.width, base, base, r.width - 1))
        if bit is not None:
            if int(bit) >= r.width:
                errors.append("%s: 下标 %s 超出宽度 %d" % (loc, bit, r.width))
        if not PIN_NAME_RE.match(r.pin):
            errors.append("%s: 封装引脚名 %r 不合法（如 P17/AA3）" % (loc, r.pin))
        if not r.iostandard:
            errors.append("%s: 缺少 iostandard" % loc)
        elif r.iostandard not in KNOWN_IOSTANDARD:
            errors.append("%s: 未知 iostandard %s（不在常见列表中，如确认无误请人工确认）" % (loc, r.iostandard))
        if r.drive and r.drive not in {"2", "4", "6", "8", "12", "16", "24"}:
            errors.append("%s: drive 值 %r 非法" % (loc, r.drive))
        if r.slew and r.slew not in {"FAST", "SLOW"}:
            errors.append("%s: slew 值 %r 非法（FAST/SLOW）" % (loc, r.slew))
        if r.pulltype and r.pulltype not in {"PULLUP", "PULLDOWN", "NONE"}:
            errors.append("%s: pulltype 值 %r 非法" % (loc, r.pulltype))
        key = "%s[%s]" % (base, bit if bit is not None else "")
        if key in seen_port_bit:
            errors.append("%s: 端口位重复定义（首次出现在第%d行）" % (loc, seen_port_bit[key]))
        seen_port_bit.setdefault(key, r.line_no)
        if r.pin in seen_pin:
            errors.append("%s: 引脚 %s 已分配给端口 %s（同一物理引脚不得复用）" % (loc, r.pin, seen_pin[r.pin]))
        seen_pin.setdefault(r.pin, "%s(%s)" % (r.name, r.iostandard))
    return errors


# ---------------------------------------------------------------- XDC 生成/解析

def gen_xdc(rows, part=None, note=""):
    """把引脚表翻译成 XDC IO 约束文本。"""
    buf = []
    buf.append("## 由 vivado_cli pins apply 生成（source: pin CSV）")
    if part:
        buf.append("## 目标器件: %s" % part)
    if note:
        buf.append("## %s" % note)
    buf.append("")
    for r in rows:
        props = ["PACKAGE_PIN %s" % r.pin]
        if r.iostandard:
            props.append("IOSTANDARD %s" % r.iostandard)
        if r.drive:
            props.append("DRIVE %s" % r.drive)
        if r.slew:
            props.append("SLEW %s" % r.slew)
        if r.pulltype and r.pulltype != "NONE":
            props.append("%s true" % r.pulltype)
        if r.comment:
            buf.append("## %s" % r.comment)
        buf.append('set_property -dict "{ %s }" [get_ports {%s}]' % (" ".join(props), r.name))
    buf.append("")
    return "\n".join(buf)


# 兼容多种 XDC 写法的解析（端口名可能是 {led[0]} 带括号或裸名）
_PORTS_RE = r"\[get_ports\s+(?:\{([^}]+)\}|([A-Za-z_]\w*(?:\[\d+\])?))\]"
# set_property -dict "{ PACKAGE_PIN P17 IOSTANDARD LVCMOS33 DRIVE 8 }" [get_ports {clk}]
_XDC_DICT_RE = re.compile(r'set_property\s+-dict\s+"?\{(.*?)\}"?\s*' + _PORTS_RE)
# set_property PACKAGE_PIN P17 [get_ports {clk}]
_XDC_PIN_ONLY_RE = re.compile(r'set_property\s+PACKAGE_PIN\s+([A-Za-z0-9]+)\s+' + _PORTS_RE)
# set_property IOSTANDARD LVCMOS33 [get_ports {clk}]
_XDC_IOSTD_RE = re.compile(r'set_property\s+IOSTANDARD\s+(\w+)\s+' + _PORTS_RE)


def _port_of(m, i):
    return ((m.group(i) or "") + (m.group(i + 1) or "")).strip()


def import_xdc(path):
    """从既有 XDC 提取 IO 约束，返回 PinRow 列表（宽松解析）。"""
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    pin_of, props_of = {}, {}

    def _store(port, pin, props):
        port = port.strip()
        if not port:
            return
        pin_of[port] = pin.upper()
        merged = props_of.setdefault(port, {})
        merged.update(props)

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _XDC_DICT_RE.search(line)
        if m:
            toks = m.group(1).split()
            kv = dict(zip(toks[0::2], toks[1::2]))
            if "PACKAGE_PIN" in kv:
                _store(_port_of(m, 2), kv["PACKAGE_PIN"],
                       {k: v for k, v in kv.items() if k != "PACKAGE_PIN"})
            continue
        m = _XDC_PIN_ONLY_RE.search(line)
        if m:
            _store(_port_of(m, 2), m.group(1), {})
            continue
        m = _XDC_IOSTD_RE.search(line)
        if m:
            props_of.setdefault(_port_of(m, 2), {})["IOSTANDARD"] = m.group(1)

    rows = []
    for port in sorted(pin_of):
        base, bit = port, None
        mb = re.match(r"^(\w+)\[(\d+)\]$", port)
        if mb:
            base, bit = mb.group(1), mb.group(2)
        props = props_of.get(port, {})
        pullup = props.pop("PULLUP", "")
        pulldown = props.pop("PULLDOWN", "")
        if pullup and pullup.lower() not in ("false", "0"):
            pulltype = "PULLUP"
        elif pulldown and pulldown.lower() not in ("false", "0"):
            pulltype = "PULLDOWN"
        else:
            pulltype = ""
        rows.append(PinRow(
            0,
            "%s[%s]" % (base, bit) if bit is not None else base,
            1, pin_of[port], props.get("IOSTANDARD", "").upper(),
            props.get("DRIVE", ""), props.get("SLEW", "").upper(),
            pulltype,
        ))
    # XDC 不含总线宽度，按同名 base 的最大下标推断 width（XDC 不含宽度信息）
    maxbit = {}
    for r in rows:
        mb = re.match(r"^(\w+)\[(\d+)\]$", r.name)
        if mb:
            b, i = mb.group(1), int(mb.group(2))
            maxbit[b] = max(maxbit.get(b, 0), i)
    for r in rows:
        mb = re.match(r"^(\w+)\[(\d+)\]$", r.name)
        r.width = (maxbit[mb.group(1)] + 1) if mb else 1

    if not rows:
        raise RuntimeError("未能从 %s 解析出任何 PACKAGE_PIN 约束" % path)
    return rows


# ---------------------------------------------------------------- 与 RTL 交叉校验

def crosscheck(rows, rtl_ports):
    """rows: PinRow 列表; rtl_ports: {bitname: direction}（led[3] 形式，宽度1无下标）。

    返回 (missing_in_csv, missing_in_rtl) 两组差异：
      missing_in_csv -- RTL 中有端口但 CSV 没分配引脚
      missing_in_rtl -- CSV 中分配了引脚但 RTL 中不存在该端口
    """
    csv_bits = set(r.name for r in rows)
    rtl_bit_names = set(rtl_ports)
    missing_in_csv = sorted(rtl_bit_names - csv_bits)
    missing_in_rtl = sorted(csv_bits - rtl_bit_names)
    return missing_in_csv, missing_in_rtl
