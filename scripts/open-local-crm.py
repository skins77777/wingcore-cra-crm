"""Desktop recovery entry: trigger existing tasks silently, then open local CRM."""
import html
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def reachable(port, path, expected=200):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
            return response.status == expected
    except urllib.error.HTTPError as error:
        return error.code == expected
    except (OSError, TimeoutError):
        return False

def main():
    results = {}
    for name in ('CRA-Wingcore-Local-Services', 'CRA-Wingcore-Review-Backend',
                 'CRA-Wingcore-Order-Report'):
        command = subprocess.run(['schtasks.exe', '/Run', '/TN', name],
                                 capture_output=True, timeout=15,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        results[name] = command.returncode
    deadline = time.monotonic() + 180
    while True:
        health = {
            'CRM': reachable(3000, '/healthz'),
            'WhatsApp服务': reachable(8082, '/'),
            '订单统计': reachable(3001, '/health'),
            '审核后台': reachable(3002, '/v1/review/errors', 403),
        }
        if all(health.values()) or time.monotonic() >= deadline:
            break
        time.sleep(3)
    status = {'checkedAt': datetime.now(timezone.utc).isoformat(),
              'taskResults': results, 'health': health}
    (ROOT / 'runtime/desktop-start-status.json').write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    if all(health.values()):
        os.startfile('http://localhost:3000/home')
    else:
        rows = ''.join('<li>' + html.escape(label) + '：' + ('正常' if ok else '未就绪') + '</li>'
                       for label, ok in health.items())
        report = ROOT / 'runtime/desktop-start-result.html'
        report.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                          '<title>CRA 启动检查</title><body><h1>CRA 启动检查</h1><ul>' + rows +
                          '</ul><p>本次已等待三分钟，仍有服务未就绪。请把这个页面的结果告诉 Codex 排查。</p>'
                          '<p><a href="http://localhost:3000/home">打开 CRM</a></p></body></html>',
                          encoding='utf-8')
        os.startfile(str(report))

if __name__ == '__main__':
    main()
