# ============================================================
# tcl/lib/common.tcl -- vivado_cli 公共过程库（Vivado 2018.x 兼容）
# 由 vc_flow.run_stage 生成的驱动脚本在批处理模式下 source 本文件。
# 约定：所有阶段参数由驱动脚本先 `set vc_<name> {...}`，再 source 阶段脚本。
# ============================================================

namespace eval vc {}

# --- 参数校验：检查全局变量是否存在 ------------------------------
proc vc::need {varlist} {
    foreach v $varlist {
        if {![info exists ::$v]} {
            puts "VC_ERROR: 阶段脚本缺少变量 $v（驱动生成异常）"
            exit 2
        }
    }
}

# --- 结构化输出标记（Python 端解析 VC_XXX: value）----------------
proc vc::ok {tag value} {
    puts "VC_${tag}: $value"
}

proc vc::warn_msg {msg} {
    puts "VC_WARN: $msg"
}

# --- 失败退出：打印标记 + 非零退出码 ------------------------------
proc vc::fail {msg} {
    puts "VC_ERROR: $msg"
    catch {close_design}
    catch {close_project}
    exit 1
}

# --- 打开工程（失败即终止）----------------------------------------
proc vc::open_xpr {path} {
    if {![file exists $path]} {
        vc::fail "工程文件不存在: $path"
    }
    if {[catch {open_project $path} em]} {
        vc::fail "open_project 失败: $em（工程可能正被 Vivado GUI 占用）"
    }
}

# --- 阶段收尾 ------------------------------------------------------
proc vc::finish {tag} {
    puts "VC_STAGE_RESULT: $tag OK"
    catch {close_design}
    catch {close_project}
}

puts "VC_TCL_ROOT: $::vc_tcl_root"
