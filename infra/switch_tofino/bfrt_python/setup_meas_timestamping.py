#!/usr/bin/env python3
# bfrt_python
#
# Programm MEAS Ingress/Egress Timestamping using bfrt Python API.

import os
import yaml
import inspect

TOPO_PATH = os.environ.get("TOPO_PATH", "/tmp/opticaldcn/system-topo.yaml")
P4_PROG = os.environ.get("P4_PROG", "hybrid_arch")

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

def get_id_from_port_id(pid: str, prefix: str) -> int:
    # Extract numeric ID from port id string with given prefix
    # e.g., "leaf3_p2" -> 3 if prefix="leaf"
    if not pid.startswith(prefix):
        raise ValueError(f"Port id {pid} does not start with expected prefix {prefix}")
    rest = pid[len(prefix):]
    return int(rest.split('_', 1)[0])

def leaf_id_from_port_id(pid: str) -> int:
    return get_id_from_port_id(pid, "leaf")

def spine_id_from_port_id(pid: str) -> int:
    return get_id_from_port_id(pid, "spine")

def downleaf_id_from_port_id(pid: str) -> int:
    # For spine ports, extract the downleaf id from port id string
    # e.g., "spine1_p2" -> 2 (downleaf id) if prefix="spine"
    if not pid.startswith("spine"):
        raise ValueError(f"Port id {pid} does not start with expected prefix 'spine'")
    rest = pid[len("spine"):]
    return int(rest.split('_p', 1)[1])

def find_switch_port_for_endpoint(topo, endpoint: str, iface: str) -> str:
    # Find the front-panel port string of the switch port connected to given endpoint and interface
    for p in topo['switch']['ports']:
        ct = p.get('connected_to', {})
        if ct.get('endpoint') == endpoint and ct.get('iface') == iface:
            return p['id']
    raise ValueError(f"Cannot find switch port connected to endpoint={endpoint} iface={iface}")

###############################################################
#               Measurement Timestamping Logic
###############################################################
def program_timestamping(bfrt, topo, endpoints, spid_to_dev):
    print("[INFO] Programming measurement timestamping rules...")
    
    # 1. Get all switch ports connected to endpoints
    endpoint_ports = []
    for ep in endpoints:
        interfaces = ep.get('network_interfaces', [])
        for iface in interfaces:
            conn_port = iface.get('tofino_port')
            
            if conn_port:
                dev_port = spid_to_dev[conn_port]
                endpoint_ports.append(dev_port)
    print(f"[INFO] Found {len(endpoint_ports)} ports connected to endpoints: {endpoint_ports}")
    
    # 2. For each such port, add entries to enable ingress/egress timestamping
    t_meas_ingress = bfrt.hybrid_arch.pipe.Ingress.t_meas_ingress_timestamp
    t_meas_egress = bfrt.hybrid_arch.pipe.Egress.t_meas_egress_timestamp

    t_meas_ingress.clear()
    t_meas_egress.clear()
    
    for dev_port in endpoint_ports:
        # Ingress timestamping: match on ingress port and valid measurement header
        print(f"[INFO] Adding Ingress timestamping rules for dev_port={dev_port}")
        t_meas_ingress.add_with_meas_ingress_timestamp(
            ingress_port=dev_port,
            valid=1
        )

        print(f"[INFO] Adding Egress timestamping rules for dev_port={dev_port}")
        # Egress timestamping: match on egress port and valid measurement header
        t_meas_egress.add_with_meas_egress_timestamp(
            egress_port=dev_port,
            valid=1
        )
    
    print("[INFO] Measurement timestamping rules programmed successfully.")

################################################################
#               BFRT Main Function
#################################################################
def main():
    print("[INFO] Setting up measurement timestamping...")
    topo_path = os.getenv("TOPO_PATH", "/tmp/opticaldcn/system-topo.yaml")
    prog = os.getenv("P4_PROG", "hybrid_arch")
    
    # Load topology
    topo = yaml.safe_load(open(topo_path))
    sw_ports = topo['switch']['ports']
    
    # Map switch port-id -> front panel port string -> dev_port
    spid_to_fp = {p['id']: p["port"] for p in sw_ports}
    spid_to_dev = {spid: get_dev_port(bfrt, fp) for spid, fp in spid_to_fp.items()}
    
    endpoints = topo.get('endpoints', [])
    
    # Program measurement timestamping rules
    # For all ports connected to endpoints, enable ingress/egress timestamping
    program_timestamping(bfrt, topo, endpoints, spid_to_dev)

if __name__ == "__main__":
    main()