#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
from typing import Optional
from cycler import cycler

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from loguru import logger

MY_COLORS = ['#0C4C8A', '#CE5C00', '#1D8E3E', '#75507B', '#555753']

import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

class AcademicStyleManager:
    def __init__(self):
        # Nordic Sci-Fi 高级感色卡
        self.colors =['#0C4C8A', '#CE5C00', '#1D8E3E', '#75507B', '#555753'] 
        self.markers = ['o', 's', '^', 'D']
        #self.font_family = font_family
        self._apply_global_settings()

    def _apply_global_settings(self):
        """初始化全局参数，强制所有图表拥有统一的黑色加粗全封闭边框"""
        plt.rcParams.update({
            #"font.family": self.font_family,
            #"font.serif": ["Times New Roman", "DejaVu Serif"],
            # --- 核心：全边框控制 ---
            "axes.linewidth": 1.2,          # 稍微加粗，让边框更有质感
            "axes.edgecolor": "black",      # 确保是纯黑
            "axes.spines.top": True,        # 强制保留顶边
            "axes.spines.right": True,      # 强制保留右边
            
            "patch.linewidth": 0.8,         # 柱状图本身的边框
            "xtick.direction": "in",        # 刻度向内是全边框标配
            "ytick.direction": "in",
            "xtick.top": True,              # 顶部也显示刻度（可选，更硬核）
            "ytick.right": True,            # 右侧也显示刻度
            
            "grid.linestyle": "--",
            "grid.alpha": 0.3,
            "figure.dpi": 300,
            "savefig.bbox": "tight",
            "legend.frameon": True,         # 这种风格通常配有边框的图例
            "legend.edgecolor": "black",
        })

    def get_palette(self, levels):
        return dict(zip(sorted(levels), self.colors[:len(levels)]))

    def get_markers(self, levels):
        return dict(zip(sorted(levels), self.markers[:len(levels)]))

    def finalize_axes(self, ax, title=None, xlabel=None, ylabel=None, is_log=False):
        """处理标签和坐标轴，不再执行 despine"""
        if title: ax.set_title(title, fontweight='bold', pad=12)
        if xlabel: ax.set_xlabel(xlabel)
        if ylabel: ax.set_ylabel(ylabel)
        
        # 确保四周的线条都是黑色的（防止被 Seaborn 默认主题覆盖）
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor('black')
        
        if is_log:
            ax.set_yscale('log')
            from matplotlib.ticker import LogFormatterMathtext
            ax.yaxis.set_major_formatter(LogFormatterMathtext())
            
        return ax

# Example Usage:
#   python plot_hopvar_analyze_predictability.py \
#     --inputs results/hopvar/hopvar_pktsize_128B.csv results/hopvar/hopvar_pktsize_512B.csv results/hopvar/hopvar_pktsize_1400B.csv \
#     --outdir results/hopvar/predictability_analysis \
#     --plot-payloads 128 512 1400 \
#     --table-payloads 128 512 1400

TS_COLS = [f"ts{i}" for i in range(10)]

def apply_my_style():
    plt.rcParams['axes.prop_cycle'] = (
        cycler(color=MY_COLORS)
    )

def fit_line(x: np.ndarray, y: np.ndarray):
    logger.debug(f"Fitting line to data: x={x}, y={y}")
    # simple linear regression using numpy polyfit, which is sufficient for our needs and avoids extra dependencies
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
    logger.info(f"Loading CSV file: {csv_path}")
    df = pd.read_csv(csv_path)

    required = ["req_id"] + TS_COLS
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in {csv_path}")

    for c in TS_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # check if payload size matched the filename
    if payload_size is not None:
        if "payload_len" in df.columns:
            unique_payloads = df["payload_len"].dropna().unique()
            if len(unique_payloads) > 1:
                raise ValueError(f"Multiple payload sizes found in {csv_path}: {unique_payloads}")
            elif len(unique_payloads) == 1 and unique_payloads[0] != payload_size:
                raise ValueError(
                    f"Payload size in {csv_path} ({unique_payloads[0]}) does not match expected {payload_size}"
                )
        else:
            logger.warning(f"No 'payload_len' column in {csv_path}, using filename payload size {payload_size}")

    df["Payload Size (bytes)"] = payload_size
    return df

