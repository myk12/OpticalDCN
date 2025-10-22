#undef TRACE_SYSTEM
#define TRACE_SYSTEM mqnic_trace

#if !defined(_MQNIC_TRACE_H_) || defined(TRACE_HEADER_MULTI_READ)
#define _MQNIC_TRACE_H_

#include <linux/tracepoint.h>

// mqnic timestamping test suite
//
// All timestamps should be in PHC nanoseconds (driver reads PHC and passes here)
// Typical fields:
//   - qid: queue ID (TX or RX)
//   - seq: sequence number (incremented for each packet sent)
//   - ts_ns: timestamp in PHC nanoseconds
//

// TX: enqueue at driver
TRACE_EVENT(mqnic_tx_enqueue,
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
	TP_printk("TX enqueue: qid=%d seq=%u ts_ns=%llu",
		__entry->qid,
		__entry->seq,
		__entry->ts_ns)
);

// TX: HW completion (PHC timestamp from NIC/FPGA)
TRACE_EVENT(mqnic_tx_cpl,
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
	TP_printk("TX completion: qid=%d seq=%u ts_ns=%llu",
		__entry->qid,
		__entry->seq,
		__entry->ts_ns)
);

// RX: HW completion (PHC timestamp from NIC/FPGA)
TRACE_EVENT(mqnic_rx_cpl,
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
	TP_printk("RX completion: qid=%d seq=%u ts_ns=%llu",
		__entry->qid,
		__entry->seq,
		__entry->ts_ns)
);

// RX: deliver to stack
TRACE_EVENT(mqnic_rx_deliver,
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
	TP_printk("RX deliver: qid=%d seq=%u ts_ns=%llu",
		__entry->qid,
		__entry->seq,
		__entry->ts_ns)
);


#endif /* _MQNIC_TRACE_H_ */

#include <trace/define_trace.h>
