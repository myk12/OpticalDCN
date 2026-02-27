#!/usr/bin/env python3
import struct
import sys
import time
import argparse
import socket
import ctypes
import pandas as pd
from scapy.all import *
from loguru import logger
logger.remove()
logger.add(sys.stdout, level="INFO")

# define custom packet formats
# bit<32> magic_number = 0xABCD1234;
# bit<32> sender_id;
# bit<32> seq_no;
# bit<32> hop_count;
# hop1
#  bit<64> hop1_ts_ingress;
#  bit<64> hop1_ts_egress;
#  bit<32> hop1_ingress_port;
#  bit<32> hop1_egress_port;
# hop2
#  bit<64> hop2_ts_ingress;
#  bit<64> hop2_ts_egress;
#  bit<32> hop2_ingress_port;
#  bit<32> hop2_egress_port;
# hop3
#  bit<64> hop3_ts_ingress;
#  bit<64> hop3_ts_egress;
#  bit<32> hop3_ingress_port;
#  bit<32> hop3_egress_port;
# hop4
#  bit<64> hop4_ts_ingress;
#  bit<64> hop4_ts_egress;
#  bit<32> hop4_ingress_port;
#  bit<32> hop4_egress_port;

###################################################################
#               Sockets Receiver
###################################################################
PROBE_HEADER_FORMAT = "!IIII"
HOP_DATA_FORMAT = "!QQII"  # ingress_ts, egress_ts, ingress_port, egress_port
HOP_DATA_SIZE = struct.calcsize(HOP_DATA_FORMAT) # 32 bytes per hop

PRJECT_ROOT="/home/yukema/OpticalDCN"
RESULT_DIR=f"{PRJECT_ROOT}/measurement/vartest/server/results/spineleaf_vartest/"

def swtich_network_namespace(namespace):
    """Switch to the specified network namespace."""
    try:
        with open(f"/var/run/netns/{namespace}", 'r') as ns_file:
            ns_fd = ns_file.fileno()
            libc = ctypes.CDLL("libc.so.6")
            if libc.setns(ns_fd, 0) != 0:
                raise OSError("setns failed")
    except Exception as e:
        logger.error(f"Failed to switch to namespace {namespace}: {e}")
        sys.exit(1)

def socket_receive_probes(namespace, interface, timeout=10):
    logger.info(f"Listening for probe packets on interface {interface} in namespace {namespace}...")
    
    swtich_network_namespace(namespace)
    
    # Create UDP socket and bind to interface
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    # Bind to port 7777
    sock.bind(("0.0.0.0", 7777))

    # bind to the specific interface
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())

    # if no packets are received within timeout seconds, stop listening
    sock.settimeout(timeout)

    results = []    # sender_id, seq_no, hop_idx, ingress_ts, egress_ts, ingress_port, egress_port, residence_ns, recv_time
    save_cnt = 0
    csv_filename_template = f"{RESULT_DIR}spineleaf_probe_results_partial_{int(time.time())}"

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            recv_time = time.time()
            
            # Parse the received packet
            header_size = struct.calcsize(PROBE_HEADER_FORMAT)
            probe_header = struct.unpack(PROBE_HEADER_FORMAT, data[:header_size])
            magic_number, sender_id, seq_no, hop_count = probe_header
            # show original log in hex format
            logger.trace(f"Raw packet data: {data.hex()}")
            
            logger.trace(f"[0x{magic_number:08X}] Received probe from sender_id={sender_id}, seq_no={seq_no}, hop_count={hop_count}")
            offset = header_size
            for hop_idx in range(hop_count):
                hop_data = struct.unpack(HOP_DATA_FORMAT, data[offset:offset + HOP_DATA_SIZE])
                ingress_ts, egress_ts, ingress_port, egress_port = hop_data
                
                residence_ns = egress_ts - ingress_ts

                record = {
                    "sender_id": sender_id,
                    "seq_no": seq_no,
                    "hop_number": hop_count,
                    "hop_idx": hop_idx,
                    "ingress_ts": ingress_ts,
                    "egress_ts": egress_ts,
                    "ingress_port": ingress_port,
                    "egress_port": egress_port,
                    "residence_ns": residence_ns,
                    "recv_time": recv_time
                }
                results.append(record)

                offset += HOP_DATA_SIZE
                logger.trace(f"  Hop {hop_idx}: ingress_port={ingress_port}, egress_port={egress_port}, residence_ns={residence_ns}")
            # save every 1000000
            if len(results) >= 1000000:
                df = pd.DataFrame(results)
                csv_filename = f"{csv_filename_template}_{save_cnt}.csv"
                save_cnt += 1
                df.to_csv(csv_filename, index=False)
                logger.info(f"Saved partial probe results to {csv_filename}")
                results = []    # reset results

        except socket.timeout:
            logger.info("Socket receive timeout reached.")
            break
        except Exception as e:
            logger.error(f"Error receiving packet: {e}")
            continue
    
    sock.close()
    return results

if __name__ == "__main__":
    logger.info("Starting Spine-Leaf Topology Probe Packet Receiver...")
    # basic argument parsing
    argparser = argparse.ArgumentParser(description="Spine-Leaf Topology Probe Packet Receiver")
    argparser.add_argument("--namespace", type=str, required=True, help="Network namespace to use")
    argparser.add_argument("--interface", type=str, required=True, help="Network interface to listen on")
    argparser.add_argument("--timeout", type=int, default=120, help="Timeout for receiving packets in seconds")
    args = argparser.parse_args()

    socket_receive_probes(args.namespace, args.interface, args.timeout)
