#!/python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2025-12-17
# description: Tofino Spine-Leaf Topology Latency Probing Module

# - This module probes the latency of packets going through a Tofino switch
#   in a spine-leaf topology.

import os
import sys
import paramiko
import threading
import time
import subprocess
import argparse
from loguru import logger
logger.remove()
logger.add(sys.stdout, level="INFO")

# define worker nodes information
SEND_WORKERS = [
    # Node 6 (Sender)
    {
        "hostname": "inet-p4lab-12",
        "user": os.getenv("TESTBED_USER"), # get from env.sh
        "password": os.getenv("TESTBED_PASSWD"), # get from env.sh
        "id": 6,
        "namespace": "node6",
        "interface": "enp177s0np0",
    },
    # Node 5 (Sender)
    {
        "hostname": "inet-p4lab-12",
        "user": os.getenv("TESTBED_USER"), # get from env.sh
        "password": os.getenv("TESTBED_PASSWD"), # get from env.sh
        "id": 5,
        "namespace": "node5",
        "interface": "enp202s0np0"
    },
    # Node 4 (Sender)
    {
        "hostname": "inet-p4lab-13",
        "user": os.getenv("TESTBED_USER"), # get from env.sh
        "password": os.getenv("TESTBED_PASSWD"), # get from env.sh
        "id": 4,
        "namespace": "node4",
        "interface": "enp177s0np0"
    },
    # Node 3 (Sender)
    {
        "hostname": "inet-p4lab-13",
        "user": os.getenv("TESTBED_USER"), # get from env.sh
        "password": os.getenv("TESTBED_PASSWD"), # get from env.sh
        "id": 3,
        "namespace": "node3",
        "interface": "enp202s0np0"
    },
    # Node 2 (Sender)
    {
        "hostname": "inet-p4lab-14",
        "user": os.getenv("TESTBED_USER"), # get from env.sh
        "password": os.getenv("TESTBED_PASSWD"), # get from env.sh
        "id": 2,
        "namespace": "node2",
        "interface": "enp177s0np0"
    },
]

RECV_ID = {
    "ip": "10.0.1.1",
    "mac": "00:0a:35:06:50:94",
    "namespace": "node1",
    "interface": "enp202s0np0"
}

SEND_WORKER_SCRIPT_PATH = "/home/yukema/OpticalDCN/measurement/vartest/server/utils/spineleaf_send_worker.py"
RECV_WORKER_SCRIPT_PATH = "/home/yukema/OpticalDCN/measurement/vartest/server/utils/spineleaf_recv_worker.py"

############################################################################
#                   Sending Worker Triggering
############################################################################
def trigger_worker(worker):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        logger.info(f"Connecting to worker {worker['id']} at {worker['hostname']}...")
        ssh.connect(worker['hostname'], username=worker['user'], password=worker['password'])
        
        cmd = f"echo '{worker['password']}' | sudo -S -E ip netns exec {worker['namespace']} \
            python3 {SEND_WORKER_SCRIPT_PATH} \
            --target_ip {RECV_ID['ip']} \
            --sender_id {worker['id']} \
            --namespace {worker['namespace']} \
            --interface {worker['interface']} \
            --packet_count {worker['packet_count']} \
            --packet_size {worker['packet_size']} \
            --packet_interval {1.0 / (worker['rate'] * 1e9 / (worker['packet_size'] + 54))} \
            --use_socket"
        
        stdin, stdout, stderr = ssh.exec_command(cmd)
        logger.info(f"Started sending probes on worker {worker['id']}.")
        for line in stdout:
            logger.info(f"[Worker {worker['id']}] {line.strip()}")
        for line in stderr:
            logger.error(f"[Worker {worker['id']} ERROR] {line.strip()}")
        ssh.close()
    except Exception as e:
        logger.error(f"Error on worker {worker['id']}: {e}")

############################################################################
#                   Receiver Starting
############################################################################
def start_receiver(args):
    logger.info("Starting receiver on controller...")
    receiver_cmd = ""
    timeout = 120
    receiver_cmd = f"python3 {RECV_WORKER_SCRIPT_PATH} \
        --namespace {RECV_ID['namespace']} \
        --interface {RECV_ID['interface']} \
        --timeout {timeout}"
    receiver_process = subprocess.Popen(receiver_cmd, shell=True)
    return receiver_process

############################################################################
#                   Main Function
############################################################################

def main():
    logger.info("Starting Spine-Leaf Topology Latency Probing Coordinator...")
    argparser = argparse.ArgumentParser(description="Spine-Leaf Topology Latency Probing Coordinator")
    argparser.add_argument("--packet_size", type=int, default=128, help="Size of each probe packet in bytes")
    argparser.add_argument("--packet_count", type=int, default=100, help="Number of probe packets to send per sender")
    argparser.add_argument("--rate", type=int, default=1, help="Bandwidth rate limit per sender in Gbps")
    args = argparser.parse_args()

    # 1. Start the receiver thread
    logger.info("Starting receiver...")
    receiver_process = start_receiver(args)

    time.sleep(2) # wait a bit for receiver to start

    # 2. Trigger sending workers
    logger.info("Starting sending workers...")
    threads = []
    for w in SEND_WORKERS:
        w["packet_size"] = args.packet_size
        w["packet_count"] = args.packet_count
        w["rate"] = args.rate
        t = threading.Thread(target=trigger_worker, args=(w,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # 3. Wait for receiver to finish
    if receiver_process:
        receiver_process.wait()
        logger.info("Receiver process finished.")
    
    logger.info("Spine-Leaf Topology Latency Probing Completed.")

if __name__ == "__main__":
    main()
