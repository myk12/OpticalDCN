#ifndef MEAS_HDR_V1_H
#define MEAS_HDR_V1_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MEAS_MAGIC      0x4d454153u
#define MEAS_HDR_VER_V1 1

enum meas_clock_domain {
    MEAS_CLK_UNSPEC      = 0,
    MEAS_CLK_HOST_MONO   = 1,
    MEAS_CLK_NIC_LOCAL   = 2,
    MEAS_CLK_FABRIC_SYNC = 3,
    MEAS_CLK_GLOBAL_PTP  = 4,
};

#define MEAS_V_T1           (1u << 0)
#define MEAS_V_T2           (1u << 1)
#define MEAS_V_T3           (1u << 2)
#define MEAS_V_T4           (1u << 3)
#define MEAS_V_T5           (1u << 4)
#define MEAS_V_T6           (1u << 5)
#define MEAS_V_T7           (1u << 6)
#define MEAS_V_T8           (1u << 7)
#define MEAS_V_SRC_DEV_ID   (1u << 8)
#define MEAS_V_SW_ID        (1u << 9)
#define MEAS_V_QUEUE_META   (1u << 10)

#define MEAS_F_SWITCH_TOUCHED   (1u << 0)
#define MEAS_F_NIC_TX_PATH      (1u << 1)
#define MEAS_F_NIC_RX_PATH      (1u << 2)
#define MEAS_F_FALLBACK_PATH    (1u << 3)
#define MEAS_F_TIME_UNSYNCED    (1u << 4)
#define MEAS_F_TRUNCATED_HDR    (1u << 5)
#define MEAS_F_REPLY_PACKET     (1u << 6)

#define MEAS_E_HDR_TOO_SHORT      (1u << 0)
#define MEAS_E_BAD_MAGIC          (1u << 1)
#define MEAS_E_NOT_WRITABLE       (1u << 2)
#define MEAS_E_CSUM_CONFLICT      (1u << 3)
#define MEAS_E_CLOCK_UNAVAILABLE  (1u << 4)
#define MEAS_E_PIPELINE_BYPASS    (1u << 5)
#define MEAS_E_UNSUPPORTED_VER    (1u << 6)
#define MEAS_E_PARSE_FAIL         (1u << 7)

#pragma pack(push, 1)
struct meas_hdr_v1 {
    uint32_t magic;
    uint16_t ver;
    uint16_t hdr_len;

    uint64_t req_id;

    uint32_t valid_bitmap;
    uint16_t clock_domain;
    uint16_t flags;

    uint64_t T1;
    uint64_t T2;
    uint64_t T3;
    uint64_t T4;
    uint64_t T5;
    uint64_t T6;
    uint64_t T7;
    uint64_t T8;

    uint32_t src_dev_id;
    uint32_t sw_id;

    uint32_t queue_meta;
    uint32_t error_bitmap;
};
#pragma pack(pop)

#define MEAS_HDR_V1_LEN ((uint16_t)sizeof(struct meas_hdr_v1))

#ifdef __cplusplus
}
#endif

#endif /* MEAS_HDR_V1_H */
