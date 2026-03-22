#ifndef HOPVAR_HDR_USER_H
#define HOPVAR_HDR_USER_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <arpa/inet.h>

#include "hopvar_hdr.h"

static inline uint64_t hopvar_bswap64(uint64_t x)
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
static inline uint64_t hopvar_cpu_to_be64(uint64_t x) { return hopvar_bswap64(x); }
static inline uint64_t hopvar_be64_to_cpu(uint64_t x) { return hopvar_bswap64(x); }
#else
static inline uint64_t hopvar_cpu_to_be64(uint64_t x) { return x; }
static inline uint64_t hopvar_be64_to_cpu(uint64_t x) { return x; }
#endif

static inline void hopvar_set_be48(uint8_t out[6], uint64_t v)
{
    out[0] = (uint8_t)((v >> 40) & 0xffu);
    out[1] = (uint8_t)((v >> 32) & 0xffu);
    out[2] = (uint8_t)((v >> 24) & 0xffu);
    out[3] = (uint8_t)((v >> 16) & 0xffu);
    out[4] = (uint8_t)((v >>  8) & 0xffu);
    out[5] = (uint8_t)((v >>  0) & 0xffu);
}

static inline uint64_t hopvar_get_be48(const uint8_t in[6])
{
    return ((uint64_t)in[0] << 40) |
           ((uint64_t)in[1] << 32) |
           ((uint64_t)in[2] << 24) |
           ((uint64_t)in[3] << 16) |
           ((uint64_t)in[4] <<  8) |
           ((uint64_t)in[5] <<  0);
}

static inline void hopvar_hdr_v1_init(struct hopvar_hdr_v1 *h, uint64_t req_id)
{
    memset(h, 0, sizeof(*h));
    h->magic = htonl(HOPVAR_MAGIC);
    h->ver = htons(HOPVAR_VER_V1);
    h->hdr_len = htons((uint16_t)sizeof(*h));
    h->req_id = hopvar_cpu_to_be64(req_id);
    h->flags = htons(0);
    h->ts_count = htons(0);
    h->valid_bitmap = htonl(0);
    h->reserved = htonl(0);
}

static inline bool hopvar_hdr_v1_basic_ok(const struct hopvar_hdr_v1 *h)
{
    if (!h)
        return false;

    return h->magic == htonl(HOPVAR_MAGIC) &&
           h->ver == htons(HOPVAR_VER_V1) &&
           ntohs(h->hdr_len) >= sizeof(struct hopvar_hdr_v1) &&
           ntohs(h->ts_count) <= HOPVAR_TS_SLOTS;
}

static inline uint64_t hopvar_get_req_id(const struct hopvar_hdr_v1 *h)
{
    return hopvar_be64_to_cpu(h->req_id);
}

static inline uint16_t hopvar_get_flags(const struct hopvar_hdr_v1 *h)
{
    return ntohs(h->flags);
}

static inline uint16_t hopvar_get_ts_count(const struct hopvar_hdr_v1 *h)
{
    return ntohs(h->ts_count);
}

static inline uint32_t hopvar_get_valid_bitmap(const struct hopvar_hdr_v1 *h)
{
    return ntohl(h->valid_bitmap);
}

static inline uint64_t hopvar_get_ts48_at(const struct hopvar_hdr_v1 *h, int idx)
{
    if (!h || idx < 0 || idx >= HOPVAR_TS_SLOTS)
        return 0;
    return hopvar_get_be48(h->ts48[idx]);
}

static inline void hopvar_set_ts48_at(struct hopvar_hdr_v1 *h, int idx, uint64_t ts48)
{
    uint32_t vb;

    if (!h || idx < 0 || idx >= HOPVAR_TS_SLOTS)
        return;

    ts48 &= 0x0000ffffffffffffULL;
    hopvar_set_be48(h->ts48[idx], ts48);

    vb = ntohl(h->valid_bitmap);
    vb |= (1u << idx);
    h->valid_bitmap = htonl(vb);
}

static inline bool hopvar_append_ts48(struct hopvar_hdr_v1 *h, uint64_t ts48)
{
    uint16_t cnt;
    uint16_t flags;

    if (!h)
        return false;

    cnt = ntohs(h->ts_count);
    if (cnt >= HOPVAR_TS_SLOTS) {
        flags = ntohs(h->flags);
        flags |= HOPVAR_F_OVERFLOW;
        h->flags = htons(flags);
        return false;
    }

    hopvar_set_ts48_at(h, cnt, ts48);
    h->ts_count = htons((uint16_t)(cnt + 1));
    return true;
}

#endif /* HOPVAR_HDR_USER_H */