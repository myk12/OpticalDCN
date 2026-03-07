#!/usr/bin/env python3
import sys
import argparse
import datetime as dt
import os
import re
import shlex
import subprocess
from pathlib import Path
from statistics import mean

RE_FINISH = re.compile(
    r"\* Finish\s+\(benchmark\.cc:\d+\):\s+Completed\s+(?P<n>\d+)\s+requests\s+in\s+(?P<sec>[\d.]+)\s+seconds"
)

RE_MED = re.compile(r"\* CooldownDone\s+\(benchmark\.cc:\d+\):\s+Median latency is\s+(?P<ns>\d+)\s+ns")
RE_AVG = re.compile(r"\* CooldownDone\s+\(benchmark\.cc:\d+\):\s+Average latency is\s+(?P<ns>\d+)\s+ns")
RE_P90 = re.compile(r"\* CooldownDone\s+\(benchmark\.cc:\d+\):\s+90th percentile latency is\s+(?P<ns>\d+)\s+ns")
RE_P95 = re.compile(r"\* CooldownDone\s+\(benchmark\.cc:\d+\):\s+95th percentile latency is\s+(?P<ns>\d+)\s+ns")
RE_P99 = re.compile(r"\* CooldownDone\s+\(benchmark\.cc:\d+\):\s+99th percentile latency is\s+(?P<ns>\d+)\s+ns")

# * LATENCY total: 46 us 128 us/65 us 10 ms (1000010 samples, 128 s total)
# Some builds show "ms" for max; we handle us/ms.
RE_LAT_TOTAL = re.compile(
    r"\* LATENCY total:\s+(?P<min>\d+)\s+us\s+(?P<med>\d+)\s+us/(?P<p25>\d+)\s+us\s+(?P<max_val>\d+)\s+(?P<max_unit>us|ms)\s+\((?P<samples>\d+)\s+samples,\s+(?P<total_s>\d+)\s+s\s+total\)"
)

# Histogram bucket lines:
# *     131 us |     267615 |
RE_HIST = re.compile(r"\*\s+(?P<bucket_us>\d+)\s+us\s+\|\s+(?P<count>\d+)\s+\|")

