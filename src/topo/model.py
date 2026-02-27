# src/topo/model.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union


# -----------------------------
# Data model
# -----------------------------
@dataclass(frozen=True)
class EndpointIfaceRef:
    endpoint: str
    iface: str  # e.g., "p1"


@dataclass
class SwitchPort:
    id: str
    port: str  # e.g., "1/0"
    role: str  # "server" | "fabric" | "unused"
    spec_speed: Optional[str] = None  # e.g., "100G"
    spec_fec: Optional[str] = None    # e.g., "RS"
    connected_to: Optional[EndpointIfaceRef] = None
    pair_with: Optional[str] = None   # another SwitchPort.id


@dataclass
class EndpointIface:
    id: str                 # "p1" / "p2"
    ifname: str
    netns: str
    ip: str                 # with CIDR
    mac: str                # lower-case
    tofino_port: Optional[str] = None  # SwitchPort.id or None


@dataclass
class Endpoint:
    id: str                 # "fpga_1"
    hostname: str
    network_interfaces: List[EndpointIface]


@dataclass
class Host:
    id: str
    hostname: str
    subnet: Optional[str]
    endpoints: List[str]


@dataclass
class Topology:
    switch_ports: Dict[str, SwitchPort]   # id -> SwitchPort
    endpoints: Dict[str, Endpoint]        # id -> Endpoint
    hosts: Dict[str, Host]                # hostname -> Host
    raw: Dict[str, Any]                   # original YAML dict (for convenience)


# -----------------------------
# Helpers: schema-tolerant access
# -----------------------------
def _get(d: Dict[str, Any], *keys: str, default=None):
    for k in keys:
        if k in d:
            return d[k]
    return default


def _parse_iface_ref(x: Any) -> Optional[EndpointIfaceRef]:
    """
    Accept both:
      - dict: {endpoint: fpga_1, iface: p1}
      - string: "fpga_1:p1"
    """
    if x is None:
        return None
    if isinstance(x, dict):
        ep = x.get("endpoint")
        iface = x.get("iface")
        if ep is None or iface is None:
            raise ValueError(f"Invalid connected_to dict (need endpoint+iface): {x}")
        return EndpointIfaceRef(endpoint=str(ep), iface=str(iface))
    if isinstance(x, str):
        if ":" not in x:
            raise ValueError(f"Invalid connected_to string (expected 'fpga_x:p1'): {x}")
        ep, iface = x.split(":", 1)
        return EndpointIfaceRef(endpoint=ep, iface=iface)
    raise ValueError(f"Invalid connected_to type: {type(x)} value={x}")


def load_topology(doc: Dict[str, Any]) -> Topology:
    # -------- switch ports --------
    sp: Dict[str, SwitchPort] = {}
    for p in doc["switch"]["ports"]:
        pid = p["id"]
        role = str(p.get("role", "")).lower()
        port = p["port"]

        spec = p.get("spec") or {}
        speed = spec.get("speed")
        fec = spec.get("fec")

        sp[pid] = SwitchPort(
            id=pid,
            port=port,
            role=role,
            spec_speed=str(speed) if speed is not None else None,
            spec_fec=str(fec) if fec is not None else None,
            connected_to=_parse_iface_ref(p.get("connected_to")),
            pair_with=p.get("pair_with"),
        )

    # -------- endpoints --------
    eps: Dict[str, Endpoint] = {}
    for e in doc["endpoints"]:
        eid = e["id"]
        hostname = e["hostname"]
        ifaces: List[EndpointIface] = []

        for n in e["network_interfaces"]:
            # tolerate old vs new field names
            ifname = _get(n, "ifname", "name")
            netns = _get(n, "netns", "namespace")
            ip = _get(n, "ip", "ip_address")
            mac = _get(n, "mac", "mac_address")
            tofino_port = n.get("tofino_port")

            if ifname is None or netns is None or ip is None or mac is None:
                raise ValueError(f"Missing required iface fields on {eid}: {n}")

            ifaces.append(
                EndpointIface(
                    id=str(n["id"]),
                    ifname=str(ifname),
                    netns=str(netns),
                    ip=str(ip),
                    mac=str(mac).lower(),
                    tofino_port=tofino_port if tofino_port is not None else None,
                )
            )
        eps[eid] = Endpoint(id=eid, hostname=hostname, network_interfaces=ifaces)

    # -------- hosts --------
    hosts: Dict[str, Host] = {}
    for h in doc.get("hosts", []):
        hid = h.get("id", h["hostname"])
        hostname = h["hostname"]
        subnet = h.get("subnet")
        endpoints = list(h.get("endpoints", []))
        hosts[hostname] = Host(id=hid, hostname=hostname, subnet=subnet, endpoints=endpoints)

    return Topology(switch_ports=sp, endpoints=eps, hosts=hosts, raw=doc)
