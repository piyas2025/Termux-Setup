#!/usr/bin/env python3
"""
termux-power-suite.py

Termux Power Suite (auto-heavy mode, retry + self-update on failure).
Preserves original features, adds:
 - Auto-Correct Engine (command typo fix + package-name fuzzy-match via pkg search)
 - Modes: silent (auto) / ask (interactive) / ai (interactive with GitHub search)
 - Rollback notifications and auto-start auto-maintain on shell open

Usage:
  - Set AUTO_CORRECT_MODE environment variable:
      export AUTO_CORRECT_MODE=silent   # default, good for background
      export AUTO_CORRECT_MODE=ask      # interactive mode (will prompt)
      export AUTO_CORRECT_MODE=ai       # interactive + GitHub candidate search
  - Optionally set GITHUB_TOKEN to reduce API rate-limits for GitHub search
  - Run: python3 termux-power-suite.py
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

# ---------------- User-tweakable constants ----------------
MAX_RETRIES = 3            # how many times to try a failed command
BACKOFF_BASE = 4           # seconds; backoff = BACKOFF_BASE * (2 ** (attempt-1))
CMD_TIMEOUT = 900          # seconds timeout for heavy commands (15 minutes)
LOG_ROTATE_BYTES = 8_000_000  # rotate logs if exceed ~8MB

# Auto-correct/config
AUTO_CORRECT_MODE = os.environ.get("AUTO_CORRECT_MODE", "silent").lower()  # 'silent'|'ask'|'ai'
PKG_NAME_CONFIDENCE = 0.72  # cutoff for fuzzy match when choosing package name candidates

# GitHub search limits
GITHUB_PER_PAGE = 30  # number of repos per GitHub page (use 30 default)
GITHUB_SEARCH_LIMIT = 120  # total limit we'll fetch at most (paged)

# ----------------------------------------------------------

HOME = Path.home()
LOGFILE = HOME / "termux-full-setup.log"
TOOLS_DIR = HOME / "tools"
TOOL_LIST = HOME / "tools-list.txt"
BACKUP_DIR = HOME / "tool-backups"
SELF_UPDATE_SCRIPT = HOME / "termux-self-update.sh"
TOOL_MANAGER_SCRIPT = HOME / "termux-tool-manager.sh"
AUTO_MAINTAIN_SCRIPT = HOME / "termux-auto-maintain.sh"
BASHRC = HOME / ".bashrc"

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str, to_console: bool = True) -> None:
    line = f"[{ts()}] {msg}"
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # don't crash on logging errors
        pass
    if to_console:
        print(line)


def rotate_logs(max_size: int = LOG_ROTATE_BYTES) -> None:
    try:
        if LOGFILE.exists() and LOGFILE.stat().st_size > max_size:
            new_name = LOGFILE.with_name(f"termux-full-setup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log")
            LOGFILE.rename(new_name)
            log(f"Rotated log to {new_name}", to_console=False)
    except Exception as e:
        log(f"Log rotation error: {e}", to_console=False)


def run_raw(cmd_list, check=False, capture=False, timeout=None, env=None):
    """Run a command list (not string). Lower-level wrapper."""
    try:
        # build printable command string for logs
        cmd_str = " ".join(shlex.quote(str(p)) for p in cmd_list)
        log(f"EXEC: {cmd_str}", to_console=False)
        cp = subprocess.run(cmd_list, check=check, capture_output=capture, text=True, timeout=timeout, env=env)
        if capture:
            # Return stdout for callers that expect text when capture=True
            return cp.stdout
        return cp
    except subprocess.CalledProcessError as e:
        # CalledProcessError contains .returncode, .stdout, .stderr
        try:
            out = e.stdout if hasattr(e, "stdout") else ""
            err = e.stderr if hasattr(e, "stderr") else ""
            log(f"CalledProcessError: rc={e.returncode} out={out} err={err}")
        except Exception:
            log(f"CalledProcessError: rc={getattr(e,'returncode', 'unknown')}")
        raise
    except subprocess.TimeoutExpired as e:
        log(f"TimeoutExpired after {timeout}s: {e}", to_console=True)
        raise
    except Exception as e:
        log(f"run_raw unexpected error: {e}", to_console=True)
        raise


def run_with_retry(cmd: str, max_retries: int = MAX_RETRIES, timeout: int = CMD_TIMEOUT) -> subprocess.CompletedProcess:
    """
    Run a shell command (string via bash -lc). On failure, call self-update and retry.
    Raises RuntimeError if all retries exhausted.
    """
    attempt = 0
    last_exc = None
    while attempt < max_retries:
        attempt += 1
        try:
            log(f"[run_with_retry] Attempt {attempt}/{max_retries} -> {cmd}")
            # run via bash to preserve shell features used in commands
            cp = run_raw(["bash", "-lc", cmd], check=True, capture=True, timeout=timeout)
            log(f"[run_with_retry] Success on attempt {attempt}")
            return cp
        except Exception as e:
            last_exc = e
            log(f"[run_with_retry] Failure on attempt {attempt}: {e}", to_console=True)
            # if not last attempt, try self-update then backoff
            if attempt < max_retries:
                try:
                    log("[run_with_retry] Running self-update (best-effort) before next retry...")
                    # run self-update script if exists and executable; don't raise on failure
                    if Path(SELF_UPDATE_SCRIPT).exists() and os.access(SELF_UPDATE_SCRIPT, os.X_OK):
                        run_raw(["bash", "-lc", f"bash {shlex.quote(str(SELF_UPDATE_SCRIPT))}"], check=False, capture=True, timeout=120)
                    else:
                        # fallback: run lightweight pkg update to refresh repos
                        run_raw(["bash", "-lc", "pkg update -y >/dev/null 2>&1 || true"], check=False, capture=True, timeout=120)
                except Exception as se:
                    log(f"[run_with_retry] self-update attempt raised: {se}", to_console=False)
                backoff = BACKOFF_BASE * (2 ** (attempt - 1))
                log(f"[run_with_retry] Backing off {backoff}s before retry...")
                time.sleep(backoff)
            else:
                log("[run_with_retry] Max retries reached, giving up.", to_console=True)
    # after loop
    raise RuntimeError(f"Command failed after {max_retries} attempts: {cmd}") from last_exc


def ensure_dirs() -> None:
    try:
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log(f"Could not ensure directories: {e}", to_console=True)

# ---------------------------------------------------------------------------
# Auto-Correct Engine (command token fixes + package-name fuzzy-match)
# ---------------------------------------------------------------------------
CANONICAL_COMMANDS = {
    "apt": "apt",
    "pkg": "pkg",
    "pip": "pip",
    "python": "python",
    "py": "python",
    "npm": "npm",
    "node": "node",
    "git": "git",
    "bash": "bash",
    "termux-battery-status": "termux-battery-status",
    "termux-notification": "termux-notification",
    "termux-setup-storage": "termux-setup-storage",
    "speedtest": "speedtest",
    "nmap": "nmap",
    "openvpn": "openvpn",
    "sqlmap": "sqlmap",
    "hydra": "hydra",
    "git-lfs": "git-lfs",
    "neofetch": "neofetch",
}

COMMON_TOKEN_CORRECTIONS = {
    "updata": "update",
    "updat": "update",
    "upgarde": "upgrade",
    "upgrde": "upgrade",
    "instal": "install",
    "insatll": "install",
    "intall": "install",
    "pul": "pull",
    "pll": "pull",
    "clne": "clone",
    "cloner": "clone",
    "insall": "install",
    "sorit": "source",
    "soruce": "source",
    "pyhton": "python",
    "termux-battry-status": "termux-battery-status",
    "termux-notificaton": "termux-notification",
    "speedet": "speedtest",
    "sqlmpa": "sqlmap",
    "hydar": "hydra",
    "openvnp": "openvpn",
    "clera": "clear",
    "lsa": "ls -a",
}

def smart_fix_token(token: str) -> str:
    if token in COMMON_TOKEN_CORRECTIONS:
        return COMMON_TOKEN_CORRECTIONS[token]
    if token in CANONICAL_COMMANDS:
        return CANONICAL_COMMANDS[token]
    choices = list(CANONICAL_COMMANDS.keys()) + list(COMMON_TOKEN_CORRECTIONS.keys())
    match = difflib.get_close_matches(token, choices, n=1, cutoff=0.78)
    if match:
        m = match[0]
        if m in CANONICAL_COMMANDS:
            return CANONICAL_COMMANDS[m]
        return COMMON_TOKEN_CORRECTIONS.get(m, m)
    return token

def autocorrect_command(cmd: str) -> str:
    original = cmd.strip()
    if not original:
        return cmd

    parts = original.split()
    parts[0] = smart_fix_token(parts[0])
    for i in range(1, len(parts)):
        token = parts[i]
        if token.startswith("-") or "/" in token or "=" in token or token.startswith("$"):
            continue
        parts[i] = smart_fix_token(parts[i])

    corrected = " ".join(parts)
    if corrected == original:
        return cmd

    if AUTO_CORRECT_MODE == "silent":
        log(f"[autocorrect] corrected (silent): '{original}' -> '{corrected}'")
        return corrected
    elif AUTO_CORRECT_MODE == "ask":
        try:
            reply = input(f"Did you mean: '{corrected}' (y/N)? ").strip().lower()
            if reply in ("y", "yes"):
                log(f"[autocorrect] user-approved: '{original}' -> '{corrected}'")
                return corrected
            else:
                log(f"[autocorrect] user-declined correction for: '{original}'")
                return original
        except Exception:
            log(f"[autocorrect] could not prompt; leaving original: '{original}'", to_console=False)
            return original
    elif AUTO_CORRECT_MODE == "ai":
        # in AI mode, we still show the corrected suggestion first and ask before auto-applying
        try:
            reply = input(f"Suggested correction: '{corrected}' — Apply? (y/N) or 'm' for menu: ").strip().lower()
            if reply in ("y", "yes"):
                log(f"[autocorrect] user-approved (ai): '{original}' -> '{corrected}'")
                return corrected
            if reply == "m":
                # 'm' will let caller handle interactive candidate resolution
                return original
            log(f"[autocorrect] user-declined correction for: '{original}'")
            return original
        except Exception:
            log(f"[autocorrect] could not prompt; leaving original: '{original}'", to_console=False)
            return original
    else:
        log(f"[autocorrect] unknown AUTO_CORRECT_MODE='{AUTO_CORRECT_MODE}', defaulting to silent")
        log(f"[autocorrect] corrected (default): '{original}' -> '{corrected}'")
        return corrected

# ---------------------------------------------------------------------------
# Package-name validation + fuzzy-match via repo search
# ---------------------------------------------------------------------------
def pkg_search_candidates(name: str) -> list[str]:
    """
    Use 'pkg search <name>' to obtain candidate package names.
    Returns list of candidate package names (unique, ordered).
    """
    try:
        out = subprocess.run(["bash", "-lc", f"pkg search {shlex.quote(name)}"], capture_output=True, text=True, timeout=20)
        lines = out.stdout.splitlines()
        candidates = []
        for L in lines:
            L = L.strip()
            if not L:
                continue
            # line often like "neofetch - fetch system information"
            tok = L.split()[0].strip()
            if tok:
                candidates.append(tok)
        # deduplicate preserving order
        seen = set()
        uniq = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        return uniq
    except Exception as e:
        log(f"[pkg_search_candidates] search failed for {name}: {e}", to_console=False)
        return []

def choose_best_package(name: str, candidates: list[str], cutoff: float = PKG_NAME_CONFIDENCE) -> str | None:
    if not candidates:
        return None
    match = difflib.get_close_matches(name, candidates, n=1, cutoff=cutoff)
    if match:
        return match[0]
    return None

# ---------------------------------------------------------------------------
# GitHub search (uses curl; set GITHUB_TOKEN env var for higher rate limits)
# ---------------------------------------------------------------------------
def search_github_repos(query: str, per_page: int = GITHUB_PER_PAGE, max_total: int = GITHUB_SEARCH_LIMIT) -> List[Tuple[str, str]]:
    """
    Returns list of (full_name, html_url). Uses GitHub Search API via curl.
    This is a best-effort helper for interactive mode. Set GITHUB_TOKEN env var to increase rate limits.
    """
    try:
        token = os.environ.get("GITHUB_TOKEN")
        results = []
        fetched = 0
        page = 1
        while fetched < max_total:
            url = f"https://api.github.com/search/repositories?q={shlex.quote(query)}&per_page={per_page}&page={page}"
            headers = ""
            if token:
                headers = f"-H 'Authorization: token {token}' -H 'Accept: application/vnd.github.v3+json'"
            cmd = f"curl -s {headers} {shlex.quote(url)}"
            out = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=15)
            if out.returncode != 0:
                break
            try:
                data = json.loads(out.stdout)
            except Exception:
                break
            items = data.get("items", []) or []
            if not items:
                break
            for it in items:
                full_name = it.get("full_name")
                html_url = it.get("html_url")
                if full_name and html_url:
                    results.append((full_name, html_url))
                    fetched += 1
                    if fetched >= max_total:
                        break
            if len(items) < per_page:
                break
            page += 1
        return results
    except Exception as e:
        log(f"[search_github_repos] failed: {e}", to_console=False)
        return []

# ---------------------------------------------------------------------------
# Interactive candidate menu & action runner
# ---------------------------------------------------------------------------
def interactive_candidates_menu(name: str, pkg_cands: List[str], gh_cands: List[Tuple[str,str]]) -> List[Tuple[str,str]]:
    """
    Show a numbered menu combining pkg candidates and GitHub repos.
    Returns list of chosen actions: tuples ('pkg', pkgname) or ('git', repo_url).
    Supports:
      - comma-separated numbers (e.g., 1,3)
      - ranges  (e.g., 1-3)
      - 'a' for all
      - 'n' next page (only for large GH lists handled outside)
      - 'q' cancel
    """
    mapping: Dict[int, Tuple[str,str]] = {}
    idx = 1
    print()
    print(f"Candidates for: '{name}'")
    if pkg_cands:
        print("--- pkg candidates ---")
        for p in pkg_cands:
            print(f"[{idx}] pkg: {p}")
            mapping[idx] = ("pkg", p)
            idx += 1
    if gh_cands:
        print("--- GitHub candidates ---")
        for full, url in gh_cands:
            print(f"[{idx}] git: {full} -> {url}")
            mapping[idx] = ("git", url)
            idx += 1
    if not mapping:
        print("No candidates found.")
        return []

    print()
    print("Choose number(s) (comma separated), ranges like 1-3, 'a' all, 'q' cancel.")
    sel = input("Selection: ").strip().lower()
    if not sel or sel == "q":
        return []
    if sel == "a":
        return list(mapping.values())

    chosen = []
    parts = [s.strip() for s in sel.split(",") if s.strip()]
    for part in parts:
        if "-" in part:
            try:
                a,b = part.split("-",1)
                a = int(a.strip()); b = int(b.strip())
                for n in range(a, b+1):
                    if n in mapping:
                        chosen.append(mapping[n])
            except Exception:
                continue
        else:
            try:
                n = int(part)
                if n in mapping:
                    chosen.append(mapping[n])
            except Exception:
                continue
    return chosen

def run_chosen_actions(actions: List[Tuple[str,str]]) -> None:
    """
    Executes chosen actions:
      - ('pkg', name) => runs pkg install for that name
      - ('git', url) => clones repo into TOOLS_DIR (shallow)
    """
    ensure_dirs()
    for typ, val in actions:
        if typ == "pkg":
            cmd = f"pkg install -y {shlex.quote(val)} 2>&1 | tee -a {shlex.quote(str(LOGFILE))}"
            try:
                log(f"[interactive] Installing pkg: {val}")
                run_with_retry(cmd, max_retries=MAX_RETRIES, timeout=CMD_TIMEOUT)
            except Exception as e:
                log(f"[interactive] Failed to install pkg {val}: {e}")
        elif typ == "git":
            dest_name = os.path.basename(val.rstrip("/")).replace(".git","")
            dest = TOOLS_DIR / dest_name
            try:
                log(f"[interactive] Cloning {val} -> {dest}")
                cmd = f"git clone --depth 1 {shlex.quote(val)} {shlex.quote(str(dest))}"
                run_with_retry(cmd, max_retries=3, timeout=300)
                # optional installs
                if (dest / "requirements.txt").exists():
                    run_with_retry(f"(cd {shlex.quote(str(dest))} && pip install -r requirements.txt) 2>&1 | tee -a {shlex.quote(str(LOGFILE))}", max_retries=2, timeout=300)
                if (dest / "install.sh").exists():
                    run_with_retry(f"(cd {shlex.quote(str(dest))} && bash install.sh) 2>&1 | tee -a {shlex.quote(str(LOGFILE))}", max_retries=1, timeout=300)
            except Exception as e:
                log(f"[interactive] Git clone failed for {val}: {e}")

# ---------------------------------------------------------------------------
# Integrate interactive resolver into prepare_command_for_run
# ---------------------------------------------------------------------------
def resolve_pkg_interactive(ptoken: str) -> bool:
    """
    Attempt to resolve a package token interactively (for AUTO_CORRECT_MODE in ask/ai).
    If resolution performed (install or clone), returns True.
    Otherwise returns False (caller can proceed with default behavior).
    """
    # 1) check exact installed/available
    try:
        rc = subprocess.run(["bash", "-lc", f"pkg list-installed 2>/dev/null | awk '{{print $1}}' | grep -xq {shlex.quote(ptoken)}"], capture_output=True, text=True, timeout=8)
        if rc.returncode == 0:
            log(f"[resolve] {ptoken} already installed (exact match).")
            return True
    except Exception:
        pass

    # 2) search pkg candidates
    pkg_cands = pkg_search_candidates(ptoken)

    # 3) search GitHub (only in ai mode or when ask explicitly requests menu)
    gh_cands = []
    if AUTO_CORRECT_MODE == "ai":
        # perform github search (best-effort)
        gh_query = ptoken
        gh_cands = search_github_repos(gh_query, per_page=GITHUB_PER_PAGE, max_total=GITHUB_SEARCH_LIMIT)

    # 4) if silent mode, try best fuzzy pkg match
    if AUTO_CORRECT_MODE == "silent":
        best = choose_best_package(ptoken, pkg_cands, cutoff=PKG_NAME_CONFIDENCE)
        if best:
            # install best automatically
            try:
                cmd = f"pkg install -y {shlex.quote(best)} 2>&1 | tee -a {shlex.quote(str(LOGFILE))}"
                log(f"[pkg-autocorrect] auto-install '{ptoken}' -> '{best}' (silent)")
                run_with_retry(cmd, max_retries=MAX_RETRIES, timeout=CMD_TIMEOUT)
                return True
            except Exception as e:
                log(f"[pkg-autocorrect] install failed for {best}: {e}")
        return False

    # 5) interactive flows (ask or ai)
    # If both pkg_cands and gh_cands empty, return False quickly
    if not pkg_cands and not gh_cands:
        return False

    # Show interactive menu combining both lists (limit shown)
    chosen = interactive_candidates_menu(ptoken, pkg_cands, gh_cands)
    if not chosen:
        log(f"[resolve] User cancelled or no selection for '{ptoken}'")
        return False

    # run chosen actions
    run_chosen_actions(chosen)
    return True

def prepare_command_for_run(cmd: str) -> str:
    """
    Apply autocorrect_command first, then special handling for pkg/apt install:
    - If command is 'pkg install <name>' or 'apt install <name>', try to validate package name.
    - If a better package name is found via pkg_search_candidates and confidence, replace it.
    - If interactive/ai mode requested, prompt user and possibly run actions directly.
    """
    orig = cmd
    cmd = autocorrect_command(cmd)
    parts = cmd.strip().split()
    if not parts:
        return cmd
    if parts[0] in ("pkg", "apt"):
        try:
            for idx, tok in enumerate(parts):
                if tok in ("install", "i"):
                    inst_idx = idx
                    break
            else:
                inst_idx = None
        except Exception:
            inst_idx = None

        if inst_idx is not None and inst_idx + 1 < len(parts):
            pkg_tokens = []
            # collect tokens after install until an option starts (-) or end
            for t in parts[inst_idx+1:]:
                if t.startswith("-"):
                    break
                pkg_tokens.append(t)
            fixed_tokens = []
            # for each token, maybe interactively resolve
            for ptoken in pkg_tokens:
                if "/" in ptoken or ptoken.startswith("http"):
                    fixed_tokens.append(ptoken)
                    continue
                # if interactive resolve handles it (installs/clones) then skip adding token
                if AUTO_CORRECT_MODE in ("ask", "ai"):
                    handled = False
                    try:
                        handled = resolve_pkg_interactive(ptoken)
                    except Exception as e:
                        log(f"[resolve] interactive resolution error for {ptoken}: {e}")
                    if handled:
                        # already installed/handled by interactive, do not add to pkg install command
                        continue
                # fallback: check if exact installed (then skip)
                try:
                    rc = subprocess.run(["bash", "-lc", f"pkg list-installed 2>/dev/null | awk '{{print $1}}' | grep -xq {shlex.quote(ptoken)}"], capture_output=True, text=True, timeout=8)
                    if rc.returncode == 0:
                        fixed_tokens.append(ptoken)
                        continue
                except Exception:
                    pass
                # search candidates and choose best
                cands = pkg_search_candidates(ptoken)
                best = choose_best_package(ptoken, cands, cutoff=PKG_NAME_CONFIDENCE)
                if best and AUTO_CORRECT_MODE == "silent":
                    log(f"[pkg-autocorrect] '{ptoken}' -> '{best}' (auto, silent)")
                    fixed_tokens.append(best)
                else:
                    fixed_tokens.append(ptoken)
            # rebuild command with replaced package tokens
            new_parts = parts[:inst_idx+1] + fixed_tokens
            after_idx = inst_idx + 1 + len(pkg_tokens)
            if after_idx < len(parts):
                new_parts += parts[after_idx:]
            new_cmd = " ".join(new_parts)
            if new_cmd != cmd:
                log(f"[prepare_command] rewritten: '{cmd}' -> '{new_cmd}'")
            return new_cmd
    return cmd

# ---------------------------------------------------------------------------
# Package installation (auto-heavy: always proceed), using prepare_command_for_run
# ---------------------------------------------------------------------------
def is_pkg_installed(pkg: str) -> bool:
    try:
        # list-installed prints "pkgname/version ..." — we compare package name only using awk + exact match
        rc = subprocess.run(["bash", "-lc", f"pkg list-installed 2>/dev/null | awk '{{print $1}}' | grep -xq {shlex.quote(pkg)}"], capture_output=True, text=True, timeout=10)
        return rc.returncode == 0
    except Exception:
        return False

def install_packages() -> None:
    log("Starting package installation (AUTO-HEAVY mode)")
    rotate_logs()

    if not shutil.which("pkg"):
        log("[!] 'pkg' not found on PATH. Skipping package installation.", to_console=True)
        return

    log("[1/3] Updating Termux packages...")
    try:
        cmd = f"pkg update -y | tee -a {shlex.quote(str(LOGFILE))}"
        cmd = prepare_command_for_run(cmd)
        run_with_retry(cmd, max_retries=2, timeout=300)
        cmd = f"pkg upgrade -y | tee -a {shlex.quote(str(LOGFILE))}"
        cmd = prepare_command_for_run(cmd)
        run_with_retry(cmd, max_retries=2, timeout=600)
        log("✔ Base packages updated.")
    except Exception as e:
        log(f"[!] pkg update/upgrade had persistent problems: {e}")

    PKGS = [
        # core
        "coreutils", "util-linux", "ncurses-utils", "termux-api", "termux-keyring",
        "curl", "wget", "git", "tree", "neofetch", "tsu", "tmux", "screen", "nano", "vim",
        # programming
        "python", "python2", "clang", "make", "gdb", "php", "ruby", "perl",
        "nodejs", "golang", "rust", "lua",
        "openjdk-17", "sqlite", "yasm", "cmake", "pkg-config", "git-lfs",
        # network / security (legal use only)
        "nmap", "ncat", "dnsutils", "traceroute", "mtr", "whois", "tcpdump", "openssl", "iproute2",
        "inetutils", "openvpn", "tor", "torsocks", "proxychains-ng", "hydra", "sqlmap", "metasploit", "iperf3",
        # wifi / api
        "jq", "iw", "speedtest-cli", "speedtest",
        # visual / fun
        "cmatrix", "cowsay", "figlet", "toilet", "lolcat", "screenfetch", "ranger", "htop",
        # browsers / downloaders
        "lynx", "w3m", "httrack", "aria2", "lftp",
        # shell/ui
        "zsh", "fish", "starship", "fd", "ripgrep", "bat", "fzf", "mc", "tree-sitter",
        # unix utils
        "sed", "grep", "gawk", "findutils", "tar", "gzip", "bzip2", "xz-utils", "p7zip", "diffutils", "zip", "unzip",
        # misc
        "ncdu", "pv", "curlftpfs", "clang-dev", "man", "man-pages", "lazygit", "silversearcher-ag"
    ]

    for pkg in PKGS:
        try:
            if is_pkg_installed(pkg):
                log(f"✔ {pkg} already installed. Skipped.")
                continue
            log(f"→ Installing: {pkg}")
            # build command and run through prepare_command_for_run (for autocorrect/search)
            raw_cmd = f"pkg install -y {shlex.quote(pkg)} 2>&1 | tee -a {shlex.quote(str(LOGFILE))}"
            prepared = prepare_command_for_run(raw_cmd)
            try:
                # Note: prepare_command_for_run may have already installed/cloned the package in interactive mode
                run_with_retry(prepared, max_retries=MAX_RETRIES, timeout=CMD_TIMEOUT)
            except Exception as ie:
                log(f"[!] Persistent failure installing {pkg}: {ie}. Skipping to next package.")
                continue
        except Exception as e:
            log(f"[!] Exception during install loop for {pkg}: {e}")

    # pip/npm/gem installs (best-effort) — prepare_command_for_run used for corrections
    log("[*] Upgrading pip (if available)...")
    if shutil.which("python"):
        try:
            cmd = "python -m pip install --upgrade pip 2>&1 | tee -a " + shlex.quote(str(LOGFILE))
            cmd = prepare_command_for_run(cmd)
            run_with_retry(cmd, max_retries=2, timeout=300)
        except Exception as e:
            log(f"[!] pip upgrade failed: {e}")

    log("[*] Installing Python speedtest-cli...")
    if shutil.which("python"):
        try:
            cmd = "python -m pip install speedtest-cli --upgrade 2>&1 | tee -a " + shlex.quote(str(LOGFILE))
            cmd = prepare_command_for_run(cmd)
            run_with_retry(cmd, max_retries=2, timeout=300)
        except Exception as e:
            log(f"[!] speedtest-cli install failed: {e}")

    log("[*] Installing fast-cli (Node)...")
    if shutil.which("npm"):
        try:
            cmd = "npm install -g fast-cli 2>&1 | tee -a " + shlex.quote(str(LOGFILE))
            cmd = prepare_command_for_run(cmd)
            run_with_retry(cmd, max_retries=2, timeout=300)
        except Exception as e:
            log(f"[!] fast-cli npm install failed: {e}")
    else:
        log("npm not present; skipping fast-cli")

    log("[*] Installing lolcat (Ruby gem)...")
    if shutil.which("gem"):
        try:
            cmd = "gem install lolcat 2>&1 | tee -a " + shlex.quote(str(LOGFILE))
            cmd = prepare_command_for_run(cmd)
            run_with_retry(cmd, max_retries=2, timeout=300)
        except Exception as e:
            log(f"[!] gem install lolcat failed: {e}")
    else:
        log("gem not present; skipping lolcat gem")

    log("[3/3] Setting up storage...")
    try:
        cmd = "termux-setup-storage 2>&1 | tee -a " + shlex.quote(str(LOGFILE))
        cmd = prepare_command_for_run(cmd)
        run_with_retry(cmd, max_retries=2, timeout=120)
    except Exception as e:
        log(f"[!] termux-setup-storage may have failed: {e}")

    log("✓ Full package setup finished (auto-heavy mode)")

# ---------------------------------------------------------------------------
# Tool manager (writer) - improved: shallow clone, retry, supports git/url/gist entries
# ---------------------------------------------------------------------------
def create_tool_manager() -> None:
    log(f"Writing tool manager to: {TOOL_MANAGER_SCRIPT}")
    content = r"""#!/data/data/com.termux/files/usr/bin/bash
