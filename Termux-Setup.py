#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import subprocess
import time
from datetime import datetime

# ================= COLORS =================
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

LOG_FILE = os.path.expanduser("~/termux-setup.log")

# ================= COMMAND LIST =================
RAW_COMMANDS = [
    "pkg update -y",
    "pkg upgrade -y",
    "pip install --upgrade pip",

    # Core tools
    "pkg install -y python git curl wget aria2 jq",
    "pkg install -y coreutils util-linux busybox procps psmisc file",
    "pkg install -y net-tools iproute2 inetutils dnsutils bind-tools",

    # Networking
    "pkg install -y nmap ncat masscan tcpdump traceroute mtr whois",
    "pkg install -y arp-scan fping netdiscover",
    "pkg install -y vnstat iftop bmon nload iperf3 speedtest-cli",

    # Web & Recon
    "pkg install -y httpie lynx w3m whatweb nikto wafw00f",
    "pkg install -y gobuster ffuf feroxbuster amass subfinder",
    "pkg install -y theharvester recon-ng",

    # Proxy / VPN
    "pkg install -y tor torsocks proxychains-ng openvpn wireguard-tools",

    # Wireless (rootless compatible only)
    "pkg install -y aircrack-ng macchanger",

    # Development & Utils
    "pkg install -y php termux-api proot proot-distro",

    # Python libraries
    "pip install requests colorama tqdm pyfiglet rich loguru",
    "pip install dnspython python-whois validators humanize",
    "pip install aiohttp httpx urllib3 websockets",
    "pip install scapy impacket",
]

# ================= FUNCTIONS =================
def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

def run(cmd):
    print(BLUE + f"\n[+] Running: {cmd}" + RESET)
    log(f"[{datetime.now()}] {cmd}")
    try:
        subprocess.run(cmd, shell=True, check=False)
    except KeyboardInterrupt:
        print(RED + "\n[!] Interrupted by user" + RESET)
        sys.exit(1)

def banner():
    os.system("clear")
    print(BLUE + r"""
████████╗███████╗██████╗ ███╗   ███╗██╗   ██╗██╗  ██╗
╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║   ██║╚██╗██╔╝
   ██║   █████╗  ██████╔╝██╔████╔██║██║   ██║ ╚███╔╝ 
   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║   ██║ ██╔██╗ 
   ██║   ███████╗██║  ██║██║ ╚═╝ ██║╚██████╔╝██╔╝ ██╗
   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝
""" + RESET)
    print(GREEN + "Termux Ultimate Setup (Learning Purpose Only)\n" + RESET)

def main():
    banner()
    print(YELLOW + "[!] This may take a long time depending on your internet\n" + RESET)
    input("Press Enter to start...")

    for cmd in RAW_COMMANDS:
        run(cmd)
        time.sleep(0.3)

    print(GREEN + "\n[✓] All tasks completed successfully!" + RESET)
    print(GREEN + f"[✓] Log saved to: {LOG_FILE}\n" + RESET)

# ================= ENTRY =================
if __name__ == "__main__":
    main()