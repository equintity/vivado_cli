# ============================================================
# tcl/flow/create_project.tcl -- 创建 Vivado 工程（project mode）
# 需要: vc_name vc_dir vc_part vc_board
# ============================================================

if {[catch {
    vc::need {vc_name vc_dir vc_part vc_board}

    if {![file isdirectory $vc_dir]} {
        file mkdir $vc_dir
    }

    if {$vc_board ne ""} {
        create_project $vc_name $vc_dir -board $vc_board -force
    } else {
        if {$vc_part eq ""} {
            error "必须提供 --part 或 --board 之一"
        }
        create_project $vc_name $vc_dir -part $vc_part -force
    }

    # 2018.2: 目标语言 Verilog（make_wrapper 等后续行为依赖此项）
    set_property target_language Verilog [current_project]
    set_property simulator_language Mixed [current_project]

    set xpr [file normalize [file join [get_property DIRECTORY [current_project]] $vc_name.xpr]]
    vc::ok XPR_PATH $xpr
    vc::ok PART [get_property PART [current_project]]
    vc::finish create_project
} em]} {
    vc::fail "create_project: $em\n$errorInfo"
}
