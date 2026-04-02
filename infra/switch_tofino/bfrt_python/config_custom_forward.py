#!/usr/bin/env python3
# brft_python
#
# Program Hybrid EPS/OCS:
#   - Classify optical ports (25-32) as OCS in t_set_port_kind
#   - Install an 8-slot round-robin perfect matching schedule in t_ocs_schedule for OCS ports
#
# Usage:
#   bfshell -b <this_script.py> --topo=/path/to/topology.yaml
#

import os
import yaml
import inspect

TOPO_PATH       = os.environ.get('TOPOLOGY', '/tmp/opticaldcn/system-topo.yaml')
P4_PROGRAM_NAME = os.environ.get('P4_PROGRAM_NAME', 'hybrid_arch')

NUM_SPINES = 2
NUM_LEAFS = 4
NUM_OPTICAL_PORTS = 8

hopvar_custom_forwarding_entries = [
    (0, "00:0a:35:06:50:94", 3),
    (4, "00:0a:35:06:50:94", 3),
    (21, "00:0a:35:06:50:94", 22),
    (7, "00:0a:35:06:50:94", 5),
    (18, "00:0a:35:06:50:94", 20),
    (13, "00:0a:35:06:50:94", 15),
    (24, "00:0a:35:06:50:94", 23),
    (11, "00:0a:35:06:50:94", 9),
    (19, "00:0a:35:06:50:94", 17),
    (1, "00:0a:35:06:50:94", 2),
    # reverse direction
    (3, "00:0a:35:06:09:24", 4),
    (22, "00:0a:35:06:09:24", 21),
    (5, "00:0a:35:06:09:24", 7),
    (20, "00:0a:35:06:09:24", 18),
    (15, "00:0a:35:06:09:24", 13),
    (23, "00:0a:35:06:09:24", 24),
    (9, "00:0a:35:06:09:24", 11),
    (17, "00:0a:35:06:09:24", 19),
    (2, "00:0a:35:06:09:24", 1),
]

incast_custom_forwarding_entries = [
    (4, "00:0a:35:06:50:94", 2),
    (6, "00:0a:35:06:50:94", 2),
    (8, "00:0a:35:06:50:94", 2),
    (10, "00:0a:35:06:50:94", 2),
    (12, "00:0a:35:06:50:94", 2),
    # reverse direction
    (2, "00:0a:35:06:09:24", 4),
    (2, "00:0a:35:06:0b:84", 6),
    (2, "00:0a:35:06:09:3c", 8),
    (2, "00:0a:35:06:0b:72", 10),
    (2, "00:0a:35:06:09:9c", 12),
]
    

#############################################################
#               BFRT Helper Functions
#############################################################
def parse_port_str(s: str):
    a, b = s.split('/')
    return int(a), int(b)

def get_dev_port(bfrt, fp_port: str):
    # Convert front-panel port string (e.g., "17/0") to device port number
    conn_id, chnl_id = parse_port_str(fp_port)
    data = bfrt.port.port_hdl_info.get(CONN_ID=conn_id, CHNL_ID=chnl_id, print_ents=False).data
    if len(data) == 0:
        raise ValueError(f"Port {fp_port} not found in BFRT database")

    return int(data[b'$DEV_PORT'])

##############################################################
#                   EPS Setup
##############################################################

def program_eps_forwarding(bfrt, custom_forwarding_entries):
    """
    Program EPS forwarding in t_eps_forward:
      key: (ingress_port, dst_mac, selected_spine)
      action: set_ucast_port(port)
    """
    print("[Hybrid Arch] Programming EPS forwarding rules...")
    t = bfrt.hybrid_arch.pipe.Ingress.t_eps_forward
    t.clear()

    n = 0
    for ingress_port, dst_mac, egress_port in custom_forwarding_entries:
        dev_ig_port = 0
        if ingress_port == 0:
            # Pktgen port
            dev_ig_port = 6
        else:
            dev_ig_port = get_dev_port(bfrt, f"{ingress_port}/0")  # Assuming channel 0 for simplicity
        dev_eg_port = get_dev_port(bfrt, f"{egress_port}/0")
        ent = t.entry_with_set_ucast_port(
            ingress_port=dev_ig_port,
            dst_addr=dst_mac,
            selected_spine=0,  # selected_spine is not used in this simple example, set to 0
            port=dev_eg_port)  # Forward back to same port for testing
        ent.push()
        n += 1
        print(f"  Added EPS forwarding entry: ingress_port={ingress_port}, dst_mac={dst_mac}, egress_port={egress_port}")

    print(f"[Hybrid Arch] EPS forwarding rules programmed: {n} entries")

#############################################################
#                   Main Function
#############################################################

def main():
    print("[Hybrid Arch] Starting setup for Hybrid EPS/OCS architecture")
    
    topo_path = os.getenv('TOPOLOGY', TOPO_PATH)
    prog = os.getenv('P4_PROGRAM_NAME', P4_PROGRAM_NAME)
    print(f"[Hybrid Arch] Loading topology from: {topo_path}")
    print(f"[Hybrid Arch] Using P4 program: {prog}")

    # Resolve program Ingress
    prog_root = getattr(bfrt, prog, None)
    if prog_root is None:
        raise ValueError(f"Program {prog} not found in BFRT database. Available programs: {bfrt.keys()}")

    ingress = prog_root.pipe.Ingress
    program_eps_forwarding(bfrt, hopvar_custom_forwarding_entries)

if __name__ == "__main__":
    main()
