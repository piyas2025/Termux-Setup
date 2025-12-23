#!/usr/bin/env python3
"""
termux-power-suite.py

FULL COMBINED VERSION
PART 1/3

⚠️ Do NOT run until PART 2 & PART 3 are appended.
"""

from __future__ import annotations

import os
import sys
import subprocess
import shlex
import shutil
import time
import difflib
import json
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Optional

# ================= ANSI COLORS =================
BLUE = "\033[94m"
RESET = "\033[0m"

# ================= BANNER =================
def show_banner():
    os.system("clear")
    print(BLUE + r"""
████████╗███████╗██████╗ ███╗   ███╗██╗   ██╗██╗  ██╗
╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║   ██║╚██╗██╔╝
   ██║   █████╗  ██████╔╝██╔████╔██║██║   ██║ ╚███╔╝
   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║   ██║ ██╔██╗
   ██║   ███████╗██║  ██║██║ ╚═╝ ██║╚██████╔╝██╔╝ ██╗
   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝

        TERMUX POWER SUITE
""" + RESET)

# ================= DASHBOARD =================
def dashboard_menu():
    while True:
        show_banner()
        print("[1] Full Termux Power Suite Setup")
        print("[2] Web → IP & Domain")
        print("[3] Web → Port Scan")
        print("[0] Exit\n")

        c = input("Select: ").strip()

        if c == "1":
            show_banner()
            original_main()
            input("\nSetup finished. Press Enter...")
        elif c == "2":
            web_to_ip()
        elif c == "3":
            web_port_scan()
        elif c == "0":
            sys.exit(0)

# ================= USER CONFIG =================
MAX_RETRIES = 3
BACKOFF_BASE = 4
CMD_TIMEOUT = 900
LOG_ROTATE_BYTES = 8_000_000

AUTO_CORRECT_MODE = os.environ.get("AUTO_CORRECT_MODE", "silent").lower()
PKG_NAME_CONFIDENCE = 0.72

GITHUB_PER_PAGE = 30
GITHUB_SEARCH_LIMIT = 120

HOME = Path.home()
LOGFILE = HOME / "termux-full-setup.log"
TOOLS_DIR = HOME / "tools"
TOOL_LIST = HOME / "tools-list.txt"
BACKUP_DIR = HOME / "tool-backups"
SELF_UPDATE_SCRIPT = HOME / "termux-self-update.sh"
TOOL_MANAGER_SCRIPT = HOME / "termux-tool-manager.sh"
AUTO_MAINTAIN_SCRIPT = HOME / "termux-auto-maintain.sh"
BASHRC = HOME / ".bashrc"

# ================= LOGGING =================
def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg, to_console=True):
    line = f"[{ts()}] {msg}"
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass
    if to_console:
        print(line)

def rotate_logs(max_size=LOG_ROTATE_BYTES):
    try:
        if LOGFILE.exists() and LOGFILE.stat().st_size > max_size:
            new = LOGFILE.with_name("termux-full-setup.old.log")
            LOGFILE.rename(new)
    except:
        pass

def ensure_dirs():
    TOOLS_DIR.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)

# ================= CORE RUN =================
def run_raw(cmd_list, check=False, capture=False, timeout=None):
    log("EXEC: " + " ".join(cmd_list), False)
    cp = subprocess.run(
        cmd_list,
        check=check,
        capture_output=capture,
        text=True,
        timeout=timeout
    )
    return cp.stdout if capture else cp

def run_with_retry(cmd, max_retries=MAX_RETRIES, timeout=CMD_TIMEOUT):
    for i in range(1, max_retries + 1):
        try:
            log(f"[TRY {i}] {cmd}")
            return run_raw(["bash", "-lc", cmd], True, True, timeout)
        except Exception as e:
            log(f"[FAIL] {e}")
            if i < max_retries:
                time.sleep(BACKOFF_BASE * i)
    raise RuntimeError(cmd)

# ================= WEB FEATURES =================
def web_to_ip():
    show_banner()
    url = input("Enter website: ").strip()
    if not url:
        return
    domain = url.replace("https://","").replace("http://","").split("/")[0]
    try:
        out = run_raw(["bash","-lc",f"getent hosts {shlex.quote(domain)}"], capture=True)
        print("\nDomain:", domain)
        for l in out.splitlines():
            print("IP:", l.split()[0])
    except:
        print("Resolve failed")
    input("\nPress Enter...")

