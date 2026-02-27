#!.venv/python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2026-01-04

# description: Tofino Spine-Leaf Topology Hop Delay Plotting Tool
from datetime import time
import os
import sys
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from loguru import logger
logger.remove()
logger.add(sys.stdout, level="INFO")

###############################################################
#                 Configuration
###############################################################

class SpineLeafHopDelayPlotter:
    def __init__(self, csv_file: str, result_dir: str):
        self.csv_file = csv_file
        self.result_dir = result_dir
    
    def load_data(self):
        df = pd.read_csv(os.path.join(self.result_dir, self.csv_file))
        self.df_raw = df
        self.df_raw.columns = ['packet_id', 'hop1_latency_ns', 'hop2_latency_ns']
        return df

    def get_fct_data(self, rate: int, flow_size: int):
        """
        Get flow completion time data for given rate and flow size.
        Args:
            rate (int): Sending rate in Gbps
            flow_size (int): Flow size in MB (e.g., 1, 10, 100)
        """
        logger.info(f"Getting FCT data for rate: {rate} Gbps, flow size: {flow_size} MB")
        # calculate packet interval in nanoseconds
        packet_size_bytes = 1024  # assuming 1KB packets
        packet_interval_ns = (packet_size_bytes * 8) / (rate * 1e9) * 1e9  # in ns
        # calculate number of packets per flow
        packets_per_flow = (flow_size * 1024 * 1024) / packet_size_bytes
        logger.info(f"Calculated packet interval: {packet_interval_ns} ns, packets per flow: {packets_per_flow}")

        total_rows = len(self.df_raw)
        num_complete_flows = total_rows // packets_per_flow
        rows_to_keep = int(num_complete_flows * packets_per_flow)
        
        df_truncated = self.df_raw.iloc[:rows_to_keep]

        df_summed = df_truncated.groupby(np.arange(len(df_truncated)) // packets_per_flow).sum()
        df_summed.columns = ['flow_id', 'hop1_fct_ns', 'hop2_fct_ns']

        return df_summed

    def plot_flow_completion_time(self):
        # plot flow completion time vs hop delay
        if not hasattr(self, 'df_raw'):
            logger.error("Data not loaded. Please run load_data() first.")
            return
        # plot flow size from 1MB to 100MB
        flow_sizes = [1, 10, 100]
        rate = 100  # Gbps
        num_plots = len(flow_sizes)
        fig, axs = plt.subplots(1, num_plots, figsize=(4 * num_plots, 3), sharey=True)
        for i, flow_size in enumerate(flow_sizes):
            df_fct = self.get_fct_data(rate, flow_size)
            ax = axs[i]
            sns.ecdfplot(data=df_fct/1e3, x='hop2_fct_ns', label=f"Flow Size: {flow_size} MB", ax=ax)
            ax.set_title(f"Flow Completion Time")
            ax.set_xlabel("Time (µs)")
            if i == 0:
                ax.set_ylabel("CDF")
            ax.legend()

        plt.tight_layout()
        plot_filename = os.path.join(self.result_dir, f"spineleaf_flow_completion_time.png")
        plt.savefig(plot_filename)
        logger.info(f"Flow completion time plot saved to {plot_filename}")
    
    def plot_hop_latency_CDF(self):
        logger.info("Plotting hop latency CDF...")
        fig, axs = plt.subplots(1, 2, figsize=(8, 3))
        sns.ecdfplot(data=self.df_raw, x='hop1_latency_ns', ax=axs[0])
        axs[0].set_title("one hop latency CDF")
        axs[0].set_xlabel("Latency (ns)")

        # two hop latency CDF hop1 + hop2
        self.df_raw['hop2_total_latency_ns'] = self.df_raw['hop1_latency_ns'] + self.df_raw['hop2_latency_ns']
        sns.ecdfplot(data=self.df_raw, x='hop2_total_latency_ns', ax=axs[1])
        axs[1].set_title("two hop latency CDF")
        axs[1].set_xlabel("Latency (ns)")
        plt.tight_layout()
        plot_filename = os.path.join(self.result_dir, f"spineleaf_hop_latency_cdf.png")
        plt.savefig(plot_filename)
        logger.info(f"Hop latency CDF plot saved to {plot_filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spine-Leaf Topology Hop Delay Plotter")
    parser.add_argument('--result_dir', type=str, default="../results/spineleaf_vartest/", help='Directory containing result CSV files')
    parser.add_argument('--csv_file', type=str, default="hop_latency.csv", help='CSV file containing hop delay data')
    args = parser.parse_args()

    plotter = SpineLeafHopDelayPlotter(csv_file=args.csv_file, result_dir=args.result_dir)
    plotter.load_data()
    plotter.plot_flow_completion_time()
    plotter.plot_hop_latency_CDF()
    
