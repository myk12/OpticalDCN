#!/usr/bin/env python3
import pandas as pd
import argparse
from loguru import logger

def main():
    parser = argparse.ArgumentParser(description="Merge sender and receiver data for direct link testing.")
    parser.add_argument('--sender', type=str, default='sender_tx_ts.csv', help='Path to sender CSV file')
    parser.add_argument('--receiver', type=str, default='receiver.csv', help='Path to receiver CSV file')
    parser.add_argument('--output', type=str, default='results/directlink/', help='Path to output CSV file')
    args = parser.parse_args()

    logger.info("Merging sender and receiver data...")
    sender_df = pd.read_csv(args.sender, usecols=['req_id', 'tx_hw_ns'])
    receiver_df = pd.read_csv(args.receiver, usecols=['req_id', 'rx_hw_ns', 'payload_len'])
    
    merged_df = pd.merge(sender_df, receiver_df, on='req_id', how='inner')
    merged_df = merged_df[['req_id', 'tx_hw_ns', 'rx_hw_ns', 'payload_len']]

    # get the unique payload lengths
    payload_lengths = merged_df['payload_len'].unique()
    logger.info("Unique payload lengths found: {}".format(payload_lengths))

    for payload_len in payload_lengths:
        output_path = args.output  + f"directlink_{payload_len}B.csv"
        merged_df[merged_df['payload_len'] == payload_len].to_csv(output_path, index=False)
        logger.info(f"Merged data saved to {output_path}")

if __name__ == "__main__":
    main()