#!/bfshell/bin/env python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2025-11-28
# description: Tofino switch setup utility for latency probing


# This script sets up the Tofino switch according to incoming parameters for latency probing tests.
# 1. Configure forwarding rules based on the specified traffic pattern.
# 2. This script is invoked by the probe_main.py before starting the latency probing.

import json
import os
import sys
import argparse
import yaml
from scapy.all import Ether, IP, UDP, Raw
from loguru import logger
logger.remove()
logger.add(sys.stdout, level="INFO")

###################################################
#                 Configuration
###################################################
PROJ_ROOT = os.environ.get('PROJ_ROOT', '/home/p4/vartest')

P4_PROG = os.environ.get('P4_PROG', 'ts_pipeline')
PKTGEN1_APP_ID = int(os.environ.get('PKTGEN1_APP_ID', '1'))  # Default application ID
PKTGEN1_PORT_ID = int(os.environ.get('PKTGEN1_PORT_ID', '6'))  # Default pktgen port ID
PKTGEN2_APP_ID = int(os.environ.get('PKTGEN2_APP_ID', '2'))  # Second application ID
PKTGEN2_PORT_ID = int(os.environ.get('PKTGEN2_PORT_ID', '68'))  # Second pktgen port ID

# Defaults for packet
SRC_MAC = os.environ.get('SRC_MAC', "00:11:22:33:44:55")
DST_MAC = os.environ.get('DST_MAC', "66:77:88:99:AA:BB")
SRC_IP = os.environ.get('SRC_IP', "10.0.0.1")
DST_IP = os.environ.get('DST_IP', "10.0.0.2")
SRC_PORT = int(os.environ.get('SRC_PORT', '1234'))
DST_PORT = int(os.environ.get('DST_PORT', '5678'))
TOPO_YAML_PATH = os.environ.get('TOPO_YAML', f'{PROJ_ROOT}/tofino/topo_fully.yaml')

###############################################
#               Helper Functions
###############################################
def get_timer_nanosec(pkt_size: int, rate_Gbps: float) -> int:
    assert rate_Gbps > 0, "Rate must be greater than 0 Gbps"

    total_bytes = pkt_size + 20  # Adding overhead bytes
    total_bits = total_bytes * 8
    
    # Rate is in Gbps
    time_ns = total_bits / rate_Gbps    # in nanoseconds
    return int(time_ns) 

def make_packet(size: int) -> Ether:
    assert size >= 64, "Packet size must be at least 64 bytes"

    # subtract packet header size: Ethernet (14 bytes) + IP (20 bytes) + UDP (8 bytes)
    payload_size = size - 14 - 20 - 8
    packet = Ether(dst=DST_MAC, src=SRC_MAC) / \
            IP(src=SRC_IP, dst=DST_IP) / \
            UDP(sport=SRC_PORT, dport=DST_PORT) / \
            Raw(load=bytes([0x17] * payload_size))

    return packet

def parser_topology(bfrt, yaml_path: str) -> dict:
    """Parse topology YAML file to get device and port mappings."""
    with open(yaml_path, 'r') as f:
        topo = yaml.safe_load(f)
    
    topo_config = {}

    # parse ports info
    topo_ports = {}
    for name, spec, in topo.get('ports', {}).items():
        port_attrs = {}
        port_attrs['conn_id'] = int(spec.get('conn_id'))
        port_attrs['chnl_id'] = int(spec.get('chnl_id'))
        port_attrs['FPGA'] = bool(spec.get('FPGA', False))

        # get dev port
        dev_port = bfrt.port.port_hdl_info.get(CONN_ID=port_attrs['conn_id'], CHNL_ID=port_attrs['chnl_id']).data[b'$DEV_PORT']
        port_attrs['dev_port'] = int(dev_port)
        topo_ports[name] = port_attrs
    topo_config['ports'] = topo_ports
    
    # add special port pktgen
    topo_config['ports']['pktgen1'] = {
        'conn_id': PKTGEN1_PORT_ID,
        'chnl_id': 0,
        'FPGA': False,
        'dev_port': PKTGEN1_PORT_ID
    }

    # parse farwading rules info
    topo_fwd_rules = {}
    fwd_rules = topo.get('fwd_rules', {})

    # 1. bi-directional rules
    bi_dir_rules = fwd_rules.get('bi-directional', [])
    topo_fwd_rules['bi-directional'] = bi_dir_rules

    # 2. uni-directional rules
    uni_dir_rules = fwd_rules.get('uni-directional', [])
    topo_fwd_rules['uni-directional'] = uni_dir_rules

    topo_config['fwd_rules'] = topo_fwd_rules

    return topo_config

################################################
#            Switch Configuration Functions
################################################
def config_pktgen_buffer(bfrt, rate: int, packet_size: int):
    """Configure pktgen buffer with specified rate and packet size."""
    logger.info("Configuring pktgen buffer...")
    pktgen_buffer = bfrt.tf2.pktgen.pkt_buffer

    # Create packet
    packet = make_packet(packet_size)
    
    # Write packet to pktgen buffer
    logger.info(f"Writing packet of size {len(packet)} bytes to pktgen buffer...")
    buffer_entry = pktgen_buffer.entry(
        pkt_buffer_offset=0,
        pkt_buffer_size=len(packet),
        buffer=list(packet.build())
    )
    buffer_entry.push()
    logger.info("Packet written to pktgen buffer.")

