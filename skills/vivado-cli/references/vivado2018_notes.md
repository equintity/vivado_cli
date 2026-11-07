# Vivado 2018 适配注意点（本 skill 的版本兼容决策）

本 skill 的 Tcl 库按 **Vivado 2018.2**（SW Build 2258646, Jun 14 2018）编写并在本机
验证。2018.x 与 2019+ 存在多处不兼容 API，以下差异是本 skill 与常见"新版参考设计"
的根本区别。`env check` 检测到非 2018.x 版本会告警。

## 1. 硬件描述导出：HDF 而非 XSA

| | 2018.x | 2019.1+ |
|--|--------|---------|
| 命令 | `write_hwdef` / `write_sysdef -hwdef [-bitstream]` | `write_hw_platform` |
| 格式 | `.hdf` | `.xsa` |
| 下游工具 | **Xilinx SDK**（hdf 建 BSP） | Vitis |

- `tcl/flow/export_hwdef.tcl` 优先 `write_sysdef`（2018 已有，可打包比特流），
  无该命令时回退 `write_hwdef`；**不要**在 2018 上照抄新教程的
  `write_hw_platform -include_bit`，会报命令不存在。
- HDF 中含 `ps7_init.tcl/.c/.h`，SDK 流程：File → New → Hardware Platform Specification
  → 选 HDF → Board Support Package → Application。

## 2. Hardware Manager Tcl：旧对象模型

2018.2 可用（本 skill 采用）：
```tcl
open_hw
connect_hw_server -allow_non_jtag
open_hw_target
get_hw_devices / set_property PROGRAM.FILE / program_hw_devices
```
注意事项：
- `open_hw_manager`（2018.1 引入的新入口）在本 skill 中**不使用**——`open_hw` 系列在
  2017~2019 全可用，兼容面最大。
- `connect_hw_server -host`/`-port` 选项 2018 可用，但默认本机 hw_server 无需传参。
- 烧写 Zynq-7000：`program_hw_devices` 直接烧 PL 比特流可用；带 PS 初始化的 JTAG
  启动（fsbl+app）属于 SDK/XSCT 流程，**不在本 skill 边界内**。

## 3. Zynq-7000 PS：processing_system7 与 CONFIG.PCW_*

- 2018.2 的 Zynq-7000 PS IP 为 `xilinx.com:ip:processing_system7`（UltraScale+ 的
  `zynq_ultra_ps_e` 是另一 IP，本 skill 锁 7 系列）。
- PS 配置属性前缀 `CONFIG.PCW_*`（PCW = Processing System Wizard），如
  `PCW_UART1_PERIPHERAL_ENABLE`、`PCW_UIPARAM_DDR_PARTNO`、`PCW_FPGA0_PERIPHERAL_FREQMHZ`。
  **属性名与新版有出入**，逐项配置失败时以本版 IP catalog 的文档为准；
  `bd-zynq` 对每个配置项独立 catch，失败项降级为 VC_WARN 而非整阶段失败。
- 板级 preset（zed/zc702 等）在 2018.2 的 BD GUI 里有 preset XML；CLI 直建 BD 时
  用 `--ps-config` 显式给关键项（DDR partno、UART/SD/ENET 使能、FCLK 频率）。
  **DDR 型号必须按实际板卡填写**，否则实现阶段报 CRITICAL WARNING。

## 4. project mode 运行控制

- `open_run synth_1` / `open_run impl_1` 在 2018.2 可用 ✓（老版本 2017 需
  `open_checkpoint`，本 skill 不兼容 2017 以下）。
- 策略名（2018.2 有效）：综合 `Flow_PerfOptimized_high`、`Flow_AreaOptimized_high`、
  `Flow_AlternateRoutability`；实现 `Performance_ExplorePostRoutePhysOpt`、
  `Performance_NetDelay_high`、`Performance_WLBlockPlacement`。
