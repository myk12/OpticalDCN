# src/topo/validate.py
from __future__ import annotations

import ipaddress
from loguru import logger
from typing import Dict, Set, Tuple

from .model import Topology, EndpointIfaceRef


def validate_topology(t: Topology) -> None:
    logger.info("Validating topology with {} switch ports and {} endpoints...", len(t.switch_ports), len(t.endpoints))

    # 1) unique hardware port strings
    logger.info("Checking unique hardware port strings...")
    hw_seen: Dict[str, str] = {}
    for pid, p in t.switch_ports.items():
        if p.port in hw_seen:
            raise ValueError(f"Duplicate hw port {p.port} used by {hw_seen[p.port]} and {pid}")
        hw_seen[p.port] = pid
    logger.info("Unique hardware port strings check passed.")

    # 2) role sanity
    for pid, p in t.switch_ports.items():
        if p.role not in ("server", "fabric", "unused"):
            raise ValueError(f"Invalid role for switch port {pid}: {p.role}")

    # 3) connected_to references for server ports
    logger.info("Checking connected_to references for server ports...")
    for pid, p in t.switch_ports.items():
        if p.role == "server":
            if not p.connected_to:
                raise ValueError(f"server port {pid} missing connected_to")
            ep = t.endpoints.get(p.connected_to.endpoint)
            if not ep:
                raise ValueError(f"{pid}.connected_to endpoint not found: {p.connected_to.endpoint}")
            iface_ids = {i.id for i in ep.network_interfaces}
            if p.connected_to.iface not in iface_ids:
                raise ValueError(f"{pid}.connected_to iface not found: {p.connected_to.endpoint}:{p.connected_to.iface}")
        else:
            # non-server ports must not pretend to connect_to endpoint
            pass
    logger.info("connected_to references check passed.")

    # 4) pair_with symmetry for fabric ports
    logger.info("Checking pair_with symmetry for fabric ports...")
    for pid, p in t.switch_ports.items():
        if p.role != "fabric":
            continue
        if not p.pair_with:
            raise ValueError(f"fabric port {pid} missing pair_with")
        peer = t.switch_ports.get(p.pair_with)
        if not peer:
            raise ValueError(f"fabric port {pid} pair_with points to missing port id {p.pair_with}")
        if peer.pair_with != pid:
            raise ValueError(f"pair_with not symmetric: {pid} -> {p.pair_with} but {p.pair_with} -> {peer.pair_with}")
        if peer.role != "fabric":
            raise ValueError(f"pair_with role mismatch: {pid} (fabric) paired with {peer.id} (role={peer.role})")
    logger.info("pair_with symmetry check passed.")

    # 5) endpoint iface tofino_port references exist + must point to server ports
    logger.info("Checking endpoint iface tofino_port references...")
    for eid, e in t.endpoints.items():
        for iface in e.network_interfaces:
            if iface.tofino_port is None:
                continue
            sp = t.switch_ports.get(iface.tofino_port)
            if not sp:
                raise ValueError(f"{eid}:{iface.id} references missing switch port id {iface.tofino_port}")
            if sp.role != "server":
                raise ValueError(f"{eid}:{iface.id} references non-server switch port {iface.tofino_port} role={sp.role}")
    logger.info("Endpoint iface tofino_port references check passed.")

    # 6) IP/MAC uniqueness + format
    logger.info("Checking IP/MAC uniqueness across all interfaces...")
    ips: Set[str] = set()
    macs: Set[str] = set()
    for eid, e in t.endpoints.items():
        for iface in e.network_interfaces:
            try:
                ipaddress.ip_interface(iface.ip)
            except Exception as ex:
                raise ValueError(f"Invalid ip format {eid}:{iface.id} ip={iface.ip}: {ex}")

            ip_key = str(ipaddress.ip_interface(iface.ip))
            if ip_key in ips:
                raise ValueError(f"Duplicate IP {ip_key} (seen again at {eid}:{iface.id})")
            ips.add(ip_key)

            mac = iface.mac.lower()
            if mac in macs:
                raise ValueError(f"Duplicate MAC {mac} (seen again at {eid}:{iface.id})")
            macs.add(mac)
    logger.info("IP/MAC uniqueness check passed.")

    # 7) Bi-directional consistency (NEW, high value):
    # For every server switch port connected_to (E,iface), ensure endpoint E:iface.tofino_port == this port.id
    logger.info("Checking bi-directional consistency (switch.connected_to <-> endpoint.tofino_port)...")
    for pid, p in t.switch_ports.items():
        if p.role != "server":
            continue
        ref = p.connected_to
        assert ref is not None
        ep = t.endpoints[ref.endpoint]
        ep_iface = next((i for i in ep.network_interfaces if i.id == ref.iface), None)
        if ep_iface is None:
            raise ValueError(f"{pid}.connected_to points to missing iface: {ref.endpoint}:{ref.iface}")
        if ep_iface.tofino_port != pid:
            raise ValueError(
                f"Bi-directional mapping mismatch: switch port {pid} connected_to={ref.endpoint}:{ref.iface} "
                f"but endpoint has tofino_port={ep_iface.tofino_port}"
            )
    logger.info("Bi-directional consistency check passed.")

    logger.info("Topology validation passed ({} switch ports, {} endpoints).", len(t.switch_ports), len(t.endpoints))
