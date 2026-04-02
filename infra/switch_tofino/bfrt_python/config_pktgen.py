#!/bfshell/bin/env python3


# descrption: This script configures the packet generator on a Tofino-based switch using BFRT APIs.

import os
import sys
import argparse
import time
from scapy.all import Ether, Raw, IP, UDP
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO")
##########################################################################
# Configuration Parameters
##########################################################################
P4_PROG = os.getenv("P4_PROG", "hybrid_arch")
PKTGEN_APP_ID = int(os.getenv("PKTGEN_APP_ID", "1"))
PKTGEN_PORT_ID = int(os.getenv("PKTGEN_PORT_ID", "6"))

# Default for packet
SRC_MAC = os.environ.get("SRC_MAC", "00:0a:35:06:50:95")
DST_MAC = os.environ.get("DST_MAC", "00:0a:35:06:50:94")
SRC_IP = os.environ.get("SRC_IP", "177.0.1.2")
DST_IP = os.environ.get("DST_IP", "177.0.1.1")
SRC_PORT = int(os.environ.get("SRC_PORT", "1999"))
DST_PORT = int(os.environ.get("DST_PORT", "1999"))


###########################################################################
# Packet Creation Function
###########################################################################
def calc_timer_nanoseconds(rate_Gbps: int, packet_size: int) -> int:
    assert rate_Gbps > 0, "Rate must be greater than 0"
    
    total_bytes = packet_size + 20  # Adding 20 bytes for inter-frame gap and preamble
    bits_per_second = rate_Gbps * 1_000_000_000
    packets_per_second = bits_per_second / (total_bytes * 8)
    timer_ns = int(1_000_000_000 / packets_per_second)
    return timer_ns

def make_packet(packet_size: int) -> Ether:
    """Create a dummy packet of specified size."""
    assert packet_size >= 64, "Packet size must be at least 64 bytes"
    payload_size = packet_size - 14 - 20 - 8  # Ethernet + IP + UDP headers

    pkt = Ether(src=SRC_MAC, dst=DST_MAC) / \
          IP(src=SRC_IP, dst=DST_IP) / \
          UDP(sport=SRC_PORT, dport=DST_PORT) / \
          Raw(load=b'7' * payload_size)
    return pkt

###########################################################################
# Packet Generator Configuration Function
###########################################################################

def config_pktgen_buffers(bfrt, rate: int, packet_size: int):
    """Configure packet generator buffers with specified rate and packet size."""
    logger.info("Configuring Packet Generator Buffers")
    pktgen_buffer = bfrt.tf2.pktgen.pkt_buffer
    
    # Create Packet Buffer Entry
    packet = make_packet(packet_size)

    # Write Packet to Buffer
    buffer_entry = pktgen_buffer.entry(
        pkt_buffer_offset=0,
        pkt_buffer_size=len(packet),
        buffer=list(packet.build())
    )
    buffer_entry.push()
    logger.info("Packet written to buffer")
    
def config_pktgen_app(bfrt, rate: int, packet_size: int):
    """Configure packet generator application with specified rate and packet size."""
    logger.info("Configuring Packet Generator Application")
    pktgen_app = bfrt.tf2.pktgen.app_cfg

    timer_ns = calc_timer_nanoseconds(rate, packet_size)

    # Create App Entry
    app_entry = pktgen_app.entry_with_trigger_timer_periodic(
        app_id=PKTGEN_APP_ID,
        app_enable=True,
        pkt_buffer_offset=0,
        pkt_len=packet_size,
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
    logger.info(f"Packet Generator App configured: Rate={rate}Gbps, Packet Size={packet_size} bytes")

def config_pktgen_ports(bfrt):
    """Enable Packet Generator on specified port."""
    logger.info("Configuring Packet Generator Ports")
    pktgen_port = bfrt.tf2.pktgen.port_cfg

    port_entry = pktgen_port.entry(
        dev_port=PKTGEN_PORT_ID,
        pktgen_enable=True
    )
    port_entry.push()
    logger.info(f"Packet Generator enabled on port {PKTGEN_PORT_ID}")
    
############################################################################
# Main Function
############################################################################
def argument_parser():
    parser = argparse.ArgumentParser(
        description="Configure Packet Generator on Tofino Switch"
    )
    parser.add_argument("--rate", type=int, default=10,
                        help="Packet generation rate in Gbps (default: 10)")
    parser.add_argument("--packet_size", type=int, default=1024,
                        help="Packet size in bytes (default: 1024)")
    
    return parser

def main():
    logger.info("Starting Packet Generator Configuration Script")
    args = argument_parser().parse_args()

    assert 'bfrt' in globals(), "This script must be run using bfshell to access BFRT APIs."
    bfrt = globals()['bfrt']

    config_pktgen_buffers(bfrt, args.rate, args.packet_size)

    config_pktgen_app(bfrt, args.rate, args.packet_size)

    config_pktgen_ports(bfrt)
    logger.info("Packet Generator Configuration Completed")

if __name__ == "__main__":
    main()
