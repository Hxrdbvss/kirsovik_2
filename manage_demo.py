"""Start/stop the three local demo processes without Docker."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / '.runtime'
STATE = RUNTIME / 'processes.json'
SERVICES = [
    ('api', 8006, '/health', [sys.executable, '-m', 'uvicorn', 'unified_api:app', '--app-dir', str(ROOT / 'knowledge-project'), '--host', '127.0.0.1', '--port', '8006']),
    ('risk', 8007, '/health', [sys.executable, '-m', 'uvicorn', 'risk_api:app', '--app-dir', str(ROOT / 'coursework-data/oulad'), '--host', '127.0.0.1', '--port', '8007']),
    ('portal', 8501, '/_stcore/health', [sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'knowledge-project/student_portal.py'), '--server.address', '127.0.0.1', '--server.port', '8501', '--server.headless', 'true', '--browser.gatherUsageStats', 'false']),
]


def ready(port, endpoint):
    try:
        with urlopen(f'http://127.0.0.1:{port}{endpoint}', timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def occupied(port):
    with socket.socket() as stream:
        return stream.connect_ex(('127.0.0.1', port)) == 0


def own_process(pid):
    try:
        return str(ROOT).encode() in Path(f'/proc/{pid}/cmdline').read_bytes()
    except OSError:
        return False


def stop(records):
    for record in records:
        if own_process(record['pid']):
            os.kill(record['pid'], signal.SIGTERM)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'
    records = json.loads(STATE.read_text()) if STATE.exists() else []
    if action == 'stop':
        stop(records)
        print('Demo processes stopped. Original project and databases preserved.')
        return
    if action == 'status':
        for name, port, endpoint, _ in SERVICES:
            print(f'{name}: {"ready" if ready(port, endpoint) else "unavailable"} (port {port})')
        return
    if action != 'start':
        raise SystemExit('Use start, status or stop.')
    if all(ready(port, endpoint) for _, port, endpoint, _ in SERVICES) and all(any(r['name'] == name and own_process(r['pid']) for r in records) for name, *_ in SERVICES):
        print('Demo already running: http://localhost:8501')
        return
    if any(own_process(record['pid']) for record in records):
        raise SystemExit('A partial demo is running. Run stop, then start.')
    for name, port, _, _ in SERVICES:
        if occupied(port):
            raise SystemExit(f'Port {port} is occupied by another process; no processes were stopped.')
    RUNTIME.mkdir(exist_ok=True)
    started = []
    try:
        for name, _, _, command in SERVICES:
            with (RUNTIME / f'{name}.log').open('a', encoding='utf-8') as log:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            started.append({'name': name, 'pid': process.pid})
            STATE.write_text(json.dumps(started, indent=2))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if all(ready(port, endpoint) for _, port, endpoint, _ in SERVICES):
                print('Demo ready: http://localhost:8501')
                print('API documentation: http://localhost:8006/docs')
                return
            if any(not own_process(record['pid']) for record in started):
                break
            time.sleep(0.5)
        raise RuntimeError(f'A service did not become ready. See logs in {RUNTIME}')
    except BaseException:
        stop(started)
        raise


if __name__ == '__main__':
    main()
