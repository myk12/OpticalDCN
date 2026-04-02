// SPDX-License-Identifier: BSD-2-Clause-Views
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <arpa/inet.h>
#include <errno.h>
#include <getopt.h>
#include <inttypes.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <strings.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#define MAX_PKT_SIZE 65536
#define HOPVAR_TS_SLOTS 10

static volatile sig_atomic_t keep_running = 1;

static void handle_sigint(int sig)
{
    (void)sig;
    keep_running = 0;
}

#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
static inline uint64_t ntohll_u64(uint64_t x)
{
    return __builtin_bswap64(x);
}
#else
static inline uint64_t ntohll_u64(uint64_t x)
{
    return x;
}
#endif

#pragma pack(push, 1)
struct hopvar_hdr_v1 {
    uint32_t magic;               /* network order */
    uint16_t ver;                 /* network order */
    uint16_t hdr_len;             /* network order */

    uint64_t req_id;              /* network order, reused as seq number */
    uint16_t flags;               /* network order */
    uint16_t ts_count;            /* network order */

    uint8_t ts48[HOPVAR_TS_SLOTS][6];   /* big-endian 48-bit timestamps */

    uint32_t valid_bitmap;        /* network order */
    uint32_t reserved;            /* network order */
};
#pragma pack(pop)

struct config {
    const char *bind_ip;
    uint16_t listen_port;
    uint64_t flow_size_bytes;
    uint64_t packet_size_bytes;
    uint64_t flow_count;
    const char *csv_path;
};

struct flow_state {
    uint64_t flow_id;
    uint64_t pkt_cnt_expected;
    uint64_t pkt_cnt_received;

    uint64_t first_req_id;
    uint64_t last_req_id;
    uint64_t expected_next_req_id;

    uint64_t first_ts0;
    uint64_t last_ts[HOPVAR_TS_SLOTS];

    uint16_t first_ts_count;
    uint16_t last_ts_count;

    uint32_t first_valid_bitmap;
    uint32_t last_valid_bitmap;

    bool started;
    bool complete;
    bool fail;
};

static void usage(const char *prog)
{
    fprintf(stderr,
        "Usage: %s [OPTIONS]\n"
        "  --bind-ip IP           Bind IP (default: 0.0.0.0)\n"
        "  --listen-port PORT     UDP port to listen on (default: 1999)\n"
        "  --flow-size SIZE       Flow size, e.g. 1MB, 16MB, 256KB (required)\n"
        "  --packet-size SIZE     Packet size used to count packets per flow,\n"
        "                         e.g. 1024B, 1KB (required)\n"
        "  --flow-count COUNT     Number of flows to receive (required)\n"
        "  --csv PATH             Output CSV path (default: flow_fct_by_hop.csv)\n",
        prog);
}

static uint64_t parse_size_bytes(const char *s)
{
    char *end = NULL;
    double value = strtod(s, &end);
    uint64_t mult = 1ull;
    double bytes_f;

    if (end == s || value <= 0) {
        fprintf(stderr, "invalid size: %s\n", s);
        exit(EXIT_FAILURE);
    }

    while (*end == ' ' || *end == '\t') {
        end++;
    }

    if (*end == '\0' || strcasecmp(end, "B") == 0) {
        mult = 1ull;
    } else if (strcasecmp(end, "KB") == 0 || strcasecmp(end, "K") == 0) {
        mult = 1024ull;
    } else if (strcasecmp(end, "MB") == 0 || strcasecmp(end, "M") == 0) {
        mult = 1024ull * 1024ull;
    } else if (strcasecmp(end, "GB") == 0 || strcasecmp(end, "G") == 0) {
        mult = 1024ull * 1024ull * 1024ull;
    } else {
        fprintf(stderr, "invalid size suffix in: %s\n", s);
        exit(EXIT_FAILURE);
    }

    bytes_f = value * (double)mult;
    if (bytes_f <= 0 || bytes_f > (double)UINT64_MAX) {
        fprintf(stderr, "size out of range: %s\n", s);
        exit(EXIT_FAILURE);
    }

    return (uint64_t)(bytes_f + 0.5);
}

static int parse_args(int argc, char **argv, struct config *cfg)
{
    static struct option long_options[] = {
        {"bind-ip", required_argument, 0, 'b'},
        {"listen-port", required_argument, 0, 'p'},
        {"flow-size", required_argument, 0, 's'},
        {"packet-size", required_argument, 0, 'k'},
        {"flow-count", required_argument, 0, 'c'},
        {"csv", required_argument, 0, 'o'},
        {0, 0, 0, 0}
    };

    cfg->bind_ip = "0.0.0.0";
    cfg->listen_port = 1999;
    cfg->flow_size_bytes = 0;
    cfg->packet_size_bytes = 0;
    cfg->flow_count = 0;
    cfg->csv_path = "flow_fct_by_hop.csv";

    while (1) {
        int option_index = 0;
        int opt = getopt_long(argc, argv, "", long_options, &option_index);
        if (opt == -1)
            break;

        switch (opt) {
        case 'b':
            cfg->bind_ip = optarg;
            break;
        case 'p':
            cfg->listen_port = (uint16_t)strtoul(optarg, NULL, 10);
            break;
        case 's':
            cfg->flow_size_bytes = parse_size_bytes(optarg);
            break;
        case 'k':
            cfg->packet_size_bytes = parse_size_bytes(optarg);
            break;
        case 'c':
            cfg->flow_count = strtoull(optarg, NULL, 10);
            break;
        case 'o':
            cfg->csv_path = optarg;
            break;
        default:
            usage(argv[0]);
            return -1;
        }
    }

    if (cfg->flow_size_bytes == 0 || cfg->packet_size_bytes == 0 || cfg->flow_count == 0) {
        usage(argv[0]);
        return -1;
    }

    return 0;
}

