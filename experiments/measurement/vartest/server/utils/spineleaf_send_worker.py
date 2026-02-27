#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2025-12-17
# description: Tofino Spine-Leaf Topology Probe Packet Sender Script
# This script sends probe packets from a specified sender to a target IP address
# in a spine-leaf topology. The packets contain a custom header for tracking
# sequence numbers and hop counts, as well as placeholders for timestamps
# collected at each hop in the network.
import sys
import time
import struct
import argparse
import socket
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

##############################################################################
#                   Socket-based Packet Sending
##############################################################################
PROBE_HEADER_FORMAT = "!IIII"
HOP_DATA_FORMAT = "!QQII"  # ingress_ts, egress_ts, ingress_port, egress_port
HOP_DATA_SIZE = struct.calcsize(HOP_DATA_FORMAT) # 32 bytes per hop

def swtich_network_namespace(namespace):
    """Switch to the specified network namespace."""
    try:
        with open(f"/var/run/netns/{namespace}", 'r') as ns_file:
            ns_fd = ns_file.fileno()
            libc = ctypes.CDLL("libc.so.6")
            if libc.setns(ns_fd, 0) != 0:
                raise OSError("setns failed")
        logger.info(f"Switched to network namespace: {namespace}")
    except Exception as e:
        logger.error(f"Failed to switch network namespace: {e}")
        sys.exit(1)

# define socket-based packet sending (alternative to Scapy)
# be sure that the arp entry for target_ip is already in the ARP table
def socket_send_probes(sender_id, target_ip, namespace, interface, packet_size, count=100, interval_us=0.1):
    logger.info(f"Sending {count} probe packets from sender {sender_id} to {target_ip} on interface {interface} using raw socket...")

    # Switch to the specified network namespace
    swtich_network_namespace(namespace)
    
    # Create UDP socket and bind to interface
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode('ascii'))

    # Bind to local address and port
    sock.bind(('', 0))

    # Enable hardware timestamping (if supported)
    # This part may require specific system configuration and permissions
    # sock.setsockopt(socket.SOL_SOCKET, socket.SO_TIMESTAMPING, ...)

    # packet template
    probe_header = struct.pack(PROBE_HEADER_FORMAT, 0xABCD1234, sender_id, 0, 0)  # hop_count=0 initially
    empty_hops = b''.join([struct.pack(HOP_DATA_FORMAT, 0, 0, 0, 0) for _ in range(4)])
    probe_header = probe_header + empty_hops
    
    for seq in range(count):
        # construct packet
        payload = probe_header[:8] + struct.pack("!I", seq) + probe_header[12:]  # update seq_no
        # pad to desired packet size
        if len(payload) < packet_size:
            payload += b'P' * (packet_size - len(payload))

        # Send packet
        sock.sendto(payload, (target_ip, 7777))
        logger.info(f"Sent probe packet seq_no={seq}")
        time.sleep(interval_us / 1e6)  # convert microseconds to seconds

##############################################################################
#                   Scapy-based Packet Sending
##############################################################################

# define custom packet structures
class ProbeHeader(Packet):
    name = "ProbeHeader"
    fields_desc = [
        ByteField("sender_id", 0),
        IntField("seq_no", 0),
        ByteField("hop_count", 0)
    ]

class HopData(Packet):
    name = "HopData"
    fields_desc = [
        ByteField("switch_id", 0),
        BitField("ingress_ts", 0, 64),
        BitField("egress_ts", 0, 64),
        ShortField("port_id", 0)
    ]

def scapy_send_probes(target_mac, target_ip, sender_id, interface, count=100, interval=0.1):
    print(f"Sending {count} probe packets from sender {sender_id} to {target_ip} on interface {interface}...")
    # Prepare the packet template with custom headers
    # Leave space for hop data for up to 4 hops
    empty_hops = HopData()
    for _ in range(3):
        empty_hops = empty_hops / HopData()
    
    for seq in range(count):
        pkt = Ether(src=args.src_mac, dst=target_mac) / \
              IP(src=args.src_ip, dst=target_ip) / \
              UDP(sport=7777, dport=7777) / \
              ProbeHeader(sender_id=sender_id, seq_no=seq, hop_count=0) / \
              empty_hops / \
              Raw("PAYLOAD_PADDING")
              
        sendp(pkt, iface=interface, verbose=False)
        print(f"Sent probe packet seq_no={seq}")
        time.sleep(interval)

if __name__ == "__main__":
    # basic argument parsing
    argparser = argparse.ArgumentParser(description="Spine-Leaf Topology Probe Packet Sender")
    argparser.add_argument("--use_socket", action="store_true", default=True, help="Use raw socket for sending packets instead of Scapy")
    argparser.add_argument("--src_mac", type=str, default=None, help="Source MAC address of the sender")
    argparser.add_argument("--target_mac", type=str, default=None, help="Target MAC address to send probe packets to")
    argparser.add_argument("--src_ip", type=str, default=None, help="Source IP address of the sender")
    # common sender arguments
    argparser.add_argument("--target_ip", type=str, required=True, help="Target IP address to send probe packets to")
    argparser.add_argument("--sender_id", type=int, required=True, help="Sender ID for the probe packets")
    argparser.add_argument("--namespace", type=str, required=True, help="Network namespace to use")
    argparser.add_argument("--interface", type=str, required=True, help="Network interface to send packets on")
    # packet-level test arguments
    argparser.add_argument("--packet_size", type=int, default=128, help="Size of each probe packet in bytes")
    argparser.add_argument("--packet_count", type=int, default=100, help="Number of probe packets to send")
    argparser.add_argument("--packet_interval", type=float, default=0.1, help="Interval between packets in microseconds")
    args = argparser.parse_args()

    if args.use_socket:
        socket_send_probes(args.sender_id, args.target_ip, args.namespace,
                           args.interface, args.packet_size,
                           args.packet_count, args.packet_interval)
    else:
        scapy_send_probes(args.target_mac, args.target_ip, args.sender_id, args.interface, args.packet_count, args.packet_interval)