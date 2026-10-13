"""Run the existing ownership-checked review starter without a console window."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    status = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'ok': False}
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy',
             'Bypass', '-File', str(ROOT / 'scripts/start-review-backend.ps1')],
            cwd=ROOT, capture_output=True, timeout=50,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        status.update(returnCode=result.returncode, ok=result.returncode == 0)
    except Exception as exc:
        status['error'] = type(exc).__name__
    (ROOT / 'runtime/review-startup-status.json').write_text(
        json.dumps(status, indent=2), encoding='utf-8')
    return 0 if status['ok'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
