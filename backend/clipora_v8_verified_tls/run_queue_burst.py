"""Independent-process admission bursts against the real SQLite queue.

This checks queue transactions, not video throughput. No Docker/network needed.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
from clipora_v8_browser_real_mp4.job_store import JobStore

PRODUCER = '''
import sys,time
sys.path.insert(0,sys.argv[1])
from clipora_v8_browser_real_mp4.job_store import JobStore,QueueFull
store=JobStore(sys.argv[2])
while time.time()<float(sys.argv[3]):time.sleep(.005)
try:
    store.create()
    print("accepted")
except QueueFull:
    print("full")
'''


def main():
    rounds = []
    with tempfile.TemporaryDirectory(prefix='clipora-queue-burst-') as tmp:
        store = JobStore(Path(tmp) / 'state')
        for number in range(4):
            start = time.time() + 1
            children = [subprocess.Popen([sys.executable, '-B', '-c', PRODUCER,
                         str(BACKEND), str(store.directory), str(start)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(12)]
            try:
                results = []
                for child in children:
                    out, err = child.communicate(timeout=15)
                    assert child.returncode == 0, err
                    results.append(out.strip())
                assert results.count('accepted') == 4 and results.count('full') == 8, results
                assert len(store.list('queued')) == 4 and not store.list('processing')
                # Drain only after producers finish; no throughput claim.
                for _ in range(4):
                    job = store.claim('burst-drain')
                    assert job and store.finish(job['job_id'], 'burst-drain', True, 'Test drain')
                rounds.append({'round': number + 1, 'producers': 12, 'accepted': 4, 'queue_full': 8})
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill(); child.wait(timeout=5)
        assert len(store.list('completed')) == 16
    report = {'scope': 'SQLite admission concurrency; no video throughput measurement', 'rounds': rounds}
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: 48 process submissions, queue limit 4 enforced in every burst')


if __name__ == '__main__':
    main()
