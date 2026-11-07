# ============================================================
# tcl/flow/run_synth.tcl -- 运行综合并收集时序/利用率报告
# 需要: vc_xpr vc_jobs vc_strategy vc_retiming vc_write_dcp vc_rpt_dir
# ============================================================

if {[catch {
    vc::need {vc_xpr vc_jobs vc_strategy vc_retiming vc_write_dcp vc_rpt_dir}
    vc::open_xpr $vc_xpr

    if {$vc_strategy ne ""} {
        set_property strategy $vc_strategy [get_runs synth_1]
        vc::ok STRATEGY $vc_strategy
    }
    if {$vc_retiming eq "1"} {
        catch {
            set_property STEPS.SYNTH_DESIGN.ARGS.RETIMING true [get_runs synth_1]
        } emr
        if {[info exists emr] && $emr ne ""} { vc::warn_msg "RETIMING 设置失败: $emr" }
    }

    reset_run synth_1
    launch_runs synth_1 -jobs $vc_jobs
    wait_on_run synth_1

    set status   [get_property STATUS   [get_runs synth_1]]
    set progress [get_property PROGRESS [get_runs synth_1]]
    vc::ok SYNTH_STATUS "$status (progress $progress)"
    if {$progress ne "100%"} {
        error "综合未完成: $status"
    }

    # 打开综合网表以收集估计时序（2018.2 支持 open_run）
    open_run synth_1
    source [file join $vc_tcl_root reports collect_reports.tcl]
    vc::collect_reports synth $vc_rpt_dir

    if {$vc_write_dcp eq "1"} {
        set dcp [file join $vc_rpt_dir synth.dcp]
        catch {write_checkpoint -force $dcp}
        if {[file exists $dcp]} { vc::ok DCP [file normalize $dcp] }
    }

    set wns ""
    catch {set wns [get_property SLACK [get_timing_paths]]}
    vc::ok WNS $wns
    vc::finish run_synth
} em]} {
    vc::fail "run_synth: $em\n$errorInfo"
}
