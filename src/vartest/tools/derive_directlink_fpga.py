#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def round1(x):
    return np.round(x, 1)


def load_profile(profile_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(profile_csv)

    required = [
        "payload_size",
        "latency_interface_tx_to_mac_ns",
        "latency_mac_rx_to_interface_ns",
    ]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in {profile_csv}")

    df = df.copy()
    df["payload_size"] = pd.to_numeric(df["payload_size"], errors="raise").astype(int)
    df["latency_interface_tx_to_mac_ns"] = pd.to_numeric(
        df["latency_interface_tx_to_mac_ns"], errors="raise"
    )
    df["latency_mac_rx_to_interface_ns"] = pd.to_numeric(
        df["latency_mac_rx_to_interface_ns"], errors="raise"
    )
    return df


def augment_one_directlink(
    directlink_csv: Path,
    profile_df: pd.DataFrame,
    out_csv: Path,
    rng: np.random.Generator,
):
    df = pd.read_csv(directlink_csv).copy()

    required = ["req_id", "tx_hw_ns", "rx_hw_ns", "payload_len"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in {directlink_csv}")

    df["payload_len"] = pd.to_numeric(df["payload_len"], errors="raise").astype(int)
    df["tx_hw_ns"] = pd.to_numeric(df["tx_hw_ns"], errors="raise")
    df["rx_hw_ns"] = pd.to_numeric(df["rx_hw_ns"], errors="raise")

    payloads = sorted(df["payload_len"].unique())
    if len(payloads) != 1:
        raise ValueError(
            f"{directlink_csv} contains multiple payload_len values: {payloads}. "
            "Expected one payload size per file."
        )
    
    payload_len = payloads[0]
    
    prof = profile_df[profile_df["payload_size"] == payload_len].copy()
    if prof.empty:
        raise ValueError(
            f"No matching payload_size={payload_len} found in profile CSV for {directlink_csv}"
        )

    n = len(df)

    # Empirical resampling with replacement
    tx_samples = rng.choice(
        prof["latency_interface_tx_to_mac_ns"].to_numpy(),
        size=n,
        replace=True,
    )
    rx_samples = rng.choice(
        prof["latency_mac_rx_to_interface_ns"].to_numpy(),
        size=n,
        replace=True,
    )

    df["fpga_tx_latency_ns"] = round1(tx_samples)
    df["fpga_rx_latency_ns"] = round1(rx_samples)

    # Direct measured link latency from tx_hw to rx_hw
    df["wire_latency_ns"] = df["rx_hw_ns"] - df["tx_hw_ns"]

    # Full modeled directlink latency including FPGA NIC processing
    df["full_directlink_latency_ns"] = round1(
        df["fpga_tx_latency_ns"] + df["wire_latency_ns"] + df["fpga_rx_latency_ns"]
    )

    # Optional extra breakdown fields
    df["tx_hw_to_rx_hw_ns"] = df["wire_latency_ns"]

    out_cols = [
        "req_id",
        "payload_len",
        "tx_hw_ns",
        "rx_hw_ns",
        "fpga_tx_latency_ns",
        "wire_latency_ns",
        "fpga_rx_latency_ns",
        "full_directlink_latency_ns",
    ]
    df[out_cols].to_csv(out_csv, index=False)

    # small summary
    summary = {
        "input_file": str(directlink_csv),
        "output_file": str(out_csv),
        #"payload_len": payload_len,
        "num_rows": len(df),
        "wire_latency_mean_ns": df["wire_latency_ns"].mean(),
        "fpga_tx_mean_ns": df["fpga_tx_latency_ns"].mean(),
        "fpga_rx_mean_ns": df["fpga_rx_latency_ns"].mean(),
        "full_latency_mean_ns": df["full_directlink_latency_ns"].mean(),
    }
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Augment directlink CSVs with FPGA NIC TX/RX processing latencies by empirical resampling from fpga_profile.csv"
    )
    parser.add_argument(
        "--directlink-dir",
        type=Path,
        default=Path("results/directlink"),
        help="Directory containing directlink_*.csv files",
    )
    parser.add_argument(
        "--profile-csv",
        type=Path,
        default=Path("tools/fpga_profile.csv"),
        help="Path to fpga_profile.csv",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("results/directlink_augmented"),
        help="Output directory for augmented CSVs",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling",
    )
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    profile_df = load_profile(args.profile_csv)
    rng = np.random.default_rng(args.seed)

    input_files = sorted(args.directlink_dir.glob("directlink_*.csv"))
    if not input_files:
        raise ValueError(f"No directlink_*.csv files found in {args.directlink_dir}")

    summaries = []
    for f in input_files:
        out_csv = args.outdir / f.name.replace(".csv", "_complete.csv")
        summary = augment_one_directlink(
            directlink_csv=f,
            profile_df=profile_df,
            out_csv=out_csv,
            rng=rng,
        )
        summaries.append(summary)
        print(
            f"[OK] {f.name} -> {out_csv.name} "
            #f"(payload={summary['payload_len']}, rows={summary['num_rows']})"
        )

    summary_df = pd.DataFrame(summaries)
    summary_csv = args.outdir / "augmentation_summary.csv"
    summary_df.to_csv(summary_csv, index=False)
    print(f"wrote summary: {summary_csv}")


if __name__ == "__main__":
    main()
