"""Restore this project's existing WSL stacks; never pull images or install software."""
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISTRO = 'CRA-Ubuntu-24.04'
FLAGS = subprocess.CREATE_NO_WINDOW
STATUS = ROOT / 'runtime/local-services-status.json'

def run(argv, timeout=30):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True,
                            encoding='utf-8', errors='replace', timeout=timeout,
                            creationflags=FLAGS)
    if result.returncode:
        raise RuntimeError('command_failed_exit_' + str(result.returncode))
    return result.stdout.strip()

def powershell(code):
    # Windows PowerShell otherwise uses the OEM code page; the project path is Chinese.
    code = '[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); ' + code
    return run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', code])

def wsl(*argv, timeout=30):
    return run(['wsl.exe', '-d', DISTRO, '-u', 'root', '--', *argv], timeout)

def read_state(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}

def process_command(pid):
    if not isinstance(pid, int) or pid <= 0:
        return ''
    return powershell(f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}" -ErrorAction SilentlyContinue).CommandLine')

def listening(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False

def detached(argv):
    return subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=FLAGS)

def ensure_holder():
    path = ROOT / 'runtime/wsl-session.json'
    state = read_state(path)
    cmd = process_command(state.get('ProcessId'))
    if DISTRO in cmd and 'sleep infinity' in cmd and 'wsl' in cmd.lower():
        return state['ProcessId']
    child = detached(['wsl.exe', '-d', DISTRO, '-u', 'root', '--', 'sleep', 'infinity'])
    path.write_text(json.dumps({'ProcessId': child.pid}), encoding='utf-8')
    return child.pid

def ensure_proxy():
    gateway = json.loads(wsl('ip', '-j', '-4', 'route', 'show', 'default'))[0]['gateway']
    adapter = json.loads(wsl('ip', '-j', '-4', 'addr', 'show', 'eth0'))[0]
    client = next(item['local'] for item in adapter['addr_info'] if item['family'] == 'inet')
    path = ROOT / 'runtime/image-proxy-state.json'
    state = read_state(path)
    if state.get('Gateway') != gateway or state.get('Client') != client:
        # Do not widen firewall scope or reuse a proxy intended for another WSL IP.
        return {'ok': False, 'reason': 'wsl_addresses_changed_run_Start_ImageProxy',
                'gateway': gateway, 'client': client}
    proxy_script = str(ROOT / 'scripts/wsl-image-proxy.py')
    cmd = process_command(state.get('ProcessId'))
    if proxy_script.lower() in cmd.lower() and listening(gateway, 18080):
        return {'ok': True, 'upstreamAvailable': listening('127.0.0.1', 10808)}
    if listening(gateway, 18080):
        return {'ok': False, 'reason': 'proxy_port_owner_not_verified'}
    child = detached([str(Path(sys.executable).with_name('pythonw.exe')), proxy_script,
                      '--listen', gateway, '--client', client])
    time.sleep(0.5)
    if child.poll() is not None or not listening(gateway, 18080):
        return {'ok': False, 'reason': 'proxy_start_failed'}
    state['ProcessId'] = child.pid
    path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    return {'ok': True, 'upstreamAvailable': listening('127.0.0.1', 10808)}

def ensure_stack(name, services):
    linux_root = '/mnt/' + ROOT.drive[0].lower() + ROOT.as_posix()[2:]
    directory = linux_root + '/deployment/' + name
    base = ['wsl.exe', '-d', DISTRO, '-u', 'root', '--cd', directory,
            '--', 'docker', 'compose']
    rows = run(base + ['ps', '--all', '--format', 'json']).splitlines()
    states = [json.loads(row) for row in rows if row.strip()]
    healthy = all(any(row.get('Service') == service and row.get('State') == 'running'
                      and row.get('Health', '') in ('', 'healthy') for row in states)
                  for service in services)
    if not healthy:
        run(base + ['up', '-d', '--pull', 'never', '--no-build', '--wait',
                    '--wait-timeout', '90'], timeout=110)
    return {'ok': True, 'recoveryNeeded': not healthy}

def main():
    state = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'ok': False}
    try:
        state['holderPid'] = ensure_holder()
        state['proxy'] = ensure_proxy()
        for name, services in [('twenty', ('server', 'worker', 'db', 'redis')),
                               ('evolution', ('api', 'db', 'redis'))]:
            state[name] = ensure_stack(name, services)
        state['ok'] = True
    except Exception as exc:
        state['error'] = type(exc).__name__
        if isinstance(exc, RuntimeError):
            state['reason'] = str(exc)
    STATUS.write_text(json.dumps(state, indent=2), encoding='utf-8')
    return 0 if state['ok'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
