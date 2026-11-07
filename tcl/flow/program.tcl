# ============================================================
# tcl/flow/program.tcl -- Hardware Manager：列器件 / JTAG 烧写
# 需要: vc_bit vc_device vc_list_only
# 2018.2 命令集: open_hw / connect_hw_server / open_hw_target / program_hw_devices
# ============================================================

if {[catch {
    vc::need {vc_bit vc_device vc_list_only}

    open_hw
    connect_hw_server -allow_non_jtag

    # 打开全部可见 target（已打开的忽略）
    foreach t [get_hw_targets] {
        catch {open_hw_target $t}
    }

    set devs [get_hw_devices]
    if {[llength $devs] == 0} {
        error "JTAG 链上未发现器件（检查板上电/USB 连接/hw_server 进程）"
    }
    vc::ok DEVICES [join $devs ", "]

    if {$vc_list_only eq "1"} {
        foreach d $devs {
            set fp ""
            catch {set fp [get_property FULL_NAME $d]}
            puts "VC_DEVICE_INFO: $d ($fp)"
        }
        vc::finish list_targets
        return
    }

    if {$vc_bit eq ""} {
        error "未提供比特流路径"
    }
    if {![file exists $vc_bit]} {
        error "比特流不存在: $vc_bit"
    }

    if {$vc_device ne ""} {
        set dev [get_hw_devices $vc_device]
    } else {
        set dev [lindex $devs 0]
    }
    current_hw_device $dev
    set_property PROGRAM.FILE $vc_bit $dev
    program_hw_devices $dev
    vc::ok DEVICE [get_property NAME $dev]
    vc::ok PROGRAMMED [file normalize $vc_bit]
    vc::finish program
    catch {close_hw}
} em]} {
    vc::fail "program: $em\n$errorInfo"
    catch {close_hw}
}
