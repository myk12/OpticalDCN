#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2025-11-26
# description: Plotting utility for variance test results

import os
import argparse
from sys import stderr, stdout
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from loguru import logger

EGRESS_FPGA_STR="tx_raw_hw_ts"
INGRESS_FPGA_STR="rx_raw_hw_ts"
IN_MAC_STR="ingress_mac_ts"
INGRESS_STR="ingress_global_ts"
EGRESS_STR="egress_global_ts"

class PlotVarResult:
    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.data = pd.DataFrame()  # DataFrame to hold the loaded data
        os.makedirs(self.output_dir, exist_ok=True)

    def load_data(self):
        """Load variance test results from a CSV file."""
        logger.info(f"Loading data from {self.input_dir}...")
        csv_files = [f for f in os.listdir(self.input_dir) if f.endswith('.csv')]
        if not csv_files:
            logger.error("No CSV files found in the input directory.")
            raise FileNotFoundError("No CSV files found in the input directory.")
        
        for csv_file in csv_files:
            file_path = os.path.join(self.input_dir, csv_file)
            # parse params from filename: pattern_rate_size.csv
            params = csv_file[:-4].split('_')
            assert len(params) == 3, f"Filename {csv_file} does not match expected format 'pattern_rate_size.csv'"
            pattern, rate, size = params
            rate_int = int(rate[:-4])  # remove 'Gbps' suffix
            size_int = int(size[:-1])  # remove 'B' suffix
            df = pd.read_csv(file_path)
            df['Pattern'] = pattern
            df['Rate_Gbps'] = rate_int
            df['Packet_Size_B'] = size_int
            
            logger.info(f"Loaded data from {csv_file} with pattern={pattern}, rate={rate_int}Gbps, size={size_int}B")
            self.data = pd.concat([self.data, df], ignore_index=True)
        logger.info("Data loaded successfully.")

    def plot_variance(self):
        """Plot variance results."""
        # There is no pattern filter here
        logger.info("Plotting overall variance results...")
        num_rates = self.data['Rate_Gbps'].nunique()
        num_packet_sizes = self.data['Packet_Size_B'].nunique()
        logger.info(f"Total unique rates: {num_rates}, Total unique packet sizes: {num_packet_sizes}")
        # subplot row1: num_rates columns, 1 row, for each figure plot CDF of different packet sizes
        # subplot row2: num_packet_sizes colums, 1 row, for each figure plot CDF of different packet sizes
        # subplot row3: num_rates columns, 1 row, for each figure plot CDF of different packet sizes
        fig, axes = plt.subplots(3, num_rates, figsize=(5 * num_rates, 4 * 2), sharex=False)
        if num_rates == 1:
            axes = axes.reshape(3, 1)  # Make it 2D array for consistency
        for i, (rate, group) in enumerate(self.data.groupby('Rate_Gbps')):
            ax = axes[0, i]
            for packet_size, size_group in group.groupby('Packet_Size_B'):
                sns.ecdfplot(size_group[EGRESS_STR] - size_group[IN_MAC_STR], ax=ax, label=f'Packet Size: {packet_size}B')
            ax.set_title(f'Latency CDF for Rate: {rate}Gbps (All Patterns)')
            ax.set_xlabel('Latency (ns)')
            ax.set_ylabel('CDF')
            #ax.set_xscale('log')
            ax.legend(title='Packet Size')
            ax.grid(True)
        for j, (packet_size, group) in enumerate(self.data.groupby('Packet_Size_B')):
            ax = axes[1, j % num_rates]
            for rate, rate_group in group.groupby('Rate_Gbps'):
                sns.ecdfplot(rate_group[EGRESS_STR] - rate_group[IN_MAC_STR], ax=ax, label=f'Rate: {rate}Gbps')
            ax.set_title(f'Latency CDF for Packet Size: {packet_size}B (All Patterns)')
            ax.set_xlabel('Latency (ns)')
            ax.set_ylabel('CDF')
            #ax.set_xscale('log')
            ax.legend(title='Rate')
            ax.grid(True)
        for i, (rate, group) in enumerate(self.data.groupby('Rate_Gbps')):
            ax = axes[2, i]
            for packet_size, size_group in group.groupby('Packet_Size_B'):
                sns.ecdfplot(size_group[INGRESS_FPGA_STR] - size_group[EGRESS_FPGA_STR], ax=ax, label=f'Packet Size: {packet_size}B')
            ax.set_title(f'Latency Density for Rate: {rate}Gbps (All Patterns)')
            ax.set_xlabel('Latency (ns)')
            ax.set_ylabel('Density')
            #ax.set_xscale('log')
            ax.legend(title='Packet Size')
            ax.grid(True)
        plt.tight_layout()
        output_file = os.path.join(self.output_dir, 'variance_all_patterns.png')
        plt.savefig(output_file)
        logger.info(f"Saved variance plot to {output_file}")
        plt.close(fig)

    def run(self):
        self.load_data()
        self.plot_variance()

def main():
    parser = argparse.ArgumentParser(description="Plot variance test results.")
    parser.add_argument('--input_dir', type=str, required=True, help='Input CSV file with variance test results')
    parser.add_argument('--output_dir', type=str, required=True, help='Directory to save the plots')
    args = parser.parse_args()

    plotter = PlotVarResult(input_dir=args.input_dir, output_dir=args.output_dir)
    plotter.run()

if __name__ == "__main__":
    main()
