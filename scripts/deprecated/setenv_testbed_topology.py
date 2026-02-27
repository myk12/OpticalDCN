#!/usr/bin/python3

import argparse
import datetime as dt
import os
import socket
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass
from loguru import logger
from typing import Optional, Any
from utils.logging import setup_logger

import yaml

def run(cmd: list[str], sudo: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    if sudo and os.geteuid() != 0:
        cmd = ["sudo"] + cmd
    
    logger.debug(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode != 0:
        logger.error(f"Command failed with return code {result.returncode}")
        logger.error(f"stdout: {result.stdout}")
        logger.error(f"stderr: {result.stderr}")
        if check:
            raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
    else:
        logger.debug(f"Command succeeded with stdout: {result.stdout}")

    return result

def run_in_ns(ns: str, cmd: list[str], sudo: bool = False, check: bool = True) -> subprocess.CompletedProcess:  
    cmd = ["ip", "netns", "exec", ns] + cmd
    return run(cmd, sudo=sudo, check=check)

def now_run_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")

@dataclass
class Iface:
    endpoint_id: str
    ifname: str
    ns: str
    ip: str
    mac: str

def load_local_ifaces(topo_path: Path, host_name: str) -> list[Iface]:
    data = yaml.safe_load(topo_path.read_text())
    endpoints = data["topology"]["endpoints"]
    local = [ep for ep in endpoints if ep["hostname"] == host_name]
    ifaces: list[Iface] = []
    for ep in local:
        for n in ep["network_interfaces"]:
            ifaces.append(Iface(
                endpoint_id=ep["id"],
                ifname=n["ifname"],
                ns=n["namespace"],
                ip=n["ip_address"],
                mac=n["mac_address"],
            ))
    
    return ifaces

def get_ns_list() -> list[str]:
    result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
    namespaces = [line.split()[0] for line in result.stdout.splitlines()]
    return namespaces

def ensure_netns(ns: str) -> None:
    # Check if the namespace already exists
    existing_namespaces = get_ns_list()
    
    if ns in existing_namespaces:
        logger.debug(f"Namespace {ns} already exists.")
        return
    
    # Create the namespace
    logger.info(f"Creating network namespace: {ns}")
    run(["ip", "netns", "add", ns], sudo=True)

def ensure_loopback_up(ns: str) -> None:
    logger.info(f"Ensuring loopback interface is up in namespace {ns}")
    run_in_ns(ns, ["ip", "link", "set", "lo", "up"], sudo=True)

def iface_in_ns(ifname: str, ns: str) -> bool:
    result = run_in_ns(ns, ["ip", "link", "show", ifname], sudo=True, check=False)
    return result.returncode == 0

def iface_in_root(ifname: str) -> bool:
    result = run(["ip", "link", "show", ifname], sudo=True, check=False)
    return result.returncode == 0

def parse_all_arp_entries(topo: dict) -> dict[str, str]:
    """
    Return ip -> mac mapping from topo YAML
    """
    ip2mac: dict[str, str] = {}
    endpoints = topo["topology"]["endpoints"]
    for ep in endpoints:
        for n in ep["network_interfaces"]:
            ip2mac[n["ip_address"]] = n["mac_address"]

    return ip2mac

def install_static_arp_entries(ns: str, ifname: str, self_ip: str, ip2mac: dict[str, str]) -> None:
    """
    Install static ARP entries in the given namespace except self entries (i.e., where IP matches the namespace's own IP). This ensures that the namespace can resolve MAC addresses of other endpoints in the topology without relying on ARP broadcasts, which may not work properly in isolated namespaces.
    """
    logger.info(f"Installing static ARP entries in namespace {ns} for all IPs except {self_ip}")
    for ip, mac in ip2mac.items():
        if ip == self_ip:
            continue
        logger.debug(f"Adding static ARP entry in namespace {ns}: {ip} -> {mac}")
        
        cp = run_in_ns(ns, ["ip", "neigh", "replace", ip, "lladdr", mac, "dev", ifname], sudo=True, check=False)
        if cp.returncode != 0:
            logger.error(f"Failed to add ARP entry for {ip} in namespace {ns}: {cp.stderr}")
    
    logger.info(f"Static ARP entries installed in namespace {ns}")

def install_static_arp_from_topo(ns: str, topo: dict) -> None:
    topo 
    ip2mac = parse_all_arp_entries(topo)
    endpoints = topo["topology"]["endpoints"]
    for ep in endpoints:
        for n in ep["network_interfaces"]:
            if n["namespace"] == ns:
                install_static_arp_entries(ns, n["ifname"], n["ip_address"], ip2mac)

    
def move_iface_to_ns(ifname: str, ns: str) -> None:
    logger.info(f"Moving interface {ifname} to namespace {ns}")
    if iface_in_ns(ifname, ns):
        logger.debug(f"Interface {ifname} is already in namespace {ns}")
        return
    if not iface_in_root(ifname):
        logger.error(f"Interface {ifname} not found in root namespace. Cannot move to {ns}.")
        raise RuntimeError(f"Interface {ifname} not found in root namespace.")
    
    run(["ip", "link", "set", ifname, "netns", ns], sudo=True)

def config_ip_up(ifname: str, ns: str, ip: str, prefix: int) -> None:
    logger.info(f"Configuring IP {ip}/{prefix} on interface {ifname} in namespace {ns} and bringing it up")
    run_in_ns(ns, ["ip", "addr", "flush", "dev", ifname], sudo=True)
    run_in_ns(ns, ["ip", "addr", "add", f"{ip}/{prefix}", "dev", ifname], sudo=True)
    run_in_ns(ns, ["ip", "link", "set", ifname, "up"], sudo=True)
    logger.debug(f"Interface {ifname} in namespace {ns} configured with IP {ip}/{prefix} and brought up")

def smoke_ping(ns: str, dst: str, count: int = 3, timeout: int = 5) -> bool:
    logger.info(f"Performing smoke test: pinging {dst} from namespace {ns}")
    try:
        run_in_ns(ns, ["ping", "-c", str(count), "-W", str(timeout), dst], sudo=True)
        logger.info(f"Smoke test successful: {dst} is reachable from namespace {ns}")
        return True
    except subprocess.CalledProcessError:
        logger.error(f"Smoke test failed: {dst} is not reachable from namespace {ns}")
        return False

def main() -> None:
    argparser = argparse.ArgumentParser(description="Host-side setup script for setting up the Corundum FPGAs.")
    argparser.add_argument("--topo", type=Path, default=Path("configs/system-spineleaf-topo.yaml"), help="Path to the topology YAML file describing the testbed configuration.")
    argparser.add_argument("--out-dir", type=Path, default=Path("logs") / dt.datetime.now().strftime("%Y%m%d_%H%M%S"), help="Directory to store logs.")
    argparser.add_argument("--prefix", type=int, default=24, help="Prefix length for IP addresses (default: 24).")
    argparser.add_argument("--no-smoke", action="store_true", help="Skip the smoke test that verifies connectivity to the FPGAs.")
    
    args = argparser.parse_args()
    
    setup_logger(args.out_dir)

    logger.info("=== Starting host-side setup script for Corundum FPGAs ===")
    logger.info(f"Parsed arguments: {args}")

    # Load topology from YAML file
    topo_path = Path(args.topo).resolve()
    if not topo_path.exists():
        logger.error(f"Topology file {topo_path} does not exist.")
        return
    
    host_name = socket.gethostname()
    logger.info(f"Host name: {host_name}")
    
    run_id = now_run_id()
    
    out_dir = Path(args.out_dir or f"runs/{run_id}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory for logs: {out_dir}")
    
    logs: list[str] = []
    logger.info(f"Loading topology from {topo_path}")
    
    ifaces = load_local_ifaces(topo_path, host_name)
    inv = {
        "host" : host_name,
        "topo_path" : str(topo_path),
        "ifaces" : [iface.__dict__ for iface in ifaces],
    }
    (out_dir / "inventory.json").write_text(json.dumps(inv, indent=2))
    logger.info(f"Loaded {len(ifaces)} local interfaces from topology:")
    
    if not ifaces:
        logger.warning("No local interfaces found in topology for this host. Check the topology file and host name.")
    
    arp_entries = parse_all_arp_entries(yaml.safe_load(topo_path.read_text()))
    logger.info(f"Parsed {len(arp_entries)} ARP entries from topology.")
    # Apply configuration for each local interface
    ns_list: list[str] = []
    for iface in ifaces:
        logger.info(f"Setting up interface {iface.ifname} in namespace {iface.ns} with IP {iface.ip}/{args.prefix} and MAC {iface.mac}")

        ensure_netns(iface.ns)
        
        move_iface_to_ns(iface.ifname, iface.ns)
        
        config_ip_up(iface.ifname, iface.ns, iface.ip, args.prefix)

        install_static_arp_entries(iface.ns, iface.ifname, iface.ip, arp_entries)

        ensure_loopback_up(iface.ns)
    
    (out_dir / "apply.log").write_text("\n".join(logs) + "\n")
    logger.info("Interface configuration applied successfully.")

    # Smoke test (local ping)
    if not args.no_smoke:
        report: dict[str, Any] = {"host": host_name, "checks": []}
        # 1) each ns ping its own IP
        for iface in ifaces:
            report["checks"].append(
                {
                    "name": "ping_self",
                    "endpoint": iface.endpoint_id,
                    "ns": iface.ns,
                    "ifname": iface.ifname,
                    "result": smoke_ping(iface.ns, iface.ip),
                }
            )    
        
        # 2) pairwise ping between all ifaces on this host (if multiple)
        for i in range(len(ifaces) - 1):
            src = ifaces[i]
            dst = ifaces[i + 1]
            report["checks"].append(
                {
                    "name": "ping_peer",
                    "src_endpoint": src.endpoint_id,
                    "dst_endpoint": dst.endpoint_id,
                    "src_ns": src.ns,
                    "dst_ns": dst.ns,
                    "src_ifname": src.ifname,
                    "dst_ifname": dst.ifname,
                    "result": smoke_ping(src.ns, dst.ip),
                }
            ) 
        
        (out_dir / "smoke_report.json").write_text(json.dumps(report, indent=2))
        logger.info("Smoke test completed. Report saved to smoke_report.json")

if __name__ == "__main__":
    main()