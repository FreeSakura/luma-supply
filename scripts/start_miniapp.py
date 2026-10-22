"""Configure the unified mini-program for the current LAN and start its dev API."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
LAN_RANGES = tuple(ipaddress.ip_network(net) for net in
                   ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def lan_ip(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise ValueError('请使用有效的局域网 IPv4 地址。') from None
    if not any(address in network for network in LAN_RANGES):
        raise ValueError('请选择 10.x、172.16–31.x 或 192.168.x 的局域网地址。')
    return str(address)


def detect_ip():
    # Enumerate physical interfaces instead of following a possible VPN default route.
    if sys.platform == 'darwin':
        output = subprocess.check_output(['/sbin/ifconfig'], text=True)
        candidates = []
        for block in re.split(r'\n(?=\S)', output):
            name = block.split(':', 1)[0]
            if not re.fullmatch(r'en\d+|bridge\d+', name):
                continue
            if not re.search(r'^\s*status: active\s*$', block, re.M):
                continue
            for value in re.findall(r'^\s*inet (\S+)', block, re.M):
                try:
                    candidates.append((name, lan_ip(value)))
                except ValueError:
                    pass
    elif sys.platform.startswith('linux'):
        output = subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'up'], text=True)
        candidates = []
        for interface in json.loads(output):
            name = interface['ifname']
            if not re.fullmatch(r'(?:eth|wlan|en|wl)[\w.-]*', name):
                continue
            for address in interface.get('addr_info', []):
                try:
                    candidates.append((name, lan_ip(address['local'])))
                except ValueError:
                    pass
    else:
        raise ValueError('此系统请用 --ip 指定电脑的局域网 IPv4 地址。')
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) != 1:
        found = '、'.join(f'{name}: {ip}' for name, ip in candidates) or '未找到活动的局域网网卡'
        raise ValueError(f'{found}。请连接 Wi-Fi/热点，或用 --ip 明确指定地址。')
    name, address = candidates[0]
    print(f'当前网络：{name} / {address}', flush=True)
    return address


def configure(base_url):
    target = ROOT / 'miniapps' / 'unified'
    config_path = target / 'config.js'
    source = config_path.read_text(encoding='utf-8')
    match = re.fullmatch(r'\s*module\.exports\s*=\s*(\{.*\})\s*;?\s*', source, re.S)
    if not match:
        raise ValueError(f'{config_path} 不是支持的 JSON 配置格式，未修改文件。')
    config = json.loads(match[1])
    config.update(baseUrl=base_url, demo=True)
    # Read all files before writing; keep AppID and unrelated settings intact.
    projects = []
    for filename in ('project.config.json', 'project.private.config.json'):
        path = target / filename
        if path.exists():
            project = json.loads(path.read_text(encoding='utf-8'))
            project.setdefault('setting', {})['urlCheck'] = False
            projects.append((path, project))
    config_path.write_text('module.exports = ' + json.dumps(config, ensure_ascii=False) + '\n', encoding='utf-8')
    for path, project in projects:
        path.write_text(json.dumps(project, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'已更新统一小程序 API：{base_url}', flush=True)
    print('请在微信开发者工具重新编译；手机测试需重新预览扫码并开启调试。', flush=True)


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        return connection.connect_ex(('127.0.0.1', port)) == 0


def check_backend(base_url):
    try:
        # Local probes must not be sent through an HTTP proxy.
        with build_opener(ProxyHandler({})).open(base_url + '/api/health', timeout=3) as response:
            data = json.load(response)
            valid = (response.status == 200 and isinstance(data, dict) and data.get('status') == 'ok'
                     and data.get('version') == '2.1.0'
                     and data.get('environment') == 'development'
                     and 'integrations' in data)
    except (OSError, ValueError) as exc:
        raise ValueError('端口已有服务，但无法通过局域网验证后端。若旧后端只监听 '
                         '127.0.0.1，请先在原终端按 Ctrl+C 停止，再运行本脚本。') from exc
    if not valid:
        raise ValueError('此端口不是可复用的 LumaSupply 2.1 开发后端；请检查服务或用 --port 指定其他端口。')


def main(argv=None):
    parser = argparse.ArgumentParser(description='自动更新小程序局域网地址并启动本地开发后端。')
    parser.add_argument('--ip', help='手动指定 IP（有多张活动网卡时使用）')
    parser.add_argument('--port', type=int, default=8000, help='后端端口，默认 8000')
    parser.add_argument('--configure-only', action='store_true', help='只更新配置，不检查或启动后端')
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError('端口必须介于 1 和 65535 之间。')
        address = lan_ip(args.ip) if args.ip else detect_ip()
        base_url = f'http://{address}:{args.port}'
        reuse = not args.configure_only and port_in_use(args.port)
        if reuse:
            check_backend(base_url)
        elif not args.configure_only:
            import uvicorn  # noqa: F401 -- fail before modifying files if dependencies are missing
        configure(base_url)
        print(f'手机浏览器检测地址：{base_url}/api/health', flush=True)
        if args.configure_only:
            return 0
        if reuse:
            print('现有后端健康检查通过，继续使用原进程（未重启）。', flush=True)
            print('如果原进程未启用局域网演示验证码，请停止后通过本脚本启动。', flush=True)
            return 0
        env = dict(os.environ, APP_ENV='development', DEMO_SMS_LAN='1')
        print('正在启动开发后端，监听 0.0.0.0；保持此窗口开启，按 Ctrl+C 停止。', flush=True)
        os.chdir(ROOT)
        os.execve(sys.executable, [sys.executable, '-m', 'uvicorn', 'backend.main:app',
                                  '--host', '0.0.0.0', '--port', str(args.port)], env)
    except (ValueError, OSError, subprocess.SubprocessError, ImportError) as exc:
        print(f'启动失败：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
