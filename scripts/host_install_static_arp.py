#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import os
import socket
import subprocess
from pathlib import Path

import yaml
from loguru import logger

from utils.logging import setup_logger
from src.topo.model import load_topology
from src.topo.validate import validate_topology


def run(cmd: list[str], sudo: bool = False, check: bool = True):
    real = (["sudo"] + cmd) if sudo and os.geteuid() != 0 else cmd
    cp = subprocess.run(real, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and cp.returncode != 0:
        logger.error("CMD failed rc={} cmd={}", cp.returncode, " ".join(real))
        logger.error("stdout: {}", (cp.stdout or "")[-800:])
        logger.error("stderr: {}", (cp.stderr or "")[-800:])
        raise RuntimeError("command failed")
    return cp


def run_ns(ns: str, cmd: list[str], sudo: bool = False, check: bool = True):
    return run(["ip", "netns", "exec", ns] + cmd, sudo=sudo, check=check)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topo", default="configs/system-topo-v3.yaml")
    ap.add_argument("--logdir", default="logs")
    args = ap.parse_args()

    topo_path = Path(args.topo).resolve()
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.logdir) / run_id
    setup_logger(out_dir)
    logger.info("run_id={} topo={}", run_id, topo_path)

    doc = yaml.safe_load(topo_path.read_text())
    topo = load_topology(doc)
    validate_topology(topo)

    host = socket.gethostname()
    local_ep_ids = topo.hosts.get(host, [])
    if not local_ep_ids:
        logger.warning("No endpoints for host {}", host)
        return

    # Build global ip->mac map for switch-facing interfaces only
    ip2mac = {}
    for ep in topo.endpoints.values():
        for nic in ep.network_interfaces:
            if nic.tofino_port is None:
                continue
            ip2mac[nic.ip.split("/")[0]] = nic.mac

    logger.info("global ARP entries: {}", len(ip2mac))

    # Install into each local namespace
    for eid in local_ep_ids.endpoints:
        ep = topo.endpoints[eid]
        for nic in ep.network_interfaces:
            if nic.tofino_port is None:
                continue
            self_ip = nic.ip.split("/")[0]
            logger.info("install ARP in ns={} dev={} (self_ip={})", nic.netns, nic.ifname, self_ip)
            for ip, mac in ip2mac.items():
                if ip == self_ip:
                    continue
                run_ns(
                    nic.netns,
                    ["ip", "neigh", "replace", ip, "lladdr", mac, "dev", nic.ifname, "nud", "permanent"],
                    sudo=True,
                    check=False,
                )

    logger.info("static ARP install done: {}", out_dir)


if __name__ == "__main__":
    main()
