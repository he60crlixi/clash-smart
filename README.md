# clash-smart

智能代理控制工具 - 自动检测网络状态、按需调用 Clash Verge Rev、大文件下载预警、智能切换防滥用。

## 灵感来源

本项目受 [Hsiifu3/clash-verge-skill](https://github.com/Hsiifu3/clash-verge-skill) 启发，在原作者的 CLI 控制思路基础上，增加了：

- **网络检测**：综合检测国内直连 / 国际访问 / Clash 状态
- **大文件预警**：检测 >5GB 下载请求，主动询问用户
- **防滥用机制**：30 秒冷却期，防止频繁切换代理
- **按需调用策略**：访问完不自动切回，由用户决定是否关闭
- **Windows 适配**：纯 HTTP API（Unix socket 仅 macOS/Linux 保留）

原作者项目是一个优秀的 OpenClaw Skill，本项目在此基础上扩展为面向 Agent 的完整智能控制方案。

## 功能

| 功能 | 命令 |
|------|------|
| 综合网络检测 | `check-network --proxy` |
| 开启/关闭代理 | `enable` / `disable` |
| 设置代理模式 | `mode <rule\|global\|direct>` |
| 大文件检测 | `check-download <url> [--size N]` |
| 订阅状态 | `subscription` |
| 代理组管理 | `groups` / `nodes` / `select` |

## 安装

### OpenCode / OpenClaw Skill

```bash
# 手动安装
git clone https://github.com/he60crlixi/clash-smart.git
# 将 clash-smart/ 目录放到你的 skill 目录
# macOS/Linux: ~/.config/claw/agents/skills/
# Windows: %APPDATA%\claw\agents\skills\
```

### 独立使用

```bash
git clone https://github.com/he60crlixi/clash-smart.git
cd clash-smart

# 测试网络检测
python scripts/clash-smart.py check-network --proxy

# 查看 Clash 状态
python scripts/clash-smart.py status
```

## 配置

通过环境变量设置 Clash API：

```bash
# Windows (PowerShell)
$env:CLASH_API = "http://127.0.0.1:9090"
$env:CLASH_SECRET = "your-secret"

# macOS / Linux
export CLASH_API="http://127.0.0.1:9090"
export CLASH_SECRET="your-secret"
```

## 智能决策规则

### 访问网站流程

1. 执行 `check-network --proxy` 检测网络
2. 根据 `suggestion` 字段判断：

| suggestion | 操作 |
|------------|------|
| `clash-needed` | 询问用户是否开启代理 |
| `switch-clash` | 询问是否切换代理模式 |
| `clash-running` | 直接访问 |
| `none` | 正常访问 |

3. 访问完成后询问用户是否关闭代理（不自动切回）

### 大文件下载流程

```bash
python scripts/clash-smart.py check-download <url> --size <bytes>
```

如果 `is_large` 为 `true` 且代理已开启 → 询问用户。

### 防滥用机制

- 30 秒冷却期（记录在 `~/.clash-smart-cache/last_action.json`）
- 无需代理时不执行任何操作
- 用户说"不用代理"时尊重选择

## 许可证

本项目采用 MIT 许可证。

> 本作品灵感来源于 [Hsiifu3/clash-verge-skill](https://github.com/Hsiifu3/clash-verge-skill)，受其 MIT 许可证保护。本项目的扩展代码由本项目作者贡献，同样采用 MIT 许可证。
