/* meas_hdr_v1.h
 *
 * Shared packet-carried measurement header definition for:
 *   - user-space sender / receiver
 *   - FPGA NIC RTL / simulation side reference
 *   - switch pipeline control-plane reference
 *
 * All multi-byte fields are serialized in network byte order (big-endian)
 * when carried in packet payload.
 */

#ifndef MEAS_HDR_V1_H
#define MEAS_HDR_V1_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MEAS_MAGIC      0x4d454153u  /* 'MEAS' */
#define MEAS_HDR_VER_V1 1

enum meas_clock_domain {
    MEAS_CLK_UNSPEC      = 0,
    MEAS_CLK_HOST_MONO   = 1,
    MEAS_CLK_NIC_LOCAL   = 2,
    MEAS_CLK_FABRIC_SYNC = 3,
    MEAS_CLK_GLOBAL_PTP  = 4,
};

/* valid_bitmap */
#define MEAS_V_T1           (1u << 0)
#define MEAS_V_T2           (1u << 1)
#define MEAS_V_T3           (1u << 2)
#define MEAS_V_T4           (1u << 3)
#define MEAS_V_T5           (1u << 4)
#define MEAS_V_T6           (1u << 5)
#define MEAS_V_T7           (1u << 6)
#define MEAS_V_S1           (1u << 7)
#define MEAS_V_S2           (1u << 8)
#define MEAS_V_SRC_DEV_ID   (1u << 9)
#define MEAS_V_SW_ID        (1u << 10)
#define MEAS_V_QUEUE_META   (1u << 11)

/* flags */
#define MEAS_F_SWITCH_TOUCHED   (1u << 0)
#define MEAS_F_NIC_TX_PATH      (1u << 1)
#define MEAS_F_NIC_RX_PATH      (1u << 2)
#define MEAS_F_FALLBACK_PATH    (1u << 3)
#define MEAS_F_TIME_UNSYNCED    (1u << 4)
#define MEAS_F_TRUNCATED_HDR    (1u << 5)
#define MEAS_F_REPLY_PACKET     (1u << 6)

/* error_bitmap */
#define MEAS_E_HDR_TOO_SHORT      (1u << 0)
#define MEAS_E_BAD_MAGIC          (1u << 1)
#define MEAS_E_NOT_WRITABLE       (1u << 2)
#define MEAS_E_CSUM_CONFLICT      (1u << 3)
#define MEAS_E_CLOCK_UNAVAILABLE  (1u << 4)
#define MEAS_E_PIPELINE_BYPASS    (1u << 5)
#define MEAS_E_UNSUPPORTED_VER    (1u << 6)
#define MEAS_E_PARSE_FAIL         (1u << 7)

/*
 * queue_meta layout (v1):
 *   [31:24] pipe / block / stage group
 *   [23:16] traffic class / priority
 *   [15: 8] queue id low 8 bits
 *   [ 7: 0] port / lane / endpoint id
 */
#define MEAS_QM_MAKE(pipe, tc, qid_low8, port) \
    ((((uint32_t)(pipe)     & 0xffu) << 24) | \
     (((uint32_t)(tc)       & 0xffu) << 16) | \
     (((uint32_t)(qid_low8) & 0xffu) <<  8) | \
     (((uint32_t)(port)     & 0xffu) <<  0))

#define MEAS_QM_PIPE(x)      (((uint32_t)(x) >> 24) & 0xffu)
#define MEAS_QM_TC(x)        (((uint32_t)(x) >> 16) & 0xffu)
#define MEAS_QM_QID8(x)      (((uint32_t)(x) >>  8) & 0xffu)
#define MEAS_QM_PORT(x)      (((uint32_t)(x) >>  0) & 0xffu)

/*
 * Timestamp semantics (v1):
 *   T1: sender application create/send point
 *   T2: host TX driver boundary
 *   T3: source FPGA NIC TX pipeline ingress
 *   T4: source FPGA NIC scheduler dequeue
 *   T5: source FPGA NIC MAC-adjacent egress
 *   T6: destination host RX driver boundary
 *   T7: reserved for reply path / destination app writeback
 *
 *   S1: programmable switch ingress
 *   S2: programmable switch egress
 */

#pragma pack(push, 1)
struct meas_hdr_v1 {
    uint32_t magic;         /* MEAS_MAGIC */
    uint16_t ver;           /* MEAS_HDR_VER_V1 */
    uint16_t hdr_len;       /* sizeof(struct meas_hdr_v1) */

    uint64_t req_id;        /* packet / transaction identifier */

    uint32_t valid_bitmap;  /* MEAS_V_* */
    uint16_t clock_domain;  /* enum meas_clock_domain */
    uint16_t flags;         /* MEAS_F_* */

    uint64_t T1;
    uint64_t T2;
    uint64_t T3;
    uint64_t T4;
    uint64_t T5;
    uint64_t T6;

    uint64_t S1;
    uint64_t S2;

    uint32_t src_dev_id;    /* source NIC / host identifier */
    uint32_t sw_id;         /* switch identifier */

    uint32_t queue_meta;    /* compact queue / pipe / tc / port summary */
    uint32_t error_bitmap;  /* MEAS_E_* */
};
#pragma pack(pop)

#define MEAS_HDR_V1_LEN ((uint16_t)sizeof(struct meas_hdr_v1))

#ifdef __cplusplus
}
#endif

#endif /* MEAS_HDR_V1_H */
