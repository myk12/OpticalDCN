#include <arpa/inet.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/socket.h>
#include <linux/net_tstamp.h>
#include <linux/errqueue.h>
#include <errno.h>
#include <fcntl.h>

#include "config.h"
#include "meas_hdr_user.h"

#define DRAIN_BURST 64
#define FINAL_DRAIN_RETRY 1000
#define FINAL_DRAIN_SLEEP_US 1000

#define PHC_NAME ("/dev/ptp6")
#define CLOCKFD (3)
#define FD_TO_CLOCKID(fd) ((clockid_t) ((((unsigned int)~(fd)) << 3) | CLOCKFD))

struct tx_ts_record {
    uint64_t req_id;
    uint64_t tx_hw_ns;
    int has_tx_hw_ts;
};

static uint64_t timespec_to_ns(const struct timespec *ts)
{
    return (uint64_t)ts->tv_sec * 1000000000ull + (uint64_t)ts->tv_nsec;
}

static uint64_t realtime_ns(void)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_REALTIME, &ts) != 0) {
        perror("clock_gettime");
        exit(1);
    }

    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void sleep_us(int us)
{
    struct timespec ts;
    ts.tv_sec = us / 1000000;
    ts.tv_nsec = (long)(us % 1000000) * 1000L;
    nanosleep(&ts, NULL);
}

/*
 * Nonblocking drain of TX timestamps from MSG_ERRQUEUE.
 *
 * Returns the number of timestamps drained, or -1 on error.
 */
static int drain_tx_timestamps(int fd,
                               struct tx_ts_record *txrecs,
                               int sent_count,
                               int *next_unmatched_idx,
                               FILE *csv_ts)
{
    int drained = 0;

    for (;;)
    {
        char data[256];
        char control[512];
        struct iovec iov = {
            .iov_base = data,
            .iov_len = sizeof(data),
        };
        struct msghdr msg = {
            .msg_name = NULL,
            .msg_namelen = 0,
            .msg_iov = &iov,
            .msg_iovlen = 1,
            .msg_control = control,
            .msg_controllen = sizeof(control),
        };
        ssize_t ret;
        uint64_t tx_hw_ns = 0;
        int found_ts = 0;

        ret = recvmsg(fd, &msg, MSG_ERRQUEUE | MSG_DONTWAIT);
        if (ret < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                break;
            } else {
                perror("recvmsg(MSG_ERRQUEUE)");
                return -1;
            }
        }

        for (struct cmsghdr *cmsg = CMSG_FIRSTHDR(&msg);
             cmsg != NULL;
             cmsg = CMSG_NXTHDR(&msg, cmsg))
        {
            if (cmsg->cmsg_level == SOL_SOCKET &&
                cmsg->cmsg_type == SCM_TIMESTAMPING) {
                struct scm_timestamping *ts = (struct scm_timestamping *)CMSG_DATA(cmsg);

                if (ts->ts[2].tv_sec != 0 || ts->ts[2].tv_nsec != 0) {
                    tx_hw_ns = timespec_to_ns(&ts->ts[2]);
                    found_ts = 1;
                } else if (ts->ts[0].tv_sec != 0 || ts->ts[0].tv_nsec != 0) {
                    tx_hw_ns = timespec_to_ns(&ts->ts[0]);
                    found_ts = 1;
                }
            }
        }

        if (!found_ts) {
            continue;
        }

        if (*next_unmatched_idx < sent_count)
        {
            txrecs[*next_unmatched_idx].tx_hw_ns = tx_hw_ns;
            txrecs[*next_unmatched_idx].has_tx_hw_ts = 1;

            if (csv_ts) {
                fprintf(csv_ts, "%llu,%llu\n",
                        (unsigned long long)txrecs[*next_unmatched_idx].req_id,
                        (unsigned long long)tx_hw_ns);
            }

            (*next_unmatched_idx)++;
            drained++;
        }
    }

    return drained;
}

