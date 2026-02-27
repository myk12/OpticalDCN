#!/bin/bash/env python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2024-06-10
# description: Tofino latency probing module

# - This module probes the latency of packets going through a Tofino switch.
#   It starts a packet sender to send packets and a receiver to capture them,
#   measuring the time taken for packets to traverse the switch.
# - One thread is used for sending packets, and another for receiving them.

import struct
import ctypes
import os
import argparse
import paramiko
import time
from loguru import logger
from utils.setup_switch import clear_switch, config_switch
from utils.start_probing import start_probing

#======================= Configurations =======================#
SENDER_NS = os.getenv("NS1", "fpganic_p1")
RECEIVER_NS = os.getenv("NS2", "fpganic_p2")
SENDER_IFACE = os.getenv("PORTNAME1", "enp202s0np0")
RECEIVER_IFACE = os.getenv("PORTNAME2", "enp202s0np1")
SENDER_IP = os.getenv("IP1", "10.0.0.1")
RECEIVER_IP = os.getenv("IP2", "10.0.0.2")

TOFINO_SSH_HOST = os.getenv("TOFINO_SSH_HOST", "10.0.13.21")
TOFINO_SSH_USER = os.getenv("TOFINO_SSH_USER", "p4")
TOFINO_SSH_PASSWORD = os.getenv("TOFINO_SSH_PASSWORD", "rocks")

SETUPENV_SCRIPT_PATH = os.getenv("SETUPENV_SCRIPT_PATH", "/home/p4/vartest/tofino/set_env.bash")
CLEAR_SCRIPT_PATH = os.getenv("CLEAR_SCRIPT_PATH", "/home/p4/vartest/tofino/bfrt/bfrt_clear_switch.py")
CONFIG_SCRIPT_PATH = os.getenv("CONFIG_SCRIPT_PATH", "/home/p4/vartest/tofino/bfrt/bfrt_config_switch.py")
FULL_CONFIG_SCRIPT_PATH = os.getenv("FULL_CONFIG_SCRIPT_PATH", "/home/p4/vartest/tofino/bfrt/bfrt_full_setup.py")
FULL_TOPO_YAML_PATH = os.getenv("FULL_TOPO_YAML_PATH", "topo_fully.yaml")

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

def main():
    logger.info("Starting Tofino latency probing module.")
    # check root privilege
    if os.geteuid() != 0:
        logger.error("This script must be run as root.")
        exit(1)
    
    argparser = argparse.ArgumentParser(description="Tofino Latency Probing Module")
    argparser.add_argument('--pattern', type=str, choices=['SINGLE', 'MULTIPLE', 'FULL'], default='SINGLE',
                           help='Traffic pattern to use for probing')
    argparser.add_argument('--rate', type=int, default=10,
                           help='Packet send rate (Gbps)')
    argparser.add_argument('--packet_size', type=int, default=1024,
                           help='Packet size in bytes')
    argparser.add_argument('--topo_yaml', type=str, default='topo_fully.yaml',
                           help='Topology YAML file')
    argparser.add_argument('--result_dir', type=str, default="./results",
                           help='Directory to save results')
    args = argparser.parse_args()
    
    # create SSH client to connect to Tofino switch
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(TOFINO_SSH_HOST, username=TOFINO_SSH_USER, password=TOFINO_SSH_PASSWORD)
    
    context = {
        "PATTERN": args.pattern,
        "RATE": args.rate,
        "PACKET_SIZE": args.packet_size,
        "TOFINO_SSH_HOST": TOFINO_SSH_HOST,
        "TOFINO_SSH_USER": TOFINO_SSH_USER,
        "TOFINO_SSH_PASSWORD": TOFINO_SSH_PASSWORD,
        "SETUPENV_SCRIPT_PATH": SETUPENV_SCRIPT_PATH,
        "CLEAR_SCRIPT_PATH": CLEAR_SCRIPT_PATH,
        "CONFIG_SCRIPT_PATH": FULL_CONFIG_SCRIPT_PATH,
        "TOPO_YAML": args.topo_yaml
    }

    logger.info("Context for switch setup: {}".format(context))

    # clear remote Tofino switch configurations
    logger.info("Clearing remote Tofino switch configurations.")
    clear_switch(ssh_client, context)
    # configure remote Tofino switch
    logger.info("Configuring remote Tofino switch.")
    config_switch(ssh_client, context)
    ssh_client.close()
    
    # wait a bit for switch to stabilize
    time.sleep(5)

    # start probing processes
    start_probing(result_dir=args.result_dir, pattern=args.pattern, rate=args.rate, packet_size=args.packet_size)

    # clear remote Tofino switch configurations after probing
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(TOFINO_SSH_HOST, username=TOFINO_SSH_USER, password=TOFINO_SSH_PASSWORD)
    logger.info("Clearing remote Tofino switch configurations after probing.")
    clear_switch(ssh_client, context)
    ssh_client.close()

if __name__ == "__main__":
    main()
