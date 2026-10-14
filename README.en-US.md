# clash-smart

> 中文版: [README.md](README.md)

Smart proxy control tool — auto-detect network status, invoke Clash Verge Rev on demand, large file download warnings, intelligent switching to prevent abuse.

## Inspiration

This project is inspired by [Hsiifu3/clash-verge-skill](https://github.com/Hsiifu3/clash-verge-skill). On top of the original CLI control approach, it adds:

- **Network Detection**: Comprehensive check for mainland direct / international access / Clash status
- **Large File Warning**: Detects download requests >5GB, proactively asks the user
- **Anti-Abuse Mechanism**: 30-second cooldown prevents frequent proxy switching
- **On-Demand Strategy**: Doesn't auto-switch back after access, user decides when to disable
- **Windows Support**: Pure HTTP API (Unix socket retained for macOS/Linux)

The original project is an excellent OpenClaw Skill. This project extends it into a complete agent-centric intelligent control solution.

## Features

| Feature | Command |
|---------|---------|
| Network detection | `check-network --proxy` |
| Enable/disable proxy | `enable` / `disable` |
| Set proxy mode | `mode <rule\|global\|direct>` |
| Large file detection | `check-download <url> [--size N]` |
| Subscription info | `subscription` |
| Proxy group management | `groups` / `nodes` / `select` |

## Installation

### OpenCode / OpenClaw Skill

```bash
# Manual installation
git clone https://github.com/he60crlixi/clash-smart.git
# Place the clash-smart/ directory in your skill directory
# macOS/Linux: ~/.config/claw/agents/skills/
# Windows: %APPDATA%\claw\agents\skills\
```

### Standalone Usage

```bash
git clone https://github.com/he60crlixi/clash-smart.git
cd clash-smart

# Test network detection
python scripts/clash-smart.py check-network --proxy

# Check Clash status
python scripts/clash-smart.py status
```

## Configuration

Set Clash API via environment variables:

```bash
# Windows (PowerShell)
$env:CLASH_API = "http://127.0.0.1:9090"
$env:CLASH_SECRET = "your-secret"

# macOS / Linux
export CLASH_API="http://127.0.0.1:9090"
export CLASH_SECRET="your-secret"
```

## Intelligent Decision Rules

### Website Access Flow

1. Run `check-network --proxy` to detect network status
2. Judge based on the `suggestion` field:

| suggestion | Action |
|------------|--------|
| `clash-needed` | Ask user whether to enable proxy |
| `switch-clash` | Ask whether to switch proxy mode |
| `clash-running` | Access directly |
| `none` | Access normally |

3. After access, ask the user if they want to disable the proxy (does not auto-switch back)

### Large File Download Flow

```bash
python scripts/clash-smart.py check-download <url> --size <bytes>
```

If `is_large` is `true` and the proxy is already enabled → ask the user.

### Anti-Abuse Mechanism

- 30-second cooldown (recorded in `~/.clash-smart-cache/last_action.json`)
- No operation when proxy is not needed
- Respects user choice when they say "no proxy"

## License

This project uses the MIT License.

> This work was inspired by [Hsiifu3/clash-verge-skill](https://github.com/Hsiifu3/clash-verge-skill), protected under its MIT License. The extended code in this project was contributed by the project author and also uses the MIT License.
