#!/bfshell/bin/env python3
# -*- coding: utf-8 -*-
# author: Yuke Ma
# date: 2024-06-15
# description: Tofino switch setup utility for latency probing

# This script clear existing configurations on the Tofino switch before setting up new ones.
import sys
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO")

def main():
    """Main function to clear switch configurations."""
    logger.info("Clearing existing switch configurations...")
    # Assuming bfshell environment is already set up
    assert 'bfrt' in globals(), "This script must be run within the bfshell environment."
    bfrt = globals()['bfrt']
    bfrt_pktgen = bfrt.tf2.pktgen
    bfrt_pipeline = bfrt.ts_pipeline.pipe

    # Stop pktgen app
    logger.info("Stopping pktgen application...")
    bfrt_pktgen.app_cfg.mod_with_trigger_timer_periodic(app_id=1, app_enable=False)
    bfrt_pktgen.app_cfg.mod_with_trigger_timer_periodic(app_id=2, app_enable=False)

    # Clear pktgen pkt_buffer
    logger.info("Clearing pktgen packet buffer...")
    bfrt_pktgen.pkt_buffer.clear()

    # Disable pktgen ports
    logger.info("Disabling pktgen ports...") 
    bfrt_pktgen.port_cfg.mod(dev_port=6, pktgen_enable=False)

    # Clear forwarding rules
    logger.info("Clearing forwarding rules...")
    bfrt_pipeline.Ingress.pass_through.clear()

if __name__ == "__main__":
    main()