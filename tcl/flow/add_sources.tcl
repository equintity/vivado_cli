# ============================================================
# tcl/flow/add_sources.tcl -- 向 fileset 添加源/仿真/约束文件
# 需要: vc_xpr vc_files("|"分隔) vc_fileset vc_top
# ============================================================

if {[catch {
    vc::need {vc_xpr vc_files vc_fileset vc_top}
    vc::open_xpr $vc_xpr

    set fs $vc_fileset
    set n 0
    foreach f [split $vc_files "|"] {
        set f [string trim $f]
        if {$f eq ""} { continue }
        if {![file exists $f]} { error "源文件不存在: $f" }
        add_files -fileset $fs -norecurse $f
        switch -glob -- [string tolower [file extension $f]] {
            .sv  { catch {set_property file_type SystemVerilog [get_files $f]} }
            .v   { catch {set_property file_type Verilog [get_files $f]} }
            .vh  { catch {set_property file_type {Verilog Header} [get_files $f]} }
            .vhd { catch {set_property file_type VHDL [get_files $f]} }
        }
        puts "VC_ADDED: $f"
        incr n
    }

    if {$vc_top ne ""} {
        if {$fs eq "constrs_1"} {
            error "约束文件集不设置 top"
        }
        set_property top $vc_top [get_filesets $fs]
    }
    catch {update_compile_order -fileset sources_1}
    if {$fs eq "sim_1"} { catch {update_compile_order -fileset sim_1} }

    vc::ok ADDED_COUNT $n
    vc::finish add_sources
} em]} {
    vc::fail "add_sources: $em\n$errorInfo"
}
