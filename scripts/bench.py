"""Tiny load generator for the redirect hot path (stdlib only).

Usage: python scripts/bench.py --key usk_... --threads 16 --seconds 10
Creates one link, then hammers GET /{code} (no redirect following) and reports
throughput and latency percentiles. Numbers depend heavily on the machine and
on a single Python client process being the bottleneck - treat them as a
sanity check, not a capacity claim.
"""
import argparse
import http.client
import json
import statistics
import threading
import time
from urllib.parse import urlsplit


def main() -> None:
    """Create a link, load-test its redirect with threads, and print throughput, latency and clicks."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--key", required=True)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--seconds", type=float, default=10)
    args = ap.parse_args()
    u = urlsplit(args.base)

    conn = http.client.HTTPConnection(u.hostname, u.port)
    conn.request("POST", "/api/v1/links", json.dumps({"url": "https://example.com/bench"}),
                 {"Content-Type": "application/json", "X-API-Key": args.key})
    code = json.loads(conn.getresponse().read())["short_code"]

    latencies: list[float] = []
    errors = 0
    lock = threading.Lock()
    stop = time.perf_counter() + args.seconds

    def worker():
        """Issue redirect requests until the deadline, then merge latencies and error counts."""
        nonlocal errors
        c = http.client.HTTPConnection(u.hostname, u.port)
        local, bad = [], 0
        while time.perf_counter() < stop:
            t = time.perf_counter()
            c.request("GET", f"/{code}", headers={"User-Agent": "bench/1.0"})
            r = c.getresponse()
            r.read()
            local.append(time.perf_counter() - t)
            bad += r.status != 302
        with lock:
            latencies.extend(local)
            errors += bad

    threads = [threading.Thread(target=worker) for _ in range(args.threads)]
    start = time.perf_counter()
    [t.start() for t in threads]
    [t.join() for t in threads]
    elapsed = time.perf_counter() - start

    latencies.sort()
    pct = lambda p: latencies[min(len(latencies) - 1, int(len(latencies) * p))] * 1000
    print(f"requests={len(latencies)} errors={errors} rps={len(latencies) / elapsed:.0f}")
    print(f"latency ms: mean={statistics.mean(latencies) * 1000:.2f} p50={pct(.5):.2f} p95={pct(.95):.2f} p99={pct(.99):.2f}")
    time.sleep(1.5)  # let the async click recorder drain
    conn = http.client.HTTPConnection(u.hostname, u.port)  # the first one idled out during the run
    conn.request("GET", f"/api/v1/links/{code}", headers={"X-API-Key": args.key})
    print("recorded clicks:", json.loads(conn.getresponse().read())["click_count"])


if __name__ == "__main__":
    main()
