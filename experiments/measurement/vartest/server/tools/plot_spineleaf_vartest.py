#!/bin/python3

import os
import sys
import argparse
import time
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from loguru import logger
logger.remove()
logger.add(sys.stdout, level="INFO")

PROJECT_ROOT="/home/yukema/OpticalDCN"
RESULT_DIR=f"{PROJECT_ROOT}/measurement/vartest/server/results/spineleaf_vartest/"

class SpineLeafVarTestPlotter:
    def __init__(self, type: str, csv_file: str, flow_size: int = 1000, result_dir: str = RESULT_DIR):
        self.type = type    # 'hop' or 'flow'
        self.csv_file = csv_file
        self.flow_size = flow_size
        self.result_dir = result_dir
    
    def load_hop_data(self):
        df = pd.read_csv(os.path.join(self.result_dir, self.csv_file))
        self.df_raw = df
        return df

    def plot_hop_latency(self):
        if not hasattr(self, 'df_raw'):
            logger.error("Data not loaded. Please run load_data() first.")
            return
        
        df = self.df_raw
        # filter out 3 hops data
        df = df[df['hop_number'] == 3]
        
        # for each seq_no, calculate hop latency by hop_i[ingress_ts] - hop_(i-1)[ingress_ts]
        one_hop_latency_records = []
        for sender_id in df['sender_id'].unique():
            sender_df = df[df['sender_id'] == sender_id]
            for seq_no in sender_df['seq_no'].unique():
                seq_df = sender_df[sender_df['seq_no'] == seq_no].sort_values(by='hop_idx')
                previous_ingress_ts = None
                for _, row in seq_df.iterrows():
                    hop_idx = row['hop_idx']
                    ingress_ts = row['ingress_ts']
                    if previous_ingress_ts is not None:
                        latency = ingress_ts - previous_ingress_ts
                        one_hop_latency_records.append({
                            'sender_id': sender_id,
                            'seq_no': seq_no,
                            'hop': f'hop_{hop_idx}',
                            'latency_us': latency / 1e3  # convert to microseconds
                        })
                    previous_ingress_ts = ingress_ts
        
        # we add two latency of the same seq_no to get two-hop latency
        two_hop_latency_records = []
        for sender_id in df['sender_id'].unique():
            sender_df = df[df['sender_id'] == sender_id]
            for seq_no in sender_df['seq_no'].unique():
                seq_df = sender_df[sender_df['seq_no'] == seq_no].sort_values(by='hop_idx')
                if len(seq_df) < 3:
                    continue
                first_hop_ingress_ts = seq_df.iloc[0]['ingress_ts']
                third_hop_ingress_ts = seq_df.iloc[2]['ingress_ts']
                latency = third_hop_ingress_ts - first_hop_ingress_ts
                two_hop_latency_records.append({
                    'sender_id': sender_id,
                    'seq_no': seq_no,
                    'latency_us': latency / 1e3  # convert to microseconds
                })
        two_hop_latency_df = pd.DataFrame(two_hop_latency_records)
        # plot CDF of one and two hop latencies
        plt.figure(figsize=(10, 6))
        sns.ecdfplot(data=pd.DataFrame(one_hop_latency_records), x='latency_us', hue='sender_id', stat='proportion', label='One Hop Latency')
        sns.ecdfplot(data=two_hop_latency_df, x='latency_us', hue='sender_id', stat='proportion', linestyle='--', label='Two Hop Latency')
        plt.xlabel('Latency (microseconds)')
        plt.ylabel('Cumulative Probability')
        plt.title('Latency CDF for Spine-Leaf Topology')
        plt.legend(title='Sender ID')
        # set x-ticks start from 0 to max latency with step 10
        max_latency = max(df['egress_ts'] - df['ingress_ts']) / 1e3
        plt.xticks(range(0, int(max_latency) + 10, 10))
        plot_filename = os.path.join(self.result_dir, f"spineleaf_latency_cdf_{int(time.time())}.png")
        plt.savefig(plot_filename)
        logger.info(f"Saved latency CDF plot to {plot_filename}")
    
    def load_flow_data(self):
        logger.info("Loading flow data...")
        # Get all results csv files starting by self.csv_file prefix
        all_files = [f for f in os.listdir(self.result_dir) if f.startswith(self.csv_file) and f.endswith('.csv')]
        df_list = []

        # multi-threaded loading to speed up
        for f in all_files:
            logger.info(f"Loading flow data from {f}...")
            # for flow data, we only need sender_id, seq_no, hop_count, total_latency in order to save memory
            df = pd.read_csv(os.path.join(self.result_dir, f))
            
            for sender_id in df['sender_id'].unique():
                sender_df = df[df['sender_id'] == sender_id]
                for seq_no in sender_df['seq_no'].unique():
                    seq_df = sender_df[sender_df['seq_no'] == seq_no].sort_values(by='hop_idx')
                    if len(seq_df)  < 3:
                        continue
                    hop1_ingress_ts = seq_df.iloc[0]['ingress_ts']
                    hop3_ingress_ts = seq_df.iloc[2]['ingress_ts']
                    total_latency = hop3_ingress_ts - hop1_ingress_ts
                    df_list.append({
                        'sender_id': sender_id,
                        'seq_no': seq_no,
                        'hop_count': 3,
                        'total_latency_us': total_latency / 1e3  # convert to microseconds
                    })
        self.df_flow = pd.DataFrame(df_list)
        logger.info("Flow data loaded.")
        logger.info(self.df_flow.head())
        return self.df_flow
    
    def plot_flow_latency(self):
        logger.info("Plotting flow latency...")
        # for each sender_id we aggregate every [flow_size] packets into one flow
        # and calculate the flow completion time (FCT) of that flow
        df = self.df_flow
        flow_records = []
        for sender_id in df['sender_id'].unique():
            sender_df = df[df['sender_id'] == sender_id]
            max_seq_no = sender_df['seq_no'].max()
            num_flows = (max_seq_no + 1) // self.flow_size
            for flow_idx in range(num_flows):
                flow_start_seq = flow_idx * self.flow_size
                flow_end_seq = flow_start_seq + self.flow_size - 1
                flow_df = sender_df[(sender_df['seq_no'] >= flow_start_seq) & (sender_df['seq_no'] <= flow_end_seq)]
                if flow_df.empty:
                    continue
                fct = flow_df['total_latency_us'].sum()
                flow_records.append({
                    'sender_id': sender_id,
                    'flow_idx': flow_idx,
                    'fct_us': fct
                })
        flow_df = pd.DataFrame(flow_records)
        # plot CDF of flow completion times
        plt.figure(figsize=(10, 6))
        sns.ecdfplot(data=flow_df, x='fct_us', hue='sender_id', stat='proportion')
        plt.xlabel('Flow Completion Time (microseconds)')
        plt.ylabel('Cumulative Probability')
        plt.title('Flow Completion Time CDF for Spine-Leaf Topology')
        plt.legend(title='Sender ID')
        # set x-ticks start from 0 to max fct with step 100
        max_fct = flow_df['fct_us'].max()
        plt.xticks(range(0, int(max_fct) + 100, 100))
        plot_filename = os.path.join(self.result_dir, f"spineleaf_flow_fct_cdf_{int(time.time())}.png")
        plt.savefig(plot_filename)
    
    def plot(self):
        if self.type == 'hop':
            logger.info("Plotting hop latency...")
            self.load_hop_data()
            self.plot_hop_latency()
        elif self.type == 'flow':
            logger.info("Plotting flow latency...")
            self.load_flow_data()
            self.plot_flow_latency()
        else:
            logger.error(f"Unknown plot type: {self.type}")
        
def main():
    logger.info("Starting Spine-Leaf VarTest Plotter...")
    argparser = argparse.ArgumentParser(description="Spine-Leaf VarTest Plotter")
    argparser.add_argument("--type", type=str, choices=['hop', 'flow'], default='hop', help="Type of plot to generate")
    argparser.add_argument("--csv_file", type=str, required=True, help="CSV file with probe results")
    argparser.add_argument("--flow_size", type=int, default=1000, help="Number of packets per flow (only for flow type)")
    args = argparser.parse_args()

    # if type=hop, the csv_file is the single csv file with hop data
    # if type=flow, the csv_file is the prefix of multiple csv files with flow data
    plotter = SpineLeafVarTestPlotter(args.type, args.csv_file, args.flow_size)
    plotter.plot()

if __name__ == "__main__":
    main()
