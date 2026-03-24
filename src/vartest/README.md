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

Currently, we have implemented T1, T2, T4, T5, T7, and T8. For the FPGA NIC timestamps (T3 and T6), we get them from the FPGA NIC's simulation environment, which provides detailed internal timing information. We are working on integrating these timestamps into the live testbed in the future.

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



## Run the Tests

**Prerequisites:**

1. Set up the testbed environment with the FPGA NICs and Tofino switches.
2. Compile the necessary binaries for the MEAS test.


### MEAS Test

**Running the Test:**

1. Start one terminal for the receiver and sender respectively.

2. Start another terminal for the background traffic generator.


### HOPVar Test

**Receiver:**
```bash
Usage: ./hopvar_receiver --mode {packet|flow} --bind-ip IP --listen-port PORT --csv FILE [options]

Common options:
  --mode MODE            packet | flow
  --bind-ip IP           local IPv4 address to bind
  --listen-port PORT     local UDP port to listen on
  --csv FILE             output CSV file
  --packet-count N       stop after receiving N packets
  --flow-count N         stop after completing N flows (flow mode)
  --buf-size N           recv buffer size (default: 4096)
  --flush-every N        fflush every N rows (default: 1000 packet / 100 flow)

```

```
./hopvar_receiver --mode packet --bind-ip 0.0.0.0 --listen-port 1999 --csv hopvar_packet_incast0.csv --packet-count 1000000
```

**Sender:**
```bash
./hopvar_sender 
Usage: ./hopvar_sender --mode {packet|flow} --dst-ip IP --dst-port PORT [options]

Common options:
  --mode MODE            packet | flow
  --dst-ip IP            destination IPv4 address
  --dst-port PORT        destination UDP port
  --payload-len N        UDP payload length including headers (default: 1400)
  --bind-ip IP           optional source bind IPv4 address
  --csv FILE             output CSV file

Packet mode options:
  --count N              number of packets to send (default: 1)
  --interval-us N        interval between packets in us (default: 1000000)
  --start-req-id N       starting req_id (default: 1)

Flow mode options:
  --flow-size BYTES      application bytes per flow
  --num-flows N          number of flows (default: 1)
  --start-flow-id N      starting flow_id (default: 1)
  --inter-flow-gap-us N  gap between flows in us (default: 0)

```

```bash
./hopvar_sender --mode packet --dst-ip 177.0.1.1 --dst-port 1999 --payload-len 1400 --count 1000000 --interval-us 1
```


