# Latency Profiling in Spine-Leaf Architecture

This document provides an overview of latency profiling in a spine-leaf network architecture. It outlines the key components, methodologies, and tools used to measure and analyze latency within this type of network topology.

![alt text](images/leaf-spine-topo.png "Spine-Leaf Topology")

## Overview of Spine-Leaf Architecture

Yaml configuration for a basic spine-leaf topology:

```yaml
topology:
  spine:
    - name: spine1
      pipeline: 3
      ports: [17, 18, 19, 20, 21, 22, 23, 24]
  leaf:
    - name: leaf1
      pipeline: 1
      ports: [1, 2, 3, 4]
      network: "10.0.1.0/24"
    - name: leaf2
      pipeline: 1
      ports: [5, 6, 7, 8]
      network: "10.0.2.0/24"
    - name: leaf3
      pipeline: 2
      ports: [9, 10, 11, 12]
      network: "10.0.3.0/24"
    - name: leaf4
      pipeline: 2
      ports: [13, 14, 15, 16]
      network: "10.0.4.0/24"
```

## Timestamps in Tofino Switches

There are several types of timestamps available in Tofino switches for latency measurement:

![alt text](images/tofino-tstamp.png)

### TS1 to TS5

These timestamps are automatically captured by the switch and can be accessed directly in the P4 program:

Table: Tofino Timestamps TS1 to TS5

| Timestamp | Type | Metadata Variable | Description |
|-----------|------|-------------------|-------------|
| TS1 / iTS | ingress_intrinsic_metadata_t | bit<48> ingress_mac_tstamp; | IEEE 1588 timestamp (ns), taken upon arrival at ingress MAC. |
| TS2 | ingress_intrinsic_metadata_from_parser_t | bit<48> global_tstamp; | Global timestamp (ns), taken upon arrival at ingress parser. |
| TS3 | egress_intrinsic_metadata_t | bit<18> enq_tstamp; // TF1<br>bit<32> enq_tstamp; // TF2 | Global timestamp (ns), taken when the packet is enqueued in the TM. |
| TS4 (Derived) | egress_intrinsic_metadata_t | bit<18> deq_timedelta; // TF1<br>bit<32> deq_timedelta; // TF2 | Time delta (ns) between the packet's enqueue and dequeue in the TM. TS4 can be derived by adding TS3 and deq_timedelta. |
| TS5 | egress_intrinsic_metadata_from_parser_t | bit<48> global_tstamp; | Global timestamp (ns), taken upon arrival at egress parser. |

### TS6 and TS7

These timestamps are not automatically captured and cannot be directly accessed in the P4 program. They require special handling:
| Timestamp | Description |
|-----------|-------------|
| TS6 / eTS | Cannot be directly read in P4 or control plane, but can be written into the packet by the Egress MAC by setting specific intrinsic metadata in P4. |
| TS7 | Cannot be directly read in P4, but can be captured by the control plane by setting specific intrinsic metadata in P4. |




TS1-TS5 自动保存在数据包的 Intrinsic metadata 中，可以直接在 P4 程序中读取（也就是可以附加在数据包头中）：

时间戳	类型	元变量	含义
TS1 / iTS	ingress_intrinsic_metadata_t	bit<48> ingress_mac_tstamp;	IEEE 1588 timestamp (ns), taken upon arrival at ingress MAC.
TS2	ingress_intrinsic_metadata_from_parser_t	bit<48> global_tstamp;	Global timestamp (ns), taken upon arrival at ingress parser.
TS3	egress_intrinsic_metadata_t	bit<18> enq_tstamp; // TF1
bit<32> enq_tstamp; // TF2	Global timestamp (ns), taken when the packet is enqueued in the TM.
TS4 (Derived)	egress_intrinsic_metadata_t	bit<18> deq_timedelta; // TF1
bit<32> deq_timedelta; // TF2	Time delta (ns) between the packet's enqueue and dequeue in the TM. TS4 can be derived by adding TS3 and deq_timedelta.
TS5	egress_intrinsic_metadata_from_parser_t	bit<48> global_tstamp;	Global timestamp (ns), taken upon arrival at egress parser.
TS6 和 TS7 不会自动获取，也不能在 P4 程序中直接读取，它们需要通过特殊方式获取：

