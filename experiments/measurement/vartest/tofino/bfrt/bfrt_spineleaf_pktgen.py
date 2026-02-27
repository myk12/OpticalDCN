#!/bfshell/bin/env python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2025-12-23

# description: Tofino BFRT Spine-Leaf Topology Packet Generator Setup

import os
import sys
import argparse
import time
from scapy.all import *
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO")

###################################################
#                 Configuration
###################################################
P4_PROG = os.environ.get('P4_PROG', 'spineleaf_topo')
PKTGEN_APP_ID = int(os.environ.get('PKTGEN_APP_ID', '1'))  # Default application ID
PKTGEN_PORT_ID = int(os.environ.get('PKTGEN_PORT_ID', '6'))  # Default pktgen port ID

# from fpga_7 port 0 to fpga_1 port 0
SRC_MAC = os.environ.get('SRC_MAC', "00:0a:35:06:09:9c")
DST_MAC = os.environ.get('DST_MAC', "00:0a:35:06:50:94")
SRC_IP = os.environ.get('SRC_IP', "10.0.3.3")
DST_IP = os.environ.get('DST_IP', "10.0.1.1")
UDP_PORT = 7777

# Port definitions
# Leaf 1
LEAF1_P1 = 1  # to server 1 nic 1
LEAF1_P2 = 2  # to server 1 nic 2
LEAF1_P4 = 4  # to spine switch

# Logical switch ID for this setup
LEAF1_ID = 1
LEAF2_ID = 2
LEAF3_ID = 3
LEAF4_ID = 4
SPINE_ID = 10

# Header format:
# | Eth (14 bytes) | IP (20 bytes) | UDP (8 bytes) | Vartest () |
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
PROBE_HEADER_FORMAT = "!IIII"
HOP_DATA_FORMAT = "!QQII"  # ingress_ts, egress_ts, ingress_port, egress_port
HOP_DATA_SIZE = 32  # bytes per hop

class ProbeHeader(Packet):
    name = "ProbeHeader"
    fields_desc = [
        IntField("magic_number", 0xABCD1234),
        IntField("sender_id", 0),
        IntField("seq_no", 0),
        IntField("hop_count", 0),
        # Hop data will be added dynamically
    ]
    
class HopData(Packet):
    name = "HopData"
    fields_desc = [
        LongField("ts_ingress", 0),
        LongField("ts_egress", 0),
        IntField("ingress_port", 0),
        IntField("egress_port", 0),
    ]

###############################################
#               Helper Functions
###############################################
def get_timer_nanosec(pkt_size: int, rate_Gbps: float) -> int:
    """Calculate timer in nanoseconds based on packet size and rate in Gbps."""
    assert rate_Gbps > 0, "Rate must be greater than 0 Gbps"

    total_bytes = pkt_size + 20  # Adding overhead bytes
    total_bits = total_bytes * 8
    
    # Rate is in Gbps
    time_ns = total_bits / rate_Gbps    # in nanoseconds
    return int(time_ns)

def make_packet(size: int) -> Ether:
    """Create a dummy packet of specified size."""
    assert size >= 64, "Packet size must be at least 64 bytes"
    
    # empty hops for 4 hops
    empty_hops = HopData() / HopData() / HopData() / HopData()
    probe_header = ProbeHeader(sender_id=100, seq_no=1, hop_count=0)

    # subtract packet header size: Ethernet (14 bytes) + IP (20 bytes) + UDP (8 bytes)
    payload_size = size - 14 - 20 - 8 - len(empty_hops) - len(ProbeHeader())
    logger.info(f"Creating packet of size {size} bytes with payload size {payload_size} bytes")
    pkt = Ether(src=SRC_MAC, dst=DST_MAC) / \
          IP(src=SRC_IP, dst=DST_IP) / \
          UDP(sport=UDP_PORT, dport=UDP_PORT) / \
            probe_header / \
            empty_hops / \
          Raw(load=b'7' * payload_size)
    logger.info(f"Packet created: {pkt.summary()}")

    return pkt

