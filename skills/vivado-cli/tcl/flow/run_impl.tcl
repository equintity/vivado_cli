# ============================================================
# tcl/flow/run_impl.tcl -- 运行实现（可选到比特流）并收集报告
# 需要: vc_xpr vc_jobs vc_bitstream vc_strategy vc_phys_opt vc_rpt_dir
# ============================================================

if {[catch {
    vc::need {vc_xpr vc_jobs vc_bitstream vc_strategy vc_phys_opt vc_rpt_dir}
    vc::open_xpr $vc_xpr

    # 综合必须已完成
    set sprog [get_property PROGRESS [get_runs synth_1]]
    if {$sprog ne "100%"} {
        error "综合尚未完成（progress=$sprog），请先运行 synth run"
    }

    if {$vc_strategy ne ""} {
        set_property strategy $vc_strategy [get_runs impl_1]
        vc::ok STRATEGY $vc_strategy
    }
    if {$vc_phys_opt eq "1"} {
        catch {
            set_property STEPS.POST_ROUTE_PHYS_OPT.IS_ENABLED true [get_runs impl_1]
            set_property STEPS.POST_ROUTE_PHYS_OPT.DIRECTIVE AggressiveExplore [get_runs impl_1]
        } emp
        if {[info exists emp] && $emp ne ""} { vc::warn_msg "phys_opt 启用失败: $emp" }
    }

    reset_run impl_1
    if {$vc_bitstream eq "1"} {
        launch_runs impl_1 -to_step write_bitstream -jobs $vc_jobs
    } else {
        launch_runs impl_1 -jobs $vc_jobs
    }
    wait_on_run impl_1

    set status   [get_property STATUS   [get_runs impl_1]]
    set progress [get_property PROGRESS [get_runs impl_1]]
    vc::ok IMPL_STATUS "$status (progress $progress)"
    if {$progress ne "100%"} {
        error "实现未完成: $status"
    }

    open_run impl_1
    source [file join $vc_tcl_root reports collect_reports.tcl]
    vc::collect_reports impl $vc_rpt_dir

    set wns ""
    catch {set wns [get_property SLACK [get_timing_paths]]}
    vc::ok WNS $wns

    if {$vc_bitstream eq "1"} {
        set top [get_property TOP [current_fileset]]
        set bit [file normalize [file join [get_property DIRECTORY [get_runs impl_1]] $top.bit]]
        if {![file exists $bit]} { error "比特流未生成: $bit" }
        vc::ok BIT_PATH $bit
    }
    vc::finish run_impl
} em]} {
    vc::fail "run_impl: $em\n$errorInfo"
}
