/* SPDX-License-Identifier: GPL-2.0 */

#undef TRACE_SYSTEM
#define TRACE_SYSTEM mqnic_ts_probe

#if !defined(_MQNIC_TS_PROBE_TRACE_H_) || defined(TRACE_HEADER_MULTI_READ)
#define _MQNIC_TS_PROBE_TRACE_H_

#include <linux/types.h>
#include <linux/tracepoint.h>

// TX: enqueue at driver
TRACE_EVENT(mqnic_ts_probe_tx_enqueue,
    TP_PROTO(int qid, u16 seq, u64 ts_ns),
    TP_ARGS(qid, seq, ts_ns),
    TP_STRUCT__entry(
        __field(int, qid)
        __field(u16, seq)
        __field(u64, ts_ns)
    ),
    TP_fast_assign(
        __entry->qid = qid;
        __entry->seq = seq;
        __entry->ts_ns = ts_ns;
    ),
    TP_printk("TX enqueue: qid=%d,seq=%u,ts_ns=%llu",
        __entry->qid,
        __entry->seq,
        __entry->ts_ns)
);

// TX: HW completion (PHC timestamp from NIC/FPGA)
TRACE_EVENT(mqnic_ts_probe_tx_cpl,
    TP_PROTO(int qid, u16 seq, u64 ts_ns),
    TP_ARGS(qid, seq, ts_ns),
    TP_STRUCT__entry(
        __field(int, qid)
        __field(u16, seq)
        __field(u64, ts_ns)
    ),
    TP_fast_assign(
        __entry->qid = qid;
        __entry->seq = seq;
        __entry->ts_ns = ts_ns;
    ),
    TP_printk("TX completion: qid=%d,seq=%u,ts_ns=%llu",
        __entry->qid,
        __entry->seq,
        __entry->ts_ns)
);

// RX: HW completion (PHC timestamp from NIC/FPGA)
TRACE_EVENT(mqnic_ts_probe_rx_cpl,
    TP_PROTO(int qid, u16 seq, u64 ts_ns),
    TP_ARGS(qid, seq, ts_ns),
    TP_STRUCT__entry(
        __field(int, qid)
        __field(u16, seq)
        __field(u64, ts_ns)
    ),
    TP_fast_assign(
        __entry->qid = qid;
        __entry->seq = seq;
        __entry->ts_ns = ts_ns;
    ),
    TP_printk("RX completion: qid=%d,seq=%u,ts_ns=%llu",
        __entry->qid,
        __entry->seq,
        __entry->ts_ns)
);

// RX: deliver to stack
TRACE_EVENT(mqnic_ts_probe_rx_deliver,
    TP_PROTO(int qid, u16 seq, u64 ts_ns),
    TP_ARGS(qid, seq, ts_ns),
    TP_STRUCT__entry(
        __field(int, qid)
        __field(u16, seq)
        __field(u64, ts_ns)
    ),
    TP_fast_assign(
        __entry->qid = qid;
        __entry->seq = seq;
        __entry->ts_ns = ts_ns;
    ),
    TP_printk("RX deliver: qid=%d,seq=%u,ts_ns=%llu",
        __entry->qid,
        __entry->seq,
        __entry->ts_ns)
);

#endif /* _MQNIC_TS_PROBE_TRACE_H_ */

#include <trace/define_trace.h>