def get_port_hdl(bfrt, conn_id: int, chnl_id: int) -> int:
    """Get the device port handle from connection ID and channel ID."""
    dev_port = bfrt.port.port_hdl_info.get(CONN_ID=conn_id, CHNL_ID=chnl_id, print_ents=False).data[b'$DEV_PORT']
    return int(dev_port)

###############################################
#           Packet Generator Configuration
###############################################
def config_pktgen_buffer(bfrt, rate: int, pkt_size: int):
    """Configure the packet generator buffer settings."""
    logger.info(f"Configuring packet generator buffer with rate: {rate} Gbps, packet size: {pkt_size} bytes")
    pktgen_buffer = bfrt.tf2.pktgen.pkt_buffer
    pktgen_buffer.clear()

    packet = make_packet(pkt_size)

    # Write packet to pktgen buffer
    logger.info("Writing packet to pktgen buffer...")
    buffer_entry = pktgen_buffer.entry(
        pkt_buffer_offset=0,
        pkt_buffer_size=len(packet),
        buffer=list(packet.build())
    )
    buffer_entry.push()
    logger.info("Packet written to pktgen buffer.")

def stop_pktgen_app(bfrt, app_id: int):
    """Stop the packet generator application."""
    logger.info(f"Stopping packet generator app with app_id: {app_id}")
    pktgen_app = bfrt.tf2.pktgen.app_cfg
    pktgen_app.mod_with_trigger_timer_periodic(app_id=app_id, app_enable=False)
    logger.info("Packet generator app stopped.")

def config_pktgen_app(bfrt, app_id: int, port_id: int, rate: int, pkt_size: int):
    """Configure the packet generator application settings."""
    logger.info(f"Configuring packet generator app with app_id: {app_id}, port_id: {port_id}, rate: {rate} Gbps, packet size: {pkt_size} bytes")
    pktgen_app = bfrt.tf2.pktgen.app_cfg

    timer_ns = get_timer_nanosec(pkt_size, rate)
    
    # configure pktgen app
    app_entry = pktgen_app.entry_with_trigger_timer_periodic(
        app_id=PKTGEN_APP_ID,
        app_enable=True,
        pkt_buffer_offset=0,
        pkt_len=pkt_size,
        pipe_local_source_port=PKTGEN_PORT_ID,
        increment_source_port=False,
        timer_nanosec=timer_ns,
        batch_count_cfg=0,
        packets_per_batch_cfg=0,
        ibg=0, ibg_jitter=0,
        ipg=0, ipg_jitter=0,
        batch_counter=0, pkt_counter=0, trigger_counter=0,
        offset_len_from_recir_pkt_enable=False,
        source_port_wrap_max=0,
        assigned_chnl_id=PKTGEN_PORT_ID,
    )
    app_entry.push()
    logger.info("Packet generator app configured.")

def config_pktgen_port(bfrt):
    """Configure the packet generator port settings."""
    logger.info(f"Configuring packet generator port with port_id: {PKTGEN_PORT_ID}")
    pktgen_port = bfrt.tf2.pktgen.port_cfg

    port_entry = pktgen_port.entry(
        dev_port=PKTGEN_PORT_ID,  # adjust for device port mapping
        pktgen_enable=True
    )
    port_entry.push()
    logger.info("Packet generator port configured.")

####################################################
#           Generated Packet forwarding
####################################################
def add_port_mapping(bfrt, pktgen_port: int, log_switch_id: int):
    """Add forwarding rules for the generated packets."""
    logger.info(f"Adding forwarding rules for pktgen_port: {pktgen_port}, log_switch_id: {log_switch_id}")
    port_mapping_table = bfrt.spineleaf_topo.pipe.SnosIngress.t_port_mapping

    # delete existing entry
    try:
        port_mapping_table.delete(ingress_port=pktgen_port)
        logger.info("Existing port mapping entry deleted.")
    except Exception as e:
        logger.info("No existing port mapping entry to delete.")

    try:
        port_mapping_table.add_with_set_logical_switch(
            ingress_port=pktgen_port,
            switch_id=log_switch_id
        )
        logger.info("Port mapping entry added.")
    except Exception as e:
        if "Already exists" in str(e):
            logger.warning("Port mapping entry already exists. Skipping addition.")
        else:
            raise e

