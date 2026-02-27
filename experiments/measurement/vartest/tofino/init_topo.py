"""
Basic Setup module for the topology which:
    1. Sets up ports based on a provided topology YAML file.
    2. Programs pass-through entries for health checking.
"""
import os
import sys
import yaml
import argparse
from loguru import logger
from scapy.all import Ether, IP, UDP, Raw

logger.remove()
logger.add(sys.stdout, level="INFO")

# Ensure `py` dir is on sys.path so `from core...` works when executed by
# `bfshell -b` which typically runs with a different CWD (the SDE install dir).
# Prefer a path relative to this script file so imports work regardless of cwd.
script_dir = os.path.dirname(os.path.abspath(__file__))
candidate_py = os.path.abspath(os.path.join(script_dir, '.'))
if os.path.isdir(candidate_py) and candidate_py not in sys.path:
    sys.path.insert(0, candidate_py)
else:
    # fallback to cwd-based layout (useful when running outside bfshell)
    py_dir = os.path.join(os.getcwd(), 'py')
    if os.path.isdir(py_dir) and py_dir not in sys.path:
        sys.path.insert(0, py_dir)

P4_PROG = os.environ.get('P4_PROG', 'ts_pipeline')
TOPO_PATH = os.environ.get('TOPO_YAML', 'topo2.yaml')
PKTGEN_APP_ID = int(os.environ.get('PKTGEN_APP_ID', 1))  # Default application ID

def setup_topology(bfrt, topo_yaml):
    """Sets up the topology based on the provided YAML file."""
    # Load topology
    with open(topo_yaml, 'r') as f:
        topo = yaml.safe_load(f) or {}

    # Enable requested ports
    logger.info("Enabling ports from topology...")
    port_map = {}
    for name, spec in topo.get('ports', {}).items():
        port_attrs = {}
        port_attrs["conn_id"] = int(spec['conn_id'])
        port_attrs["chnl_id"] = int(spec['chnl_id'])
        port_attrs["FPGA"] = bool(spec.get('FPGA', False))
        
        # get dev port
        dev_port = bfrt.port.port_hdl_info.get(CONN_ID=int(spec['conn_id']),
                                         CHNL_ID=int(spec['chnl_id']),
                                         print_ents=False).data[b'$DEV_PORT']
        dp = int(dev_port)
        port_attrs['dev_port'] = dp
        
        if port_attrs["FPGA"]:
            logger.info(f"  Configuring port {name} as FPGA port")
            bfrt.port.port.add(DEV_PORT=dp,
                            SPEED='BF_SPEED_100G',
                            FEC='BF_FEC_TYP_RS',
                            AUTO_NEGOTIATION='PM_AN_FORCE_DISABLE',
                            PORT_ENABLE=True)
        else:
            logger.info(f"  Configuring port {name} as non-FPGA port")
            bfrt.port.port.add(DEV_PORT=dp,
                            SPEED='BF_SPEED_100G',
                            FEC='BF_FEC_TYP_NONE',
                            AUTO_NEGOTIATION='PM_AN_FORCE_DISABLE',
                            PORT_ENABLE=True)

        port_map[name] = port_attrs
        logger.info(f"  Enabled port {name}: CONN_ID={spec['conn_id']}, CHNL_ID={spec['chnl_id']}, DEV_PORT={dp}")

    logger.info("Setup Summary:")
    for name, attrs in port_map.items():
        logger.info(f"  Port {name}: CONN_ID={attrs['conn_id']}/CHNL_ID={attrs['chnl_id']}/DEV_PORT={attrs['dev_port']}")
    logger.info("Health check setup complete.")
    return port_map

def main():
    logger.info("Starting topology initialization...")
    parser = argparse.ArgumentParser(description="Initialize topology")
    parser.add_argument('--p4_prog', default=P4_PROG, help="P4 program name")
    parser.add_argument('--topo_yaml', default=TOPO_PATH, help="Topology YAML file path")
    args = parser.parse_args()
    logger.info(f"Using P4 program: {args.p4_prog}")
    logger.info(f"Using topology YAML: {args.topo_yaml}")

    # Obtain the BF-RT program handle
    if 'bfrt' not in globals():
        raise RuntimeError("BF-RT program handle not found; run via bfshell -b or adapt client init")
    bfrt = globals()['bfrt']
    
    # Load topology
    port_map = setup_topology(bfrt, args.topo_yaml)
    
    # Enable requested ports
    logger.info("Enabling ports from topology...")
    port_map = {}
    for name, spec in topo.get('ports', {}).items():
        port_attrs = {}
        port_attrs["conn_id"] = int(spec['conn_id'])
        port_attrs["chnl_id"] = int(spec['chnl_id'])
        port_attrs["FPGA"] = bool(spec.get('FPGA', False))
        
        # get dev port
        dev_port = bfrt.port.port_hdl_info.get(CONN_ID=int(spec['conn_id']),
                                         CHNL_ID=int(spec['chnl_id']),
                                         print_ents=False).data[b'$DEV_PORT']
        dp = int(dev_port)
        port_attrs['dev_port'] = dp
        
        if port_attrs["FPGA"]:
            logger.info(f"  Configuring port {name} as FPGA port")
            bfrt.port.port.add(DEV_PORT=dp,
                            SPEED='BF_SPEED_100G',
                            FEC='BF_FEC_TYP_RS',
                            AUTO_NEGOTIATION='PM_AN_FORCE_DISABLE',
                            PORT_ENABLE=True)
        else:
            logger.info(f"  Configuring port {name} as non-FPGA port")
            bfrt.port.port.add(DEV_PORT=dp,
                            SPEED='BF_SPEED_100G',
                            FEC='BF_FEC_TYP_NONE',
                            AUTO_NEGOTIATION='PM_AN_FORCE_DISABLE',
                            PORT_ENABLE=True)

        port_map[name] = port_attrs
        logger.info(f"  Enabled port {name}: CONN_ID={spec['conn_id']}, CHNL_ID={spec['chnl_id']}, DEV_PORT={dp}")

    logger.info("Setup Summary:")
    for name, attrs in port_map.items():
        logger.info(f"  Port {name}: CONN_ID={attrs['conn_id']}/CHNL_ID={attrs['chnl_id']}/DEV_PORT={attrs['dev_port']}")
    logger.info("Health check setup complete.")

    # Final summary
    logger.info("Setup complete. Summary:")
    logger.info(f"  P4 Program: {P4_PROG}")
    logger.info(f"  Topology YAML: {TOPO_PATH}")

if __name__ == '__main__':
    main()
