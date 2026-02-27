#!/bin/python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2024-06-15
# description: Tofino switch setup utility for latency probing

# This script sets up the Tofino switch according incoming parameters for latency probing tests.
# 1. Reset the switch to a known state.
# 2. Configure forwarding rules based on the specified traffic pattern.
# 3. This script is invoked by the probe_main.py before starting the latency probing.

# This script will call scripts located in the remote tofino switch server via network.
import os
import paramiko
import argparse
from loguru import logger

TOFINO_SSH_HOST = os.getenv("TOFINO_SSH_HOST", "10.0.13.21")
TOFINO_SSH_USER = os.getenv("TOFINO_SSH_USER", "p4")
TOFINO_SSH_PASSWORD = os.getenv("TOFINO_SSH_PASSWORD", "rocks")

def clear_switch(ssh_client, context: dict):
    """Clear existing configurations on the Tofino switch."""
    logger.info("Clearing existing switch configurations...")
    try:
        SETUPENV_SCRIPT_PATH = context.get("SETUPENV_SCRIPT_PATH")
        CLEAR_SCRIPT_PATH = context.get("CLEAR_SCRIPT_PATH")
    except KeyError as e:
        logger.error(f"Missing configuration parameter: {e}")
        raise 

    clear_cmd = f"source {SETUPENV_SCRIPT_PATH} && bfshell -b {CLEAR_SCRIPT_PATH}"
    logger.info(f"Executing switch clearing command: {clear_cmd}")

    stdin, stdout, stderr = ssh_client.exec_command(clear_cmd)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        logger.info("Switch configurations cleared successfully.")
    else:
        logger.error(f"Failed to clear switch configurations. Error: {stderr.read().decode()}")
        raise RuntimeError("Switch configuration clearing failed.")

def config_switch(ssh_client, context: dict):
    """Configure the Tofino switch according to the specified parameters."""
    logger.info("Configuring switch with new parameters...")
    try:
        SETUPENV_SCRIPT_PATH = context.get("SETUPENV_SCRIPT_PATH")
        CONFIG_SCRIPT_PATH = context.get("CONFIG_SCRIPT_PATH")
        PATTERN = context.get("PATTERN")
        RATE = context.get("RATE")
        PACKET_SIZE = context.get("PACKET_SIZE")
        TOPO_YAML = context.get("TOPO_YAML")
    except KeyError as e:
        logger.error(f"Missing configuration parameter: {e}")
        raise

    config_cmd = f"source {SETUPENV_SCRIPT_PATH} --pattern {PATTERN} --rate {RATE} --packet_size {PACKET_SIZE} --topo_yaml {TOPO_YAML} && " \
                 f"bfshell -b {CONFIG_SCRIPT_PATH} "
    logger.info(f"Executing switch configuration command: {config_cmd}")

    stdin, stdout, stderr = ssh_client.exec_command(config_cmd)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        logger.info("Switch configured successfully.")
    else:
        logger.error(f"Failed to configure switch. Error: {stderr.read().decode()}")
        raise RuntimeError("Switch configuration failed.")

def setup_switch(ssh_client, context: dict):
    """Setup the Tofino switch according to the specified parameters."""
    clear_switch(ssh_client, context)
    config_switch(ssh_client, context)

if __name__ == "__main__":
    logger.info("Starting Tofino switch setup utility.")
    parser = argparse.ArgumentParser(description="Setup Tofino switch for latency probing.")
    parser.add_argument("--pattern", type=str, default="SINGLE", help="Traffic pattern (SINGLE or MULTIPLE)")
    parser.add_argument("--rate", type=int, default=10, help="Packet send rate (Gbps)")
    parser.add_argument("--packet_size", type=int, default=1024, help="Packet size in bytes")
    parser.add_argument("--topo_yaml", type=str, default="topo_fully.yaml", help="Topology YAML file")
    args = parser.parse_args()

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(TOFINO_SSH_HOST, username=TOFINO_SSH_USER, password=TOFINO_SSH_PASSWORD)

    setup_context = {
        "PATTERN": args.pattern,
        "RATE": args.rate,
        "PACKET_SIZE": args.packet_size,
        "SETUPENV_SCRIPT_PATH": os.environ.get("SETUPENV_SCRIPT_PATH"),
        "CLEAR_SCRIPT_PATH": os.environ.get("CLEAR_SCRIPT_PATH"),
        "CONFIG_SCRIPT_PATH": os.environ.get("CONFIG_SCRIPT_PATH"),
        "TOPO_YAML": args.topo_yaml
    }

    setup_switch(ssh_client, setup_context)
    ssh_client.close()
