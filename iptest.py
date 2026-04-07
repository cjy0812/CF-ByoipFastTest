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
    return list(set(re.findall(r"\d+\.\d+\.\d+\.\d+/\d+", html)))


# ===== 过滤 =====
def filter_cidrs(cidrs):
    result = []
    for c in cidrs:
        net = ipaddress.ip_network(c, strict=False)
        if isinstance(net, ipaddress.IPv6Network):
            continue
        if net.prefixlen < 20:
            continue
        result.append(net)
    return result


# ===== 抽样（无全展开）=====
def sample_ips(net):
    size = net.num_addresses

    if size <= 256:
        count = 10
    elif size <= 1024:
        count = 20
    else:
        return []

    base = int(net.network_address)
    return [
        str(ipaddress.ip_address(base + random.randint(1, size - 2)))
        for _ in range(count)
    ]


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
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--domain", default=DEFAULT_DOMAIN)
    args = parser.parse_args()

    domain = args.domain

    print(f"[*] 目标: {domain}")

    cidrs = filter_cidrs(fetch_cidrs())
    print(f"[*] 有效网段: {len(cidrs)}")

    ips = []
    for net in cidrs:
        ips.extend(sample_ips(net))

    print(f"[*] 抽样IP: {len(ips)}\n")

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
    