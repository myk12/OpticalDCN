#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.ticker import MultipleLocator, AutoMinorLocator

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

def ecdf(values: np.ndarray):
    x = np.sort(values)
    y = np.arange(1, len(x) + 1) / len(x)
    return x, y


def parse_payload_from_name(path: Path) -> int:
    m = re.search(r"(\d+)B", path.name)
    if not m:
        raise ValueError(f"Cannot parse payload size from filename: {path}")
    return int(m.group(1))


def load_one(csv_path: Path):
    df = pd.read_csv(csv_path).copy()

    required = [
        "payload_len",
        "fpga_tx_latency_ns",
        "wire_latency_ns",
        "fpga_rx_latency_ns",
        "full_directlink_latency_ns",
    ]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in {csv_path}")

    payload = parse_payload_from_name(csv_path)

    # keep everything in ns
    df["fpga_total_latency_ns"] = (
        df["fpga_tx_latency_ns"] + df["fpga_rx_latency_ns"]
    )
    df["wire_latency_ns"] = df["wire_latency_ns"]
    df["full_directlink_latency_ns"] = df["full_directlink_latency_ns"]

    return payload, df


def style_axis_ns(ax, major_step=None):
    if major_step is not None:
        ax.xaxis.set_major_locator(MultipleLocator(major_step))
    ax.xaxis.set_minor_locator(AutoMinorLocator(2))

    for spine in ax.spines.values():
        spine.set_linewidth(1.3)

    ax.tick_params(axis="both", which="major", width=1.2, length=4, labelsize=10)
    ax.tick_params(axis="both", which="minor", width=0.9, length=2)


def plot_full_cdf(all_data: dict, out_path: Path):
    plt.figure(figsize=(4, 3))
    ax = plt.gca()
    palette = sns.color_palette("deep", len(all_data))

    all_vals = []

    for color, payload in zip(palette, sorted(all_data.keys())):
        df = all_data[payload]
        vals = df["full_directlink_latency_ns"].dropna().to_numpy()
        all_vals.append(vals)
        x, y = ecdf(vals)
        plt.plot(x, y, linewidth=2, color=color, label=f"{payload} B")

    all_concat = np.concatenate(all_vals)
    xmin = np.floor(all_concat.min() - 2)
    xmax = np.ceil(all_concat.max() + 2)
    ax.set_xlim(xmin, xmax)

    span = xmax - xmin
    if span <= 20:
        major_step = 2
    elif span <= 50:
        major_step = 5
    else:
        major_step = 10

    plt.xlabel("Full direct-link latency (ns)")
    plt.ylabel("CDF")
    plt.grid(True, alpha=0.25)
    plt.legend(title="Payload", frameon=True, ncol=1, fontsize=8)

    style_axis_ns(ax, major_step=major_step)

    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()

def plot_full_centered_cdf(all_data: dict, out_path: Path):
    plt.figure(figsize=(4, 3))
    ax = plt.gca()
    palette = sns.color_palette("deep", len(all_data))

    all_vals = []

    for color, payload in zip(palette, sorted(all_data.keys())):
        df = all_data[payload]
        vals = df["full_directlink_latency_ns"].dropna().to_numpy()
        mean_ns = np.mean(vals)
        centered = vals - mean_ns
        all_vals.append(centered)

        x, y = ecdf(centered)
        plt.plot(
            x,
            y,
            linewidth=2,
            color=color,
            label=f"{payload} B ($\\mu$={mean_ns:.1f} ns)"
        )

    all_concat = np.concatenate(all_vals)
    xmin = np.floor(all_concat.min() - 1)
    xmax = np.ceil(all_concat.max() + 1)
    ax.set_xlim(xmin, xmax)

    span = xmax - xmin
    if span <= 10:
        major_step = 1
    elif span <= 20:
        major_step = 2
    else:
        major_step = 5

    plt.xlabel("Latency deviation from mean (ns)")
    plt.ylabel("CDF")
    plt.grid(True, alpha=0.25)
    plt.legend(title="Payload / Mean", frameon=True, ncol=1)

    style_axis_ns(ax, major_step=major_step)
    
    style_manager = AcademicStyleManager()
    style_manager.finalize_axes(ax)

    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def plot_components_cdf(all_data: dict, out_path: Path):
    fig, axes = plt.subplots(1, 3, figsize=(9.0, 2.8), sharey=True)
    palette = sns.color_palette("deep", len(all_data))

    component_map = {
        "FPGA TX+RX": "fpga_total_latency_ns",
        "Wire": "wire_latency_ns",
        "Full direct-link": "full_directlink_latency_ns",
    }

    for ax, (title, col) in zip(axes, component_map.items()):
        all_vals = []

        for color, payload in zip(palette, sorted(all_data.keys())):
            df = all_data[payload]
            vals = df[col].dropna().to_numpy()
            all_vals.append(vals)
            x, y = ecdf(vals)
            ax.plot(x, y, linewidth=2, color=color, label=f"{payload} B")

        all_concat = np.concatenate(all_vals)
        xmin = np.floor(all_concat.min() - 1)
        xmax = np.ceil(all_concat.max() + 1)
        ax.set_xlim(xmin, xmax)

        span = xmax - xmin
        if span <= 10:
            major_step = 1
        elif span <= 20:
            major_step = 2
        elif span <= 50:
            major_step = 5
        else:
            major_step = 10

        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Latency (ns)")
        ax.grid(True, alpha=0.25)

        style_axis_ns(ax, major_step=major_step)

    axes[0].set_ylabel("CDF")
    axes[0].legend(title="Payload", frameon=True, fontsize=8)

    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def print_summary(all_data: dict):
    rows = []
    for payload in sorted(all_data.keys()):
        df = all_data[payload]
        vals = df["full_directlink_latency_ns"].dropna().to_numpy()
        rows.append({
            "payload_B": payload,
            "mean_ns": np.mean(vals),
            "p50_ns": np.percentile(vals, 50),
            "p99_ns": np.percentile(vals, 99),
            "max_ns": np.max(vals),
            "range_ns": np.max(vals) - np.min(vals),
        })
    summary = pd.DataFrame(rows)
    print(summary.to_string(index=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        default="results/directlink_augmented",
        help="Directory containing directlink_*_complete.csv files"
    )
    parser.add_argument(
        "--outdir",
        default="plots/directlink",
        help="Output directory for plots"
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update({
        "font.size": 12,
        "axes.titlesize": 12,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9,
        "legend.title_fontsize": 9,
        "axes.linewidth": 1.3,
    })

    files = sorted(input_dir.glob("directlink_*_complete.csv"))
    if not files:
        raise ValueError(f"No directlink_*_complete.csv found in {input_dir}")

    all_data = {}
    for f in files:
        payload, df = load_one(f)
        all_data[payload] = df

    print_summary(all_data)

    plot_full_centered_cdf(
        all_data,
        outdir / "cdf_full_directlink_centered_latency_ns.pdf"
    )

    print(f"wrote {outdir / 'cdf_full_directlink_latency_ns.pdf'}")
    print(f"wrote {outdir / 'cdf_directlink_components_ns.pdf'}")


if __name__ == "__main__":
    main()
