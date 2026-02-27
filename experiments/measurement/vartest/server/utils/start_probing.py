#!/bin/bash/env python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2025-11-24
# description: Tofino latency probing module

# - This module probes the latency of packets going through a Tofino switch.
#   It starts a packet sender to send packets and a receiver to capture them,
#   measuring the time taken for packets to traverse the switch.
# - One thread is used for sending packets, and another for receiving them.

import argparse
import multiprocessing
import socket
import sys
import time
import struct
import ctypes
import os
import pandas as pd
import select
import fcntl
import errno
import subprocess

from loguru import logger

# set level to INFO
logger.remove()
logger.add(sys.stdout, level="INFO")

#======================= Configurations =======================#
SENDER_NS = os.getenv("NS1", "fpganic_p1")
RECEIVER_NS = os.getenv("NS2", "fpganic_p2")
SENDER_IFACE = os.getenv("PORTNAME1", "enp202s0np0")
RECEIVER_IFACE = os.getenv("PORTNAME2", "enp202s0np1")
SENDER_IP = os.getenv("IP1", "10.0.0.1")
RECEIVER_IP = os.getenv("IP2", "10.0.0.2")

PACKET_COUNT = int(os.getenv("PACKET_COUNT", "1000"))
PACKET_SIZE = int(os.getenv("PACKET_SIZE", "256"))
SEND_RATE = int(os.getenv("SEND_RATE", "10"))  # packets per second

EXP_PORT = 17777

# TS header (ts_h) layout packed into UDP payload
#   bit<16>   exp_id;
#   bit<32>   seq;
#   ts64_t    ingress_mac_ts;
#   ts64_t    ingress_global_ts;
#   ts64_t    egress_global_ts;
#   bit<16>   ingress_port;
#   bit<16>   egress_port;
EXP_ID = int(os.getenv("EXP_ID", "1"))
HEADER_FORMAT = "!HIQQQHH" # H=16bit, I=32bit, Q=64bit
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# load necessary libraries
libc = ctypes.CDLL("libc.so.6")
CLONE_NEWNET = 0x40000000
#==============================================================#
# ioctl constants (may vary by platform)
SIOCSHWTSTAMP = 0x89b0
SIOCGHWTSTAMP = 0x89b1

# SO_TIMESTAMPING
SOF_TIMESTAMPING_TX_HARDWARE = 1 << 0
SOF_TIMESTAMPING_TX_SOFTWARE = 1 << 1
SOF_TIMESTAMPING_RX_HARDWARE = 1 << 2
SOF_TIMESTAMPING_RX_SOFTWARE = 1 << 3
SOF_TIMESTAMPING_SOFTWARE = 1 << 4
SOF_TIMESTAMPING_SYS_HARDWARE = 1 << 5
SOF_TIMESTAMPING_RAW_HARDWARE = 1 << 6
SOF_TIMESTAMPING_OPT_ID = 1 << 7
SOF_TIMESTAMPING_TX_SCHED = 1 << 8
SOF_TIMESTAMPING_TX_ACK = 1 << 9
SOF_TIMESTAMPING_OPT_CMSG = 1 << 10
SOF_TIMESTAMPING_OPT_TSONLY = 1 << 11
SOF_TIMESTAMPING_OPT_STATS = 1 << 12
SOF_TIMESTAMPING_OPT_PKTINFO = 1 << 13
SOF_TIMESTAMPING_OPT_TX_SWHW = 1 << 14
SOF_TIMESTAMPING_LAST = SOF_TIMESTAMPING_OPT_TX_SWHW
SOF_TIMESTAMPING_MASK = (SOF_TIMESTAMPING_LAST - 1) | SOF_TIMESTAMPING_LAST

SO_TIMESTAMPING = 37     # linux/socket.h
SOF_TIMESTAMPING = 127

def switch_namespace(ns_name):
    """Switch to the specified network namespace."""
    logger.info(f"Switching to namespace: {ns_name}")
    ns_path = f"/var/run/netns/{ns_name}"
    try:
        with open(ns_path) as ns_file:
            # setns(fd, nstype): fd is the file descriptor of the namespace
            ret = libc.setns(ns_file.fileno(), CLONE_NEWNET)
            if ret != 0:
                raise OSError(f"setns failed for {ns_name}")
    except Exception as e:
        logger.error(f"Error switching namespace: {e}")
        exit(1)