def run_cmd(cmd, timeout_s=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    out = []
    try:
        for line in p.stdout:
            out.append(line)
        rc = p.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        p.kill()
        out.append("\n[TIMEOUT]\n")
        rc = 124
    return rc, "".join(out)

def parse_log(text: str):
    finishes = []
    med, avg, p90, p95, p99 = [], [], [], [], []
    lat_total = None
    hist = {}

    for line in text.splitlines():
        m = RE_FINISH.search(line)
        if m:
            finishes.append((int(m.group("n")), float(m.group("sec"))))
            continue
        m = RE_MED.search(line)
        if m: med.append(int(m.group("ns"))); continue
        m = RE_AVG.search(line)
        if m: avg.append(int(m.group("ns"))); continue
        m = RE_P90.search(line)
        if m: p90.append(int(m.group("ns"))); continue
        m = RE_P95.search(line)
        if m: p95.append(int(m.group("ns"))); continue
        m = RE_P99.search(line)
        if m: p99.append(int(m.group("ns"))); continue

        m = RE_LAT_TOTAL.search(line)
        if m:
            max_val = int(m.group("max_val"))
            max_unit = m.group("max_unit")
            max_us = max_val if max_unit == "us" else max_val * 1000
            lat_total = {
                "min_us": int(m.group("min")),
                "med_us": int(m.group("med")),
                "p25_us": int(m.group("p25")),
                "max_us": int(max_us),
                "samples": int(m.group("samples")),
                "total_s": int(m.group("total_s")),
            }
            continue

        m = RE_HIST.search(line)
        if m:
            b = int(m.group("bucket_us"))
            c = int(m.group("count"))
            hist[b] = c
            continue

    def mean_or_none(xs):
        return int(mean(xs)) if xs else None

    # wall time: use max finish seconds (slowest thread dominates)
    wall_s = max((sec for _, sec in finishes), default=None)

    # total ops: if each thread runs n_per_thread, total_ops = threads*n_per_thread (we compute in main)
    # max latency: prefer LATENCY total max (converted to ns); else estimate from histogram max bucket.
    max_ns = None
    if lat_total and lat_total.get("max_us") is not None:
        max_ns = int(lat_total["max_us"] * 1000)
    elif hist:
        # bucket max is a lower bound, but better than nothing
        max_bucket_us = max(hist.keys())
        max_ns = int(max_bucket_us * 1000)

    return {
        "finish_list": finishes,
        "wall_s": wall_s,
        "median_ns": mean_or_none(med),
        "avg_ns": mean_or_none(avg),
        "p90_ns": mean_or_none(p90),
        "p95_ns": mean_or_none(p95),
        "p99_ns": mean_or_none(p99),
        "max_ns": max_ns,
        "lat_total": lat_total,
    }

def csv_escape(s: str) -> str:
    # wrap in double quotes and escape internal quotes
    s = s.replace('"', '""')
    return f'"{s}"'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--netns", default="ns_fpga_1_p1", help="Linux netns name, e.g. ns_fpga_1_p1")
    ap.add_argument("--client", default="third_party/NOPaxos/bench/client", help="Path to client binary")
    ap.add_argument("--conf", default="infra/host_server/nopaxos/cluster.conf", help="Cluster config path")
    ap.add_argument("--mode", default="nopaxos", help="Protocol mode")
    ap.add_argument("-n", "--n_per_thread", type=int, default=100000, help="Requests per thread")
    ap.add_argument("-t", "--threads", default="1,4,8,16,32", help="Comma-separated thread counts")
    ap.add_argument("--reps", type=int, default=1, help="Repetitions per threads setting")
    ap.add_argument("--timeout", type=float, default=None, help="Timeout seconds per run")
    ap.add_argument("--out", default=f"bench_summary_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    ap.add_argument("--logdir", default="logs", help="Optional dir to store raw logs")
    args = ap.parse_args()

    threads_list = [int(x) for x in args.threads.split(",") if x.strip()]
    out_path = Path(args.out)

    logdir = Path(args.logdir) if args.logdir else None
    if logdir:
        logdir.mkdir(parents=True, exist_ok=True)

    header = "timestamp,netns,mode,n_per_thread,threads,total_ops,wall_s,iops,median_ns,avg_ns,p90_ns,p95_ns,p99_ns,max_ns,cmd\n"
    if not out_path.exists():
        out_path.write_text(header)

    for t in threads_list:
        for rep in range(args.reps):
            ts = dt.datetime.now().isoformat(timespec="seconds")
            total_ops = t * args.n_per_thread

            cmd = [
                "sudo", "ip", "netns", "exec", args.netns,
                args.client,
                "-c", args.conf,
                "-m", args.mode,
                "-n", str(args.n_per_thread),
                "-t", str(t),
            ]
            cmd_str = " ".join(shlex.quote(x) for x in cmd)
            print(f"[RUN] {ts} t={t} rep={rep} :: {cmd_str}", flush=True)

            rc, text = run_cmd(cmd, timeout_s=args.timeout)

            if logdir:
                (logdir / f"t{t}_rep{rep}_{ts.replace(':','')}.log").write_text(text)

            parsed = parse_log(text)
            wall_s = parsed["wall_s"]
            iops = (total_ops / wall_s) if (wall_s and wall_s > 0) else None

            row = [
                ts,
                args.netns,
                args.mode,
                str(args.n_per_thread),
                str(t),
                str(total_ops),
                f"{wall_s:.6f}" if wall_s is not None else "",
                f"{iops:.3f}" if iops is not None else "",
                str(parsed["median_ns"] or ""),
                str(parsed["avg_ns"] or ""),
                str(parsed["p90_ns"] or ""),
                str(parsed["p95_ns"] or ""),
                str(parsed["p99_ns"] or ""),
                str(parsed["max_ns"] or ""),
                csv_escape(cmd_str),
            ]
            out_path.open("a").write(",".join(row) + "\n")
            out_path.open("a").flush()

            if rc != 0:
                print(f"[WARN] rc={rc} for t={t} rep={rep}", file=sys.stderr)

    print(f"[DONE] wrote {out_path}")

if __name__ == "__main__":
    main()
