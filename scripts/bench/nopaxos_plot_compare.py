#!/usr/bin/env python3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

HOST_CSV = "summary_host_sequencer.csv"
TOFINO_CSV = "summary_tofino_sequencer.csv"

OUT_THROUGHPUT = "throughput_compare.png"
OUT_CDF = "latency_cdf_compare.png"

def load_and_norm(path: str, label: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    # normalize column names (defensive)
    df.columns = [c.strip() for c in df.columns]

    required = ["threads", "iops", "median_ns", "p90_ns", "p95_ns", "p99_ns", "max_ns"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path} missing columns: {missing}")

    df = df.copy()
    df["scheme"] = label
    df["threads"] = df["threads"].astype(int)

    # Convert to microseconds for plots (float)
    for c in ["median_ns", "p90_ns", "p95_ns", "p99_ns", "max_ns"]:
        df[c.replace("_ns", "_us")] = df[c].astype(float) / 1000.0

    # IOPS is already ops/s; for label like KOps/s
    df["kops"] = df["iops"].astype(float) / 1000.0

    return df

def common_threads(df_a: pd.DataFrame, df_b: pd.DataFrame):
    ta = set(df_a["threads"].unique())
    tb = set(df_b["threads"].unique())
    return sorted(list(ta & tb))

def plot_throughput_bar(host: pd.DataFrame, tofino: pd.DataFrame, threads_common):
    h = host[host["threads"].isin(threads_common)].sort_values("threads")
    t = tofino[tofino["threads"].isin(threads_common)].sort_values("threads")

    # Align by threads
    h = h.set_index("threads").loc[threads_common].reset_index()
    t = t.set_index("threads").loc[threads_common].reset_index()

    x = np.arange(len(threads_common))
    width = 0.38

    plt.figure(figsize=(4, 3))
    b1 = plt.bar(x - width/2, h["kops"], width, label="Host sequencer")
    b2 = plt.bar(x + width/2, t["kops"], width, label="Tofino sequencer")

    plt.xticks(x, [str(v) for v in threads_common])
    plt.xlabel("Threads")
    plt.ylabel("IOPS (KOps/s)")
    plt.title("NOPaxos Throughput vs Threads (Host vs Tofino)")
    plt.grid(axis="y", linestyle=":", linewidth=1)
    plt.legend()

    # annotate bars
    def annotate(bars):
        for bar in bars:
            y = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2, y, f"{y:.0f}",
                     ha="center", va="bottom", fontsize=12)
    annotate(b1)
    annotate(b2)

    plt.tight_layout()
    plt.savefig(OUT_THROUGHPUT, dpi=200)
    plt.close()
    print(f"[OK] wrote {OUT_THROUGHPUT}")

def approx_cdf_points(row):
    """
    Build an approximate CDF using quantile summary:
      (x0,0), (p50,0.5), (p90,0.9), (p95,0.95), (p99,0.99), (max,1.0)
    x0 is a small positive value to allow log-scale.
    """
    p50 = row["median_us"]
    p90 = row["p90_us"]
    p95 = row["p95_us"]
    p99 = row["p99_us"]
    pmax = row["max_us"]

    # pick a positive start point for log axis
    xmin = min(p50, p90, p95, p99, pmax)
    x0 = max(xmin * 0.8, 1e-3)  # >= 1 ns in us scale is 1e-3 us

    xs = np.array([x0, p50, p90, p95, p99, pmax], dtype=float)
    ys = np.array([0.0, 0.5, 0.9, 0.95, 0.99, 1.0], dtype=float)

    # ensure non-decreasing xs (just in case of weird logs)
    xs = np.maximum.accumulate(xs)
    return xs, ys

def plot_latency_cdf(host: pd.DataFrame, tofino: pd.DataFrame, threads_common):
    # We plot per-thread, with same thread style: host dashed, tofino solid.
    plt.figure(figsize=(4, 3))

    # give each thread a stable color by plotting tofino first then host with same color
    for thr in threads_common:
        trow = tofino[tofino["threads"] == thr].iloc[0]
        hrow = host[host["threads"] == thr].iloc[0]

        tx, ty = approx_cdf_points(trow)
        hx, hy = approx_cdf_points(hrow)

        # plot tofino (solid) first, capture its line color
        line_t, = plt.step(tx, ty, where="post", linewidth=2, label=f"t={thr} Tofino")
        color = line_t.get_color()

        # host: dashed, same color
        plt.step(hx, hy, where="post", linewidth=2, linestyle="--", color=color, label=f"t={thr} Host")

    plt.xscale("log")
    plt.xlabel("Latency (us) [log scale]")
    plt.ylabel("CDF")
    plt.title("NOPaxos Approx. Latency CDF (Host vs Tofino)")
    plt.ylim(0, 1.01)
    plt.grid(True, which="both", linestyle=":", linewidth=1)

    # Make legend less insane
    plt.legend(ncol=2, framealpha=0.9)

    plt.tight_layout()
    plt.savefig(OUT_CDF, dpi=200)
    plt.close()
    print(f"[OK] wrote {OUT_CDF}")

def main():
    host = load_and_norm(HOST_CSV, "host")
    tofino = load_and_norm(TOFINO_CSV, "tofino")

    threads_common = common_threads(host, tofino)
    if not threads_common:
        raise RuntimeError("No common thread counts between the two CSVs.")

    print(f"[INFO] common threads = {threads_common}")

    plot_throughput_bar(host, tofino, threads_common)
    plot_latency_cdf(host, tofino, threads_common)

if __name__ == "__main__":
    main()