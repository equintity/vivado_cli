# ============================================================
# tcl/flow/export_hwdef.tcl -- 导出硬件描述（Vivado 2018.x: HDF）
# 需要: vc_xpr vc_out vc_include_bit
# 说明: 2018.x 无 write_hw_platform（那是 2019.1+ 的 XSA API）。
#       优先 write_sysdef（可含比特流），缺失时回退 write_hwdef。
# ============================================================

if {[catch {
    vc::need {vc_xpr vc_out vc_include_bit}
    vc::open_xpr $vc_xpr

    # 优先用实现结果，其次综合结果
    if {[catch {open_run impl_1} em1]} {
        if {[catch {open_run synth_1} em2]} {
            error "无已完成的综合/实现结果: $em2"
        }
    }

    file mkdir [file dirname $vc_out]
    if {[llength [info commands write_sysdef]] > 0} {
        if {$vc_include_bit eq "1"} {
            write_sysdef -hwdef -bitstream -file $vc_out
        } else {
            write_sysdef -hwdef -file $vc_out
        }
    } else {
        vc::warn_msg "当前版本无 write_sysdef，回退 write_hwdef（不含比特流）"
        write_hwdef -file $vc_out
    }

    if {![file exists $vc_out]} { error "HDF 未生成: $vc_out" }
    vc::ok HDF_PATH [file normalize $vc_out]
    vc::finish export_hwdef
} em]} {
    vc::fail "export_hwdef: $em\n$errorInfo"
}
