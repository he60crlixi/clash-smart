#!/usr/bin/env python3
"""Clash Smart - 智能代理控制与网络检测。

纯 Python 零依赖。通过 Clash Verge Rev 的 HTTP API 控制代理，
并内置网络检测、大文件下载预警、智能切换策略。
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ── 默认配置 ──────────────────────────────────────────────────────────

DEFAULT_HTTP = os.environ.get("CLASH_API", "http://127.0.0.1:9090")
DEFAULT_SECRET = os.environ.get("CLASH_SECRET", "")

# 网络检测端点（按优先级）
NETWORK_CHECK_ENDPOINTS = [
    ("tcp", "120.53.53.53", 80, 3),   # 阿里云 (国内)
    ("tcp", "8.8.8.8", 53, 3),        # Google DNS (国际)
    ("url", "https://www.apple.com/library/test/success.html", 5),  # 苹果（国内直连）
    ("url", "https://www.google.com/generate_204", 5),              # Google（需代理）
]

# 大文件下载阈值 (5GB)
LARGE_FILE_THRESHOLD = 5 * 1024 * 1024 * 1024

# 最小切换间隔（秒），防止频繁切换
MIN_SWITCH_INTERVAL = 30

# 缓存目录（记录最近操作）
CACHE_DIR = Path(os.environ.get("CLASH_CACHE_DIR", str(Path.home() / "AppData" / "Local" / "clash-smart-cache")))


# ── API 客户端 ──────────────────────────────────────────────────────

def _http_request(method: str, path: str, body=None, timeout: int = 10):
    """向 mihomo 发送 HTTP 请求，返回 JSON 结果。"""
    headers = {"Content-Type": "application/json"}
    secret = os.environ.get("CLASH_SECRET", DEFAULT_SECRET)
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    api_url = os.environ.get("CLASH_API", DEFAULT_HTTP)
    url = api_url.rstrip("/") + path

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace") if e.fp else ""
        return {"_error": f"HTTP {e.code}: {err_body}", "_status": e.code}
    except (urllib.error.URLError, OSError) as e:
        return {"_error": str(e), "_status": 0}


# ── 状态缓存 ────────────────────────────────────────────────────────

def _load_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / "last_action.json"
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_cache(data: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / "last_action.json"
    with open(cache_file, "w") as f:
        json.dump(data, f)


def _can_switch():
    """检查是否可以执行切换操作（不在冷却期内）。"""
    cache = _load_cache()
    if not cache.get("action"):
        return True
    elapsed = time.time() - cache.get("time", 0)
    if elapsed < MIN_SWITCH_INTERVAL:
        return False
    return True


def _record_action(action: str):
    """记录最近一次操作时间。"""
    _save_cache({"action": action, "time": time.time()})


# ── 网络检测 ────────────────────────────────────────────────────────

def _check_tcp(host, port, timeout):
    """TCP 连通性检测。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except (socket.timeout, OSError):
        s.close()
        return False


def _check_url(url, timeout):
    """HTTP URL 连通性检测。"""
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "clash-smart/1.0")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def check_network(check_proxy: bool = False) -> dict:
    """综合网络检测。

    检测国内直连、国际访问、Clash 状态，返回综合结果。
    """
    results = {}
    clashing_working = False

    # 依次检测各端点
    for i, (scheme, target, timeout) in enumerate(NETWORK_CHECK_ENDPOINTS[:2]):
        key = "cn_direct" if i == 0 else "global_proxy"
        if scheme == "tcp":
            results[key] = _check_tcp(target, timeout=timeout)
        elif scheme == "url":
            results[key] = _check_url(target, timeout=timeout)

    # 检测 Clash API 是否可用
    clash_resp = _http_request("GET", "/version")
    if "_error" not in clash_resp:
        clashing_working = True

    # 检测 Clash 当前模式
    if clashing_working:
        try:
            cfg = _http_request("GET", "/configs")
            clash_mode = cfg.get("mode", "?")
        except Exception:
            clash_mode = "?"
    else:
        clash_mode = "clash-not-running"

    # 判断结论
    cn_ok = results.get("cn_direct", False)
    global_ok = results.get("global_proxy", False)

    if not cn_ok and not global_ok:
        conclusion = "network-down"
        suggestion = "clash-needed"
        desc = "网络完全不可用"
    elif not global_ok:
        conclusion = "no-proxy-needed"
        suggestion = "none"
        desc = "国内直连正常，国际站不可达（可能需要代理）"
    else:
        conclusion = "proxy-ok"
        suggestion = "clash-ready"
        desc = "直连和代理均正常"

    # 如果检测代理状态（首次访问未知站点）
    if check_proxy and not cn_ok and not global_ok:
        # 两个都 fail → 可能需要 Clash
        if clashing_working and clash_mode != "direct":
            suggestion = "clash-running"
            desc = "Clash 已在运行且非直连模式"
        elif clashing_working and clash_mode == "direct":
            suggestion = "switch-clash"
            desc = "Clash 在运行但为直连模式，需要切换"

    return {
        "cn_direct": cn_ok,
        "global_proxy": global_ok,
        "clash_working": clashing_working,
        "clash_mode": clash_mode,
        "conclusion": conclusion,
        "suggestion": suggestion,
        "description": desc,
        "details": results,
    }


