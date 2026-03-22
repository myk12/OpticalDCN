#!/usr/bin/env python3
# Example Usage:
#   python plot_meas_phase_paper.py \
#     --inputs results/vartest_incast_0.csv results/vartest_incast_1.csv results/vartest_incast_2.csv results/vartest_incast_3.csv results/vartest_incast_4.csv \
#     --outdir paper_plots \
#     --low-incast 0 \
#     --high-incast 4
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


def ecdf(values: np.ndarray):
    x = np.sort(values)
    y = np.arange(1, len(x) + 1) / len(x)
    return x, y


def parse_incast_from_name(path: Path) -> int:
    m = re.search(r"incast_(\d+)", path.name)
    if not m:
        raise ValueError(f"Cannot parse incast from filename: {path}")
    return int(m.group(1))


def load_one(csv_path: Path):
    df = pd.read_csv(csv_path)

    print(df["received"].dtype)
    print(df["received"].value_counts())

    total_count = len(df)
    recv_df = df[df["received"] == True].copy()
    recv_count = len(recv_df)
    loss_rate = 1.0 - (recv_count / total_count if total_count > 0 else 0.0)

    # Aggregate into 4 phases on received packets only
    recv_df["Kernel"] = recv_df["tx_kernel_ns"] + recv_df["rx_kernel_ns"]
    recv_df["PCIe/DMA"] = recv_df["tx_pcie_ns"] + recv_df["rx_pcie_ns"]
    recv_df["NIC"] = recv_df["tx_nic_ns"] + recv_df["rx_nic_ns"]
    recv_df["Switch"] = recv_df["switch_ns"]

    stats = {
        "total_count": total_count,
        "recv_count": recv_count,
        "loss_rate": loss_rate,
    }

    return recv_df, stats


def build_all_data(paths):
    all_rows = []
    dfs = {}
    stats_by_incast = {}

    for p in paths:
        p = Path(p)
        incast = parse_incast_from_name(p)
        df, stats = load_one(p)

        dfs[incast] = df
        stats_by_incast[incast] = stats

        for phase in ["Kernel", "PCIe/DMA", "NIC", "Switch"]:
            vals = df[phase].dropna().to_numpy()
            all_rows.append({
                "incast": incast,
                "Phase": phase,
                "p50_ns": np.percentile(vals, 50),
                "p99_ns": np.percentile(vals, 99),
            })

    summary_df = pd.DataFrame(all_rows)
    summary_df = summary_df.sort_values(["Phase", "incast"]).reset_index(drop=True)
    return dfs, stats_by_incast, summary_df


