#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <netinet/in.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include "hopvar_hdr.h"
#include "hopvar_hdr_user.h"
#include "flow_hdr.h"
#include "flow_hdr_user.h"

enum run_mode {
    MODE_PACKET = 0,
    MODE_FLOW = 1,
};

#define MAX_FLOWS 100000

struct flow_state {
    bool used;
    uint64_t flow_id;
    uint64_t first_recv_ns;
    uint64_t last_recv_ns;
    uint32_t pkt_cnt_expected;
    uint32_t pkt_cnt_received;
    uint32_t flow_size_bytes;
    uint64_t bytes_received;
};

static uint64_t now_monotonic_ns(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        perror("clock_gettime");
        exit(1);
    }
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static enum run_mode parse_mode(const char *s)
{
    if (!strcmp(s, "packet")) return MODE_PACKET;
    if (!strcmp(s, "flow")) return MODE_FLOW;

    fprintf(stderr, "invalid mode: %s (must be 'packet' or 'flow')\n", s);
    exit(1);
}

static void usage(const char *prog)
{
    fprintf(stderr,
            "Usage: %s --mode {packet|flow} --bind-ip IP --listen-port PORT --csv FILE [options]\n"
            "\n"
            "Common options:\n"
            "  --mode MODE            packet | flow\n"
            "  --bind-ip IP           local IPv4 address to bind\n"
            "  --listen-port PORT     local UDP port to listen on\n"
            "  --csv FILE             output CSV file\n"
            "  --packet-count N       stop after receiving N packets\n"
            "  --flow-count N         stop after completing N flows (flow mode)\n"
            "  --buf-size N           recv buffer size (default: 4096)\n"
            "  --flush-every N        fflush every N rows (default: 1000 packet / 100 flow)\n",
            prog);
}

static size_t flow_slot(uint64_t flow_id)
{
    return (size_t)(flow_id % MAX_FLOWS);
}

static struct flow_state *get_flow_state(struct flow_state *tbl, uint64_t flow_id)
{
    size_t pos = flow_slot(flow_id);

    for (size_t i = 0; i < MAX_FLOWS; i++) {
        size_t idx = (pos + i) % MAX_FLOWS;
        if (!tbl[idx].used) {
            tbl[idx].used = true;
            tbl[idx].flow_id = flow_id;
            return &tbl[idx];
        }
        if (tbl[idx].flow_id == flow_id) {
            return &tbl[idx];
        }
    }

    return NULL;
}

static void write_packet_csv_header(FILE *csv)
{
    fprintf(csv,
            "recv_local_ns,peer_ip,peer_port,payload_len,"
            "req_id,flags,ts_count,valid_bitmap,reserved");
    for (int i = 0; i < HOPVAR_TS_SLOTS; i++) {
        fprintf(csv, ",ts%d", i);
    }
    fprintf(csv, "\n");
}

static void write_packet_csv_row(FILE *csv,
                                 uint64_t recv_local_ns,
                                 const char *peer_ip,
                                 uint16_t peer_port,
                                 size_t payload_len,
                                 const struct hopvar_hdr_v1 *h)
{
    uint64_t req_id = hopvar_get_req_id(h);
    uint16_t flags = hopvar_get_flags(h);
    uint16_t ts_count = hopvar_get_ts_count(h);
    uint32_t valid_bitmap = hopvar_get_valid_bitmap(h);
    uint32_t reserved = ntohl(h->reserved);

    fprintf(csv,
            "%" PRIu64 ",%s,%u,%zu,"
            "%" PRIu64 ",%u,%u,%u,%u",
            recv_local_ns,
            peer_ip,
            (unsigned)peer_port,
            payload_len,
            req_id,
            (unsigned)flags,
            (unsigned)ts_count,
            valid_bitmap,
            reserved);

    for (int i = 0; i < HOPVAR_TS_SLOTS; i++) {
        uint64_t ts = hopvar_get_ts48_at(h, i);
        if (ts != 0) {
            fprintf(csv, ",%" PRIu64, ts);
        } else {
            fprintf(csv, ",");
        }
    }
    fprintf(csv, "\n");
}

static void write_flow_csv_header(FILE *csv)
{
    fprintf(csv,
            "flow_id,flow_size_bytes,pkt_cnt_expected,pkt_cnt_received,bytes_received,"
            "recv_start_ns,recv_end_ns,fct_ns,flow_complete\n");
}