def enable_hw_timestamping(sock):
    flags = (SOF_TIMESTAMPING_TX_HARDWARE |
             SOF_TIMESTAMPING_TX_SOFTWARE |
             SOF_TIMESTAMPING_RX_HARDWARE |
             SOF_TIMESTAMPING_RAW_HARDWARE |
             SOF_TIMESTAMPING_SOFTWARE)

    sock.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPING, struct.pack('i', flags))
    logger.info("Hardware timestamping enabled on socket.")

def receiver_task(result_queue, stop_event):
    """Receiver process to capture packets and measure latency."""
    # Switch to receiver namespace
    switch_namespace(RECEIVER_NS)

    # Create UDP socket to receive packets
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    
    # Bind to specific interface/device
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, RECEIVER_IFACE.encode('ascii'))
    # Enable hardware timestamping on socket
    enable_hw_timestamping(sock)
    
    sock.bind((RECEIVER_IP, EXP_PORT))
    #sock.settimeout(10)    # Set timeout to avoid blocking indefinitely
    logger.info("Receiver started on {}:{}".format(RECEIVER_IP, EXP_PORT))

    received_data = {} # Key: seq_num, Value: ts_header
    received_count = 0  # We assume that every sent packet will be received for simplicity
    while received_count < PACKET_COUNT:
        data, ancdata, flags, addr = sock.recvmsg(2048, 512)
        (exp_id, seq_num, ingress_mac_ts, ingress_global_ts,
        egress_global_ts, ingress_port, egress_port) = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
        logger.trace(f"Received packet seq={seq_num} from {addr}")
        # Store full header information plus recv_time and latency
        received_data[seq_num] = {
            'exp_id': exp_id,
            'seq': seq_num,
            'ingress_mac_ts': ingress_mac_ts,
            'ingress_global_ts': ingress_global_ts,
            'egress_global_ts': egress_global_ts,
            'ingress_port': ingress_port,
            'egress_port': egress_port,
        }
        logger.info(f"Packet seq={seq_num} received with ingress_mac_ts={ingress_mac_ts}, ingress_global_ts={ingress_global_ts}, egress_global_ts={egress_global_ts}")
        # Check ancillary data for timestamps
        for cmsg_level, cmsg_type, cmsg_data in ancdata:
            if cmsg_level == socket.SOL_SOCKET and cmsg_type == SO_TIMESTAMPING:
                logger.info(f"Received ancillary data for seq={seq_num}")
                # Unpack three timestamps (software, hardware, raw hardware)
                ts = struct.unpack('=qqqqqq', cmsg_data[:48])
                sw_ts = (ts[0], ts[1])  # seconds, nanoseconds
                hw_ts = (ts[2], ts[3])
                raw_hw_ts = (ts[4], ts[5])
                logger.info(f"Ancillary timestamps for seq={seq_num}: SW={sw_ts}, HW={hw_ts}, RAW_HW={raw_hw_ts}")
                received_data[seq_num]['rx_sw_ts'] = sw_ts[0] * 1_000_000_000 + sw_ts[1]
                received_data[seq_num]['rx_hw_ts'] = hw_ts[0] * 1_000_000_000 + hw_ts[1]
                received_data[seq_num]['rx_raw_hw_ts'] = raw_hw_ts[0] * 1_000_000_000 + raw_hw_ts[1]
        received_count += 1
        logger.info(f"Total packets received: {received_count}/{PACKET_COUNT}")

    logger.info("All packets received.")
    result_queue.put(received_data)
    sock.close()
    logger.info("Receiver stopped.")
    