static uint64_t ceil_div_u64(uint64_t a, uint64_t b)
{
    return (a + b - 1) / b;
}

static uint64_t read_be48(const uint8_t b[6])
{
    return ((uint64_t)b[0] << 40) |
           ((uint64_t)b[1] << 32) |
           ((uint64_t)b[2] << 24) |
           ((uint64_t)b[3] << 16) |
           ((uint64_t)b[4] << 8)  |
           ((uint64_t)b[5]);
}

static void flow_state_init(struct flow_state *st, uint64_t flow_id, uint64_t pkt_cnt_expected)
{
    memset(st, 0, sizeof(*st));
    st->flow_id = flow_id;
    st->pkt_cnt_expected = pkt_cnt_expected;
}

static void write_csv_header(FILE *fp)
{
    int i;
    fprintf(fp,
        "flow_id,flow_size_bytes,packet_size_bytes,pkt_cnt_expected,pkt_cnt_received,"
        "first_req_id,last_req_id,first_ts0,"
        "last_ts_count,last_valid_bitmap");
    for (i = 0; i < HOPVAR_TS_SLOTS; i++) {
        fprintf(fp, ",last_ts%d", i);
    }
    for (i = 0; i < HOPVAR_TS_SLOTS; i++) {
        fprintf(fp, ",fct_hop%d_ns", i);
    }
    fprintf(fp, ",flow_complete,flow_fail\n");
}

static void write_flow_row(FILE *fp, const struct config *cfg, const struct flow_state *st)
{
    int i;
    fprintf(fp,
        "%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ","
        "%" PRIu64 ",%" PRIu64 ",%" PRIu64 ","
        "%" PRIu16 ",%" PRIu32,
        st->flow_id,
        cfg->flow_size_bytes,
        cfg->packet_size_bytes,
        st->pkt_cnt_expected,
        st->pkt_cnt_received,
        st->first_req_id,
        st->last_req_id,
        st->first_ts0,
        st->last_ts_count,
        st->last_valid_bitmap);

    for (i = 0; i < HOPVAR_TS_SLOTS; i++) {
        fprintf(fp, ",%" PRIu64, st->last_ts[i]);
    }

    for (i = 0; i < HOPVAR_TS_SLOTS; i++) {
        uint64_t fct = 0;
        if (st->first_ts0 != 0 && st->last_ts[i] != 0 && st->last_ts[i] >= st->first_ts0) {
            fct = st->last_ts[i] - st->first_ts0;
        }
        fprintf(fp, ",%" PRIu64, fct);
    }

    fprintf(fp, ",%d,%d\n", st->complete ? 1 : 0, st->fail ? 1 : 0);
}

struct parsed_pkt {
    uint64_t req_id;
    uint16_t ts_count;
    uint32_t valid_bitmap;
    uint64_t ts[HOPVAR_TS_SLOTS];
};

static bool parse_packet(const uint8_t *buf, size_t n, struct parsed_pkt *pkt)
{
    size_t i;
    const struct hopvar_hdr_v1 *hdr;

    if (n < sizeof(struct hopvar_hdr_v1)) {
        return false;
    }

    hdr = (const struct hopvar_hdr_v1 *)buf;
    pkt->req_id = ntohll_u64(hdr->req_id);
    pkt->ts_count = ntohs(hdr->ts_count);
    pkt->valid_bitmap = ntohl(hdr->valid_bitmap);

    for (i = 0; i < HOPVAR_TS_SLOTS; i++) {
        pkt->ts[i] = read_be48(hdr->ts48[i]);
    }

    return true;
}

static void start_flow_from_packet(struct flow_state *st, const struct parsed_pkt *pkt)
{
    size_t i;

    st->started = true;
    st->pkt_cnt_received = 1;
    st->first_req_id = pkt->req_id;
    st->last_req_id = pkt->req_id;
    st->expected_next_req_id = pkt->req_id + 1;

    st->first_ts0 = pkt->ts[0];
    st->first_ts_count = pkt->ts_count;
    st->first_valid_bitmap = pkt->valid_bitmap;

    st->last_ts_count = pkt->ts_count;
    st->last_valid_bitmap = pkt->valid_bitmap;

    for (i = 0; i < HOPVAR_TS_SLOTS; i++) {
        st->last_ts[i] = pkt->ts[i];
    }
}