def add_ipv4_route(bfrt, log_switch_id: int, dst_ip: str, prefix_len: int, out_port: int):
    """Add IPv4 routing entry."""
    logger.info(f"Adding IPv4 route: log_switch_id={log_switch_id}, dst_ip={dst_ip}/{prefix_len} -> out_port={out_port}")
    dev_port = get_port_hdl(bfrt, out_port, 0)
    ipv4_table = bfrt.spineleaf_topo.pipe.SnosIngress.t_ipv4_lpm
    try:
        ipv4_table.add_with_ipv4_forward(
            logical_switch_id=log_switch_id,
            dst_addr=dst_ip,
            dst_addr_p_length=prefix_len,
            port=dev_port
        )
        logger.info(f"IPv4 route added for dst_ip={dst_ip}/{prefix_len} on switch_id={log_switch_id}")
    except Exception as e:
        if "Already exists" in str(e):
            logger.warning("IPv4 route entry already exists. Skipping addition.")
        else:
            raise e

def add_pass_through_route(bfrt, ingress_port: int, egress_port: int):
    """Add pass through routing entry for non-IPv4 packets."""
    logger.info(f"Adding pass through route: ingress_port={ingress_port} -> egress_port={egress_port}")
    dev_port = get_port_hdl(bfrt, egress_port, 0)
    pass_through_table = bfrt.spineleaf_topo.pipe.SnosIngress.pass_through
    try:
        pass_through_table.add_with_set_port(
            ingress_port=ingress_port, # no hdl conversion needed for pktgen port
            egress_port=dev_port
        )
        logger.info(f"Pass through route added for ingress_port={ingress_port} to egress_port={egress_port}")
    except Exception as e:
        if "Already exists" in str(e):
            logger.warning("Pass through route entry already exists. Skipping addition.")
        else:
            raise e

###################################################
#                   Main Function
###################################################
def main():
    parser = argparse.ArgumentParser(description="Tofino BFRT Spine-Leaf Topology Packet Generator Setup")
    parser.add_argument('--p4_prog', type=str, default=P4_PROG, help='P4 program name')
    parser.add_argument('--app_id', type=int, default=PKTGEN_APP_ID, help='Packet generator application ID')
    parser.add_argument('--port_id', type=int, default=PKTGEN_PORT_ID, help='Packet generator port ID')
    parser.add_argument('--rate', type=int, default=1, help='Packet generation rate in Gbps')
    parser.add_argument('--pkt_size', type=int, default=1024, help='Packet size in bytes (minimum 64 bytes)')
    args = parser.parse_args()

    # get BFRT instance from globals
    assert 'bfrt' in globals(), "This script must be run in bfshell with bfrt loaded."
    bfrt = globals()['bfrt']

    # Add forwarding rules
    add_port_mapping(bfrt, args.port_id, LEAF3_ID)  # assuming pktgen on Leaf 4

    # Add pass through route for generated packets
    #add_pass_through_route(bfrt, PKTGEN_PORT_ID, LEAF1_P1)  # forward to server 1 nic 1
    
    # Configure packet generator buffer
    config_pktgen_buffer(bfrt, args.rate, args.pkt_size)

    # Configure packet generator application
    stop_pktgen_app(bfrt, args.app_id)
    config_pktgen_app(bfrt, args.app_id, args.port_id, args.rate, args.pkt_size)

    # Configure packet generator port
    config_pktgen_port(bfrt)
    logger.info("Tofino Spine-Leaf Topology Packet Generator setup complete.")

if __name__ == "__main__":
    main()
