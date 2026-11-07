# vivado_cli — Vivado 2018 全工作流 CLI Skill

面向 AI 编程助手（Claude Code / ZCode / Codex 等）与命令行用户的 **Xilinx Vivado 2018.x
全流程自动化 skill**：工程创建、Verilog 开发辅助、引脚映射关系管理、Zynq-7000 PL/PS
设计、综合与时序逻辑优化、实现到比特流、JTAG 烧写、HDF 导出（对接 Xilinx SDK）。

> 设计动机与同类开源方案对比见 [docs/comparison.md](docs/comparison.md)；
> 架构与模块调用关系见 [docs/design.md](docs/design.md)；
> **Vivado 2018 适配注意点（必读）**见 [docs/vivado2018_notes.md](docs/vivado2018_notes.md)。

## 特性

- **批处理直调，无守护进程**：每阶段生成驱动 Tcl，`vivado.bat -mode batch` 执行，
  状态由 project mode 的 `.xpr` 持久化，任意阶段可独立重入、可从日志恢复
- **版本锁定 2018 API**：`write_sysdef/write_hwdef`（HDF，非 XSA）、`open_hw` 系列烧写命令、
  Zynq-7000 `processing_system7`，全部按 2018.2 验证命令集
- **引脚映射一等公民**：CSV 引脚表 ⇄ XDC 双向转换、重复引脚/电平标准静态校验、
  与 RTL 顶层端口交叉校验、目标封装存在性校验（调 `get_package_pins`）
- **时序优化建议引擎**：解析 `report_timing_summary`，按跨时钟域/IO 路径/深组合逻辑/
  布线主导/hold 违例分类给出可操作动作与对应 CLI 命令
- **C 盘保护**：所有工程与输出强制非系统盘（可显式 `--allow-system-drive` 解除）

## 环境要求

- Windows + Vivado 2018.2/2018.3（含 SDK 2018.2 更佳），Python 3.8+（仅标准库）
- 板卡文件按需（本仓库开发环境含 zed/zc702 等 Zynq-7000 板卡）

## 快速开始

```bash
cd D:\FPGA\projects\demo                      # 工程目录（非系统盘）
python <skill目录>/scripts/vivado_cli.py env set --vivado-home "D:\FPGA\vivado\Xilinux\Vivado\2018.2"
python scripts\vivado_cli.py project create --name demo --dir . --part xc7a35tcpg236-1
python scripts\vivado_cli.py project add-src --files ..\..\examples\blink_counter.v --top blink_counter
python scripts\vivado_cli.py pins new && python scripts\vivado_cli.py pins apply --csv pins.csv --out pins.xdc
python scripts\vivado_cli.py project add-src --files pins.xdc --fileset constrs_1
python scripts\vivado_cli.py synth run        # 打印 WNS + 优化建议
python scripts\vivado_cli.py impl run --to-bitstream
python scripts\vivado_cli.py hw program       # 板上电 + JTAG
```

一键：`workflow full --create --name demo --dir . --part xc7a35tcpg236-1`

完整工作流手册（PL 流 / Zynq PL+PS 流 / 时序优化循环）见 [SKILL.md](SKILL.md)。

## 命令结构

```
vivado_cli.py
├── env        detect | set | check            环境探测/配置
├── project    create | add-src | open | status 工程生命周期
├── pins       new | apply | import | check | crosscheck   引脚映射管理
├── pins-vivado check                          封装存在性校验（Vivado 端）
├── rtl        new-module | new-tb | lint | list           Verilog 开发
├── synth      run                             综合 + 报告 + 建议
├── impl       run                             实现 + 比特流 + 报告
├── hwdef      export                          HDF 导出（2018: 非 XSA）
├── hw         program | list-targets          JTAG 烧写
├── pl         bd-zynq                         Zynq-7000 PS7 Block Design
├── report     summary | timing | util         日志/时序/利用率解析
└── workflow   full                            一键全流程（含时序门限）
```

## 目录结构

```
vivado_cli/
├── SKILL.md            # AI 助手使用手册（工作流、边界、触发词）
├── scripts/            # Python CLI（纯标准库）
│   ├── vivado_cli.py   #   入口与命令分发
│   ├── vc_env.py       #   环境探测/配置
│   ├── vc_flow.py      #   批处理编排（生成驱动 Tcl -> vivado.bat）
│   ├── vc_pins.py      #   引脚表校验/XDC 生成/导入/交叉校验
│   ├── vc_rtl.py       #   模板/端口解析/启发式 lint/xvlog 调用
│   ├── vc_report.py    #   日志、时序、利用率解析 + 建议引擎
│   └── vc_util.py      #   路径防护（C 盘禁写）/子进程/标记解析
├── tcl/                # Vivado 2018.2 兼容 Tcl 库（结果经 VC_* 标记回传）
│   ├── lib/common.tcl
│   ├── flow/{create_project,add_sources,open_project,run_synth,run_impl,export_hwdef,program}.tcl
│   ├── ps/zynq7000_ps7.tcl
│   ├── pins/pin_vivado_check.tcl
│   └── reports/collect_reports.tcl
├── templates/          # 引脚表模板
├── examples/           # 示例 RTL / 示例引脚表
└── docs/               # 设计文档 / 对比研究 / 2018 适配注意点
```

## License

MIT
