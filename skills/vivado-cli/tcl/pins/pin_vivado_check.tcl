# ============================================================
# tcl/pins/pin_vivado_check.tcl -- 校验引脚是否存在于目标器件封装
# 需要: vc_part vc_pairs（"port=pin;port=pin;..."）
# 说明: Vivado 2018.2 的 get_package_pins 需要设计上下文（open_design），
#       且工程内 link_design 会与活跃综合 run 冲突，故本脚本在
#       全新批处理会话中 link_design -part 建立空网表上下文（不启动综合引擎）。
# ============================================================

if {[catch {
    vc::need {vc_part vc_pairs}

    if {[catch {link_design -part $vc_part} emlink]} {
        error "link_design -part $vc_part 失败: $emlink"
    }

    set n_missing 0
    foreach pair [split $vc_pairs ";"] {
        set pair [string trim $pair]
        if {$pair eq ""} { continue }
        set eq [string first "=" $pair]
        if {$eq < 0} { continue }
        set port [string trim [string range $pair 0 [expr {$eq - 1}]]]
        set pin  [string trim [string range $pair [expr {$eq + 1}] end]]
        # 2018.2 中 package_pin 对象的引脚名属性是 NAME（无 PACKAGE_PIN 属性）
        set cnt [llength [get_package_pins -quiet -filter "NAME == \"$pin\""]]
        if {$cnt == 0} {
            puts "VC_PIN_MISSING: $port $pin"
            incr n_missing
        }
    }

    close_design
    if {$n_missing > 0} {
        error "共 $n_missing 个引脚不在目标封装 $vc_part 内"
    }
    vc::finish pin_check
} em]} {
    vc::fail "pin_check: $em\n$errorInfo"
}