TS6 / eTS: 无法在 P4 和控制平面中直接读取，但可以在 P4 中通过设置以下 Intrinsic metadata 请求 Egress Mac 直接将值写入数据包：

元变量类型	元变量	含义
egress_intrinsic_metadata_for_output_port_t	bit<1> update_delay_on_tx;	Request for PTP delay update at egress MAC
设置完以上 metadata 后，获取 TS6 的流程：

在数据包前附加一个临时的头部用于向 Egress MAC 传参，MAC 会将 TS6 处理后写入数据包指定位置，并可选的更新校验和，最后去除临时头部
在 Egress Pipeline 中，于 Ethernet 头之前添加以下 Header（即必须是 Packet 的第一个 Header）（定义在 tofino.p4 中，不需要用户提供）：
header ptp_metadata_t { bit<8> udp_cksum_byte_offset; // Byte offset at which the egress MAC needs to update the UDP checksum bit<8> cf_byte_offset; // Byte offset at which the egress MAC needs to re-insert ptp_sync.correction field bit<48> updated_cf; // Updated correction field in ptp sync message }

PTP 的 correction field 用于记录目前为止产生的延迟，该 field 共有 64 位，其中高 48 位为 ns 级时间戳；进入交换机时该 field 具有初始值，Tofino 将在初始值上增加 eTS - iTS
由于 eTS 只能在 Egress MAC 中获取，P4 程序无法完成完整的 correction field 更新，因此实现逻辑应当如下:
在 P4 程序中读取 correction field 初始值以及 iTS，两者相减后存入 ptp_metadata_t.updated_cf，最后 Egress MAC 将会计算 updated_cf + eTS，并将其存入 cf_byte_offset 指向的位置;
如果 updated_cf 置为 0，则输出的结果就是 TS6 自身
Egress MAC 向数据包写 correction field 时不会覆盖 offset 位置的已有数据，而是插入 8 字节新数据（高 6 字节为时间戳，低 2 字节全零）
如果 correction field 位于 UDP 封装内，还需要更新 UDP 校验和；如果无需更新则设置 udp_cksum_byte_offset 为 0
注：完整的 PTP 时间戳有 64 位，Tofino 实现中高 16 位仅保留在控制面（控制面判断低 48 位是否 rollover，若发生则高 16 位增加 1），低 48 位体现在 Global Time Counter 中
TS7: 无法在 P4 中直接读取，但可以由控制面读取，通过在 P4 中设置以下 Intrinsic metadata 进行记录

元变量类型	元变量	含义
egress_intrinsic_metadata_for_output_port_t	bit<1> capture_tstamp_on_tx;	Request for packet departure timestamping at egress MAC for IEEE 1588
Egress Mac 会把 TS7 存入一个深度为 4 的 FIFO 队列中（每个出端口都有一个队列），可以在控制面通过 bf_port_1588_timestamp_tx_get() 接口获取值

由于涉及控制面，TS7 无法在高传输速率时准确获取（队列很快填满并溢出，控制面无法得知本次获取到的值属于哪个数据包）

TS7 的用例：日志、测试、PTP 同步

注：TS6 是数据包到达 Egress MAC 的时间戳，MAC 能够将其记入数据包；TS7 是数据包离开 Egress MAC 的时间戳，因此只能由控制面读取

不同时间戳的精度
TS1 / TS2 / TS5 三个时间戳都是 48 位，直接对应 Global time counter 中 Nanosecond componet 的值

约 3 天（78 小时）会 roll over 一次
TS3 的低 18 或 32 位通过 enq_tstamp 读取，高 30 或 16 位可以通过读取 TS2 获得

18 位的 enq_tstamp 每 262.1us rollover 一次；32 位的 enq_tstamp 每 4.3s rollover 一次
如果 TS2 的低 18/32 位大于 enq_tstamp，则 enq_tstamp 发生 rollover，需要将高 30 或 16 位加 1
TS4 通过在 TS3 上加 deq_timedelta 计算获得