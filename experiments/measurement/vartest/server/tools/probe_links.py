#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2025-12-17
# description: This script is used to send probe packets on specified network interfaces 
# to test link connectivity.
import sys
import time
from scapy.all import *
from loguru import logger

def send_probe(interface, target_ip="10.0.1.1"):
    logger.info(f"[*] Preparing to send probe packets on interface: {interface} to target IP: {target_ip}")

    # construct and send probe packets
    # dst="ff:ff:ff:ff:ff:ff" ensures the packet is not filtered at layer 2
    # raw(load=...) includes a distinctive string for easy identification in packet captures
    pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / \
          IP(dst=target_ip) / \
          UDP(dport=1234) / \
          Raw(load=f"PROBE_FROM_{interface}")
    logger.info(f"[+] Sending probe packets on interface: {interface} to target IP: {target_ip}")

    # Send 10 packets with a short interval
    sendp(pkt, iface=interface, count=10, inter=0.1, verbose=True)
    logger.info(f"[+] Finished sending probe packets on interface: {interface}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error("Usage: python3 probe_links.py <interface>")
        sys.exit(1)
    
    iface = sys.argv[1]
    send_probe(iface)
