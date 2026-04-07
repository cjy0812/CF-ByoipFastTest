import sys
import subprocess
import argparse

# ===== 自动依赖 =====
def ensure(pkg):
    try:
        __import__(pkg)
    except:
        print(f"[!] 安装依赖 {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

ensure("requests")

import requests
import re
import ipaddress
import random
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== 配置 =====
DEFAULT_DOMAIN = ""
TIMEOUT = 1.5
MAX_WORKERS = 100

SSL_CONTEXT = ssl.create_default_context()


# ===== 获取CIDR =====
def fetch_cidrs():
    print("[*] 获取网段...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:149.0) Gecko/20100101 Firefox/149.0"})
    html = session.get("https://ipregistry.co/AS209242", timeout=10).text
    
    # 匹配IPv4和IPv6的CIDR格式
    ipv4_pattern = r"\d+\.\d+\.\d+\.\d+/\d+"
    ipv6_pattern = r"[0-9a-fA-F:.]+/\d+"
    
    ipv4_cidrs = re.findall(ipv4_pattern, html)
    ipv6_cidrs = re.findall(ipv6_pattern, html)
    
    # 合并并去重
    all_cidrs = list(set(ipv4_cidrs + ipv6_cidrs))
    print(f"[*] 找到 {len(all_cidrs)} 个网段")
    return all_cidrs


# ===== 处理IP段 =====
def process_cidrs(cidrs):
    ipv4_ips = []
    ipv6_ips = []
    
    for cidr in cidrs:
        try:
            # 去掉CIDR后缀，得到网络地址
            ip = cidr.split('/')[0]
            # 验证是否为有效IP
            ip_obj = ipaddress.ip_address(ip)
            if isinstance(ip_obj, ipaddress.IPv4Address):
                ipv4_ips.append(ip)
            elif isinstance(ip_obj, ipaddress.IPv6Address):
                ipv6_ips.append(ip)
        except:
            continue
    
    print(f"[*] 处理后 - IPv4: {len(ipv4_ips)} 个, IPv6: {len(ipv6_ips)} 个")
    return ipv4_ips, ipv6_ips

# ===== 检测IPv6可用性 =====
def check_ipv6_availability():
    print("[*] 检测IPv6可用性...")
    try:
        # 测试连接阿里IPv6 DNS检测v6可用性
        socket.create_connection(("2400:3200::1", 53), timeout=3)
        print("[*] IPv6可用")
        return True
    except:
        print("[*] IPv6不可用，将使用IPv4")
        return False


# ===== 测试 =====
def test_ip(ip, domain):
    start = time.time()

    try:
        sock = socket.create_connection((ip, 443), timeout=TIMEOUT)

        with SSL_CONTEXT.wrap_socket(sock, server_hostname=domain) as ssock:
            ssock.settimeout(TIMEOUT)

            req = f"HEAD / HTTP/1.1\r\nHost: {domain}\r\nConnection: close\r\n\r\n"
            ssock.send(req.encode())

            data = b""
            while True:
                chunk = ssock.recv(512)
                if not chunk:
                    break
                data += chunk
                if len(data) > 2048:
                    break

            text = data.decode(errors="ignore").lower()

            latency = round((time.time() - start) * 1000, 1)

            is_cf = ("cloudflare" in text or "cf-ray" in text)
            ok = ("200" in text or "404" in text)

            if ok:
                return (ip, latency, is_cf)

    except:
        return None

    return None


# ===== 主程序 =====
def main():
    # 从终端获取域名
    domain = input("请输入测试域名 (例如: example.com): ").strip()
    
    # 验证域名输入
    if not domain:
        print("[!] 域名不能为空，请重新运行并输入有效的域名")
        return

    print(f"[*] 目标: {domain}")

    # 获取并处理IP段
    cidrs = fetch_cidrs()
    ipv4_ips, ipv6_ips = process_cidrs(cidrs)
    
    # 检测IPv6可用性
    ipv6_available = check_ipv6_availability()
    
    # 构建测试IP列表
    ips = ipv4_ips.copy()  # 基础测试v4
    
    # 如果v6可用且有v6地址，增加v6测试
    if ipv6_available and len(ipv6_ips) > 0:
        ips.extend(ipv6_ips)
        print(f"[*] 测试IP: IPv4 {len(ipv4_ips)} 个 + IPv6 {len(ipv6_ips)} 个 = 共 {len(ips)} 个\n")
    else:
        # v6不可用或无v6地址
        if not ipv6_available:
            print("[*] IPv6不可用，仅测试IPv4地址\n")
        elif len(ipv6_ips) == 0:
            print("[*] 未找到IPv6地址，仅测试IPv4地址\n")
        print(f"[*] 测试IP: IPv4 {len(ips)} 个\n")
    
    # 如果没有IP，提示错误
    if not ips:
        print("[!] 没有找到可用的IP地址")
        return

    results = []

    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        futures = [ex.submit(test_ip, ip, domain) for ip in ips]

        for f in as_completed(futures):
            r = f.result()
            if r:
                ip, latency, cf = r
                tag = "CF" if cf else "??"
                print(f"[✓] {ip:<15} {latency:>6} ms   {tag}")
                if cf:
                    results.append((ip, latency))
            else:
                print("[×] timeout")

    results.sort(key=lambda x: x[1])

    print("\n===== 最优IP =====\n")
    for ip, latency in results[:10]:
        print(f"{ip:<15} {latency} ms")

    with open("best_ips.txt", "w") as f:
        for ip, latency in results:
            f.write(f"{ip} {latency}ms\n")

    print("\n[✔] 已输出 best_ips.txt")


if __name__ == "__main__":
    main()
    