int main(int argc, char **argv)
{
    enum run_mode mode = MODE_PACKET;
    const char *bind_ip = NULL;
    const char *csv_path = NULL;
    int listen_port = -1;
    uint64_t packet_count = 10000;
    uint64_t flow_count = 0;
    size_t buf_size = 4096;
    uint64_t flush_every = 0;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--mode") && i + 1 < argc) {
            mode = parse_mode(argv[++i]);
        } else if (!strcmp(argv[i], "--bind-ip") && i + 1 < argc) {
            bind_ip = argv[++i];
        } else if (!strcmp(argv[i], "--listen-port") && i + 1 < argc) {
            listen_port = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--csv") && i + 1 < argc) {
            csv_path = argv[++i];
        } else if (!strcmp(argv[i], "--packet-count") && i + 1 < argc) {
            packet_count = strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--flow-count") && i + 1 < argc) {
            flow_count = strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--buf-size") && i + 1 < argc) {
            buf_size = (size_t)strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--flush-every") && i + 1 < argc) {
            flush_every = strtoull(argv[++i], NULL, 10);
        } else {
            usage(argv[0]);
            return 1;
        }
    }

    if (!bind_ip || listen_port <= 0 || listen_port > 65535 || !csv_path) {
        usage(argv[0]);
        return 1;
    }

    if (flush_every == 0) {
        flush_every = (mode == MODE_PACKET) ? 1000 : 100;
    }

    FILE *csv = fopen(csv_path, "w");
    if (!csv) {
        perror("fopen(csv)");
        return 1;
    }

    if (mode == MODE_PACKET) {
        write_packet_csv_header(csv);
    } else {
        write_flow_csv_header(csv);
    }

    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        fclose(csv);
        return 1;
    }

    int one = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)listen_port);
    if (inet_pton(AF_INET, bind_ip, &addr.sin_addr) != 1) {
        fprintf(stderr, "invalid bind IP: %s\n", bind_ip);
        close(fd);
        fclose(csv);
        return 1;
    }

    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        perror("bind");
        close(fd);
        fclose(csv);
        return 1;
    }

    uint8_t *buf = malloc(buf_size);
    struct flow_state *tbl = NULL;
    if (!buf) {
        perror("malloc");
        close(fd);
        fclose(csv);
        return 1;
    }

    if (mode == MODE_FLOW) {
        tbl = calloc(MAX_FLOWS, sizeof(*tbl));
        if (!tbl) {
            perror("calloc(flow table)");
            free(buf);
            close(fd);
            fclose(csv);
            return 1;
        }
    }

    printf("hopvar_receiver listening on %s:%d, mode=%s, writing CSV to %s\n",
           bind_ip, listen_port, mode == MODE_PACKET ? "packet" : "flow", csv_path);

    uint64_t recv_pkt_cnt = 0;
    uint64_t completed_flow_cnt = 0;
    uint64_t written_rows = 0;

    while (1) {
        if (mode == MODE_PACKET) {
            if (packet_count != 0 && recv_pkt_cnt >= packet_count)
                break;
        } else {
            if (flow_count != 0 && completed_flow_cnt >= flow_count)
                break;
            if (packet_count != 0 && recv_pkt_cnt >= packet_count)
                break;
        }

        struct sockaddr_in peer;
        socklen_t peer_len = sizeof(peer);
        ssize_t n = recvfrom(fd, buf, buf_size, 0, (struct sockaddr *)&peer, &peer_len);
        if (n < 0) {
            fprintf(stderr, "recvfrom failed: %s\n", strerror(errno));
            continue;
        }

        uint64_t recv_ns = now_monotonic_ns();

        char peer_ip[INET_ADDRSTRLEN] = {0};
        inet_ntop(AF_INET, &peer.sin_addr, peer_ip, sizeof(peer_ip));
        uint16_t peer_port = ntohs(peer.sin_port);

        if ((size_t)n < sizeof(struct hopvar_hdr_v1)) {
            recv_pkt_cnt++;
            continue;
        }

        const struct hopvar_hdr_v1 *hh = (const struct hopvar_hdr_v1 *)buf;
        if (!hopvar_hdr_v1_basic_ok(hh)) {
            recv_pkt_cnt++;
            continue;
        }

        if (mode == MODE_PACKET) {
            write_packet_csv_row(csv, recv_ns, peer_ip, peer_port, (size_t)n, hh);
            written_rows++;
            if (flush_every > 0 && (written_rows % flush_every) == 0) {
                fflush(csv);
            }
        } else {
            size_t min_len = sizeof(struct hopvar_hdr_v1) + sizeof(struct flow_hdr_v1);
            if ((size_t)n < min_len) {
                recv_pkt_cnt++;
                continue;
            }

            const struct flow_hdr_v1 *fh =
                (const struct flow_hdr_v1 *)(buf + sizeof(struct hopvar_hdr_v1));
            if (!flow_hdr_v1_basic_ok(fh)) {
                recv_pkt_cnt++;
                continue;
            }

            uint64_t flow_id = flow_get_flow_id(fh);
            uint32_t pkt_cnt_expected = flow_get_pkt_cnt(fh);
            uint32_t flow_size_bytes = flow_get_flow_size_bytes(fh);
            uint32_t payload_bytes = flow_get_payload_bytes(fh);

            struct flow_state *st = get_flow_state(tbl, flow_id);
            if (!st) {
                fprintf(stderr, "flow table full\n");
                recv_pkt_cnt++;
                continue;
            }

            if (st->pkt_cnt_received == 0) {
                st->first_recv_ns = recv_ns;
                st->pkt_cnt_expected = pkt_cnt_expected;
                st->flow_size_bytes = flow_size_bytes;
            }

            st->last_recv_ns = recv_ns;
            st->pkt_cnt_received += 1;
            st->bytes_received += payload_bytes;

            if (st->pkt_cnt_received == st->pkt_cnt_expected) {
                uint64_t fct_ns = st->last_recv_ns - st->first_recv_ns;
                fprintf(csv, "%" PRIu64 ",%u,%u,%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",1\n",
                        st->flow_id,
                        st->flow_size_bytes,
                        st->pkt_cnt_expected,
                        st->pkt_cnt_received,
                        st->bytes_received,
                        st->first_recv_ns,
                        st->last_recv_ns,
                        fct_ns);

                memset(st, 0, sizeof(*st));
                completed_flow_cnt++;
                written_rows++;

                if (flush_every > 0 && (written_rows % flush_every) == 0) {
                    fflush(csv);
                }
            }
        }

        recv_pkt_cnt++;
    }

    fclose(csv);
    free(buf);
    free(tbl);
    close(fd);
    return 0;
}
