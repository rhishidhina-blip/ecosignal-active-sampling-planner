"""Bound the heavy preparation child; emit live heartbeat and retain diagnostics."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def supervise(command, *, deadline_seconds=1200, heartbeat_seconds=30, log_dir=None):
    out = Path(log_dir or ROOT / '.preparation-cache')
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    env = dict(os.environ, PYTHONUNBUFFERED='1')
    print(f'Preparation started; hard deadline {deadline_seconds}s; heartbeat {heartbeat_seconds}s.', flush=True)
    with (out / 'preparation.log').open('w') as log:
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        offset = 0
        next_heartbeat = started + heartbeat_seconds
        try:
            while True:
                with (out / 'preparation.log').open() as reader:
                    reader.seek(offset)
                    chunk = reader.read()
                    offset = reader.tell()
                if chunk:
                    print(chunk, end='', flush=True)
                code = child.poll()
                elapsed = time.monotonic() - started
                if code is not None:
                    # Read bytes flushed just as the child exited.
                    with (out / 'preparation.log').open() as reader:
                        reader.seek(offset)
                        print(reader.read(), end='', flush=True)
                    status = 'success' if code == 0 else 'failed'
                    break
                if elapsed >= deadline_seconds:
                    print('::error::Preparation exceeded its bounded deadline. See the last stage above and retained diagnostics. No unverified pool will be published.', flush=True)
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                    code, status = 124, 'deadline_exceeded'
                    break
                if time.monotonic() >= next_heartbeat:
                    print(f'[heartbeat] Preparation child running: {elapsed:.0f}s elapsed; {deadline_seconds-elapsed:.0f}s remaining.', flush=True)
                    next_heartbeat = time.monotonic() + heartbeat_seconds
                time.sleep(.2)
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    report = {'status': status, 'exit_code': code, 'elapsed_seconds': round(time.monotonic()-started, 2),
              'note': 'External runner cancellation cannot be diagnosed or prevented by this child-process watchdog.'}
    (out / 'execution-status.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    return code


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--spacing-m', type=int, choices=[120, 240], default=240)
    p.add_argument('--deadline-seconds', type=int, default=1200)
    args = p.parse_args()
    if not 1 <= args.deadline_seconds <= 1800:
        p.error('deadline must be 1..1800 seconds')
    sys.exit(supervise([sys.executable, '-u', 'scripts/prepare_data.py', '--spacing-m', str(args.spacing_m)],
                      deadline_seconds=args.deadline_seconds))