int main(int argc, char **argv)
{
    const char *cfg_path = (argc >= 2) ? argv[1] : "meas.cfg";
    struct cfg cfg;
    int fd = -1;
    struct sockaddr_in src_addr, dst_addr;
    const char *src_ip;
    const char *dst_ip;
    int payload_size;
    const char *sender_csv;
    const char *sender_tx_ts_csv;
    int dst_port;
    int count;
    int interval_us;
    unsigned long long req_id_start;
    FILE *csv = NULL;
    FILE *csv_ts = NULL;
    struct tx_ts_record *txrecs = NULL;
    int next_unmatched_idx = 0;
    int i;

    if (!cfg_load(cfg_path, &cfg))
    {
        fprintf(stderr, "failed to load cfg: %s\n", cfg_path);
        return 1;
    }

    src_ip = cfg_get_string(&cfg, "probe", "src_ip", NULL);
    dst_ip = cfg_get_string(&cfg, "probe", "dst_ip", NULL);
    payload_size = cfg_get_int(&cfg, "probe", "payload_size", 1024);
    sender_csv = cfg_get_string(&cfg, "probe", "sender_csv", "sender.csv");
    sender_tx_ts_csv = cfg_get_string(&cfg, "probe", "sender_tx_ts_csv", "sender_tx_ts.csv");
    dst_port = cfg_get_int(&cfg, "probe", "dst_port", 9000);
    count = cfg_get_int(&cfg, "probe", "count", 1);
    interval_us = cfg_get_int(&cfg, "probe", "interval_us", 100000);
    req_id_start = cfg_get_ull(&cfg, "probe", "req_id_start", 1);

    if (!src_ip || !dst_ip)
    {
        fprintf(stderr, "probe.src_ip and probe.dst_ip must be set\n");
        cfg_free(&cfg);
        return 1;
    }

    if (count <= 0) {
        fprintf(stderr, "invalid count: %d\n", count);
        cfg_free(&cfg);
        return 1;
    }

    printf("======== start measurement sender =======\n");
    printf("cfg: src_ip=%s \n\
            dst_ip=%s \n\
            dst_port=%d \n\
            payload_size=%d \n\
            count=%d \n\
            interval_us=%d \n\
            req_id_start=%llu \n\
            sender_csv=%s \n\
            sender_tx_ts_csv=%s\n",
           src_ip, dst_ip, dst_port, payload_size, count, interval_us, (unsigned long long)req_id_start, sender_csv, sender_tx_ts_csv);

    txrecs = calloc((size_t)count, sizeof(*txrecs));
    if (!txrecs) {
        perror("calloc(txrecs)");
        goto error;
    }

    csv = fopen(sender_csv, "w");
    if (!csv)
    {
        perror("fopen(sender_csv)");
        goto error;
    }

    csv_ts = fopen(sender_tx_ts_csv, "w");
    if (!csv_ts)
    {
        perror("fopen(sender_tx_ts_csv)");
        goto error;
    }

    fprintf(csv, "req_id,phc_usr_tx,t1_ns,dst_ip,dst_port,payload_len\n");
    fprintf(csv_ts, "req_id,tx_hw_ns\n");

    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0)
    {
        perror("socket");
        goto error;
    }

    {
        int tsmode = SOF_TIMESTAMPING_TX_HARDWARE |
                     SOF_TIMESTAMPING_RAW_HARDWARE |
                     SOF_TIMESTAMPING_SOFTWARE |
                     SOF_TIMESTAMPING_TX_SOFTWARE |
                     SOF_TIMESTAMPING_OPT_ID;

        if (setsockopt(fd, SOL_SOCKET, SO_TIMESTAMPING, &tsmode, sizeof(tsmode)) < 0)
        {
            perror("setsockopt(SO_TIMESTAMPING)");
            goto error;
        }
    }

    memset(&src_addr, 0, sizeof(src_addr));
    src_addr.sin_family = AF_INET;
    src_addr.sin_port = htons(0);

    if (inet_pton(AF_INET, src_ip, &src_addr.sin_addr) != 1)
    {
        fprintf(stderr, "invalid src ip: %s\n", src_ip);
        goto error;
    }

    if (bind(fd, (struct sockaddr *)&src_addr, sizeof(src_addr)) < 0)
    {
        perror("bind(src)");
        goto error;
    }

    memset(&dst_addr, 0, sizeof(dst_addr));
    dst_addr.sin_family = AF_INET;
    dst_addr.sin_port = htons((uint16_t)dst_port);

    if (inet_pton(AF_INET, dst_ip, &dst_addr.sin_addr) != 1)
    {
        fprintf(stderr, "invalid dst ip: %s\n", dst_ip);
        goto error;
    }

    // PHC Clock
    int phc_fd = open(PHC_NAME, O_RDONLY);
    if (phc_fd < 0)    {
        perror("open PHC");
        goto error;
    }

    struct timespec phc_user_tx = {0};

    for (i = 0; i < count; i++)
    {
        char buf[2048];
        struct meas_hdr_v1 *mh = (struct meas_hdr_v1 *)buf;
        uint64_t t1 = realtime_ns();
        uint64_t req_id = req_id_start + (unsigned long long)i;

        if (payload_size > 2048)
        {
            fprintf(stderr, "payload too large\n");
            break;
        }

        memset(buf, 0, payload_size);
        meas_hdr_v1_init(mh, req_id, MEAS_CLK_HOST_MONO, t1);
        memcpy(buf + sizeof(*mh), "X", payload_size - sizeof(*mh)); // dummy payload

        // Get PHC timestamp immediately before sending
        if (clock_gettime(FD_TO_CLOCKID(phc_fd), &phc_user_tx) != 0) {
            perror("clock_gettime(PHC)");
            goto error;
        }

        // Send the packet
        if (sendto(fd, buf, payload_size, 0,
                   (struct sockaddr *)&dst_addr, sizeof(dst_addr)) < 0)
        {
            perror("sendto");
            goto error;
        }

        txrecs[i].req_id = req_id;
        txrecs[i].tx_hw_ns = 0;
        txrecs[i].has_tx_hw_ts = 0;

        // Output CSV with user-space timestamp (T1) for reference, even though the main focus is on hardware timestamps
        fprintf(csv, "%llu,%llu,%llu,%s,%d,%u\n",
                (unsigned long long)req_id,
                (unsigned long long)timespec_to_ns(&phc_user_tx),
                (unsigned long long)t1,
                dst_ip,
                dst_port,
                payload_size);

        if (i % 100000 == 0)
        {
            printf("sent req_id=%llu T1=%llu\n",
                   (unsigned long long)req_id,
                   (unsigned long long)t1);
        }

        if ((i + 1) % DRAIN_BURST == 0) {
            if (drain_tx_timestamps(fd, txrecs, i + 1, &next_unmatched_idx, csv_ts) < 0) {
                goto error;
            }
        }

        if (i != count - 1 && interval_us > 0)
            sleep_us(interval_us);
    }

    for (i = 0; i < FINAL_DRAIN_RETRY; i++) {
        int n = drain_tx_timestamps(fd, txrecs, count, &next_unmatched_idx, csv_ts);
        if (n < 0) {
            goto error;
        }
        if (next_unmatched_idx >= count) {
            break;
        }
        if (n == 0) {
            sleep_us(FINAL_DRAIN_SLEEP_US);
        }
    }

    printf("sent=%d tx_ts_received=%d\n", count, next_unmatched_idx);

    close(fd);
    fclose(csv);
    fclose(csv_ts);
    free(txrecs);
    cfg_free(&cfg);
    return 0;

error:
    if (fd >= 0)
        close(fd);
    if (csv)
        fclose(csv);
    if (csv_ts)
        fclose(csv_ts);
    free(txrecs);
    cfg_free(&cfg);
    return 1;
}
