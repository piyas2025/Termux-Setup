#!/usr/bin/env python3
from __future__ import annotations
import os, sys, subprocess, shlex, shutil, time, difflib, json
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict

BLUE = "\033[94m"
RESET = "\033[0m"

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

def dashboard_menu():
    while True:
        show_banner()
        print("[1] Full Termux Power Suite Setup")
        print("[2] Web → IP & Domain")
        print("[3] Web → Port Scan")
        print("[0] Exit\n")

        c = input("Select: ").strip()
        if c == "1":
            original_main()
            input("\nDone. Press Enter...")
        elif c == "2":
            web_to_ip()
        elif c == "3":
            web_port_scan()
        elif c == "0":
            sys.exit(0)
HOME = Path.home()
LOGFILE = HOME / "termux-full-setup.log"
TOOLS_DIR = HOME / "tools"
BACKUP_DIR = HOME / "tool-backups"
BASHRC = HOME / ".bashrc"

MAX_RETRIES = 3
BACKOFF_BASE = 4
CMD_TIMEOUT = 900
PKG_NAME_CONFIDENCE = 0.72

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg, to_console=True):
    line = f"[{ts()}] {msg}"
    try:
        with open(LOGFILE, "a") as f:
            f.write(line + "\n")
    except:
        pass
    if to_console:
        print(line)

def run_raw(cmd, timeout=None):
    log("EXEC: " + cmd, False)
    return subprocess.run(
        ["bash", "-lc", cmd],
        text=True,
        timeout=timeout
    )

def run_with_retry(cmd):
    for i in range(1, MAX_RETRIES + 1):
        try:
            log(f"[TRY {i}] {cmd}")
            run_raw(cmd, CMD_TIMEOUT)
            return
        except Exception as e:
            log(f"[FAIL] {e}")
            time.sleep(BACKOFF_BASE * i)
    raise RuntimeError(cmd)
