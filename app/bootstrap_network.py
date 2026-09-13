"""WSL-native Docker network bootstrap, independent of app configuration/secrets."""
import ipaddress
import os
from pathlib import Path
import socket
import struct
import sys


def windows_gateway(routes: str) -> str:
    candidates = []
    for line in routes.splitlines()[1:]:
        columns = line.split()
        if len(columns) < 8:
            continue
        try:
            if columns[1] != '00000000' or columns[7] != '00000000':
                continue
            if int(columns[3], 16) & 3 != 3:
                continue
            address = socket.inet_ntoa(struct.pack('<I', int(columns[2], 16)))
            if ipaddress.IPv4Address(address).is_unspecified:
                continue
            candidates.append((int(columns[6]), address))
        except (ValueError, OSError, struct.error):
            continue
    if not candidates:
        raise ValueError('No usable default host route')
    return min(candidates)[1]


def hosts_with_alias(text: str, address: str) -> str:
    address = str(ipaddress.IPv4Address(address))
    if ipaddress.IPv4Address(address).is_unspecified:
        raise ValueError('Unspecified host address')
    lines = []
    for line in text.splitlines():
        body, marker, comment = line.partition('#')
        fields = body.split()
        if 'ollama.windows.host' in fields[1:]:
            fields = [fields[0]] + [f for f in fields[1:] if f != 'ollama.windows.host']
            if len(fields) > 1:
                lines.append(' '.join(fields) + (' #' + comment if marker else ''))
            elif marker:
                lines.append('#' + comment)
        else:
            lines.append(line)
    return '\n'.join(lines) + f'\n{address}\tollama.windows.host\n'


def main():
    try:
        address = os.environ.get('OLLAMA_WINDOWS_IP', '').strip()
        if not address:
            route_path = os.environ.get('TAX_WSL_HOST_ROUTE', '/run/tax-wsl-host-route')
            address = windows_gateway(Path(route_path).read_text())
        hosts = Path('/etc/hosts')
        # /etc/hosts is a Docker bind mount: write in place, not atomic rename.
        hosts.write_text(hosts_with_alias(hosts.read_text(), address))
    except (OSError, ValueError):
        print('[ERROR] Windows Ollama address resolution failed. Check WSL host route mount '
              'or set OLLAMA_WINDOWS_IP explicitly.', file=sys.stderr)
        return 1
    if len(sys.argv) < 2:
        print('[ERROR] Missing container command', file=sys.stderr)
        return 1
    print('[OK] Windows Ollama host alias configured', flush=True)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    raise SystemExit(main())
