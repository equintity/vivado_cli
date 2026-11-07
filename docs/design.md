# 架构设计与模块调用关系

## 1. 总体架构

```
                    ┌────────────────────────────────────────────┐
                    │                SKILL.md（AI 层）            │
                    │  工作流编排知识 / 命令路由 / 触发词 / 边界    │
                    └───────────────────┬────────────────────────┘
                                        │ 指导 Agent/用户 调用
                                        ▼
                    ┌────────────────────────────────────────────┐
                    │        scripts/vivado_cli.py（CLI 入口）    │
                    │  argparse 子命令分发: env/project/pins/rtl/ │
                    │  synth/impl/hwdef/hw/pl/report/workflow    │
                    └───┬──────────┬──────────┬──────────┬───────┘
                        │          │          │          │
        纯本地逻辑（无需 Vivado）   │          │   Vivado 批处理编排
              ┌───────────────────┘          └──────────┬─────────────┐
              ▼                                         ▼             ▼
   ┌─────────────────────┐  ┌───────────────────┐  ┌──────────────────────┐
   │ vc_env  环境探测配置 │  │ vc_pins 引脚映射   │  │ vc_flow  流程编排     │
   │ vc_rtl  RTL 辅助    │  │ vc_report 报告解析 │  │  (生成驱动 Tcl)      │
   └─────────────────────┘  └───────────────────┘  └──────────┬───────────┘
                                                              │ vivado.bat
                                                              │ -mode batch
                                                              ▼
                                                  ┌─────────────────────────┐
                                                  │ tcl/ 库（Vivado 2018.2）│
                                                  │ lib/common.tcl 公共过程  │
                                                  │ flow/* 阶段脚本          │
                                                  │ ps/zynq7000_ps7.tcl     │
                                                  │ pins/pin_vivado_check   │
                                                  │ reports/collect_reports │
                                                  └─────────────────────────┘
```

## 2. 执行模型：批处理 + 标记回传

1. `vc_flow.run_stage()` 在 `<工程>/vc_work/` 写驱动脚本 `stage.tcl`：
   ```tcl
   set vc_xpr {D:/FPGA/projects/demo/demo.xpr}
   set vc_jobs {4}
   ...
   set vc_tcl_root {<skill>/tcl}
   source [file join $vc_tcl_root lib common.tcl]
   source [file join $vc_tcl_root flow run_synth.tcl]
   ```
2. 以 `vivado.bat -mode batch -source ... -notrace -log vc_work/<stage>.log -journal ...`
   执行（CWD=工程目录），超时按阶段预设（综合 2h，实现 4h，可 `--timeout` 覆盖）
3. 阶段脚本把结果以 `VC_XXX: value` 标记打印（如 `VC_XPR_PATH:`、`VC_BIT_PATH:`、
   `VC_ERROR:`）；Python 解析日志收集标记 + `vc_report.parse_log` 统计错误
4. 工程状态持久化在 `.xpr`（Vivado project mode），因此各阶段**无会话依赖**，
   任意阶段可重跑；轻量状态（当前工程/器件）记录在 `<工程>/vivado_cli_env.json`

## 3. 模块调用关系

```
vivado_cli.py
 ├─ env     ───────────────► vc_env       ──(vivado.bat -version)──► Vivado
 ├─ project create ────────► vc_flow.run_stage("create_project") ──► tcl/flow/create_project.tcl
 │             └─成功──► 写 vivado_cli_env.json（当前工程/器件）
 ├─ project add-src ───────► vc_flow.run_stage("add_sources") ────► tcl/flow/add_sources.tcl
 ├─ pins new/apply/check ──► vc_pins（纯本地: CSV 校验 + XDC 生成）
 ├─ pins import ───────────► vc_pins.import_xdc（XDC 反解析）
 ├─ pins crosscheck ───────► vc_pins.crosscheck + vc_rtl.parse_ports_of_top
 ├─ pins-vivado check ─────► vc_pins.validate ─► vc_flow.run_stage("pin_check") ─► tcl/pins/pin_vivado_check.tcl
 ├─ rtl new-module/new-tb ─► vc_rtl（模板生成）
 ├─ rtl lint ──────────────► vc_rtl.lint_file（启发式）＋(可选) xvlog.bat 真实编译
 ├─ synth run ─────────────► vc_flow.run_stage("run_synth") ─────► tcl/flow/run_synth.tcl
 │             └─成功──► vc_report.parse_timing_summary + suggest_timing 打印建议
 ├─ impl run ──────────────► vc_flow.run_stage("run_impl") ──────► tcl/flow/run_impl.tcl
 ├─ pl bd-zynq ────────────► vc_flow.run_stage("bd_zynq") ───────► tcl/ps/zynq7000_ps7.tcl
 ├─ hwdef export ──────────► vc_flow.run_stage("export_hwdef") ──► tcl/flow/export_hwdef.tcl
 ├─ hw program ────────────► vc_flow.run_stage("program") ───────► tcl/flow/program.tcl
 ├─ report summary/timing ─► vc_report（解析既有日志/报告，不启动 Vivado）
 └─ workflow full ─────────► project create → synth run → WNS 门限判定 → impl run（组合以上路径）
```

依赖方向：`vivado_cli.py → vc_* → vc_util`；`vc_flow → vc_report`（失败时自动摘要日志）、
`vc_flow → vc_env`（状态文件读写）；Tcl 侧只依赖驱动脚本注入的 `vc_*` 变量与
`vc_tcl_root`，无反向依赖。阶段脚本之间互不引用，仅 `run_synth/run_impl` 共享
`reports/collect_reports.tcl` 中的 `vc::collect_reports` 过程。

## 4. 数据流与产物

| 阶段 | 输入 | 产物 |
|------|------|------|
| project create | name/part | `<dir>/<name>.xpr` + 状态文件登记 |
| pins apply | pins.csv | pins.xdc（校验不通过则拒绝生成） |
| synth run | .xpr + 源 + 约束 | vc_reports/{timing_summary_synth,utilization_synth,clocks_synth}.rpt |
| impl run | synth_1 完成 | impl_1/<top>.bit + vc_reports/*_impl.rpt |
| hwdef export | synth/impl 结果 | `<工程名>.hdf`（可选含 bit） |
| report timing | *.rpt | WNS/TNS/WHS/THS + 违例路径 + 优化建议 |

## 5. 设计取舍

- **批处理而非常驻 Tcl 会话**：交互式桥（socket）单步延迟低，但服务生命周期、
  崩溃恢复、Windows 兼容都是负担；project mode 下批处理每阶段多花 10-30s 打开工程，
  换来完全确定的故障恢复（看日志即可）。
- **流程逻辑放 Tcl、编排放 Python**：Tcl 贴近 Vivado API（版本差异集中在一处）；
  Python 负责参数、文件、解析、安全策略，二者通过 VC_* 标记协议解耦。
- **启发式 lint 与 xvlog 并存**：纯 Python lint 秒回、可离线；`--vivado` 调用
  xvlog 做权威语法检查。两者定位不同，不互替。
- **时序建议是规则引擎而非黑盒**：每条建议都能映射回具体 CLI 命令或 XDC/RTL 改动，
  便于 Agent 按建议自主迭代（第 5 节"时序优化循环"）。
