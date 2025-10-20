# FPGA SmartNIC Datapath Loopback Test with Network Namespaces

This document describes how to verify packet transmission through an FPGA-based SmartNIC (e.g., **mqnic** or **Corundum**) by directly wiring its two physical ports and isolating them into separate Linux network namespaces.

---

## 1. Overview

**Goal:**  
Create two independent network namespaces, each owning one physical NIC port:

ns0 (10.0.0.1) ── enp202s0np0 ⇄ FPGA ⇄ enp202s0np1 ── (10.0.0.2) ns1


Packets sent from `ns0` should traverse:

1. The Linux networking stack in `ns0`
2. The FPGA SmartNIC datapath (TX → RX through the physical cable)
3. The Linux networking stack in `ns1`

This allows us to confirm that the FPGA design, PHYs, and driver are functioning correctly.

---

## 2. Prerequisites

- Linux host with two FPGA NIC ports (e.g., `enp202s0np0`, `enp202s0np1`)
- Ports physically connected by a direct link (DAC or loopback cable)
- `mqnic` driver loaded and devices visible under `ip link`
- Root privileges

---

## 3. Setup Environments

This project needs to create two seperate network namespaces and assign each of the one interface.

Use `setup.bash` to:
1. create network namesapce
2. assign ip addr
3. test connectivity

## 4. Start Testing

1. start receving process
    `sudo ip netns exec fpganic_p2 ./rx enp202s0np1 0.0.0.0 7777`
2. start sending process
    `sudo ip netns exec fpganic_p1 ./tx  -n 10 enp202s0np0 10.0.0.1 10.0.0.2 7777`

The results will be save into `ts_probe_rx.csv` and `ts_probe_tx.csv`
