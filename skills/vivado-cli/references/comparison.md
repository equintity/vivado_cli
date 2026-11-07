# GitHub 检索：已有 Vivado CLI Skills 方案对比

检索时间：2026-11；检索范围：GitHub 仓库搜索（`vivado skill` / `vivado claude` /
`vivado mcp` / `vivado cli`）+ Web 搜索交叉验证。**结论：已有多个开源方案**，
无"从零空白"需要，但都存在与本地 Vivado 2018 / Windows 原生环境不完全匹配的问题，
故参考其设计再实现本 skill。

## 检索到的代表性方案

| 仓库 | ★ | 类型 | 功能范围 | 关键设计 |
|------|----|------|----------|----------|
| [QingquanYao/xilinx-skill](https://github.com/QingquanYao/xilinx-skill) | 482 | 文档路由型 | HLS/Vivado/Vitis/PetaLinux 全链，含 MPSoC PS 配置、JESD204 迁移 | SKILL.md + references/*.md 按工具路由加载；生成脚本但不执行，全自动依赖 vivado-mcp 等 MCP Server |
| [phamcuong21478/rtl-skills](https://github.com/phamcuong21478/rtl-skills) | 21 | 流程 skills 集 | 架构→RTL→lint→仿真→回归→综合→文档 | 一页 IP 规格驱动，偏验证流程 |
| [LNC0831/oh-my-fpga](https://github.com/LNC0831/oh-my-fpga) | 23 | 技能包 | 时序收敛、CDC 审计、全流程、Zynq bring-up | 依赖 SynthPilot MCP |
| [hjxxlogic/open-vivado](https://github.com/hjxxlogic/open-vivado) | 15 | 常驻桥接型 | 工程管理、RTL/XDC、综合实现、时序解析、比特流 | Python ⇄ JSON/TCP ⇄ Vivado Tcl socket server；明确支持 2018.1+；报告解析（timing/utilization/power） |
| [Nacholazabal/fpga-claude](https://github.com/Nacholazabal/fpga-claude) | 11 | 批处理 CLI | ILA 抓波 + LLM 分析 | Python CLI 驱动批处理 Tcl，tagged stdout（`FPGA_CLAUDE_JSON:`）回传——与本 skill 的 VC_* 标记同思路 |
| [Aneein/Vivado-Automation-Skill](https://github.com/Aneein/Vivado-Automation-Skill) | 5 | 批处理 CLI | 项目迁移（2020.2→2021.1）、BD 重建、IP 升级、Vitis BSP 补丁 | Python `vivado_assistant.py` 直调 vivado.bat + 配置 JSON；"hard workflow"固定顺序 |
| [AMD Ross](https://www.amd.com)（官方） | - | 官方技能 | FPGA/SoC 设计步骤化、Hardware Manager Tcl 调试 | SKILL.md 指令集，绑定官方工具链 |

## 设计范式对比

### ① 文档路由型（xilinx-skill）
- **优点**：知识密度最高（版本化 API 参考、PS 配置引导、迁移指南）；零执行依赖，
  任何 Agent 都能装；覆盖面最广（HLS/PetaLinux/Vitis）。
- **缺点**：**不落地执行**——生成脚本后仍需人跑或接 MCP；对本任务要求的
  "CLI skills"（可执行、可反馈、可迭代）差一环；无 2018 版本锁定。

### ② 常驻桥接型（open-vivado、SynthPilot 系）
- **优点**：真正的交互式会话，单命令延迟低；结构化 JSON 协议；报告解析能力强；
  明确支持 Vivado 2018.1+。
- **缺点**：常驻服务生命周期管理（start/stop/lock/崩溃恢复）复杂；Windows 原生
  路径下 socket 桥易受防火墙/编码影响；对 Agent 而言多一层故障面。

### ③ 批处理直调型（fpga-claude、Vivado-Automation-Skill）
- **优点**：与 Vivado 官方脚本化用法一致（`-mode batch`），可靠性最高；
  日志即状态，失败可恢复；无守护进程。fpga-claude 的 tagged stdout 协议
  验证了"批处理 + 标记回传"对 Agent 友好。
- **缺点**：每阶段重开工程（10-30s 开销）；fpga-claude 只覆盖 ILA 场景；
  Aneein 版把工作流顺序硬编码进 Python，且 Tcl 逻辑散在 Python 字符串里，版本适配差。

### ④ MCP 型（vivado-mcp 等）
- 优点：工具粒度细、Agent 可自由组合；缺点：MCP Server 安装/连接是额外依赖，
  与"纯 CLI skill"目标不符，且多数按新版 Vivado 编写。

## 本 skill（vivado_cli）与参考设计的差异

| 维度 | 参考方案 | vivado_cli 的选择 |
|------|----------|-------------------|
| 执行模型 | 文档路由（不执行）/ MCP / 常驻桥 | **批处理直调 + VC_* 标记回传**（取 ③ 的可靠性 + ① 的可迭代性） |
| 流程逻辑位置 | Python 字符串（Aneein）/ MCP 内（vivado-mcp） | **独立版本化 Tcl 库**（tcl/），Python 只编排与解析——2018 API 差异集中在一处 |
| 引脚管理 | 均无专门模块（只有 XDC 生成指引） | **一等模块**：CSV 引脚表 ⇄ XDC、静态/封装/RTL 交叉三层校验 |
| 时序优化 | 报告解析为主（open-vivado 最强） | 解析 + **规则化建议引擎**，每条建议映射回可执行 CLI/XDC/RTL 动作 |
| PS/PL | xilinx-skill 覆盖 MPSoC（新版）；open-vivado 无 BD | **Zynq-7000 PS7 最小系统**（2018 时代器件），CONFIG.PCW_* 键值直通 |
| 版本目标 | 2020+ 为主 | **锁定 Vivado 2018.x**（HDF 而非 XSA、open_hw 而非新 HW API、SDK 而非 Vitis） |
| 交付物 | 脚本/文档 | 全流程产物：.xpr/.xdc/.bit/.hdf + 报告 + 建议 |
| 依赖 | 多需 MCP/第三方库 | **纯标准库 Python + Vivado 自带工具** |

明确**不引入**的参考设计元素：
- xilinx-skill 的 HLS/PetaLinux/Vitis 路由（2018.2 无 Vitis Unified；PetaLinux 超出边界）；
- open-vivado 的常驻 socket 桥（换取免维护的批处理模型）；
- fpga-claude 的 ILA 抓波（后续可作为 `hw ila` 扩展，参考其 tagged stdout 协议即可）。

## 结论

GitHub 上**已存在**成熟度不一的 Vivado CLI skills，最有价值的参考是：
xilinx-skill 的"参考文档路由 + 输出规范"、open-vivado 的"报告解析与 2018 兼容性关注"、
fpga-claude/Aneein 的"批处理直调 + 结构化回传"。本 skill 取三者之长，并补齐
三者都缺的**引脚映射管理**与**时序建议→行动闭环**，全部按本地 Vivado 2018.2
适配（详见 [vivado2018_notes.md](vivado2018_notes.md)）。