# termux-tool-manager.sh
# Reads $HOME/tools-list.txt where each non-comment line can be:
#   git+https://github.com/user/repo.git
#   url+https://example.com/some-tool.tar.gz
#   gist+https://gist.github.com/user/id.git
#   plain git URLs will also be accepted
set -e
TOOLS_DIR="$HOME/tools"
TOOL_LIST="$HOME/tools-list.txt"
BACKUP_DIR="$HOME/tool-backups"
mkdir -p "$TOOLS_DIR" "$BACKUP_DIR"

notify() {
  title="$1"; message="$2"; id="${3:-9999}"
  if command -v termux-notification >/dev/null 2>&1; then
    termux-notification -t "$title" -c "$message" -i "$id" >/dev/null 2>&1 || true
  fi
}

backup_tool() {
  local name="$1"; local src="$TOOLS_DIR/$name"
  if [ ! -d "$src" ]; then
    echo ""
    return 0
  fi
  local ts; ts=$(date +"%Y%m%d-%H%M%S")
  local backup_file="$BACKUP_DIR/${name}-${ts}.tar.gz"
  if tar -czf "$backup_file" -C "$TOOLS_DIR" "$name"; then
    echo "$backup_file"
  else
    echo ""
  fi
}

rollback_tool() {
  local name="$1"; local backup="$2"
  if [ -z "$backup" ] || [ ! -f "$backup" ]; then
    echo "No backup for $name"
    return 1
  fi
  rm -rf "$TOOLS_DIR/$name"
  mkdir -p "$TOOLS_DIR"
  if tar -xzf "$backup" -C "$TOOLS_DIR"; then
    echo "Rollback completed for $name"
    notify "Tool rollback" "Rolled back $name to previous version" 1010
    return 0
  else
    echo "Rollback failed for $name"
    notify "Tool rollback failed" "Rollback failed for $name" 1011
    return 1
  fi
}

