#ifndef HOPVAR_HDR_H
#define HOPVAR_HDR_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define HOPVAR_MAGIC        0x48565052u   /* 'HVPR' */
#define HOPVAR_VER_V1       1
#define HOPVAR_TS_SLOTS     10

/* valid_bitmap bit i => ts48[i] is valid */
#define HOPVAR_V_TS0        (1u << 0)
#define HOPVAR_V_TS1        (1u << 1)
#define HOPVAR_V_TS2        (1u << 2)
#define HOPVAR_V_TS3        (1u << 3)
#define HOPVAR_V_TS4        (1u << 4)
#define HOPVAR_V_TS5        (1u << 5)
#define HOPVAR_V_TS6        (1u << 6)
#define HOPVAR_V_TS7        (1u << 7)
#define HOPVAR_V_TS8        (1u << 8)
#define HOPVAR_V_TS9        (1u << 9)

#define HOPVAR_F_OVERFLOW   (1u << 0)  /* more ingress stamps than slots */
#define HOPVAR_F_TRUNCATED  (1u << 1)  /* packet/header malformed or shortened */

#pragma pack(push, 1)
struct hopvar_hdr_v1 {
    uint32_t magic;               /* network order */
    uint16_t ver;                 /* network order */
    uint16_t hdr_len;             /* network order */

    uint64_t req_id;              /* network order */
    uint16_t flags;               /* network order */
    uint16_t ts_count;            /* network order */

    uint8_t ts48[HOPVAR_TS_SLOTS][6];   /* big-endian 48-bit timestamps */

    uint32_t valid_bitmap;        /* network order */
    uint32_t reserved;            /* network order */
};
#pragma pack(pop)

#define HOPVAR_HDR_V1_LEN ((uint16_t)sizeof(struct hopvar_hdr_v1))

#ifdef __cplusplus
}
#endif

#endif /* HOPVAR_HDR_H */