def plot_breakdown_bar(summary_df: pd.DataFrame, stats_by_incast: dict, out_path: Path):
    plot_df = summary_df.copy()
    sns.set_theme(style="whitegrid", context="paper")

    phase_order = ["Kernel", "PCIe/DMA", "NIC", "Switch"]

    # Build incast -> legend label mapping
    incast_values = sorted(plot_df["incast"].unique())
    label_map = {}
    for incast in incast_values:
        loss_rate_pct = stats_by_incast[incast]["loss_rate"] * 100.0
        label_map[incast] = f"{incast} / {loss_rate_pct:.2f}%"

    plot_df["legend_label"] = plot_df["incast"].map(label_map)
    hue_order = [label_map[i] for i in incast_values]

    # convert ns to us for better readability
    plot_df["p50_ns"] = plot_df["p50_ns"] / 1000.0
    plot_df["p99_ns"] = plot_df["p99_ns"] / 1000.0

    plt.figure(figsize=(4, 3))
    ax = sns.barplot(
        data=plot_df,
        x="Phase",
        y="p99_ns",
        hue="legend_label",
        order=phase_order,
        hue_order=hue_order,
        errorbar=None
    )
    ax.set_yscale("log")
    ax.set_ylabel("99th percentile latency (us)")
    ax.set_xlabel("")
    ax.grid(True, axis="y")
    ax.legend(title="Incast / Loss Rate", ncol=2, frameon=True)

    for spine in ax.spines.values():
        spine.set_linewidth(1.4)
    ax.tick_params(axis="both", which="both", width=1.2)

    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def plot_phase_ccdf_2x2(
    dfs: dict,
    out_path: Path,
    low_incast=0,
    high_incast=4
):
    if low_incast not in dfs:
        raise ValueError(f"incast={low_incast} not found in provided inputs")
    if high_incast not in dfs:
        raise ValueError(f"incast={high_incast} not found in provided inputs")

    df0 = dfs[low_incast].copy()
    df1 = dfs[high_incast].copy()

    phase_order = ["Kernel", "PCIe/DMA", "NIC", "Switch"]

    fig, axes = plt.subplots(2, 2, figsize=(4, 3), sharey=True)
    axes = axes.flatten()

    palette = sns.color_palette("deep", 2)

    # convert ns to us for better readability
    for df in [df0, df1]:
        for phase in phase_order:
            df[phase] = df[phase] / 1000.0

    for ax, phase in zip(axes, phase_order):
        vals0 = df0[phase].dropna().to_numpy()
        vals1 = df1[phase].dropna().to_numpy()

        x0, y0 = ecdf(vals0)
        x1, y1 = ecdf(vals1)

        ax.plot(x0, 1.0 - y0, label=f"Incast={low_incast}", color=palette[0], linewidth=2)
        ax.plot(x1, 1.0 - y1, label=f"Incast={high_incast}", color=palette[1], linewidth=2)

        ax.set_yscale("log")
        ax.set_title(phase, fontsize=10)
        ax.grid(False)

        for spine in ax.spines.values():
            spine.set_linewidth(1.4)
        ax.tick_params(axis="both", which="both", width=1.2, labelsize=9)

    axes[0].set_ylabel("CCDF")
    axes[2].set_ylabel("CCDF")
    axes[2].set_xlabel("Latency (us)")
    axes[3].set_xlabel("Latency (us)")
    axes[0].legend(loc="upper right", frameon=True, fontsize=7)

    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def save_table(summary_df: pd.DataFrame, out_path: Path):
    pivot = summary_df.pivot(index="Phase", columns="incast", values=["p50_ns", "p99_ns"])
    pivot.to_csv(out_path)


def print_table(summary_df: pd.DataFrame):
    print(summary_df.to_string(index=False))


def print_loss_summary(stats_by_incast: dict):
    print("=== Loss summary ===")
    rows = []
    for incast in sorted(stats_by_incast.keys()):
        s = stats_by_incast[incast]
        rows.append({
            "incast": incast,
            "total_count": s["total_count"],
            "recv_count": s["recv_count"],
            "loss_rate": s["loss_rate"],
        })
    print(pd.DataFrame(rows).to_string(index=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="input CSV files, e.g. results/vartest_incast_0.csv results/vartest_incast_1.csv ..."
    )
    parser.add_argument("--outdir", default="paper_plots", help="output directory")
    parser.add_argument("--low-incast", type=int, default=0, help="low incast used in Figure 2")
    parser.add_argument("--high-incast", type=int, default=4, help="high incast used in Figure 2")
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
        "legend.fontsize": 9,
        "legend.title_fontsize": 9,
        "axes.linewidth": 1.4,
    })

    dfs, stats_by_incast, summary_df = build_all_data(args.inputs)

    save_table(summary_df, outdir / "phase_breakdown_table.csv")
    print_table(summary_df)
    print_loss_summary(stats_by_incast)

    plot_breakdown_bar(
        summary_df,
        stats_by_incast,
        outdir / "figure1_phase_breakdown_bar.pdf"
    )

    plot_phase_ccdf_2x2(
        dfs,
        outdir / "figure2_phase_ccdf_2x2.pdf",
        low_incast=args.low_incast,
        high_incast=args.high_incast
    )

    print(f"plots written to {outdir}")


if __name__ == "__main__":
    main()