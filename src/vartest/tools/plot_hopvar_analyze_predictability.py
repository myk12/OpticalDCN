#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


TS_COLS = [f"ts{i}" for i in range(10)]


def fit_line(x: np.ndarray, y: np.ndarray):
    coeff = np.polyfit(x, y, 1)
    a, b = coeff[0], coeff[1]
    y_hat = a * x + b
    resid = y - y_hat

    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    residual_std = np.std(resid, ddof=1) if len(resid) > 1 else 0.0

    return a, b, r2, residual_std, y_hat


def parse_payload_size(path: Path) -> int:
    m = re.search(r"(\d+)\s*[Bb]?", path.stem)
    if not m:
        raise ValueError(
            f"Cannot parse payload size from filename: {path.name}. "
            f"Please use names like hopvar_recv_1400B.csv"
        )
    return int(m.group(1))


def load_one_packet_csv(csv_path: Path, payload_size: Optional[int] = None) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    required = ["req_id"] + TS_COLS
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in {csv_path}")

    for c in TS_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if payload_size is None:
        if "payload_len" in df.columns:
            uniq = sorted(pd.to_numeric(df["payload_len"], errors="coerce").dropna().unique())
            if len(uniq) == 1:
                payload_size = int(uniq[0])
            else:
                payload_size = parse_payload_size(csv_path)
        else:
            payload_size = parse_payload_size(csv_path)

    df["Payload Size (bytes)"] = payload_size
    return df


