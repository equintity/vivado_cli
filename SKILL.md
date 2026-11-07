---
name: vivado_cli
description: >-
  Vivado 2018.x 全工作流 CLI skill：工程创建、Verilog 开发辅助、引脚映射管理
  （CSV<->XDC）、Zynq-7000 PL/PS Block Design、综合、时序解析与优化建议、
  实现到比特流、JTAG 烧写、HDF 导出（对接 Xilinx SDK）。
  触发词: vivado、xilinx、fpga、zynq、verilog、xdc、引脚、约束、综合、
  时序、timing、比特流、bit、烧写、下载、block design、ps7、hdl。
  适用于 Windows 本机 Vivado 2018.2/2018.3 批处理自动化。
---

# Vivado 2018 全工作流 CLI Skill

通过 `scripts/vivado_cli.py`（纯标准库 Python）驱动本机 Vivado 2018.2 批处理模式，
覆盖 PL/PS 设计全流程。**所有工程与输出强制位于非系统盘**（防止污染 C 盘）。

## 0. 前置：一次性环境配置

在**工程目录**（建议如 `D:\FPGA\projects\<工程名>\`）执行：

```bash
# 首次：探测本机 Vivado 并写入 vivado_cli_env.json
python <skill目录>/scripts/vivado_cli.py env detect
python <skill目录>/scripts/vivado_cli.py env set --vivado-home "D:\FPGA\vivado\Xilinux\Vivado\2018.2"
python <skill目录>/scripts/vivado_cli.py env check
```

约定：所有后续命令都在该工程目录执行（状态文件与 vc_work/ 临时目录都在这里）。
`<skill目录>` 指本 skill 安装位置（含 SKILL.md 的目录）。

## 1. 命令总览（模块 -> 动作）

| 模块 | 动作 | 作用 |
|------|------|------|
| env | detect / set / check | 探测、配置、校验 Vivado 2018 环境 |
| project | create / add-src / open / status | 工程创建、源文件管理、状态概览 |
| pins | new / apply / import / check / crosscheck | 引脚 CSV <-> XDC，静态与交叉校验 |
| pins-vivado | check | 引脚是否存在于器件封装（Vivado 端校验） |
| rtl | new-module / new-tb / lint / list | Verilog 模板、testbench、启发式 lint、模块清单 |
| synth | run | 综合 + 时序/利用率报告 + 建议输出 |
| timing→report | timing --suggest | 时序报告解析与优化建议（不跑 Vivado） |
| impl | run | 实现 + 比特流 + 报告 |
| hwdef | export | 导出 HDF（2018 专有，对接 Xilinx SDK） |
| hw | program / list-targets | JTAG 烧写 / 在线器件列表 |
| pl | bd-zynq | 创建 Zynq-7000 PS7 Block Design |
| report | summary / util | 日志错误统计 / 资源利用率解析 |
| workflow | full | 建(可选)→综合→时序门限→实现 一键流 |

每个动作的参数用 `--help` 查看（如 `python scripts/vivado_cli.py synth run --help`）。

## 2. 标准工作流 A：纯 PL（RTL 流）

1. `env set` + `env check`（首次）
2. `project create --name demo --dir D:\FPGA\projects\demo --part xc7a35tcpg236-1`
3. `rtl new-module --name top --ports "clk:in,rst_n:in,led[3:0]:out" --out src/top.v`（或直接手写 Verilog）
4. `rtl lint --files src/*.v --vivado`（xvlog 真实语法检查 + 启发式 lint）
5. `pins new --out pins.csv` → 填写 → `pins apply --csv pins.csv --out pins.xdc`
6. `pins crosscheck --csv pins.csv --top-rtl src/top.v`（引脚与 RTL 端口一致性）
7. `project add-src --files src/*.v --top top`；`project add-src --files pins.xdc --fileset constrs_1`
8. `synth run`（产出 vc_reports/timing_summary_synth.rpt 并打印 WNS 与建议）
9. WNS<0 时进入时序优化循环（见 §5），收敛后 `impl run --to-bitstream`
10. `hw program`（板子接好 JTAG 后）

或一键：`workflow full --create --name demo --dir ... --part ... --wns-threshold 0`

## 3. 标准工作流 B：Zynq-7000 PL/PS

1. `project create --name zsys --dir D:\FPGA\projects\zsys --part xc7z020clg484-1`（或 --board zc702 / zed）
2. `pl bd-zynq --bd-name system --ps-config "PCW_UART1_PERIPHERAL_ENABLE=1;PCW_FPGA0_PERIPHERAL_FREQMHZ=100" --ext-fclk`
   - `--ps-config` 用分号分隔的 `CONFIG.PCW_*` 键值（前缀 PCW_ 自动补全为 CONFIG.）；
     常用：UART/ENET/SD/USB 使能、DDR 参数（PCW_UIPARAM_DDR_PARTNO）、M_AXI_GP0 等
   - DDR 型号必须按实际板卡填写，生成后用 `report summary` 检查 CRITICAL WARNING
3. `project add-src` 添加自定义 RTL（如需挂 AXI，先在 Vivado GUI 或手工 Tcl 里加 AXI interconnect——本 skill 不代建复杂 BD 网络）
4. 综合/实现/时序流程同工作流 A 步骤 7-10
5. `hwdef export --include-bit` → 用 **Xilinx SDK**（2018 无 Vitis）从 HDF 新建 BSP/应用

## 4. 引脚表规范（pins 模块核心）

CSV 表头固定：`name,width,pin,iostandard,drive,slew,pulltype,comment`（8 列，注意空位数量）
- 每行一个端口位：`led[0],4,P15,LVCMOS33,8,FAST,,备注`；宽度 1 端口不带下标 `clk,1,P17,LVCMOS33,,,,备注`
- **width 列填总线总宽度**（如 sw[0]..sw[3] 每行都填 4），下标必须 < width
- 差分对：P/N 各一行，iostandard 填差分电平（如 LVDS_25）
- `pins check` 抓：重复引脚/端口、非法电平标准、下标越界；`pins-vivado check --part <器件>` 再验封装存在性（无需工程，秒级）
- `pins import --xdc old.xdc` 可从既有工程反向提取引脚表归档

## 5. 时序优化循环（timing 逻辑优化的标准打法）

1. `synth run` 或 `report timing --rpt vc_reports/timing_summary_impl.rpt --suggest`
2. 读建议分类处理：
   - **跨时钟域** → 双同步器/异步 FIFO/set_clock_groups -asynchronous（改 RTL/XDC）
   - **IO 路径** → 核对 set_input_delay/set_output_delay 真实板级时序
   - **逻辑级 >= 8** → 插流水线寄存器拆组合逻辑（改 RTL），或 `synth run --retiming`
   - **布线主导（逻辑级少延迟大）** → 高扇出：`set_property MAX_FANOUT N [get_nets ...]`；
     或直接换实现策略：`impl run --strategy Performance_ExplorePostRoutePhysOpt --phys-opt`
   - **WHS<0（hold）** → 实现策略修正，检查约束误设
3. 改完重跑 `synth run` → `impl run`，直到 WNS>=0
4. 只想验证策略不改 RTL 时，不要 reset 工程：直接 `impl run --strategy ...`（脚本内部会 reset_run impl_1，synth 结果保留）

## 6. 错误处理约定

- 任何阶段失败：`report summary --log vc_work/<阶段>.log` 看去重后的 ERROR/CRITICAL WARNING
- Tcl 侧错误以 `VC_ERROR:` 打印在日志；Python 侧以 `[vivado_cli][错误]` 打印
- CRITICAL WARNING 不可忽略（尤其 BD/约束类），逐条定位后重跑
- 综合成功 ≠ 时序收敛：以 vc_reports/timing_summary_*.rpt 的 WNS/WHS 为准

## 7. 功能边界（明确不做）

- **不做** Vitis/PetaLinux/软件编译：2018.2 对应 Xilinx SDK，skill 只交付 HDF（hwdef export）+ 指引
- **不代跑** behavioral 仿真（rtl new-tb 只生成测试台；仿真在 Vivado GUI/xsim 中执行）
- **不创建** 复杂 BD 网络（AXI interconnect 拓扑等）；bd-zynq 只交付 PS7 最小系统 + 配置项
- **版本锁定** Vivado 2018.x：2019+（XSA/Vitis/新 HW API）与更老版本不保证；`env check` 会警告
- **C 盘保护**：所有工程/输出强制非系统盘；`--allow-system-drive` 仅在确有必要时使用
- 不修改用户工程外的任何文件；vc_work/ 临时驱动脚本可随时删除

## 8. 关键文件

- `scripts/vivado_cli.py` — CLI 入口（子命令分发）
- `scripts/vc_flow.py` — 批处理编排（生成驱动 Tcl -> vivado.bat -mode batch）
- `tcl/flow/*.tcl` `tcl/ps/*.tcl` — 2018.2 兼容的流程/BD 脚本（结果经 VC_* 标记回传）
- `docs/design.md` — 架构与模块调用关系；`docs/comparison.md` — 与 GitHub 参考方案对比；
  `docs/vivado2018_notes.md` — 2018 适配注意点（必读，尤其 HDF/XSA 与 HW Tcl 差异）
