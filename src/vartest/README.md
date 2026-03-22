# SyncDC Testbed Latency Test

This project is designed to measure the latency of SyncDC in it's testbed environment.

The testbed is comprised of programmable FPGA NICs and Tofino switches.

## Setup Environment

**FPGA NICs**

For the FPGA NICs, we use Xilinx Alveo U200 cards and Corundum's FPGA NIC design.

**Tofino Switches**

For the Tofino switches, we use Barefoot's Tofino 2 switch and P4's SDE.

## Main Test

There are two main tests that we run in this project:

1. **MEAS:** This test breaks down the latency of our testbed into its components, such as the time taken for the FPGA NIC to process a packet, the time taken for the Tofino switch to process a packet, and the time taken for the packet processed by the host CPU. This test helps us understand where the latency is coming from and identify any bottlenecks in our testbed.

2. **HOPVar:** This test measures the latency of a packet as it traverses through the Tofino switch. We send packets with varying sizes and traverse through different path lengths in the Tofino switch to measure the latency. This test helps us understand how the latency changes with different packet sizes and path lengths (hops).

### MEAS Test

Here we use a customed packet header to measure the latency of each component in our testbed. The packet header includes fields for timestamps that are recorded at various points in the packet's journey through the testbed.

The timestamps currently used in the workflow are conceptually:

- **T1**: user-space send timestamp
- **T2**: TX kernel/driver timestamp
- **T3**: FPGA NIC ingress/internal timestamp (if available)
- **T4**: packet enters the switch ingress pipeline
- **T5**: packet leaves / completes the switch path
- **T6**: FPGA NIC RX-side internal timestamp (if available)
- **T7**: RX kernel/driver timestamp
- **T8**: user-space receive timestamp

These timestamps are then aggregated into phase-level components such as:

- **Kernel**
- **PCIe/DMA**
- **NIC**
- **Switch**

and analyzed under different load conditions, especially different **incast degrees**.

Typical outputs include:

- merged sender/receiver timestamp tables
- per-stage latency summaries
- phase-breakdown plots for paper figures
- CDF / CCDF plots under different incast levels
- packet loss statistics


### HOPVar Test

The HOPVAR path is used to characterize switch-side latency in the uncongested regime and to study how latency accumulates hop by hop.

The core idea is to attach a lightweight hop measurement header to each packet and let the switch append timestamps at successive traversals. This enables us to reconstruct:

- per-hop latency accumulation
- latency predictability as a function of **hop count**
- latency dependence on **payload size**
- packet-level and flow-level variance behavior

The HOPVAR workflow currently supports two modes:

- **packet mode**: analyze per-packet latency accumulation
- **flow mode**: aggregate packets into flows and analyze flow completion behavior

Typical outputs include:

- raw hopvar receive traces
- expanded long-format per-packet latency tables
- per-hop latency summaries
- predictability tables with slope / R² / residual std
- flow-level CDF / CCDF plots

## Project Structure

The project is organized into the following directories:

- `sources/`: Contains the source code of generators, receivers, protocol headers, and helpers.
- `build/`: Contains the build scripts and compiled binaries.
- `results/`: Contains the results of the tests, including raw data and processed outputs.
- `tools/`: Contains scripts for data analysis and visualization.

