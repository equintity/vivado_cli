# ============================================================
# tcl/flow/open_project.tcl -- 打开工程并输出概览信息
# 需要: vc_xpr
# ============================================================

if {[catch {
    vc::need {vc_xpr}
    vc::open_xpr $vc_xpr

    vc::ok PROJECT_NAME [get_property NAME [current_project]]
    vc::ok PART [get_property PART [current_project]]
    vc::ok TOP [get_property TOP [current_fileset]]
    set nsrc [llength [get_files -quiet -of_objects [get_filesets sources_1]]]
    set nxdc [llength [get_files -quiet -of_objects [get_filesets constrs_1]]]
    vc::ok SRC_COUNT $nsrc
    vc::ok XDC_COUNT $nxdc
    vc::finish open_project
} em]} {
    vc::fail "open_project: $em\n$errorInfo"
}
