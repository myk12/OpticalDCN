#ifndef FLOW_HDR_H
#define FLOW_HDR_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FLOW_MAGIC   0x464c4f57u   /* 'FLOW' */
#define FLOW_VER_V1  1

#pragma pack(push, 1)
struct flow_hdr_v1 {
    uint32_t magic;              /* network order */
    uint16_t ver;                /* network order */
    uint16_t hdr_len;            /* network order */

    uint64_t flow_id;            /* network order */
    uint32_t pkt_idx;            /* network order */
    uint32_t pkt_cnt;            /* network order */

    uint32_t flow_size_bytes;    /* network order */
    uint32_t payload_bytes;      /* network order */
};
#pragma pack(pop)

#define FLOW_HDR_V1_LEN ((uint16_t)sizeof(struct flow_hdr_v1))

#ifdef __cplusplus
}
#endif

#endif /* FLOW_HDR_H */