def install_packages():
    log("AUTO-HEAVY INSTALL START")

    COMMANDS = [
        "pkg update",
        "pkg upgrade",
        "apt update",
        "apt upgrade -y",

    "pkg install -y curl",
    "pkg install -y wget",
    "pkg install -y axel",
    "pkg install -y parallel",
    "pkg install -y socat",
    "pkg install -y rlwrap",
    "pkg install -y expect",
    "pkg install -y inetutils-traceroute",
    "pkg install -y inetutils-ping",
    "pkg install -y inetutils-telnet",
    "pkg install -y busybox",
    "pkg install -y coreutils",
    "pkg install -y util-linux",
    "pkg install -y procps",
    "pkg install -y psmisc",
    "pkg install -y file",
    "pkg install -y strace",
    "pkg install -y ltrace",
    "pkg install -y which",
    "pkg install -y time",
    "pkg install -y ncurses-utils",
    "pip install typer",
    "pip install click",
    "pip install argparse",
    "pip install validators",
    "pip install humanize",

    "pkg install -y iputils-ping",
    "pkg install -y iputils-arping",
    "pkg install -y ndisc6",
    "pkg install -y rt-tools",
    "pkg install -y conntrack-tools",
    "pkg install -y nftables",
    "pkg install -y tcpdump-minimal",
    "pkg install -y moreutils",
    "pkg install -y watch",
    "pkg install -y progress",
    "pkg install -y pv",
    "pkg install -y dstat",
    "pkg install -y glances",
    "pkg install -y btop",
    "pip install rich",
    "pip install loguru",

    "pkg install -y net-tools",
    "pkg install -y bridge-utils",
    "pkg install -y radvd",
    "pkg install -y ndpmon",
    "pkg install -y iputils",
    "pkg install -y tcpflow",
    "pkg install -y httptoolkit",
    "pkg install -y mitmproxy",
    "pip install httpcore",
    "pip install h2",
    "pip install hyperframe",
    "pip install idna",

     "pkg install -y snmp",
    "pkg install -y snmp-mibs-downloader",
    "pkg install -y nbtscan",
    "pkg install -y smbclient",
    "pkg install -y enum4linux",
    "pkg install -y crackmapexec",
    "pkg install -y responder",
    "pkg install -y xh",
    "pkg install -y curlie",
    "pkg install -y dog",
    "pkg install -y httpstat",
    "pkg install -y bandwhich",
    "pkg install -y netsniff-ng",
    "pip install trafilatura",
    "pip install newspaper3k",
    "pip install tldextract",
    "pip install yarl",

    "pkg install -y masscan",
    "pkg install -y zmap",
    "pkg install -y fping",
    "pkg install -y hping3",
    "pkg install -y socat",
    "pkg install -y tcptraceroute",
    "pkg install -y ipcalc",
    "pkg install -y ethtool",
    "pkg install -y bettercap",
    "pkg install -y feroxbuster",
    "pkg install -y gobuster",
    "pkg install -y dirsearch",
    "pkg install -y ffuf",
    "pkg install -y amass",
    "pkg install -y subfinder",
    "pkg install -y assetfinder",
    "pkg install -y nuclei",
    "pkg install -y httpx",
    "pkg install -y gau",
    "pkg install -y waybackurls",
    "pkg install -y chaos-client",
    "pip install aiohttp",
    "pip install pycurl",
    "pip install urllib3",
    "pip install websocket-client",
    "pip install pyopenssl",
    "pip install cryptography",

    "pkg install -y nmap",
    "pkg install -y ncat",
    "pkg install -y tcpdump",
    "pkg install -y traceroute",
    "pkg install -y mtr",
    "pkg install -y dnsutils",
    "pkg install -y inetutils",
    "pkg install -y iproute2",
    "pkg install -y netcat-openbsd",
    "pkg install -y arp-scan",
    "pkg install -y speedtest-cli",
    "pkg install -y iperf3",
    "pkg install -y vnstat",
    "pkg install -y whois",
    "pkg install -y theharvester",
    "pkg install -y recon-ng",
    "pkg install -y maltego",
    "pkg install -y sslscan",
    "pkg install -y testssl.sh",
    "pkg install -y nikto",
    "pkg install -y wafw00f",
    "pkg install -y httpie",
    "pkg install -y websocat",
    "pkg install -y grpcurl",
    "pkg install -y lynx",
    "pkg install -y w3m",
    "pkg install -y tor",
    "pkg install -y torsocks",
    "pkg install -y proxychains-ng",
    "pkg install -y openvpn",
    "pkg install -y rclone",
    "pkg install -y croc",
    "pkg install -y rsync",
    "pkg install -y lftp",
    "pkg install -y aria2",
    "pkg install -y chisel",
    "pkg install -y frp",
    "pkg install -y siege",
    "pkg install -y hey",
    "pkg install -y hydra",
    "pkg install -y sqlmap",
    "pkg install -y metasploit",
    "pkg install -y bind-tools",
    "pkg install -y ldns",
    "pkg install -y knot-dnsutils",
    "pkg install -y tshark",
    "pkg install -y ngrep",
    "pkg install -y iftop",
    "pkg install -y bmon",
    "pkg install -y aircrack-ng",
    "pkg install -y reaver",
    "pkg install -y pixiewps",
    "pkg install -y httrack",
    "pkg install -y wget2",
    "pkg install -y medusa",
    "pkg install -y patator",
    "pkg install -y hashcat",
    "pkg install -y john",
    "pkg install -y swaks",
    "pkg install -y proot",
    "pkg install -y proot-distro",
    "pkg install -y protobuf",
    "pkg install -y thrift",
    "pip install requests-html",
    "pip install beautifulsoup4",
    "pip install scrapy",
    "pip install mitmproxy",
    "pip install dnspython",
    "pip install shodan",
    "pip install censys",
    "pip install sherlock-project",
    "pip install socialscan",
    "pip install holehe",
    "pip install scapy",
    "pip install impacket",

    "pip install scapy",
    "pip install dnspython",
    "pip install aiohttp",
    "pip install websockets",
    "pip install httpx",
    "pip install rich",

    "pkg install -y curl",
    "pkg install -y wget",
    "pkg install -y httpie",
    "pkg install -y aria2",
    "pkg install -y lynx",
    "pkg install -y w3m",
    "pkg install -y jq",

    "pkg install -y nmap",
    "pkg install -y ncat",
    "pkg install -y tcpdump",
    "pkg install -y traceroute",
    "pkg install -y mtr",
    "pkg install -y dnsutils",
    "pkg install -y inetutils",
    "pkg install -y iproute2",
    "pkg install -y netcat-openbsd",
    "pkg install -y arp-scan",

        "pkg install -y speedtest-cli",
    "pkg install -y iperf3",
    "pkg install -y vnstat",

     "pkg install -y whois",
    "pkg install -y theharvester",
    "pkg install -y recon-ng",
    "pkg install -y maltego",

    
    "pkg install -y sslscan",
    "pkg install -y testssl.sh",
    "pkg install -y nikto",
    "pkg install -y wafw00f",

        "pkg install -y httpie",
    "pkg install -y websocat",
    "pkg install -y grpcurl",
    "pkg install -y lynx",
    "pkg install -y w3m",

        "pkg install -y tor",
    "pkg install -y torsocks",
    "pkg install -y proxychains-ng",
    "pkg install -y openvpn",

        "pkg install -y rclone",
    "pkg install -y croc",
    "pkg install -y rsync",
    "pkg install -y lftp",
    "pkg install -y aria2",
    "pkg install -y chisel",
    "pkg install -y frp",

    "pkg install -y siege",
    "pkg install -y hey",

    "pkg install -y hydra",
    "pkg install -y sqlmap",
    "pkg install -y metasploit",

    "pip install requests-html",
    "pip install beautifulsoup4",
    "pip install scrapy",
    "pip install mitmproxy",
    "pip install dnspython",
    "pip install shodan",
    "pip install censys",

    "pip install shodan",
    "pip install censys",
    "pip install python-nmap",
    "pip install netaddr",
    "pip install pysocks",

    "pkg install -y aircrack-ng",
    "pkg install -y bettercap",
    "pkg install -y macchanger",

    "pkg install -y amass",
    "pkg install -y subfinder",
    "pkg install -y dnsenum",
    "pkg install -y fierce",
    "pkg install -y nikto",
    "pkg install -y whatweb",
    "pkg install -y httprobe",
    "pkg install -y gobuster",
    "pkg install -y ffuf",

    "pkg install -y socat",
    "pkg install -y tshark",
    "pkg install -y bmon",
    "pkg install -y vnstat",
    "pkg install -y nload",

    "pkg install -y inetutils",
    "pkg install -y net-tools",
    "pkg install -y iproute2",
    "pkg install -y bind-tools",
    "pkg install -y dnsutils",

    "pkg install -y ncat",
    "pkg install -y arp-scan",
    "pkg install -y fping",
    "pkg install -y netdiscover",
    "pkg install -y masscan",

    "pkg install -y tcpdump",
    "pkg install -y iftop",
    "pkg install -y iptraf-ng",

    "pkg install -y iperf3",
    "pkg install -y traceroute",
    "pkg install -y mtr",
    "pkg install -y fast-cli",

    "pkg install -y tor",
    "pkg install -y torsocks",
    "pkg install -y proxychains-ng",
    "pkg install -y wireguard-tools",

    "pkg install -y wrk",
    "pkg install -y apache2-utils",

        "pkg install python -y",
        "pkg install python2",
        "pkg install python3",
        "pkg install git",
        "pkg install termux-api",
        "pkg install php",
        "pkg install python-pip -y",

        "pip install --upgrade pip",
        "pip install colorama",
        "pip install python-whois",
        "pip install tqdm",
        "pip install pyfiglet",
        "pip install requests",
        "pip install tqdm pyfiglet colorama requests",
    ]

    for cmd in COMMANDS:
        try:
            run_with_retry(cmd)
        except Exception as e:
            log(f"[SKIP] {cmd} : {e}")

    log("AUTO-HEAVY INSTALL FINISHED")
def github_tools_auto_update():
    log("GITHUB TOOL AUTO UPDATE START")
    TOOLS_DIR.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)

    for tool in TOOLS_DIR.iterdir():
        if not (tool / ".git").exists():
            continue

        name = tool.name
        backup = BACKUP_DIR / f"{name}-{int(time.time())}.tar.gz"

        run_raw(f"tar -czf {backup} -C {TOOLS_DIR} {name}")

        try:
            run_raw(f"cd {tool} && git pull")
        except:
            run_raw(f"rm -rf {tool}")
            run_raw(f"tar -xzf {backup} -C {TOOLS_DIR}")
            log(f"[ROLLBACK] {name}")

def original_main():
    install_packages()
    github_tools_auto_update()

# 🔒 AUTO-INSTALL OFF (IMPORTANT)
if __name__ == "__main__":
    dashboard_menu()