- retiming：`set_property STEPS.SYNTH_DESIGN.ARGS.RETIMING true [get_runs synth_1]` ✓。
- 后布线 phys_opt：`STEPS.POST_ROUTE_PHYS_OPT.IS_ENABLED/DIRECTIVE` ✓。
- `report_utilization -hierarchical` 在 2018.2 **不可用**（2019+ 才有），
  本 skill 只用标准 `report_utilization`。

## 5. 约束与时序

- XDC 语法与新版无差异；引脚校验用
  `get_package_pins -filter "PACKAGE_PIN == \"P17\""`（需先 open_project 获得 part 上下文）。
- `report_timing_summary` 输出格式 2018.2 与新版基本一致，解析器已按其
  "Design Timing Summary"（WNS/TNS/.../TPWS 11 列）与 "Slack (VIOLATED)" 路径块适配；
  若未来报告格式变化，改 `vc_report.py` 的正则即可。

## 6. 编码与平台（Windows 中文环境）

- Vivado 日志为 UTF-8/ASCII；中文 Windows 控制台为 GBK。Python 侧统一
  `decode(errors="replace")` + `stdout.reconfigure(errors="replace")`，避免 GBK 崩溃。
- Tcl 传参经 `set vc_x {值}` 花括号包裹；路径统一正斜杠；含 `{}`/换行的参数被拒绝。
- `-notrace` 精简日志；`-log/-journal` 显式落盘到 `vc_work/`，避免污染 CWD 之外。

## 7. 版本检测与升级路径

- `env check`：非 `2018.*` → 警告（skill 面向 2018 API）。
- 若将来迁移 2019+：改 `tcl/flow/export_hwdef.tcl`（write_hw_platform + .xsa）、
  `tcl/flow/program.tcl`（open_hw_manager 新流程）、`tcl/ps/`（换 Zynq US+ IP），
  Python 编排与标记协议无需变动——这是"流程逻辑放 Tcl 层"决策的直接收益。

## 8. Windows 11 (24H2+) 综合崩溃：环境级不兼容（本机实测结论）

**症状**：工程模式 `launch_runs` 或非工程模式 `synth_design`，在
"done synthesizing module" 后立即崩溃，日志出现
`TclStackFree: incorrect freePtr. Call out of sequence?`，run 状态 `synth_design ERROR`。

**本机排查记录（2026-11，Win11 build 26200 / 25H2 + Vivado 2018.2）**：
1. 空设计（2 位计数器）同样崩溃 → 与设计内容无关；
2. 最小 PATH + `set_param general.maxThreads 1` → 仍崩溃；
3. 按 [NI 知识库 hotfix](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA0VU0000008pq90AA&l=en-US)
   将 `ids_lite/ISE/lib/nt64/libPortability.dll` 换为 `libPortabilityNOSH.dll` → 无效
   （该 DLL 只作用于 ISE 流，vivado.exe 的综合引擎不加载它）；
4. [AMD 社区与官方口径](https://adaptivesupport.amd.com/s/question/0D5Pd00001umQiKKAU/)：
   Vivado 2018.x 未适配 Windows 11 24H2+，属引擎级 Tcl 栈内存损坏。

**结论与出路**（按推荐顺序）：
- 在 Windows 10 / 23H2 以前的系统或虚拟机中运行本 skill（综合/实现可完整验证）；
- 升级 Vivado 到适配 24H2+ 的版本（2023.2+），并按 docs/comparison.md 的
  "版本迁移路径"调整 `tcl/flow/export_hwdef.tcl`、`tcl/flow/program.tcl`；
- 回退 Windows 至 23H2。

**不受影响的功能**：本机已实测通过——env/project/add-src/pins 全链
（含 `link_design -part` 封装校验）/rtl（含 xvlog）/pl bd-zynq（Zynq-7020
PS7 BD + wrapper）/report 解析。skill 对综合失败的检测、日志摘要与提示链路
也在该环境上得到了真实验证。

**辅助命令**：`env fix-win11 status|apply|revert` 保留为 ISE 类流程的
libPortability 诊断/修复工具（apply 有备份、可 revert）。
