#ifndef FLOW_HDR_USER_H
#define FLOW_HDR_USER_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <arpa/inet.h>

#include "flow_hdr.h"

static inline uint64_t flow_bswap64(uint64_t x)
{
#if defined(__GNUC__) || defined(__clang__)
    return __builtin_bswap64(x);
#else
    return ((x & 0x00000000000000ffULL) << 56) |
           ((x & 0x000000000000ff00ULL) << 40) |
           ((x & 0x0000000000ff0000ULL) << 24) |
           ((x & 0x00000000ff000000ULL) << 8)  |
           ((x & 0x000000ff00000000ULL) >> 8)  |
           ((x & 0x0000ff0000000000ULL) >> 24) |
           ((x & 0x00ff000000000000ULL) >> 40) |
           ((x & 0xff00000000000000ULL) >> 56);
#endif
}

#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
static inline uint64_t flow_cpu_to_be64(uint64_t x) { return flow_bswap64(x); }
static inline uint64_t flow_be64_to_cpu(uint64_t x) { return flow_bswap64(x); }
#else
static inline uint64_t flow_cpu_to_be64(uint64_t x) { return x; }
static inline uint64_t flow_be64_to_cpu(uint64_t x) { return x; }
#endif

static inline void flow_hdr_v1_init(struct flow_hdr_v1 *h,
                                    uint64_t flow_id,
                                    uint32_t pkt_idx,
                                    uint32_t pkt_cnt,
                                    uint32_t flow_size_bytes,
                                    uint32_t payload_bytes)
{
    memset(h, 0, sizeof(*h));
    h->magic = htonl(FLOW_MAGIC);
    h->ver = htons(FLOW_VER_V1);
    h->hdr_len = htons((uint16_t)sizeof(*h));
    h->flow_id = flow_cpu_to_be64(flow_id);
    h->pkt_idx = htonl(pkt_idx);
    h->pkt_cnt = htonl(pkt_cnt);
    h->flow_size_bytes = htonl(flow_size_bytes);
    h->payload_bytes = htonl(payload_bytes);
}

static inline bool flow_hdr_v1_basic_ok(const struct flow_hdr_v1 *h)
{
    if (!h)
        return false;

    return h->magic == htonl(FLOW_MAGIC) &&
           h->ver == htons(FLOW_VER_V1) &&
           ntohs(h->hdr_len) >= sizeof(struct flow_hdr_v1);
}

static inline uint64_t flow_get_flow_id(const struct flow_hdr_v1 *h)
{
    return flow_be64_to_cpu(h->flow_id);
}

static inline uint32_t flow_get_pkt_idx(const struct flow_hdr_v1 *h)
{
    return ntohl(h->pkt_idx);
}

static inline uint32_t flow_get_pkt_cnt(const struct flow_hdr_v1 *h)
{
    return ntohl(h->pkt_cnt);
}

static inline uint32_t flow_get_flow_size_bytes(const struct flow_hdr_v1 *h)
{
    return ntohl(h->flow_size_bytes);
}

static inline uint32_t flow_get_payload_bytes(const struct flow_hdr_v1 *h)
{
    return ntohl(h->payload_bytes);
}

#endif /* FLOW_HDR_USER_H */
