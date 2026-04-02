#!/usr/bin/env python3
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


def ecdf(values: np.ndarray):
    x = np.sort(values)
    y = np.arange(1, len(x) + 1) / len(x)
    return x, y


def load_fct_long(csv_path: Path, max_hop: int) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    required_cols = ["flow_id", "flow_complete", "flow_fail"]
    for c in required_cols:
        if c not in df.columns:
            raise ValueError(f"'{c}' column not found in {csv_path}")

    # Keep only successful flows
    df = df[(df["flow_complete"] == 1) & (df["flow_fail"] == 0)].copy()

    hop_cols = [c for c in df.columns if c.startswith("fct_hop") and c.endswith("_ns")]
    if not hop_cols:
        raise ValueError(f"No fct_hop*_ns columns found in {csv_path}")

    long_rows = []
    for _, row in df.iterrows():
        flow_id = int(row["flow_id"])
        for col in hop_cols:
            hop_idx = int(col[len("fct_hop") : -len("_ns")])
            if hop_idx >= max_hop or hop_idx == 0:
                continue

            val = pd.to_numeric(row[col], errors="coerce")
            if pd.isna(val):
                continue
            val = float(val)
            if val <= 0:
                continue

            long_rows.append(
                {
                    "flow_id": flow_id,
                    "hop_idx": hop_idx,
                    "fct_ns": val,
                }
            )

    long_df = pd.DataFrame(long_rows)
    if long_df.empty:
        raise ValueError("No valid non-zero FCT samples found after filtering failed flows")

    return long_df.sort_values(["hop_idx", "flow_id"]).reset_index(drop=True)

def plot_fct_mean_deviation_cdf(long_df: pd.DataFrame, out_path: Path):
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.titlesize": 12,
            "axes.labelsize": 12,
            "axes.edgecolor": "black",
            "axes.spines.top": True,
            "axes.spines.right": True,
            "axes.spines.bottom": True,
            "axes.spines.left": True,

            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 7,
            "legend.frameon": True,
            "legend.title_fontsize": 7,
            "legend.edgecolor": "black",
            "axes.linewidth": 1.2,
            
            "grid.linestyle": "--",
            "grid.linewidth": 0.8,
            "grid.alpha": 0.3,
        }
    )

    plt.figure(figsize=(4, 3))
    palette = sns.color_palette("deep", n_colors=long_df["hop_idx"].nunique())

    for color, hop_idx in zip(palette, sorted(long_df["hop_idx"].unique())):
        vals = long_df.loc[long_df["hop_idx"] == hop_idx, "fct_ns"].to_numpy()
        mean_ns = int(round(np.mean(vals)))
        centered = vals - mean_ns
        x, y = ecdf(centered)

        plt.plot(
            x,
            y,
            linewidth=2,
            color=color,
            label=f"{hop_idx} hops ($\\mu$={mean_ns} ns)"
        )

    plt.xlabel("FCT deviation from mean (ns)")
    plt.ylabel("CDF")
    plt.grid(True, alpha=0.25)
    plt.legend(title="Hop (Mean)", frameon=True, ncol=1)
    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def drop_topk_both_sides_per_hop(long_df: pd.DataFrame, topk: int):
    kept = []
    stats = []

    for hop_idx, g in long_df.groupby("hop_idx"):
        g_sorted = g.sort_values("fct_ns", ascending=True).copy()
        before = len(g_sorted)

        if topk > 0 and len(g_sorted) > 2 * topk:
            removed_low = g_sorted.head(topk).copy()
            removed_high = g_sorted.tail(topk).copy()
            g_kept = g_sorted.iloc[topk:-topk].copy()
        else:
            removed_low = g_sorted.iloc[0:0].copy()
            removed_high = g_sorted.iloc[0:0].copy()
            g_kept = g_sorted.copy()

        after = len(g_kept)

        stats.append(
            {
                "hop_idx": hop_idx,
                "before_count": before,
                "after_count": after,
                "removed_low_count": len(removed_low),
                "removed_high_count": len(removed_high),
                "removed_low_min_ns": removed_low["fct_ns"].min() if len(removed_low) > 0 else np.nan,
                "removed_low_max_ns": removed_low["fct_ns"].max() if len(removed_low) > 0 else np.nan,
                "removed_high_min_ns": removed_high["fct_ns"].min() if len(removed_high) > 0 else np.nan,
                "removed_high_max_ns": removed_high["fct_ns"].max() if len(removed_high) > 0 else np.nan,
                "kept_min_ns": g_kept["fct_ns"].min() if len(g_kept) > 0 else np.nan,
                "kept_max_ns": g_kept["fct_ns"].max() if len(g_kept) > 0 else np.nan,
            }
        )

        kept.append(g_kept)

    filtered_df = (
        pd.concat(kept, ignore_index=True)
        .sort_values(["hop_idx", "flow_id"])
        .reset_index(drop=True)
    )
    stats_df = pd.DataFrame(stats).sort_values("hop_idx").reset_index(drop=True)
    return filtered_df, stats_df