def config_pktgen_app(bfrt, rate: int, packet_size: int):
    """Configure pktgen application with specified rate and packet size."""
    logger.info("Configuring pktgen application...")
    pktgen_app = bfrt.tf2.pktgen.app_cfg

    timer_ns = get_timer_nanosec(packet_size, rate)
    logger.info(f"Setting pktgen timer to {timer_ns} ns for rate {rate} Gbps and packet size {packet_size} bytes")

    # Configure pktgen application
    app1_entry = pktgen_app.entry_with_trigger_timer_periodic(
        app_id = PKTGEN1_APP_ID,
        app_enable = True,
        pkt_buffer_offset = 0,
        pkt_len = packet_size,
        pipe_local_source_port = PKTGEN1_PORT_ID,
        increment_source_port = False,
        timer_nanosec = timer_ns,
        batch_count_cfg = 0,
        packets_per_batch_cfg = 0,
        ibg = 0, ibg_jitter = 0,
        ipg = 0, ipg_jitter = 0,
        batch_counter = 0, pkt_counter = 0, trigger_counter = 0,
        offset_len_from_recir_pkt_enable = False,
        source_port_wrap_max = 0,
        assigned_chnl_id = PKTGEN1_PORT_ID,
    )
    app1_entry.push()
    logger.info("Pktgen application 1 configured.")

def config_pktgen_ports(bfrt):
    """Configure pktgen ports."""
    logger.info("Configuring pktgen ports...")
    pktgen_port = bfrt.tf2.pktgen.port_cfg

    port1_entry = pktgen_port.entry(
        dev_port=PKTGEN1_PORT_ID,
        pktgen_enable=True
    )
    port1_entry.push()

    logger.info("Pktgen ports configured.")

def configure_forward_rules(bfrt, topo_config: dict):
    """Configure the Tofino switch according to the specified parameters."""
    logger.info("Configuring forwarding rules...")
    # Config forwarding rules based on topology config
    fwd_rules = topo_config.get('fwd_rules', {})
    fwd_table = bfrt.ts_pipeline.pipe.Ingress.pass_through
    # 1. Bi-directional rules 
    bi_dir_rules = fwd_rules.get('bi-directional', [])
    for rule in bi_dir_rules:
        logger.info(f"Configuring bi-directional rule: {rule}")
        # Add logic to configure bi-directional forwarding rules here
        src_port_name, dst_port_name = rule
        src_port = topo_config['ports'][src_port_name]['dev_port']
        dst_port = topo_config['ports'][dst_port_name]['dev_port']
        try:
            fwd_table.add_with_set_port(ingress_port=src_port, egress_port=dst_port)
            fwd_table.add_with_set_port(ingress_port=dst_port, egress_port=src_port)
        except Exception as e:
            if 'Already' in str(e):
                logger.warning(f"Rule already exists: {e}")
            else:
                logger.error(f"Failed to add table entry: {e}")
                raise e
        
    # 2. Uni-directional rules
    uni_dir_rules = fwd_rules.get('uni-directional', [])
    for rule in uni_dir_rules:
        logger.info(f"Configuring uni-directional rule: {rule}")
        # Add logic to configure uni-directional forwarding rules here
        src_port_name, dst_port_name = rule
        src_port = topo_config['ports'][src_port_name]['dev_port']
        dst_port = topo_config['ports'][dst_port_name]['dev_port']
        try:
            fwd_table.add_with_set_port(ingress_port=src_port, egress_port=dst_port)
        except Exception as e:
            if 'Already' in str(e):
                logger.warning(f"Rule already exists: {e}")
            else:
                logger.error(f"Failed to add table entry: {e}")
                raise e
    
    logger.info("Forwarding rules configured.")

###########################################
#            Main Function
###########################################
def main():
    """Main function to configure the switch."""
    logger.info("Starting Tofino switch configuration...")
    # TODO: using bfshell we cannot pass command line arguments directly
    # so we read from a temp json file written by probe_main.py.
    # In future we can improve this by using bfrt APIs to pass parameters directly.
    # Parse command line arguments
    #parser = argparse.ArgumentParser(description="Configure Tofino switch for latency probing.")
    #parser.add_argument('--rate', type=int, default=10, help='Packet sending rate(Gbps)')
    #parser.add_argument('--packet_size', type=int, default=1024, help='Size of each packet (bytes)')
    #args = parser.parse_args()

    # Assuming bfshell environment is already set up
    assert 'bfrt' in globals(), "This script must be run within the bfshell environment."
    bfrt = globals()['bfrt']

    with open("/tmp/tofino_env.json", "r") as f:
        env_config = json.load(f)

    rate = int(env_config.get("RATE", 10))
    packet_size = int(env_config.get("PACKET_SIZE", 1024))
    topo_yaml = env_config.get("TOPO_YAML", TOPO_YAML_PATH)

    topo_config = parser_topology(bfrt, topo_yaml)

    # 1. Configure forwarding rules
    configure_forward_rules(bfrt, topo_config)

    # 2. Configure pktgen buffer
    config_pktgen_buffer(bfrt, rate, packet_size)
    
    # 3. Configure pktgen application
    config_pktgen_app(bfrt, rate, packet_size)
    
    # 4. Configure pktgen ports
    config_pktgen_ports(bfrt)

if __name__ == "__main__":
    main()