# ── Clash 控制 ──────────────────────────────────────────────────────

def get_status() -> dict:
    """获取 Clash 完整状态。"""
    resp = _http_request("GET", "/version")
    cfg_resp = _http_request("GET", "/configs")
    conns_resp = _http_request("GET", "/connections")
    proxies_resp = _http_request("GET", "/proxies")

    version = resp.get("version", "unknown") if "_error" not in resp else "not-running"
    mode = cfg_resp.get("mode", "?") if "_error" not in cfg_resp else "?"
    conns = conns_resp.get("connections", []) if "_error" not in conns_resp else []
    proxies_data = proxies_resp.get("proxies", {}) if "_error" not in proxies_resp else {}

    active_conns = len(conns)
    upload_total = conns_resp.get("uploadTotal", 0) if "_error" not in conns_resp else 0
    download_total = conns_resp.get("downloadTotal", 0) if "_error" not in conns_resp else 0

    # 代理组
    group_types = ("Selector", "URLTest", "Fallback", "LoadBalance")
    groups = {}
    for name, info in proxies_data.items():
        if info.get("type") in group_types:
            now = info.get("now", "-")
            n_all = len(info.get("all", []))
            groups[name] = {"current": now, "total": n_all}

    return {
        "version": version,
        "mode": mode,
        "active_connections": active_conns,
        "upload_total": upload_total,
        "download_total": download_total,
        "groups": groups,
        "proxy_count": len(proxies_data),
    }


def enable_clash() -> dict:
    """切换到代理模式（rule 模式即可走代理规则）。"""
    if not _can_switch():
        cache = _load_cache()
        remaining = int(MIN_SWITCH_INTERVAL - (time.time() - cache.get("time", 0)))
        return {"ok": False, "error": f"冷却中，{remaining}秒后可再次切换"}

    resp = _http_request("PATCH", "/configs", {"mode": "rule"})
    if "_error" not in resp:
        _record_action("enable")
        return {"ok": True, "mode": "rule", "message": "已切换到代理模式（rule）"}
    return {"ok": False, "error": resp.get("_error", "unknown error")}


def disable_clash() -> dict:
    """切换到直连模式。"""
    if not _can_switch():
        cache = _load_cache()
        remaining = int(MIN_SWITCH_INTERVAL - (time.time() - cache.get("time", 0)))
        return {"ok": False, "error": f"冷却中，{remaining}秒后可再次切换"}

    resp = _http_request("PATCH", "/configs", {"mode": "direct"})
    if "_error" not in resp:
        _record_action("disable")
        return {"ok": True, "mode": "direct", "message": "已切换到直连模式"}
    return {"ok": False, "error": resp.get("_error", "unknown error")}


def switch_mode(mode: str) -> dict:
    """设置代理模式。"""
    if mode not in ("rule", "global", "direct"):
        return {"ok": False, "error": f"无效模式: {mode}，可选: rule, global, direct"}

    resp = _http_request("PATCH", "/configs", {"mode": mode})
    if "_error" not in resp:
        _record_action("switch")
        return {"ok": True, "mode": mode, "message": f"已切换到 {mode} 模式"}
    return {"ok": False, "error": resp.get("_error", "unknown error")}


def list_groups() -> dict:
    """列出所有代理组。"""
    resp = _http_request("GET", "/proxies")
    if "_error" in resp:
        return {"ok": False, "error": resp["_error"]}

    proxies = resp.get("proxies", {})
    group_types = ("Selector", "URLTest", "Fallback", "LoadBalance")
    groups = {}

    for name, info in proxies.items():
        if info.get("type") in group_types:
            now = info.get("now", "-")
            delay_info = _get_node_delay(name)
            groups[name] = {
                "current": now,
                "type": info.get("type"),
                "delay": delay_info,
            }

    return {"ok": True, "groups": groups}


