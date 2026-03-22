/* meas_hdr_v1_user.h
 *
 * User-space helpers for sender / receiver.
 */

#ifndef MEAS_HDR_V1_USER_H
#define MEAS_HDR_V1_USER_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <arpa/inet.h>

#include "meas_hdr.h"

static inline uint64_t meas_bswap64(uint64_t x)
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
static inline uint64_t meas_cpu_to_be64(uint64_t x) { return meas_bswap64(x); }
static inline uint64_t meas_be64_to_cpu(uint64_t x) { return meas_bswap64(x); }
#else
static inline uint64_t meas_cpu_to_be64(uint64_t x) { return x; }
static inline uint64_t meas_be64_to_cpu(uint64_t x) { return x; }
#endif

static inline void meas_hdr_v1_init(struct meas_hdr_v1 *mh,
                                    uint64_t req_id,
                                    uint16_t clock_domain,
                                    uint64_t t1_ns)
{
    memset(mh, 0, sizeof(*mh));
    mh->magic        = htonl(MEAS_MAGIC);
    mh->ver          = htons(MEAS_HDR_VER_V1);
    mh->hdr_len      = htons((uint16_t)sizeof(*mh));
    mh->req_id       = meas_cpu_to_be64(req_id);
    mh->clock_domain = htons(clock_domain);
    mh->T1           = meas_cpu_to_be64(t1_ns);
    mh->valid_bitmap = htonl(MEAS_V_T1);
}

static inline bool meas_hdr_v1_basic_ok_user(const struct meas_hdr_v1 *mh)
{
    if (!mh)
        return false;

    return mh->magic == htonl(MEAS_MAGIC) &&
           mh->ver   == htons(MEAS_HDR_VER_V1) &&
           ntohs(mh->hdr_len) >= sizeof(struct meas_hdr_v1);
}

static inline uint32_t meas_get_valid_bitmap(const struct meas_hdr_v1 *mh)
{
    return ntohl(mh->valid_bitmap);
}

static inline uint16_t meas_get_flags(const struct meas_hdr_v1 *mh)
{
    return ntohs(mh->flags);
}

static inline uint32_t meas_get_error_bitmap(const struct meas_hdr_v1 *mh)
{
    return ntohl(mh->error_bitmap);
}

static inline uint16_t meas_get_clock_domain(const struct meas_hdr_v1 *mh)
{
    return ntohs(mh->clock_domain);
}

static inline uint64_t meas_get_req_id(const struct meas_hdr_v1 *mh)
{
    return meas_be64_to_cpu(mh->req_id);
}

static inline uint64_t meas_get_t1(const struct meas_hdr_v1 *mh)
{
    return meas_be64_to_cpu(mh->T1);
}

static inline uint64_t meas_get_t2(const struct meas_hdr_v1 *mh)
{
    return meas_be64_to_cpu(mh->T2);
}

static inline uint64_t meas_get_t3(const struct meas_hdr_v1 *mh)
{
    return meas_be64_to_cpu(mh->T3);
}

static inline uint64_t meas_get_t4(const struct meas_hdr_v1 *mh)
{
    return meas_be64_to_cpu(mh->T4);
}

static inline uint64_t meas_get_t5(const struct meas_hdr_v1 *mh)
{
    return meas_be64_to_cpu(mh->T5);
}

static inline uint64_t meas_get_t6(const struct meas_hdr_v1 *mh)
{
    return meas_be64_to_cpu(mh->T6);
}

static inline uint64_t meas_get_t7(const struct meas_hdr_v1 *mh)
{
    return meas_be64_to_cpu(mh->T7);
}

static inline uint64_t meas_get_t8(const struct meas_hdr_v1 *mh)
{
    return meas_be64_to_cpu(mh->T8);
}

static inline uint32_t meas_get_src_dev_id(const struct meas_hdr_v1 *mh)
{
    return ntohl(mh->src_dev_id);
}

static inline uint32_t meas_get_sw_id(const struct meas_hdr_v1 *mh)
{
    return ntohl(mh->sw_id);
}

static inline uint32_t meas_get_queue_meta(const struct meas_hdr_v1 *mh)
{
    return ntohl(mh->queue_meta);
}

#endif /* MEAS_HDR_V1_USER_H */