static void append_packet_to_flow(struct flow_state *st, const struct parsed_pkt *pkt)
{
    size_t i;

    st->pkt_cnt_received++;
    st->last_req_id = pkt->req_id;
    st->expected_next_req_id = pkt->req_id + 1;
    st->last_ts_count = pkt->ts_count;
    st->last_valid_bitmap = pkt->valid_bitmap;

    for (i = 0; i < HOPVAR_TS_SLOTS; i++) {
        st->last_ts[i] = pkt->ts[i];
    }
}

int main(int argc, char **argv)
{
    struct config cfg;
    uint64_t pkt_cnt_expected;
    int fd;
    int reuse = 1;
    struct sockaddr_in addr;
    FILE *csv;
    uint8_t buf[MAX_PKT_SIZE];
    uint64_t next_flow_id = 1;
    struct flow_state st;

    if (parse_args(argc, argv, &cfg) != 0)
        return 1;

    signal(SIGINT, handle_sigint);
    signal(SIGTERM, handle_sigint);

    pkt_cnt_expected = ceil_div_u64(cfg.flow_size_bytes, cfg.packet_size_bytes);

    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        return 1;
    }

    if (setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse)) < 0) {
        perror("setsockopt(SO_REUSEADDR)");
        close(fd);
        return 1;
    }

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(cfg.listen_port);
    if (inet_pton(AF_INET, cfg.bind_ip, &addr.sin_addr) != 1) {
        fprintf(stderr, "invalid bind ip: %s\n", cfg.bind_ip);
        close(fd);
        return 1;
    }

    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(fd);
        return 1;
    }

    csv = fopen(cfg.csv_path, "w");
    if (!csv) {
        perror("fopen(csv)");
        close(fd);
        return 1;
    }

    write_csv_header(csv);
    fflush(csv);

    fprintf(stderr,
        "pktgen_hopvar_flow_receiver listening on %s:%u, "
        "flow_size=%" PRIu64 "B, packet_size=%" PRIu64 "B, "
        "pkt_cnt_expected=%" PRIu64 ", flow_count=%" PRIu64 ", csv=%s\n",
        cfg.bind_ip, cfg.listen_port,
        cfg.flow_size_bytes, cfg.packet_size_bytes,
        pkt_cnt_expected, cfg.flow_count, cfg.csv_path);

    flow_state_init(&st, next_flow_id, pkt_cnt_expected);

    while (keep_running && next_flow_id <= cfg.flow_count) {
        ssize_t n;
        struct parsed_pkt pkt;
        bool ok;

        n = recvfrom(fd, buf, sizeof(buf), 0, NULL, NULL);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            perror("recvfrom");
            break;
        }

        ok = parse_packet(buf, (size_t)n, &pkt);
        if (!ok) {
            fprintf(stderr, "warning: short or invalid packet (%zd bytes), ignored\n", n);
            continue;
        }

        if (!st.started) {
            start_flow_from_packet(&st, &pkt);
        } else {
            if (pkt.req_id != st.expected_next_req_id) {
                fprintf(stderr,
                    "flow_id=%" PRIu64 " FAIL: expected req_id=%" PRIu64
                    " but got %" PRIu64 "; pkt_cnt_received=%" PRIu64 "\n",
                    st.flow_id,
                    st.expected_next_req_id,
                    pkt.req_id,
                    st.pkt_cnt_received);

                st.fail = true;
                st.complete = false;
                write_flow_row(csv, &cfg, &st);
                fflush(csv);

                next_flow_id++;
                if (next_flow_id > cfg.flow_count) {
                    break;
                }

                flow_state_init(&st, next_flow_id, pkt_cnt_expected);

                /* Start next flow using current packet */
                start_flow_from_packet(&st, &pkt);
            } else {
                append_packet_to_flow(&st, &pkt);
            }
        }

        if (st.started && st.pkt_cnt_received >= st.pkt_cnt_expected) {
            st.complete = true;
            st.fail = false;
            write_flow_row(csv, &cfg, &st);
            fflush(csv);

            // logout flow completion every 10000 flows to avoid too much logging
            if (st.flow_id % 1000 == 0) {
                fprintf(stderr,
                    "completed flow_id=%" PRIu64
                    " pkts=%" PRIu64 "/%" PRIu64
                    " req_id_range=[%" PRIu64 ", %" PRIu64 "]\n",
                    st.flow_id,
                    st.pkt_cnt_received,
                    st.pkt_cnt_expected,
                    st.first_req_id,
                    st.last_req_id);
            }

            next_flow_id++;
            if (next_flow_id > cfg.flow_count) {
                break;
            }

            flow_state_init(&st, next_flow_id, pkt_cnt_expected);
        }
    }

    if (st.started && !st.complete && !st.fail) {
        write_flow_row(csv, &cfg, &st);
        fflush(csv);
        fprintf(stderr,
            "partial flow_id=%" PRIu64 " pkts=%" PRIu64 "/%" PRIu64 "\n",
            st.flow_id, st.pkt_cnt_received, st.pkt_cnt_expected);
    }

    fclose(csv);
    close(fd);
    return 0;
}