def web_port_scan():
    show_banner()
    target = input("Enter website/IP: ").strip()
    if not target:
        return
    print("⚠️ Legal use only.")
    if input("Continue? (y/N): ").lower() != "y":
        return
    run_raw(["bash","-lc",f"nmap -F {shlex.quote(target)}"])
    input("\nPress Enter...")
# ================= AUTO-CORRECT ENGINE =================
CANONICAL_COMMANDS = {
    "apt": "apt",
    "pkg": "pkg",
    "pip": "pip",
    "python": "python",
    "git": "git",
    "bash": "bash",
    "nmap": "nmap",
    "sqlmap": "sqlmap",
    "hydra": "hydra",
    "openvpn": "openvpn",
}

COMMON_TOKEN_CORRECTIONS = {
    "updata": "update",
    "upgarde": "upgrade",
    "instal": "install",
    "insatll": "install",
    "pyhton": "python",
    "clne": "clone",
    "clera": "clear",
}

def smart_fix_token(token: str) -> str:
    if token in COMMON_TOKEN_CORRECTIONS:
        return COMMON_TOKEN_CORRECTIONS[token]
    if token in CANONICAL_COMMANDS:
        return CANONICAL_COMMANDS[token]
    matches = difflib.get_close_matches(
        token,
        list(CANONICAL_COMMANDS.keys()) + list(COMMON_TOKEN_CORRECTIONS.keys()),
        n=1,
        cutoff=0.78
    )
    if matches:
        m = matches[0]
        return COMMON_TOKEN_CORRECTIONS.get(m, CANONICAL_COMMANDS.get(m, m))
    return token

def autocorrect_command(cmd: str) -> str:
    parts = cmd.split()
    if not parts:
        return cmd
    parts[0] = smart_fix_token(parts[0])
    for i in range(1, len(parts)):
        if parts[i].startswith("-"):
            continue
        parts[i] = smart_fix_token(parts[i])
    fixed = " ".join(parts)
    if fixed != cmd:
        log(f"[autocorrect] {cmd} -> {fixed}")
    return fixed

# ================= PKG SEARCH + FUZZY =================
def pkg_search_candidates(name: str) -> list[str]:
    try:
        out = subprocess.run(
            ["bash","-lc",f"pkg search {shlex.quote(name)}"],
            capture_output=True,text=True,timeout=20
        )
        cands = []
        for l in out.stdout.splitlines():
            tok = l.split()[0]
            if tok:
                cands.append(tok)
        return list(dict.fromkeys(cands))
    except:
        return []

def choose_best_package(name: str, cands: list[str]) -> str | None:
    match = difflib.get_close_matches(name, cands, n=1, cutoff=PKG_NAME_CONFIDENCE)
    return match[0] if match else None

def prepare_command_for_run(cmd: str) -> str:
    cmd = autocorrect_command(cmd)
    parts = cmd.split()
    if not parts:
        return cmd

    if parts[0] in ("pkg","apt") and "install" in parts:
        idx = parts.index("install")
        pkgs = []
        for p in parts[idx+1:]:
            if p.startswith("-"):
                break
            pkgs.append(p)
        fixed = []
        for p in pkgs:
            cands = pkg_search_candidates(p)
            best = choose_best_package(p, cands)
            fixed.append(best if best else p)
        new_cmd = " ".join(parts[:idx+1] + fixed)
        if new_cmd != cmd:
            log(f"[pkg-fix] {cmd} -> {new_cmd}")
        return new_cmd

    return cmd