def build_long_latency_df(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Transforming raw packet timestamp data into long format with latency calculations...")
    # data cleaning: only keep rows where ts0 is valid, since it's the baseline timestamp for latency calculation
    df = df[df["ts0"].notna() & (df["ts0"] != 0)].copy()

    # Reshape from wide to long format for easier analysis and plotting
    long_df = df.melt(
        id_vars=["req_id", "Payload Size (bytes)", "ts0"],
        value_vars=[f"ts{i}" for i in range(1, 10)],
        var_name="Hop Count",
        value_name="tsk"
    )

    # Clean the data: only keep rows where tsk is valid, since we need it to calculate latency
    long_df = long_df[long_df["tsk"].notna() & (long_df["tsk"] != 0)].copy()
    long_df["Latency (ns)"] = (long_df["tsk"] - long_df["ts0"]).astype(int)
    
    # Clean the Hop Count column: 'ts1' -> 1
    long_df["Hop Count"] = long_df["Hop Count"].str.extract('(\d+)').astype(int)

    return long_df[["req_id", "Payload Size (bytes)", "Hop Count", "Latency (ns)"]]


def build_summary_df(long_df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Building summary DataFrame with latency statistics...")
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
    logger.info("Fitting linear models to analyze predictability...")
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
    logger.info("Plotting mean latency vs. hop count...")
    fig, ax = plt.subplots(figsize=(4, 3))
    
    sns.lineplot(
        data=summary_df,
        x="Hop Count",
        y="Latency Mean (ns)",
        hue="Payload Size (bytes)",
        style="Payload Size (bytes)", 
        markers=True,
        dashes=False,
        palette=MY_COLORS,
        linewidth=1.8,
        markersize=8,
        ax=ax
    )
    
    ax.set_xlabel("Hop Count (Number of Switches)", fontsize=11)
    ax.set_ylabel("Mean Latency (ns)", fontsize=11)
    
    ax.set_xticks(range(1, 8))
    
    ax.legend(title="Payload (Bytes)", frameon=True, loc='upper left')

    for spine in ax.spines.values():
        spine.set_linewidth(1.4)
    ax.tick_params(axis="both", which="both")

    style_manager = AcademicStyleManager()
    style_manager.finalize_axes(ax)

    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()


def plot_fit_overlay(long_df: pd.DataFrame, out_path: Path):
    logger.info("Plotting latency vs. hop count with linear fit overlay...")
    payloads = sorted(long_df["Payload Size (bytes)"].unique())
    palette = sns.color_palette("deep", len(payloads))

    fig, ax = plt.subplots(figsize=(4, 3))

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
    ax.grid(True)
    ax.legend(frameon=True, fontsize=9, ncol=2)

    for spine in ax.spines.values():
        spine.set_linewidth(1.4)
    ax.tick_params(axis="both", which="both", width=1.2)

    style_manager.finalize_axes(ax)

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
    parser.add_argument("--outdir", default="plots/hopvar", help="output directory for tables and plots")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Load and process all input CSV files
    logger.info(f"Loading data from {len(args.inputs)} input CSV files...")
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

    #raw_df.to_csv(outdir / "processed_raw_packets_all.csv", index=False)
    #long_df_all.to_csv(outdir / "packet_latency_long_all.csv", index=False)
    #long_df_plot.to_csv(outdir / "packet_latency_long_plot.csv", index=False)
    #long_df_table.to_csv(outdir / "packet_latency_long_table.csv", index=False)
    #summary_df_plot.to_csv(outdir / "packet_latency_summary_plot.csv", index=False)
    fit_df_table.to_csv(outdir / "predictability_stability_table.csv", index=False)

    plot_mean_latency_vs_hop(summary_df_plot, outdir / "mean_latency_vs_hop.pdf")
    #plot_fit_overlay(long_df_plot, outdir / "latency_linear_fit_overlay.pdf")

    #logger.info(f"wrote {outdir / 'packet_latency_long_plot.csv'}")
    #logger.info(f"wrote {outdir / 'packet_latency_long_table.csv'}")
    #logger.info(f"wrote {outdir / 'packet_latency_summary_plot.csv'}")
    #logger.info(f"wrote {outdir / 'mean_latency_vs_hop.pdf'}")
    #logger.info(f"wrote {outdir / 'latency_linear_fit_overlay.pdf'}")
    logger.info(f"wrote {outdir / 'predictability_stability_table.csv'}")


if __name__ == "__main__":
    main()