def list_nodes(group: str = "") -> dict:
    """列出节点。

    如果 group 为空，列出所有组的第一层节点。
    如果指定 group，列出该组下所有节点。
    """
    resp = _http_request("GET", "/proxies")
    if "_error" in resp:
        return {"ok": False, "error": resp["_error"]}

    proxies = resp.get("proxies", {})

    if group:
        group_data = proxies.get(group)
        if not group_data:
            return {"ok": False, "error": f"找不到组: {group}"}
        all_nodes = group_data.get("all", [])
        now = group_data.get("now", "")
        result_nodes = []
        for node_name in all_nodes:
            node_info = proxies.get(node_name, {})
            delay = _get_node_delay(node_name)
            result_nodes.append({
                "name": node_name,
                "current": node_name == now,
                "type": node_info.get("type", "?"),
                "delay": delay,
            })
        return {"ok": True, "group": group, "nodes": result_nodes}

    # 列出所有组
    group_types = ("Selector", "URLTest", "Fallback", "LoadBalance")
    result = {}
    for name, info in proxies.items():
        if info.get("type") in group_types:
            now = info.get("now", "")
            all_nodes = info.get("all", [])
            result[name] = {
                "current": now,
                "node_count": len(all_nodes),
            }

    return {"ok": True, "groups": result}


def _get_node_delay(node_name: str) -> int:
    """获取节点延迟。"""
    resp = _http_request("GET", f"/proxies/{_urlencode(node_name)}/delay?url=http%3A%2F%2Fwww.google.com%2Fgenerate_204&timeout=3000")
    if "_error" not in resp:
        return resp.get("delay", 0)
    return 0


def switch_node(group: str, node: str) -> dict:
    """切换到指定节点。"""
    resp = _http_request("PUT", f"/proxies/{_urlencode(group)}", {"name": node})
    if "_error" not in resp:
        return {"ok": True, "message": f"已切换到 {group} → {node}"}
    return {"ok": False, "error": resp.get("_error", "unknown error")}