def sender_task(stop_event, send_queue):
    """Sender process to send packets. Sends TX hw timestamps back via send_queue."""
    # Switch to sender namespace
    switch_namespace(SENDER_NS)

    # Create UDP socket to send packets
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    # Bind to specific interface/device
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, SENDER_IFACE.encode('ascii'))

    # Bind to local address
    sock.bind((SENDER_IP, 0))

    # Connect to receiver address
    #sock.connect((RECEIVER_IP, EXP_PORT))

    # Enable hardware timestamping on socket
    enable_hw_timestamping(sock)

    # non-blocking to read errqueue without blocking
    sock.setblocking(False)

    logger.info("Sender started, sending packets to {}:{}".format(RECEIVER_IP, EXP_PORT))
    tx_seq = 0
    sent_data = {}
    
    for seq_num in range(PACKET_COUNT):
        if stop_event.is_set():
            break

        send_time = time.time_ns()  # in nanoseconds
        # Populate ts_h. We don't have hardware ingress MAC ts here, set to 0.
        ingress_mac_ts = 0
        ingress_global_ts = 0
        egress_global_ts = 0
        ingress_port = 0
        egress_port = 0
        header = struct.pack(HEADER_FORMAT, EXP_ID, seq_num, ingress_mac_ts, ingress_global_ts, egress_global_ts, ingress_port, egress_port)
        payload = header + bytes(max(0, PACKET_SIZE - len(header)))
        try:
            sock.sendto(payload, (RECEIVER_IP, EXP_PORT))
        except OSError as e:
            logger.error(f"send error seq={seq_num}: {e}")
            continue
        logger.trace(f"Sent packet seq_num={seq_num}")

        # Read TX timestamps from error queue
        while True:
            try:
                _, ancdata, _, _ = sock.recvmsg(0, 512, socket.MSG_ERRQUEUE)
            except BlockingIOError:
                logger.info(f"No TX timestamp available yet for seq={tx_seq}")
                break
            except OSError as e:
                logger.error(f"recvmsg error on errqueue for seq={tx_seq}: {e}")
                break
            for cmsg_level, cmsg_type, cmsg_data in ancdata:
                if cmsg_level == socket.SOL_SOCKET and cmsg_type == SO_TIMESTAMPING:
                    logger.info(f"Received TX ancillary data for seq={tx_seq}")
                    ts = struct.unpack('=qqqqqq', cmsg_data[:48])
                    sw_ts = (ts[0], ts[1])  # seconds, nanoseconds
                    hw_ts = (ts[2], ts[3])
                    raw_hw_ts = (ts[4], ts[5])
                    logger.info(f"TX Ancillary timestamps for seq={tx_seq}: SW={sw_ts}, HW={hw_ts}, RAW_HW={raw_hw_ts}")
                    tx_sw_ts = sw_ts[0] * 1_000_000_000 + sw_ts[1]
                    tx_hw_ts = hw_ts[0] * 1_000_000_000 + hw_ts[1]
                    tx_raw_hw_ts = raw_hw_ts[0] * 1_000_000_000 + raw_hw_ts[1]
                    # Send back the TX hw timestamp via send_queue
                    sent_data[tx_seq] = {
                        'tx_sw_ts': tx_sw_ts,
                        'tx_hw_ts': tx_hw_ts,
                        'tx_raw_hw_ts': tx_raw_hw_ts,
                    }
                    tx_seq += 1

        #TODO: Add precise rate control here (like randomized inter-packet gap)
        time.sleep(1.0 / SEND_RATE)  # Control send rate

    while tx_seq < PACKET_COUNT:
        try:
            _, ancdata, _, _ = sock.recvmsg(0, 512, socket.MSG_ERRQUEUE)
        except BlockingIOError:
            logger.info(f"No more TX timestamp available yet for seq={tx_seq}")
            break
        except OSError as e:
            logger.error(f"recvmsg error on errqueue for seq={tx_seq}: {e}")
            break
        for cmsg_level, cmsg_type, cmsg_data in ancdata:
            if cmsg_level == socket.SOL_SOCKET and cmsg_type == SO_TIMESTAMPING:
                logger.info(f"Received TX ancillary data for seq={tx_seq}")
                ts = struct.unpack('=qqqqqq', cmsg_data[:48])
                sw_ts = (ts[0], ts[1])  # seconds, nanoseconds
                hw_ts = (ts[2], ts[3])
                raw_hw_ts = (ts[4], ts[5])
                logger.info(f"TX Ancillary timestamps for seq={tx_seq}: SW={sw_ts}, HW={hw_ts}, RAW_HW={raw_hw_ts}")
                tx_sw_ts = sw_ts[0] * 1_000_000_000 + sw_ts[1]
                tx_hw_ts = hw_ts[0] * 1_000_000_000 + hw_ts[1]
                tx_raw_hw_ts = raw_hw_ts[0] * 1_000_000_000 + raw_hw_ts[1]
                # Send back the TX hw timestamp via send_queue
                sent_data[tx_seq] = {
                    'tx_sw_ts': tx_sw_ts,
                    'tx_hw_ts': tx_hw_ts,
                    'tx_raw_hw_ts': tx_raw_hw_ts,
                }           
                tx_seq += 1

    # Send all sent_data back via send_queue
    send_queue.put(sent_data)
    sock.close()
    logger.info("Sender stopped.")

