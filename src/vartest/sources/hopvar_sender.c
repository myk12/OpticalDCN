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
            "Usage: %s --mode {packet|flow} --dst-ip IP --dst-port PORT [options]\n"
            "\n"
            "Common options:\n"
            "  --mode MODE            packet | flow\n"
            "  --dst-ip IP            destination IPv4 address\n"
            "  --dst-port PORT        destination UDP port\n"
            "  --payload-len N        UDP payload length including headers (default: 1400)\n"
            "  --bind-ip IP           optional source bind IPv4 address\n"
            "  --csv FILE             output CSV file\n"
            "\n"
            "Packet mode options:\n"
            "  --count N              number of packets to send (default: 1)\n"
            "  --interval-us N        interval between packets in us (default: 1000000)\n"
            "  --start-req-id N       starting req_id (default: 1)\n"
            "\n"
            "Flow mode options:\n"
            "  --flow-size BYTES      application bytes per flow\n"
            "  --num-flows N          number of flows (default: 1)\n"
            "  --start-flow-id N      starting flow_id (default: 1)\n"
            "  --inter-flow-gap-us N  gap between flows in us (default: 0)\n",
            prog);
}

int main(int argc, char **argv)
{
    enum run_mode mode = MODE_PACKET;
    const char *dst_ip = NULL;
    const char *bind_ip = NULL;
    const char *csv_path = NULL;
    int dst_port = -1;
    size_t payload_len = 1400;

    /* packet mode */
    uint64_t count = 10000;
    uint64_t interval_us = 1;
    uint64_t start_req_id = 1;

    /* flow mode */
    uint32_t flow_size_bytes = 0;
    uint64_t num_flows = 1;
    uint64_t start_flow_id = 1;
    uint64_t inter_flow_gap_us = 0;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--mode") && i + 1 < argc) {
            mode = parse_mode(argv[++i]);
        } else if (!strcmp(argv[i], "--dst-ip") && i + 1 < argc) {
            dst_ip = argv[++i];
        } else if (!strcmp(argv[i], "--dst-port") && i + 1 < argc) {
            dst_port = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--payload-len") && i + 1 < argc) {
            payload_len = (size_t)strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--bind-ip") && i + 1 < argc) {
            bind_ip = argv[++i];
        } else if (!strcmp(argv[i], "--csv") && i + 1 < argc) {
            csv_path = argv[++i];
        } else if (!strcmp(argv[i], "--count") && i + 1 < argc) {
            count = strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--interval-us") && i + 1 < argc) {
            interval_us = strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--start-req-id") && i + 1 < argc) {
            start_req_id = strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--flow-size") && i + 1 < argc) {
            flow_size_bytes = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--num-flows") && i + 1 < argc) {
            num_flows = strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--start-flow-id") && i + 1 < argc) {
            start_flow_id = strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--inter-flow-gap-us") && i + 1 < argc) {
            inter_flow_gap_us = strtoull(argv[++i], NULL, 10);
        } else {
            usage(argv[0]);
            return 1;
        }
    }

    if (!dst_ip || dst_port <= 0 || dst_port > 65535) {
        usage(argv[0]);
        return 1;
    }

    size_t header_bytes = sizeof(struct hopvar_hdr_v1);
    if (mode == MODE_FLOW) {
        header_bytes += sizeof(struct flow_hdr_v1);
    }

    if (payload_len < header_bytes) {
        fprintf(stderr, "payload_len=%zu too small, must be >= %zu\n",
                payload_len, header_bytes);
        return 1;
    }

    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        return 1;
    }

    if (bind_ip) {
        struct sockaddr_in src_addr;
        memset(&src_addr, 0, sizeof(src_addr));
        src_addr.sin_family = AF_INET;
        src_addr.sin_port = htons(0);
        if (inet_pton(AF_INET, bind_ip, &src_addr.sin_addr) != 1) {
            fprintf(stderr, "invalid bind IP: %s\n", bind_ip);
            close(fd);
            return 1;
        }
        if (bind(fd, (struct sockaddr *)&src_addr, sizeof(src_addr)) != 0) {
            perror("bind");
            close(fd);
            return 1;
        }
    }

    struct sockaddr_in dst_addr;
    memset(&dst_addr, 0, sizeof(dst_addr));
    dst_addr.sin_family = AF_INET;
    dst_addr.sin_port = htons((uint16_t)dst_port);
    if (inet_pton(AF_INET, dst_ip, &dst_addr.sin_addr) != 1) {
        fprintf(stderr, "invalid destination IP: %s\n", dst_ip);
        close(fd);
        return 1;
    }

    uint8_t *buf = calloc(1, payload_len);
    if (!buf) {
        perror("calloc");
        close(fd);
        return 1;
    }

    FILE *csv = NULL;
    if (csv_path) {
        csv = fopen(csv_path, "w");
        if (!csv) {
            perror("fopen(csv)");
            free(buf);
            close(fd);
            return 1;
        }

        if (mode == MODE_PACKET) {
            fprintf(csv, "req_id,send_local_ns,dst_ip,dst_port,payload_len\n");
        } else {
            fprintf(csv,
                    "flow_id,flow_size_bytes,pkt_cnt,send_start_ns,send_end_ns,payload_len,app_bytes_per_pkt\n");
        }
    }

    if (mode == MODE_PACKET) {
        for (uint64_t k = 0; k < count; k++) {
            uint64_t req_id = start_req_id + k;
            uint64_t send_ns = now_monotonic_ns();

            memset(buf, 0, payload_len);
            struct hopvar_hdr_v1 *hh = (struct hopvar_hdr_v1 *)buf;
            hopvar_hdr_v1_init(hh, req_id);

            ssize_t n = sendto(fd, buf, payload_len, 0,
                               (struct sockaddr *)&dst_addr, sizeof(dst_addr));
            if (n < 0) {
                fprintf(stderr, "sendto failed for req_id=%" PRIu64 ": %s\n",
                        req_id, strerror(errno));
            } else {
                printf("sent req_id=%" PRIu64 " t_local_ns=%" PRIu64
                       " payload_len=%zu ts_count=%u\n",
                       req_id, send_ns, payload_len,
                       (unsigned)hopvar_get_ts_count(hh));

                if (csv) {
                    fprintf(csv, "%" PRIu64 ",%" PRIu64 ",%s,%d,%zu\n",
                            req_id, send_ns, dst_ip, dst_port, payload_len);
                }
            }

            if (k + 1 < count && interval_us > 0) {
                usleep((unsigned int)interval_us);
            }
        }
    } else {
        if (flow_size_bytes == 0) {
            fprintf(stderr, "--flow-size must be specified in flow mode\n");
            if (csv) fclose(csv);
            free(buf);
            close(fd);
            return 1;
        }

        uint32_t app_bytes_per_pkt = (uint32_t)(payload_len - header_bytes);

        for (uint64_t f = 0; f < num_flows; f++) {
            uint64_t flow_id = start_flow_id + f;
            uint32_t pkt_cnt = (flow_size_bytes + app_bytes_per_pkt - 1) / app_bytes_per_pkt;

            uint64_t send_start_ns = 0;
            uint64_t send_end_ns = 0;

            for (uint32_t pkt_idx = 0; pkt_idx < pkt_cnt; pkt_idx++) {
                uint32_t offset = pkt_idx * app_bytes_per_pkt;
                uint32_t rem = flow_size_bytes - offset;
                uint32_t payload_bytes = rem < app_bytes_per_pkt ? rem : app_bytes_per_pkt;

                memset(buf, 0, payload_len);

                struct hopvar_hdr_v1 *hh = (struct hopvar_hdr_v1 *)buf;
                struct flow_hdr_v1 *fh =
                    (struct flow_hdr_v1 *)(buf + sizeof(struct hopvar_hdr_v1));

                hopvar_hdr_v1_init(hh, flow_id);
                flow_hdr_v1_init(fh, flow_id, pkt_idx, pkt_cnt, flow_size_bytes, payload_bytes);

                uint64_t now_ns = now_monotonic_ns();
                if (pkt_idx == 0) {
                    send_start_ns = now_ns;
                }

                ssize_t n = sendto(fd,
                                   buf,
                                   sizeof(struct hopvar_hdr_v1) + sizeof(struct flow_hdr_v1) + payload_bytes,
                                   0,
                                   (struct sockaddr *)&dst_addr,
                                   sizeof(dst_addr));
                if (n < 0) {
                    fprintf(stderr,
                            "sendto failed for flow_id=%" PRIu64 " pkt_idx=%u: %s\n",
                            flow_id, pkt_idx, strerror(errno));
                    continue;
                }

                send_end_ns = now_monotonic_ns();
            }

            printf("sent flow_id=%" PRIu64 " flow_size=%u pkt_cnt=%u payload_len=%zu\n",
                   flow_id, flow_size_bytes, pkt_cnt, payload_len);

            if (csv) {
                fprintf(csv, "%" PRIu64 ",%u,%u,%" PRIu64 ",%" PRIu64 ",%zu,%u\n",
                        flow_id, flow_size_bytes, pkt_cnt,
                        send_start_ns, send_end_ns, payload_len, app_bytes_per_pkt);
            }

            if (inter_flow_gap_us > 0 && f + 1 < num_flows) {
                usleep((unsigned int)inter_flow_gap_us);
            }
        }
    }

    if (csv) fclose(csv);
    free(buf);
    close(fd);
    return 0;
}
