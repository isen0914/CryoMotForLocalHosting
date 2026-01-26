"""Send multiple POST requests to /detect/ with the sample zip and print timings.
Requires `requests` package.
"""
import time
from pathlib import Path
import requests


def run_tests(url='http://127.0.0.1:8000/detect/', zip_path=Path('..') / 'tools' / 'sample.zip', runs=3):
    zip_path = Path(zip_path)
    if not zip_path.exists():
        print('Sample zip not found:', zip_path)
        return

    for i in range(1, runs+1):
        with open(zip_path, 'rb') as f:
            files = {'zip_file': (zip_path.name, f, 'application/zip')}
            t0 = time.perf_counter()
            try:
                r = requests.post(url, files=files, timeout=120)
            except Exception as e:
                print(f'Run {i}: request failed: {e}')
                continue
            t1 = time.perf_counter()
            ms = (t1 - t0) * 1000.0
            print(f'Run {i}: {ms:.0f} ms  status={r.status_code}  len={len(r.content) if r.content is not None else 0}')


if __name__ == '__main__':
    run_tests()