def summarize(long_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for hop_idx, g in long_df.groupby("hop_idx"):
        vals = g["fct_ns"].to_numpy()
        rows.append(
            {
                "hop_idx": hop_idx,
                "count": len(vals),
                "mean_ns": np.mean(vals),
                "p50_ns": np.percentile(vals, 50),
                "p90_ns": np.percentile(vals, 90),
                "p99_ns": np.percentile(vals, 99),
                "std_ns": np.std(vals, ddof=1) if len(vals) > 1 else 0.0,
                "min_ns": np.min(vals),
                "max_ns": np.max(vals),
            }
        )
    return pd.DataFrame(rows).sort_values("hop_idx").reset_index(drop=True)


def plot_fct_curves(long_df: pd.DataFrame, out_path: Path, mode: str = "cdf"):
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.titlesize": 12,
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 7,
            "legend.title_fontsize": 7,
            "axes.linewidth": 1.2,
        }
    )

    plt.figure(figsize=(4.4, 3.2))
    palette = sns.color_palette("deep", n_colors=long_df["hop_idx"].nunique())

    for color, hop_idx in zip(palette, sorted(long_df["hop_idx"].unique())):
        vals = long_df.loc[long_df["hop_idx"] == hop_idx, "fct_ns"].to_numpy()
        x, y = ecdf(vals)
        if mode == "cdf":
            plt.plot(x, y, linewidth=2, color=color, label=f"{hop_idx} hops")
        elif mode == "ccdf":
            plt.plot(x, 1.0 - y, linewidth=2, color=color, label=f"{hop_idx} hops")
        else:
            raise ValueError(f"Unsupported mode: {mode}")

    plt.xlabel("Flow completion time (ns)")
    plt.ylabel(mode.upper())
    if mode == "ccdf":
        plt.yscale("log")
    plt.grid(True, alpha=0.25)
    plt.legend(title="Hop (Mean)", frameon=True, ncol=2)
    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def plot_fct_summary(summary_df: pd.DataFrame, out_path: Path):
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.titlesize": 12,
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 7,
            "legend.title_fontsize": 7,
            "axes.linewidth": 1.3,
        }
    )

    plt.figure(figsize=(4, 3))
    plt.plot(summary_df["hop_idx"], summary_df["mean_ns"], marker="o", linewidth=2, label="Mean")
    plt.plot(summary_df["hop_idx"], summary_df["p99_ns"], marker="s", linewidth=2, label="p99")
    plt.xlabel("Hop count")
    plt.ylabel("Flow completion time (ns)")
    plt.grid(True, alpha=0.25)
    plt.legend(frameon=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot hop-indexed flow completion time")
    parser.add_argument("--csv", default="fct_by_hop.csv", help="Input CSV")
    parser.add_argument("--outdir", default="plots/fct/", help="Output directory")
    parser.add_argument(
        "--mode",
        choices=["cdf", "ccdf"],
        default="cdf",
        help="Plot CDF or CCDF",
    )
    parser.add_argument(
        "--max-hop",
        type=int,
        default=8,
        help="Only keep hops in [0, max_hop-1], default: 7",
    )
    parser.add_argument(
        "--topk",
        type=int,
        default=0,
        help="Drop the smallest and largest top-k samples independently for each hop (default: 0 = no dropping)",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    raw_df = pd.read_csv(args.csv)
    total_flows = len(raw_df)
    ok_flows = len(raw_df[(raw_df["flow_complete"] == 1) & (raw_df["flow_fail"] == 0)])

    long_df_raw = load_fct_long(Path(args.csv), max_hop=args.max_hop)
    long_df, topk_stats_df = drop_topk_both_sides_per_hop(long_df_raw, topk=args.topk)
    summary_df = summarize(long_df)

    long_df_raw.to_csv(outdir / "fct_by_hop_long_raw.csv", index=False)
    long_df.to_csv(outdir / "fct_by_hop_long_filtered.csv", index=False)
    summary_df.to_csv(outdir / "fct_by_hop_summary.csv", index=False)
    topk_stats_df.to_csv(outdir / "fct_by_hop_topk_stats.csv", index=False)

    suffix = f"first_{args.max_hop}_{args.mode}_drop_both_{args.topk}"

    plot_fct_curves(
        long_df,
        outdir / f"fct_by_hop_{suffix}.pdf",
        mode=args.mode,
    )
    plot_fct_summary(
        summary_df,
        outdir / f"fct_by_hop_first_{args.max_hop}_summary.pdf",
    )
    plot_fct_mean_deviation_cdf(
        long_df,
        outdir / f"fct_by_hop_first_{args.max_hop}_mean_deviation.pdf",
    )

    print(f"Total flows in CSV: {total_flows}")
    print(f"Successful flows kept: {ok_flows}")
    print("=== Summary ===")
    print(summary_df.to_string(index=False))
    print("\n=== Top-k filtering stats ===")
    print(topk_stats_df.to_string(index=False))

    print(f"wrote {outdir / 'fct_by_hop_long_raw.csv'}")
    print(f"wrote {outdir / 'fct_by_hop_long_filtered.csv'}")
    print(f"wrote {outdir / 'fct_by_hop_summary.csv'}")
    print(f"wrote {outdir / 'fct_by_hop_topk_stats.csv'}")
    print(f"wrote {outdir / f'fct_by_hop_{suffix}.pdf'}")
    print(f"wrote {outdir / f'fct_by_hop_first_{args.max_hop}_summary.pdf'}")
    print(f"wrote {outdir / f'fct_by_hop_first_{args.max_hop}_mean_deviation.pdf'}")

if __name__ == "__main__":
    main()