git_clone_with_retry() {
  local repo="$1"; local dest="$2"; local tries=0; local max=3
  until [ $tries -ge $max ]; do
    if git clone --depth 1 "$repo" "$dest"; then
      notify "Tool installed" "Cloned $(basename "$repo")" 1020
      return 0
    fi
    tries=$((tries+1))
    echo "git clone failed (attempt $tries). Running self-update then retry..."
    if [ -x "$HOME/termux-self-update.sh" ]; then
      bash "$HOME/termux-self-update.sh" || true
    fi
    sleep $((5 * tries))
  done
  return 1
}

git_pull_with_retry() {
  local dir="$1"; local tries=0; local max=3
  until [ $tries -ge $max ]; do
    if (cd "$dir" && git pull --ff-only --rebase); then
      notify "Tool updated" "Updated $(basename "$dir")" 1021
      return 0
    fi
    tries=$((tries+1))
    echo "git pull failed (attempt $tries). Running self-update then retry..."
    if [ -x "$HOME/termux-self-update.sh" ]; then
      bash "$HOME/termux-self-update.sh" || true
    fi
    sleep $((5 * tries))
  done
  return 1
}

download_url_with_retry() {
  local url="$1"; local dest="$2"; local tries=0; local max=3
  until [ $tries -ge $max ]; do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsSL "$url" -o "$dest"; then
        notify "Tool downloaded" "Downloaded $(basename "$url")" 1022
        return 0
      fi
    elif command -v wget >/dev/null 2>&1; then
      if wget -qO "$dest" "$url"; then
        notify "Tool downloaded" "Downloaded $(basename "$url")" 1022
        return 0
      fi
    else
      echo "No curl/wget available"
      return 1
    fi
    tries=$((tries+1))
    echo "download failed (attempt $tries). Running self-update then retry..."
    if [ -x "$HOME/termux-self-update.sh" ]; then
      bash "$HOME/termux-self-update.sh" || true
    fi
    sleep $((5 * tries))
  done
  return 1
}

