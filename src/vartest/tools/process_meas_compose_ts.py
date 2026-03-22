#!/usr/bin/env python3
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def parse_unknown_kv(unknown_args: List[str]) -> Dict[str, str]:
    """
    Parse unknown CLI args of the form:
      --incast=1
      --round=2
      --mode congestion
      --bg yes
    into a dict.
    """
    tags: Dict[str, str] = {}
    i = 0
    while i < len(unknown_args):
        tok = unknown_args[i]

        if not tok.startswith("--"):
            raise ValueError(f"Unexpected argument format: {tok}")

        key = tok[2:]

        if "=" in key:
            k, v = key.split("=", 1)
            tags[k] = v
            i += 1
            continue

        if i + 1 < len(unknown_args) and not unknown_args[i + 1].startswith("--"):
            tags[key] = unknown_args[i + 1]
            i += 2
        else:
            tags[key] = "1"
            i += 1

    return tags


def make_output_name(prefix: str, tags: Dict[str, str], ext: str = ".csv") -> str:
    if not tags:
        return f"{prefix}{ext}"

    parts: List[str] = [prefix]
    for k in sorted(tags.keys()):
        v = str(tags[k]).replace("/", "_")
        parts.append(f"{k}_{v}")
    return "_".join(parts) + ext

#req_id,phc_usr_tx,t1_ns,tx_hw_ns,t2_ns,t3_ns,t4_ns,t5_ns,t6_ns,t7_ns,t8_ns,payload_len,rx_hw_ns,phc_user_rx_ns

def load_and_merge(sender_csv: Path, sender_hw_csv: Path, receiver_csv: Path) -> pd.DataFrame:
    sender = pd.read_csv(sender_csv)
    sender_hw = pd.read_csv(sender_hw_csv)
    receiver = pd.read_csv(receiver_csv)

    if "req_id" not in sender.columns:
        raise ValueError("sender.csv missing req_id column")
    if "req_id" not in sender_hw.columns:
        raise ValueError("sender_hw.csv missing req_id column")
    if "req_id" not in receiver.columns:
        raise ValueError("receiver.csv missing req_id column")

    # drop duplicate columns from sender_hw and receiver to avoid confusion after merge
    sender = sender.drop(columns=["dst_ip","dst_port","payload_len"], errors="ignore")
    receiver = receiver.drop(columns=["t1_ns","valid_bitmap","flags","error_bitmap"], errors="ignore")
    merged = sender.merge(sender_hw, on="req_id", how="left").merge(receiver, on="req_id", how="left")

    merged["received"] = merged["t1_ns"].notna() & merged["t8_ns"].notna()

    return merged