def build_long_latency_df(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in df.iterrows():
        ts0 = row["ts0"]
        if pd.isna(ts0) or ts0 == 0:
            continue

        for hop in range(1, 10):
            tsk = row[f"ts{hop}"]
            if pd.isna(tsk) or tsk == 0:
                continue

            latency_ns = float(tsk - ts0)
            rows.append({
                "req_id": int(row["req_id"]),
                "Payload Size (bytes)": int(row["Payload Size (bytes)"]),
                "Hop Count": hop,
                "Latency (ns)": latency_ns,
            })

    long_df = pd.DataFrame(rows)
    if long_df.empty:
        raise ValueError("No valid hop latency samples could be extracted from the input CSVs")

    return long_df


def build_summary_df(long_df: pd.DataFrame) -> pd.DataFrame:
    summary_rows = []

    grouped = long_df.groupby(["Payload Size (bytes)", "Hop Count"])
    for (payload, hop), g in grouped:
        vals = g["Latency (ns)"].to_numpy()

        mean = np.mean(vals)
        std = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
        cv = std / mean if mean != 0 else np.nan

        summary_rows.append({
            "Payload Size (bytes)": payload,
            "Hop Count": hop,
            "Latency Min (ns)": np.min(vals),
            "Latency 25th Percentile (ns)": np.percentile(vals, 25),
            "Latency Median (ns)": np.percentile(vals, 50),
            "Latency 75th Percentile (ns)": np.percentile(vals, 75),
            "Latency Max (ns)": np.max(vals),
            "Latency Mean (ns)": mean,
            "Latency Std (ns)": std,
            "Latency CV": cv,
            "Sample Count": len(vals),
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values(["Payload Size (bytes)", "Hop Count"]).reset_index(drop=True)
    return summary_df


def build_fit_table(long_df: pd.DataFrame) -> pd.DataFrame:
    fit_rows = []

    payloads = sorted(long_df["Payload Size (bytes)"].unique())
    for payload in payloads:
        sub = long_df[long_df["Payload Size (bytes)"] == payload].copy()
        x = sub["Hop Count"].to_numpy(dtype=float)
        y = sub["Latency (ns)"].to_numpy(dtype=float)

        a, b, r2, residual_std, _ = fit_line(x, y)

        fit_rows.append({
            "Payload Size (bytes)": payload,
            "Slope (ns/hop)": a,
            "Intercept (ns)": b,
            "R^2": r2,
            "Residual Std (ns)": residual_std,
            "Total Samples": len(sub),
        })

    fit_df = pd.DataFrame(fit_rows)
    fit_df = fit_df.sort_values("Payload Size (bytes)").reset_index(drop=True)
    return fit_df


def plot_mean_latency_vs_hop(summary_df: pd.DataFrame, out_path: Path):
    fig, ax = plt.subplots(figsize=(6.2, 4.0))

    sns.lineplot(
        data=summary_df,
        x="Hop Count",
        y="Latency Mean (ns)",
        hue="Payload Size (bytes)",
        marker="o",
        linewidth=2.2,
        markersize=6,
        ax=ax,
    )

    ax.set_xlabel("Hop Count")
    ax.set_ylabel("Mean Latency (ns)")
    ax.set_title("Mean packet latency vs. hop count")
    ax.grid(True, alpha=0.25)
    ax.legend(title="Payload Size", ncol=2, frameon=True)

    for spine in ax.spines.values():
        spine.set_linewidth(1.4)
    ax.tick_params(axis="both", which="both", width=1.2)

    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def plot_fit_overlay(long_df: pd.DataFrame, out_path: Path):
    payloads = sorted(long_df["Payload Size (bytes)"].unique())
    palette = sns.color_palette("deep", len(payloads))

    fig, ax = plt.subplots(figsize=(6.2, 4.0))

    for color, payload in zip(palette, payloads):
        sub = long_df[long_df["Payload Size (bytes)"] == payload].copy()
        x = sub["Hop Count"].to_numpy(dtype=float)
        y = sub["Latency (ns)"].to_numpy(dtype=float)

        a, b, r2, residual_std, _ = fit_line(x, y)

        x_line = np.array(sorted(np.unique(x)))
        y_line = a * x_line + b

        mean_points = (
            sub.groupby("Hop Count")["Latency (ns)"]
            .mean()
            .reset_index()
        )

        ax.plot(
            mean_points["Hop Count"],
            mean_points["Latency (ns)"],
            marker="o",
            linewidth=1.8,
            markersize=5,
            color=color,
            label=f"{payload} B"
        )
        ax.plot(
            x_line,
            y_line,
            linestyle="--",
            linewidth=1.6,
            color=color,
            alpha=0.9
        )

    ax.set_xlabel("Hop Count")
    ax.set_ylabel("Latency (ns)")
    ax.set_title("Linear fit of packet latency vs. hop count")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=True, fontsize=9, ncol=2)

    for spine in ax.spines.values():
        spine.set_linewidth(1.4)
    ax.tick_params(axis="both", which="both", width=1.2)

    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def print_summary(summary_df: pd.DataFrame, fit_df: pd.DataFrame):
    print("=== Packet-level summary preview ===")
    print(summary_df.head(12).to_string(index=False))
    print()
    print("=== Predictability / stability summary ===")
    print(fit_df.to_string(index=False))
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="multiple hopvar_recv csv files, e.g. results/hopvar/hopvar_recv_128B.csv ...",
    )
    parser.add_argument(
        "--plot-payloads",
        nargs="*",
        type=int,
        default=None,
        help="payload sizes to KEEP in plots only, e.g. --plot-payloads 128 512 1400",
    )
    parser.add_argument(
        "--table-payloads",
        nargs="*",
        type=int,
        default=None,
        help="payload sizes to KEEP in tables only; default is all payloads",
    )
    parser.add_argument("--outdir", default="hop_packet_predictability")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update({
        "font.size": 12,
        "axes.titlesize": 13,
        "axes.labelsize": 13,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 10,
        "legend.title_fontsize": 10,
        "axes.linewidth": 1.4,
    })

    raw_dfs = []
    for path_str in args.inputs:
        path = Path(path_str)
        payload_size = parse_payload_size(path)
        df = load_one_packet_csv(path, payload_size=payload_size)
        raw_dfs.append(df)

    raw_df = pd.concat(raw_dfs, ignore_index=True)
    long_df_all = build_long_latency_df(raw_df)

    # table data
    if args.table_payloads is not None and len(args.table_payloads) > 0:
        keep_table = set(args.table_payloads)
        long_df_table = long_df_all[long_df_all["Payload Size (bytes)"].isin(keep_table)].copy()
    else:
        long_df_table = long_df_all.copy()

    # plot data
    if args.plot_payloads is not None and len(args.plot_payloads) > 0:
        keep_plot = set(args.plot_payloads)
        long_df_plot = long_df_all[long_df_all["Payload Size (bytes)"].isin(keep_plot)].copy()
    else:
        long_df_plot = long_df_all.copy()

    summary_df_plot = build_summary_df(long_df_plot)
    fit_df_table = build_fit_table(long_df_table)

    print_summary(summary_df_plot, fit_df_table)

    raw_df.to_csv(outdir / "processed_raw_packets_all.csv", index=False)
    long_df_all.to_csv(outdir / "packet_latency_long_all.csv", index=False)
    long_df_plot.to_csv(outdir / "packet_latency_long_plot.csv", index=False)
    long_df_table.to_csv(outdir / "packet_latency_long_table.csv", index=False)
    summary_df_plot.to_csv(outdir / "packet_latency_summary_plot.csv", index=False)
    fit_df_table.to_csv(outdir / "predictability_stability_table.csv", index=False)

    plot_mean_latency_vs_hop(summary_df_plot, outdir / "mean_latency_vs_hop.png")
    plot_fit_overlay(long_df_plot, outdir / "latency_linear_fit_overlay.png")

    print(f"wrote {outdir / 'processed_raw_packets_all.csv'}")
    print(f"wrote {outdir / 'packet_latency_long_all.csv'}")
    print(f"wrote {outdir / 'packet_latency_long_plot.csv'}")
    print(f"wrote {outdir / 'packet_latency_long_table.csv'}")
    print(f"wrote {outdir / 'packet_latency_summary_plot.csv'}")
    print(f"wrote {outdir / 'predictability_stability_table.csv'}")
    print(f"wrote {outdir / 'mean_latency_vs_hop.png'}")
    print(f"wrote {outdir / 'latency_linear_fit_overlay.png'}")


if __name__ == "__main__":
    main()
