# ============================================================
# tcl/ps/zynq7000_ps7.tcl -- 创建含 Zynq-7000 PS7 的 Block Design
# 需要: vc_xpr vc_bd_name vc_ps_config vc_ext_fclk
# ps_config 形如: PCW_UART1_PERIPHERAL_ENABLE=1;PCW_FPGA0_PERIPHERAL_FREQMHZ=100
# 兼容性: processing_system7（Zynq-7000）为 2018.2 唯一 PS IP；
#         UltraScale+ 需 zynq_ultra_ps_e，本 skill 锁定 7 系列。
# ============================================================

if {[catch {
    vc::need {vc_xpr vc_bd_name vc_ps_config vc_ext_fclk}
    vc::open_xpr $vc_xpr

    set bdname $vc_bd_name

    if {[catch {create_bd_design $bdname} embd]} {
        error "create_bd_design 失败（BD 可能已存在）: $embd"
    }

    create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps7

    if {$vc_ps_config ne ""} {
        foreach kv [split $vc_ps_config ";"] {
            set kv [string trim $kv]
            if {$kv eq ""} { continue }
            set eq [string first "=" $kv]
            if {$eq < 0} {
                vc::warn_msg "忽略非法配置项（缺 =）: $kv"
                continue
            }
            set key [string trim [string range $kv 0 [expr {$eq - 1}]]]
            set val [string trim [string range $kv [expr {$eq + 1}] end]]
            if {[catch {set_property "CONFIG.$key" $val [get_bd_cells ps7]} emcfg]} {
                vc::warn_msg "配置未生效 CONFIG.$key=$val ($emcfg)"
            }
        }
    }

    if {$vc_ext_fclk eq "1"} {
        if {[catch {
            make_bd_pins_external [get_bd_pins ps7/FCLK_CLK0]
            catch {set_property NAME fclk_clk0 [get_bd_ports FCLK_CLK0_0]}
        } emf]} {
            vc::warn_msg "FCLK_CLK0 引出失败: $emf"
        }
    }

    # 最小系统：默认使能的 AXI 接口时钟（如 M_AXI_GP0_ACLK）接到 FCLK_CLK0，
    # 否则 validate_bd_design 报 [BD 41-758] 时钟未连接。
    foreach aclk {M_AXI_GP0_ACLK M_AXI_GP1_ACLK S_AXI_GP0_ACLK S_AXI_GP1_ACLK \
                  S_AXI_ACP_ACLK S_AXI_HP0_ACLK S_AXI_HP1_ACLK S_AXI_HP2_ACLK S_AXI_HP3_ACLK} {
        set aclk_pin [get_bd_pins -quiet ps7/$aclk]
        if {$aclk_pin ne ""} {
            catch {connect_bd_net [get_bd_pins ps7/FCLK_CLK0] $aclk_pin}
        }
    }

    validate_bd_design
    save_bd_design

    set bdfile [lindex [get_files -quiet "${bdname}.bd"] 0]
    if {$bdfile eq ""} { error "未能定位 $bdname.bd" }
    set bddir [file dirname $bdfile]

    make_wrapper -files $bdfile -top
    set wrapper [file join $bddir hdl "${bdname}_wrapper.v"]
    add_files -norecurse $wrapper
    set_property top "${bdname}_wrapper" [current_fileset]
    update_compile_order -fileset sources_1

    vc::ok BD_WRAPPER [file normalize $wrapper]
    vc::finish bd_zynq
} em]} {
    vc::fail "bd_zynq: $em\n$errorInfo"
}