process_line() {
  local line="$1"
  line="$(echo "$line" | sed 's/^[ \t]*//;s/[ \t]*$//')"
  [ -z "$line" ] && return
  [[ "$line" = \#* ]] && return
  local src="$line"
  if [[ "$src" == url+* ]]; then
    local url="${src#url+}"
    local name; name=$(basename "$url")
    local dest="$TOOLS_DIR/${name%.*}"
    echo "Processing URL: $url -> $dest"
    mkdir -p "$TOOLS_DIR"
    backup_file="$(backup_tool "${name%.*}")"
    tmp="$dest.tmp"
    if download_url_with_retry "$url" "$tmp"; then
      mkdir -p "$dest"
      if file "$tmp" | grep -q -E 'gzip|bzip2|Zip archive|tar'; then
        tar -xzf "$tmp" -C "$dest" || (unzip -q "$tmp" -d "$dest" || true)
        rm -f "$tmp"
      else
        mv "$tmp" "$dest/$name"
      fi
      notify "Tool installed" "Installed ${name%.*}" 1023
    else
      echo "Failed to download $url"
      [ -n "$backup_file" ] && rollback_tool "${name%.*}" "$backup_file"
    fi
  else
    if [[ "$src" == git+* ]]; then
      src="${src#git+}"
    elif [[ "$src" == gist+* ]]; then
      src="${src#gist+}"
    fi
    local name; name=$(basename "$src")
    name="${name%.git}"
    local path="$TOOLS_DIR/$name"
    echo "Processing git repo: $src -> $path"
    if [ -d "$path/.git" ]; then
      backup_file="$(backup_tool "$name")"
      if git_pull_with_retry "$path"; then
        (cd "$path" && ( [ -f requirements.txt ] && pip install -r requirements.txt || true ) )
        (cd "$path" && ( [ -f install.sh ] && bash install.sh || true ) )
        if [ -f "$path/tooltest.sh" ] || [ -f "$path/test.sh" ]; then
          (cd "$path" && bash -n tooltest.sh >/dev/null 2>&1 || true)
          (cd "$path" && bash tooltest.sh >/dev/null 2>&1) || {
            echo "Health check failed; rolling back $name"
            rollback_tool "$name" "$backup_file"
          }
        fi
      else
        echo "git pull failed for $name, attempting rollback"
        [ -n "$backup_file" ] && rollback_tool "$name" "$backup_file"
      fi
    else
      if git_clone_with_retry "$src" "$path"; then
        (cd "$path" && ( [ -f requirements.txt ] && pip install -r requirements.txt || true ) )
        (cd "$path" && ( [ -f install.sh ] && bash install.sh || true ) )
      else
        echo "git clone failed for $src"
      fi
    fi
  fi
}

main() {
  if [ ! -f "$TOOL_LIST" ]; then
    echo "# Add GitHub/git/gist URLs or url+<raw-archive-url> here (one per line)" > "$TOOL_LIST"
    echo "# Examples:" >> "$TOOL_LIST"
    echo "# git+https://github.com/user/repo.git" >> "$TOOL_LIST"
    echo "# https://github.com/user/repo.git" >> "$TOOL_LIST"
    echo "# url+https://example.com/tool.tar.gz" >> "$TOOL_LIST"
    echo "# gist+https://gist.github.com/user/id.git" >> "$TOOL_LIST"
    echo "$TOOL_LIST created. Edit it and run this script again."
    exit 0
  fi

  while IFS= read -r line || [ -n "$line" ]; do
    process_line "$line"
  done < "$TOOL_LIST"
}
main
"""
    try:
        with open(TOOL_MANAGER_SCRIPT, "w", encoding="utf-8") as f:
            f.write(content)
        run_raw(["bash", "-lc", f"chmod +x {shlex.quote(str(TOOL_MANAGER_SCRIPT))}"])
        log("Tool manager written and made executable.")
    except Exception as e:
        log(f"[create_tool_manager] write failed: {e}", to_console=True)

# ---------------------------------------------------------------------------
# Self-update script (keeps simple and safe)
# ---------------------------------------------------------------------------
def create_self_update() -> None:
    log(f"Writing self-update script to: {SELF_UPDATE_SCRIPT}")
    content = r"""#!/data/data/com.termux/files/usr/bin/bash
set -e
echo "[*] termux-self-update: updating package lists..."
pkg update -y || true
echo "[*] termux-self-update: upgrading installed packages..."
pkg upgrade -y || true
echo "✔ termux-self-update completed."
"""
    try:
        with open(SELF_UPDATE_SCRIPT, "w", encoding="utf-8") as f:
            f.write(content)
        run_raw(["bash", "-lc", f"chmod +x {shlex.quote(str(SELF_UPDATE_SCRIPT))}"])
        log("Self-update script created.")
    except Exception as e:
        log(f"[create_self_update] write failed: {e}", to_console=True)

# ---------------------------------------------------------------------------
# Auto-maintain script
# ---------------------------------------------------------------------------
def create_auto_maintain() -> None:
    log(f"Writing auto-maintain script to: {AUTO_MAINTAIN_SCRIPT}")
    content = r"""#!/data/data/com.termux/files/usr/bin/bash
# Termux Auto Maintenance
set -e
LOGFILE="$HOME/termux-auto-maintain.log"
LOCKFILE="$HOME/.termux-maintain.lock"
DATE_NOW="$(date '+%Y-%m-%d %H:%M:%S')"
log() { echo "$1" | tee -a "$LOGFILE"; }
if [ -e "$LOCKFILE" ]; then
  log "[!] Another maintenance process is running. Exiting."
  exit 0
fi
touch "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT
log "[*] Auto maintenance started at: $DATE_NOW"

# Battery-aware: requires termux-battery-status and jq
if command -v termux-battery-status >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
  BAT_JSON="$(termux-battery-status 2>/dev/null || echo '{}')"
  LEVEL="$(echo "$BAT_JSON" | jq -r '.percentage // 100' 2>/dev/null)"
  PLUGGED="$(echo "$BAT_JSON" | jq -r '.plugged // \"UNKNOWN\"' 2>/dev/null)"
  if [ "$PLUGGED" = "UNPLUGGED" ] && [ "$LEVEL" -lt 25 ]; then
    log "[!] Battery low (${LEVEL}%), skipping heavy maintenance."
    exit 0
  fi
fi

# 1) Self update
if [ -x "$HOME/termux-self-update.sh" ]; then
  log "[*] Running self-update script..."
  nice -n 10 "$HOME/termux-self-update.sh" >>"$LOGFILE" 2>&1 || log "[!] Self-update failed."
fi

# 2) Tool manager
if [ -x "$HOME/termux-tool-manager.sh" ]; then
  log "[*] Running tool manager..."
  nice -n 10 "$HOME/termux-tool-manager.sh" >>"$LOGFILE" 2>&1 || log "[!] Tool manager encountered errors."
fi

log "[*] Auto maintenance finished at: $(date '+%Y-%m-%d %H:%M:%S')"
if command -v termux-notification >/dev/null 2>&1; then
  termux-notification -t "Termux Auto Maintain" -c "Maintenance completed at $(date '+%H:%M')" -i 9999 >/dev/null 2>&1 || true
fi
"""
    try:
        with open(AUTO_MAINTAIN_SCRIPT, "w", encoding="utf-8") as f:
            f.write(content)
        run_raw(["bash", "-lc", f"chmod +x {shlex.quote(str(AUTO_MAINTAIN_SCRIPT))}"])
        log("Auto-maintain script created.")
    except Exception as e:
        log(f"[create_auto_maintain] write failed: {e}", to_console=True)

# ---------------------------------------------------------------------------
# Smart runner addition to .bashrc (auto-start auto-maintain unconditionally)
# ---------------------------------------------------------------------------
def add_smart_runner() -> None:
    marker = "# ===== Smart Auto Runner (by Termux Power Suite) ====="
    try:
        if BASHRC.exists():
            with open(BASHRC, "r", encoding="utf-8") as f:
                data = f.read()
            if marker in data:
                log("Smart Auto Runner already present in ~/.bashrc — skipping")
                return
        else:
            data = ""
    except Exception:
        data = ""

    smart = r"""
# ===== Smart Auto Runner (by Termux Power Suite) =====
run_file() {
    file="$1"
    shift
    dir=$(dirname "$file")
    base=$(basename "$file")
    ext="${base##*.}"
    cd "$dir" || exit 1
    case "$ext" in
        py)  echo "→ python $base"; python "$base" "$@" ;;
        sh)  echo "→ bash $base"; bash "$base" "$@" ;;
        php) echo "→ php $base"; php "$base" "$@" ;;
        js)  echo "→ node $base"; node "$base" "$@" ;;
        pl)  echo "→ perl $base"; perl "$base" "$@" ;;
        *)   echo "→ bash $base (default)"; bash "$base" "$@" ;;
    esac
}
command_not_found_handle() {
    query="$1"
    shift
    mapfile -t results < <(find "$HOME" -type f -name "$query" 2>/dev/null)
    case "${#results[@]}" in
        0)
            echo "command not found: $query"
            return 127
            ;;
        1)
            run_file "${results[0]}" "$@"
            return $?
            ;;
        *)
            echo "Multiple matches for: $query"
            for i in "${!results[@]}"; do
                echo "[$((i+1))] ${results[$i]#$HOME/}"
            done
            read -p "Select number: " pick
            if [ -z "$pick" ]; then
                echo "No selection."
                return 1
            fi
            index=$((pick-1))
            run_file "${results[$index]}" "$@"
            ;;
    esac
}
alias tupdate="$HOME/termux-self-update.sh"
alias toolman="$HOME/termux-tool-manager.sh"
alias maintain="$HOME/termux-auto-maintain.sh"
# Silent auto-maintain on shell start (unconditional)
($HOME/termux-auto-maintain.sh > /dev/null 2>&1 &)
# ===== End Smart Auto Runner =====
"""
    try:
        with open(BASHRC, "a", encoding="utf-8") as f:
            f.write("\n" + smart)
        log("Smart Auto Runner appended to ~/.bashrc (auto-maintain will start on shell open)", to_console=True)
    except Exception as e:
        log(f"[add_smart_runner] append failed: {e}", to_console=True)

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main() -> None:
    log("Termux Power Suite (auto-heavy + retry + pkg-autocorrect + interactive-ai) started")
    rotate_logs()
    ensure_dirs()

    try:
        install_packages()
    except Exception as e:
        log(f"[!] install_packages encountered an exception: {e}")

    try:
        create_self_update()
        create_tool_manager()
        create_auto_maintain()
        add_smart_runner()
    except Exception as e:
        log(f"[!] Error creating helper scripts: {e}")

    log("==========================================")
    log("  Termux Power Suite setup completed (auto-heavy)")
    log("  - Self-update command:   tupdate")
    log("  - Tool manager command:  toolman")
    log("  - Auto maintain command: maintain")
    log("  - Smart run: just type file name (e.g., internet.py)")
    log("==========================================")
    print()
    print("Open a NEW Termux session or run: source ~/.bashrc")
    print("Auto-maintain will start automatically when you open a new shell.")
    print(f"AUTO_CORRECT_MODE={AUTO_CORRECT_MODE} (set env var to change: silent|ask|ai)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Interrupted by user", to_console=True)
        sys.exit(1)
    except Exception as e:
        log(f"Fatal error: {e}", to_console=True)
        raise