# ================= INSTALL PACKAGES =================
def install_packages():
    log("AUTO-HEAVY INSTALL STARTED")
    rotate_logs()

    BASE_CMDS = [
        "pkg update -y",
        "pkg upgrade -y",
        "apt update",
        "apt upgrade -y",
        "pkg update && pkg upgrade",
        "pkg update -y && pkg upgrade -y",
    ]

    PIP_CMDS = [
        "pip install --upgrade pip",
        "pip install colorama",
        "python -m pip install colorama",
        "pip install python-whois",
        "pip install tqdm",
        "python -m pip install tqdm",
        "pip install pyfiglet",
        "python -m pip install pyfiglet",
        "pip install tqdm pyfiglet colorama requests",
        "pip install requests",
    ]

    PKG_CMDS = [
        "pkg install python -y",
        "pkg install python2",
        "pkg install python3",
        "pkg install python-pip -y",
        "pkg install git",
        "pkg install termux-api",
        "pkg install php",
        "pkg install python git -y",
    ]

    for cmd in BASE_CMDS + PKG_CMDS + PIP_CMDS:
        try:
            fixed = prepare_command_for_run(cmd)
            run_with_retry(fixed)
        except Exception as e:
            log(f"[INSTALL ERROR] {cmd} -> {e}")

    log("AUTO-HEAVY INSTALL FINISHED")
# ================= SELF UPDATE SCRIPT =================
def create_self_update():
    log("Creating self-update script")
    content = r"""#!/data/data/com.termux/files/usr/bin/bash
pkg update -y || true
pkg upgrade -y || true
"""
    with open(SELF_UPDATE_SCRIPT, "w") as f:
        f.write(content)
    run_raw(["bash","-lc",f"chmod +x {SELF_UPDATE_SCRIPT}"])

# ================= TOOL MANAGER SCRIPT =================
def create_tool_manager():
    log("Creating tool manager")
    content = r"""#!/data/data/com.termux/files/usr/bin/bash
TOOLS_DIR="$HOME/tools"
LIST="$HOME/tools-list.txt"
mkdir -p "$TOOLS_DIR"

[ ! -f "$LIST" ] && {
  echo "# Add git URLs here" > "$LIST"
  exit 0
}

while read -r repo; do
  [ -z "$repo" ] && continue
  name=$(basename "$repo" .git)
  if [ -d "$TOOLS_DIR/$name/.git" ]; then
    cd "$TOOLS_DIR/$name" && git pull
  else
    git clone --depth 1 "$repo" "$TOOLS_DIR/$name"
  fi
done < "$LIST"
"""
    with open(TOOL_MANAGER_SCRIPT,"w") as f:
        f.write(content)
    run_raw(["bash","-lc",f"chmod +x {TOOL_MANAGER_SCRIPT}"])

# ================= AUTO MAINTAIN SCRIPT =================
def create_auto_maintain():
    log("Creating auto-maintain script")
    content = r"""#!/data/data/com.termux/files/usr/bin/bash
LOG="$HOME/termux-auto-maintain.log"
echo "[*] Auto maintain start: $(date)" >> "$LOG"

[ -x "$HOME/termux-self-update.sh" ] && "$HOME/termux-self-update.sh" >> "$LOG" 2>&1
[ -x "$HOME/termux-tool-manager.sh" ] && "$HOME/termux-tool-manager.sh" >> "$LOG" 2>&1

echo "[*] Auto maintain end: $(date)" >> "$LOG"
"""
    with open(AUTO_MAINTAIN_SCRIPT,"w") as f:
        f.write(content)
    run_raw(["bash","-lc",f"chmod +x {AUTO_MAINTAIN_SCRIPT}"])

# ================= SMART BASHRC RUNNER =================
def add_smart_runner():
    marker = "# TERMUX POWER SUITE AUTO"
    if BASHRC.exists() and marker in BASHRC.read_text():
        log("Smart runner already exists")
        return

    block = r'''
# TERMUX POWER SUITE AUTO
alias tupdate="$HOME/termux-self-update.sh"
alias toolman="$HOME/termux-tool-manager.sh"
alias maintain="$HOME/termux-auto-maintain.sh"
($HOME/termux-auto-maintain.sh >/dev/null 2>&1 &)
'''
    with open(BASHRC,"a") as f:
        f.write(block)
    log("Smart runner added to .bashrc")

# ================= ORIGINAL MAIN =================
def original_main():
    log("=== ORIGINAL SETUP START ===")
    ensure_dirs()
    install_packages()
    create_self_update()
    create_tool_manager()
    create_auto_maintain()
    add_smart_runner()
    log("=== ORIGINAL SETUP COMPLETE ===")
    print("\nOpen new Termux session or run: source ~/.bashrc")

# ================= FINAL MAIN =================
if __name__ == "__main__":
    try:
        dashboard_menu()
    except KeyboardInterrupt:
        log("Interrupted by user")
        sys.exit(0)
