# ============================================================
# tcl/reports/collect_reports.tcl -- 定义 vc::collect_reports 过程
# 在已 open_run 的设计上收集报告到指定目录。
# ============================================================

proc vc::collect_reports {stage rpt_dir} {
    file mkdir $rpt_dir
    report_timing_summary -file [file join $rpt_dir "timing_summary_$stage.rpt"]
    report_utilization    -file [file join $rpt_dir "utilization_$stage.rpt"]
    catch {report_clocks -file [file join $rpt_dir "clocks_$stage.rpt"]}
    catch {report_power   -file [file join $rpt_dir "power_$stage.rpt"]}
    vc::ok REPORT_DIR [file normalize $rpt_dir]
}