def derive_complete_ts_from_sim(df: pd.DataFrame, fpga_sim: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    latency_col = "latency_interface_tx_to_mac_ts_ns"
    if latency_col not in fpga_sim.columns:
        print(f"FPGA sim CSV missing {latency_col} column, cannot derive complete timestamps")
        raise ValueError(f"FPGA sim CSV missing {latency_col} column")
    
    if "tx_hw_ns" not in out.columns:
        print("Merged DataFrame missing tx_hw_ns column, cannot derive complete timestamps")
        raise ValueError("Merged DataFrame missing tx_hw_ns column")
    
    latency_pool = fpga_sim[latency_col].dropna().round().astype(np.int64).to_numpy()
    print("Latency pool stats from FPGA sim CSV:")
    print(f"  Count: {len(latency_pool)}")
    print(f"  Mean: {np.mean(latency_pool):.3f} ns")
    print(f"  Std: {np.std(latency_pool):.3f} ns")
    if len(latency_pool) == 0:
        print(f"No valid latency samples in FPGA sim CSV, cannot derive complete timestamps")
        raise ValueError(f"No valid latency samples in FPGA sim CSV")
    
    rng = np.random.default_rng(seed=42)
    
    sampled_latencies_tx = rng.choice(latency_pool, size=len(out), replace=True)
    sampled_latencies_rx = rng.choice(latency_pool, size=len(out), replace=True)

    out["tx_nic_ns"] =  sampled_latencies_tx
    out["rx_nic_ns"] = sampled_latencies_rx
    out["tx_pcie_ns"] = out["tx_total_ns"] - out["tx_kernel_ns"] - out["tx_nic_ns"]
    out["rx_pcie_ns"] = out["rx_total_ns"] - out["rx_kernel_ns"] - out["rx_nic_ns"]
    
    # summary stats
    print("Derived PCIe latency stats:")
    for col in ["tx_pcie_ns", "rx_pcie_ns", "tx_nic_ns", "rx_nic_ns"]:
        vals = out[col].dropna().to_numpy()
        if len(vals) == 0:
            print(f"{col}: no valid samples")
            continue
        print(
            f"{col}: mean={np.mean(vals):.3f} ns, "
            f"p50={np.percentile(vals, 50):.3f} ns, "
            f"p99={np.percentile(vals, 99):.3f} ns, "
            f"max={np.max(vals):.3f} ns"
        )

    return out

def add_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    def safe_diff(a: str, b: str, new_col: str) -> None:
        if a in out.columns and b in out.columns:
            out[new_col] = (out[a] - out[b])
        else:
            out[new_col] = np.nan
    
    tx_kernel = safe_diff("t2_ns", "t1_ns", "tx_kernel_ns")
    tx_total = safe_diff("tx_hw_ns", "phc_usr_tx", "tx_total_ns")
    switch = safe_diff("t5_ns", "t4_ns", "switch_ns")
    rx_total = safe_diff("phc_user_rx_ns", "rx_hw_ns", "rx_total_ns")
    rx_kernel = safe_diff("t8_ns", "t7_ns", "rx_kernel_ns")
    total = safe_diff("t8_ns", "t1_ns", "total_ns")

    #summarize the metrics
    print("=== Metrics summary (for rows with valid timestamps) ===")
    for col in ["tx_kernel_ns", "tx_total_ns", "switch_ns", "rx_total_ns", "rx_kernel_ns", "total_ns"]:
        if col in out.columns:
            vals = out[col].dropna().to_numpy()
            if len(vals) == 0:
                print(f"{col}: no valid samples")
                continue
            print(
                f"{col}: mean={np.mean(vals):.3f} ns, "
                f"p50={np.percentile(vals, 50):.3f} ns, "
                f"p99={np.percentile(vals, 99):.3f} ns, "
                f"max={np.max(vals):.3f} ns"
            )
        else:
            print(f"{col}: column not found in DataFrame")

    return out


def add_tags(df: pd.DataFrame, tags: Dict[str, str]) -> pd.DataFrame:
    out = df.copy()
    for k, v in tags.items():
        out[k] = v
    return out


def summarize(df: pd.DataFrame) -> None:
    sent_count = len(df)
    recv_count = int((df["received"] == 1).sum())
    loss_count = sent_count - recv_count
    loss_rate = loss_count / sent_count if sent_count else 0.0

    print("=== Merge summary ===")
    print(f"sent_count : {sent_count}")
    print(f"recv_count : {recv_count}")
    print(f"loss_count : {loss_count}")
    print(f"loss_rate  : {loss_rate:.6f}")

    recv_df = df[df["received"] == 1].copy()

    for col, label in [
        ("tx_kernel_ns", "Tx kernel latency"),
        ("tx_pcie_ns", "Tx PCIe latency (derived)"),
        ("tx_total_ns", "Total Tx latency"),
        ("switch_ns", "Switch latency"),
        ("rx_total_ns", "Total Rx latency"),
        ("rx_pcie_ns", "Rx PCIe latency (derived)"),
        ("rx_kernel_ns", "Rx kernel latency"),
        ("total_ns", "Total latency"),
    ]:
        vals = recv_df[col].dropna().to_numpy() if col in recv_df.columns else np.array([])
        if len(vals) == 0:
            print(f"{label}: no samples")
            continue
        print(
            f"{label}: mean={np.mean(vals):.3f} us, "
            f"p50={np.percentile(vals, 50):.3f} us, "
            f"p99={np.percentile(vals, 99):.3f} us, "
            f"max={np.max(vals):.3f} us"
        )

    if "valid_bitmap" in recv_df.columns:
        print("valid_bitmap distribution:")
        print(recv_df["valid_bitmap"].value_counts().sort_index())


def main():
    parser = argparse.ArgumentParser(
        description="Merge sender.csv and receiver.csv, attach experiment tags, and emit a labeled merged CSV."
    )
    parser.add_argument("--sender", default="sender.csv", help="path to sender.csv")
    parser.add_argument("--sender_hw", default="sender_tx_ts.csv", help="optional path to sender hardware timestamp CSV")
    parser.add_argument("--receiver", default="receiver.csv", help="path to receiver.csv")
    parser.add_argument("--fpga_sim", default="fpga_sim.csv", help="optional path to FPGA sim CSV for deriving complete timestamps")
    parser.add_argument("--outdir", default="results", help="output directory")
    parser.add_argument("--prefix", default="vartest", help="output filename prefix")
    parser.add_argument("--output", default=None, help="optional explicit output filename")
    args, unknown = parser.parse_known_args()

    tags = parse_unknown_kv(unknown)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # merge sender and receiver data on req_id, compute metrics, and add tags
    merged = load_and_merge(Path(args.sender), Path(args.sender_hw), Path(args.receiver))
    merged = add_metrics(merged)

    if args.fpga_sim:
        fpga_sim = pd.read_csv(args.fpga_sim)
        merged = derive_complete_ts_from_sim(merged, fpga_sim)

    merged = add_tags(merged, tags)

    if args.output:
        out_name = args.output
    else:
        out_name = make_output_name(args.prefix, tags, ext=".csv")

    out_path = outdir / out_name
    merged.to_csv(out_path, index=False)

    summarize(merged)
    print(f"wrote merged csv: {out_path}")

if __name__ == "__main__":
    main()