def _urlencode(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(s, safe="")


# ── 大文件检测 ──────────────────────────────────────────────────────

def check_download(url_or_path: str, size_hint=None) -> dict:
    """检查是否为大文件下载，返回是否需要代理。

    策略：
    1. 如果提供了 size_hint (bytes)，直接判断
    2. 如果是 URL，尝试获取 Content-Length
    3. 如果是本地路径，获取文件大小
    4. 如果都无法获取，根据 URL 特征启发式判断
    """
    is_large = False
    size_bytes = 0
    reason = ""

    # 1. 直接提供大小
    if size_hint is not None:
        size_bytes = size_hint
        is_large = size_bytes >= LARGE_FILE_THRESHOLD
        reason = f"文件大小: {_fmt_bytes(size_bytes)}"

    # 2. 尝试 URL
    elif url_or_path.startswith("http"):
        try:
            req = urllib.request.Request(url_or_path, method="HEAD")
            req.add_header("User-Agent", "clash-smart/1.0")
            resp = urllib.request.urlopen(req, timeout=5)
            content_length = resp.headers.get("Content-Length")
            if content_length:
                size_bytes = int(content_length)
                is_large = size_bytes >= LARGE_FILE_THRESHOLD
                reason = f"Content-Length: {_fmt_bytes(size_bytes)}"

            # 启发式判断
            if not is_large:
                path = resp.headers.get("Content-Disposition", "")
                if "attachment" in path or "download" in url_or_path.lower():
                    is_large = True
                    reason = f"URL 含下载特征（可能需要代理）"
        except Exception:
            # 无法获取 → 启发式判断
            is_large = _is_likely_large(url_or_path)
            if is_large:
                reason = "URL 特征判断为大文件下载（可能需要代理）"

    # 3. 本地路径
    else:
        try:
            size_bytes = Path(url_or_path).stat().st_size
            is_large = size_bytes >= LARGE_FILE_THRESHOLD
            reason = f"文件大小: {_fmt_bytes(size_bytes)}"
        except OSError:
            is_large = False
            reason = "无法确定文件大小"

    # 返回结果
    return {
        "url": url_or_path,
        "size_bytes": size_bytes,
        "size_human": _fmt_bytes(size_bytes) if size_bytes else "unknown",
        "is_large": is_large,
        "reason": reason,
        "threshold": _fmt_bytes(LARGE_FILE_THRESHOLD),
    }


def _is_likely_large(url: str) -> bool:
    """启发式判断 URL 是否可能是大文件。"""
    large_indicators = [
        r"\.zip$", r"\.7z$", r"\.tar\.gz$", r"\.gz$", r"\.rar$",
        r"\.iso$", r"\.dmg$", r"\.pkg$", r"\.exe$",  # 注意：exe 不一定大
        r"/releases/download/", r"/download/", r"/archive/",
        r"file_size=\d{9,}", r"&size=\d{9,}",  # 9 digits = 1GB+
        r"git\s+(clone|pull)", r"pacman\s+-S", r"apt.*install",
        r"pip\s+install", r"npm\s+install", r"cargo\s+install",
    ]
    url_lower = url.lower()
    for pattern in large_indicators:
        import re
        if re.search(pattern, url_lower):
            return True
    return False


# ── 流量格式化 ──────────────────────────────────────────────────────

def _fmt_bytes(n: int) -> str:
    if n == 0:
        return "0B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Clash Smart - 智能代理控制",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--api", default=DEFAULT_HTTP, help="Clash API URL")
    p.add_argument("--secret", default=DEFAULT_SECRET, help="API secret")

    sub = p.add_subparsers(dest="cmd")

    # 网络检测
    check_p = sub.add_parser("check-network", help="综合网络检测")
    check_p.add_argument("--proxy", action="store_true",
                         help="检测是否需要代理（模拟首次访问）")

    # 状态
    sub.add_parser("status", help="Clash 完整状态")

    # 代理控制
    enable_p = sub.add_parser("enable", help="开启代理（rule 模式）")
    disable_p = sub.add_parser("disable", help="关闭代理（direct 模式）")
    mode_p = sub.add_parser("mode", help="设置代理模式")
    mode_p.add_argument("m", choices=["rule", "global", "direct"], help="目标模式")

    # 代理信息
    sub.add_parser("groups", help="列出代理组")
    nodes_p = sub.add_parser("nodes", help="列出节点")
    nodes_p.add_argument("group", nargs="?", help="组名（可选）")
    select_p = sub.add_parser("select", help="切换节点")
    select_p.add_argument("group", help="组名")
    select_p.add_argument("node", help="节点名")

    # 大文件检测
    dl_p = sub.add_parser("check-download", help="检测是否为大文件")
    dl_p.add_argument("url_or_path", help="URL 或文件路径")
    dl_p.add_argument("--size", type=int, help="文件大小 (bytes)，可选")

    # 订阅信息
    sub.add_parser("subscription", help="订阅信息（节点 + 流量）")

    args = p.parse_args()

    if not args.cmd:
        p.print_help()
        sys.exit(0)

    # 执行命令
    cmd = args.cmd

    if cmd == "check-network":
        result = check_network(check_proxy=getattr(args, "proxy", False))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "status":
        result = get_status()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "enable":
        result = enable_clash()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "disable":
        result = disable_clash()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "mode":
        result = switch_mode(args.m)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "groups":
        result = list_groups()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "nodes":
        group = getattr(args, "group", "")
        result = list_nodes(group)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "select":
        result = switch_node(args.group, args.node)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "check-download":
        size = getattr(args, "size", None)
        result = check_download(args.url_or_path, size)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "subscription":
        result = get_status()
        if "_error" not in result:
            # 格式化输出
            print(f"Clash 订阅状态:")
            print(f"  版本: {result.get('version', '?')}")
            print(f"  模式: {result.get('mode', '?')}")
            print(f"  当前连接: {result.get('active_connections', 0)}")
            up = result.get("upload_total", 0)
            down = result.get("download_total", 0)
            print(f"  本次会话流量: ↑{_fmt_bytes(up)}  ↓{_fmt_bytes(down)}")

            groups = result.get("groups", {})
            if groups:
                print(f"\n  代理组:")
                for gname, ginfo in sorted(groups.items()):
                    cur = ginfo.get("current", "?")
                    print(f"    {gname}: {cur}")
            print(f"\n  提示: 订阅剩余流量需在订阅页面查看")
        else:
            print(f"Clash 未运行")
            print(f"  错误: {result.get('error', result.get('_error', 'unknown'))}")
            sys.exit(1)

    else:
        p.print_help()


if __name__ == "__main__":
    main()
