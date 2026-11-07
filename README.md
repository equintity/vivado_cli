# vivado_cli — 通用 FPGA/Vivado Skills 集合（单一事实源）

本仓库是 **通用（host 无关）AI skills 集合仓库**，即"单一事实源"（source of truth）。
仓库内只包含标准 skills 格式的内容——`skills/<name>/SKILL.md` + 随附资源——
**不含任何特定宿主（ZCode/Claude Code/Codex 等）的插件清单、市场文件或集成代码**。

当前包含的 skills：

| Skill | 目录 | 说明 |
|-------|------|------|
| vivado-cli | [`skills/vivado-cli/`](skills/vivado-cli/) | Vivado 2018.x 全工作流：工程管理、Verilog 开发辅助、引脚映射管理、Zynq-7000 PL/PS、综合与时序优化、比特流、JTAG 烧写、HDF 导出 |

## 安装到任意 CLI/Agent（通用 skills 格式）

skill 是"一个目录，内含 SKILL.md"。把 `skills/vivado-cli/` 整个目录复制到宿主的
用户级 skills 目录即可（目录名 `vivado-cli` 与 frontmatter `name` 一致）：

```bash
# ZCode / Claude Code（用户级，跨工程生效）
cp -r skills/vivado-cli  ~/.agents/skills/vivado-cli
# 或 ZCode 工程级
cp -r skills/vivado-cli  <工程>/.agents/skills/vivado-cli
```

安装后按各宿主的 skill 触发机制使用；也可直接把本目录当普通 CLI 工具用
（`python skills/vivado-cli/scripts/vivado_cli.py --help`）。

## 目录结构

```
vivado_cli/                    ← 仓库根（通用 skills 集合）
├── README.md                  ← 本文件
├── LICENSE / .gitignore
└── skills/
    └── vivado-cli/            ← 标准 skill 目录（目录名 = frontmatter name）
        ├── SKILL.md           ← 入口：触发条件、命令总览、工作流、边界
        ├── references/        ← 按需阅读：design.md / comparison.md / vivado2018_notes.md
        ├── scripts/           ← Python CLI（纯标准库）
        ├── tcl/               ← Vivado 2018.2 兼容 Tcl 流程库
        └── assets/            ← templates/ 引脚表模板、examples/ 示例
```

## 与 ZCode 插件的关系（边界声明）

ZCode 专属插件（清单 + 本地市场 + 打包副本 + 同步工具）**独立存放于
`D:\AI\skills-git\zcode-plugins\`**，与本仓库完全分离：

- 本仓库永远是纯通用 skills，不得出现 `.zcode-plugin/`、`marketplace.json` 等
  宿主专属文件；
- 插件通过 `tools/sync_from_skill_repo.py` 从本仓库**单向同步** skill 副本，
  修改 skill 一律在本仓库进行，插件只消费。

## License

MIT