def save_results(df: pd.DataFrame, result_dir: str, filename: str):
    """Save the results DataFrame to CSV in the specified directory."""
    csv_filename = os.path.join(result_dir, filename)
    df.to_csv(csv_filename, index=False)
    logger.info(f"Saved latency data to {csv_filename}")

def start_probing(result_dir: str = "./results", pattern: str = "SINGLE", rate: int = 10, packet_size: int = 1024):
    logger.info("Starting probing process.")

    # Create a queue to collect results from receiver
    mgr = multiprocessing.Manager()
    recv_queue = mgr.Queue()
    send_queue = mgr.Queue()
    stop_event = multiprocessing.Event()

    # Start receiver process
    logger.info("Starting receiver process.")
    receiver_process = multiprocessing.Process(target=receiver_task, args=(recv_queue, stop_event))
    receiver_process.start()
    
    time.sleep(1)  # Ensure receiver is ready before sender starts
    # Start sender process
    logger.info("Starting sender process.")
    sender_process = multiprocessing.Process(target=sender_task, args=(stop_event, send_queue))
    sender_process.start()
    # Wait for sender to finish
    logger.info("Waiting for sender process to finish.")
    sender_process.join()
    sent_data = send_queue.get()
    logger.info(f"Sender process finished, sent_data collected with {len(sent_data)} entries.")
    if not sent_data:
        logger.warning("No sent data collected from sender.")
        return
    
    # Leave some time for receiver to process remaining packets
    logger.info("Sender finished. Allowing receiver to finalize.")
    time.sleep(3)
    stop_event.set()
    logger.info("stop event set, waiting for receiver to finish.")
    receiver_process.join()
    # Collect results from receiver
    logger.info("Collecting results from receiver.")
    received_data = recv_queue.get()
    # received_data is a dict mapping seq -> header-dict. Convert to pandas DataFrame
    if not received_data:
        logger.warning("No packets were received.")
        return

    # join sent_data and received_data based on seq number
    rows = []
    for seq_num, recv_info in received_data.items():
        row = {
            'seq': seq_num,
            'exp_id': recv_info['exp_id'],
            'ingress_mac_ts': recv_info['ingress_mac_ts'],
            'ingress_global_ts': recv_info['ingress_global_ts'],
            'egress_global_ts': recv_info['egress_global_ts'],
            'ingress_port': recv_info['ingress_port'],
            'egress_port': recv_info['egress_port'],
            'rx_sw_ts': recv_info.get('rx_sw_ts', None),
            'rx_hw_ts': recv_info.get('rx_hw_ts', None),
            'rx_raw_hw_ts': recv_info.get('rx_raw_hw_ts', None),
        }
        sent_info = sent_data.get(seq_num, {})
        row.update({
            'tx_sw_ts': sent_info.get('tx_sw_ts', None),
            'tx_hw_ts': sent_info.get('tx_hw_ts', None),
            'tx_raw_hw_ts': sent_info.get('tx_raw_hw_ts', None),
        })
        rows.append(row)

    df = pd.DataFrame(rows)
    logger.info(f"Converted {len(df)} packets to DataFrame with columns: {df.columns.tolist()}")
    logger.debug(f"DataFrame head:\n{df.head().to_string()}")
    
    # Save results
    os.makedirs(result_dir, exist_ok=True)
    filename = f"{pattern}_{rate}Gbps_{packet_size}B.csv"
    save_results(df, result_dir, filename)

if __name__ == "__main__":
    logger.info("This module is intended to be imported and used by probe_main.py.")
    parser = argparse.ArgumentParser(description="Start Tofino latency probing.")
    parser.add_argument('--hw_timestamping', action='store_true',
                        help='Enable hardware timestamping')
    parser.add_argument('--pattern', type=str, choices=['SINGLE', 'MULTIPLE', 'FULLY'], default='SINGLE',
                        help='Traffic pattern to use for probing')
    parser.add_argument('--rate', type=int, default=10,
                        help='Packet send rate (Gbps)')
    parser.add_argument('--packet_size', type=int, default=1024,
                        help='Packet size in bytes')
    parser.add_argument('--topo_yaml', type=str, default='topo_fully.yaml',
                        help='Topology YAML file')
    args = parser.parse_args()

    result_dir = "./results"

    start_probing(result_dir=result_dir, pattern=args.pattern, rate=args.rate, packet_size=args.packet_size)
