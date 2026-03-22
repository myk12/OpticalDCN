#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include <linux/net_tstamp.h>
#include <linux/errqueue.h>
#include <fcntl.h>

#include "config.h"
#include "meas_hdr_user.h"

#define PHC_NAME ("/dev/ptp7")
#define CLOCKFD (3)
#define FD_TO_CLOCKID(fd) ((clockid_t) ((((unsigned int)~(fd)) << 3) | CLOCKFD))

static volatile sig_atomic_t g_stop = 0;

static void handle_sigint(int signo)
{
    (void)signo;
    g_stop = 1;
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

static uint64_t timespec_to_ns(const struct timespec *ts)
{
    return (uint64_t)ts->tv_sec * 1000000000ull + (uint64_t)ts->tv_nsec;
}

int main(int argc, char **argv)
{
    const char *cfg_path = (argc >= 2) ? argv[1] : "meas.cfg";
    struct cfg cfg;
    int fd = -1;
    struct sockaddr_in addr;
    const char *listen_ip;
    const char *receiver_csv;
    int listen_port;
    int recv_timeout_ms;
    int idle_exit_after_ms;
    uint64_t last_recv_ns = 0;
    FILE *csv = NULL;

    if (!cfg_load(cfg_path, &cfg)) {
        fprintf(stderr, "failed to load cfg: %s\n", cfg_path);
        return 1;
    }

    listen_ip = cfg_get_string(&cfg, "probe", "listen_ip", "0.0.0.0");
    receiver_csv = cfg_get_string(&cfg, "probe", "receiver_csv", "receiver.csv");
    listen_port = cfg_get_int(&cfg, "probe", "listen_port", 9000);
    recv_timeout_ms = cfg_get_int(&cfg, "probe", "recv_timeout_ms", 1000);
    idle_exit_after_ms = cfg_get_int(&cfg, "probe", "idle_exit_after_ms", 3000);

    signal(SIGINT, handle_sigint);
    signal(SIGTERM, handle_sigint);

    printf("======== start measurement receiver =======\n");
    printf("cfg: listen_ip=%s listen_port=%d recv_timeout_ms=%d idle_exit_after_ms=%d receiver_csv=%s\n",
           listen_ip, listen_port, recv_timeout_ms, idle_exit_after_ms, receiver_csv);

    // open CSV file for writing
    csv = fopen(receiver_csv, "w");
    if (!csv) {
        perror("fopen(receiver_csv)");
        goto error;
    }

    fprintf(csv, "req_id,t1_ns,t2_ns,t3_ns,t4_ns,t5_ns,t6_ns,t7_ns,t8_ns,valid_bitmap,flags,error_bitmap,payload_len,rx_hw_ns,phc_user_rx_ns\n");

    // create socket
    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        goto error;
    }

    // set recv timeout
    {
        struct timeval tv;
        tv.tv_sec = recv_timeout_ms / 1000;
        tv.tv_usec = (recv_timeout_ms % 1000) * 1000;
        if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) < 0) {
            perror("setsockopt(SO_RCVTIMEO)");
            goto error;
        }
    }

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)listen_port);

    // enable HW timestamping
    int tsmode = SOF_TIMESTAMPING_RX_HARDWARE | 
                SOF_TIMESTAMPING_RAW_HARDWARE |
                SOF_TIMESTAMPING_SOFTWARE |
                SOF_TIMESTAMPING_RX_SOFTWARE;
    
    if (setsockopt(fd, SOL_SOCKET, SO_TIMESTAMPING, &tsmode, sizeof(tsmode)) < 0) {
        perror("setsockopt(SO_TIMESTAMPING)");
        goto error;
    }

    // parse listen IP
    if (inet_pton(AF_INET, listen_ip, &addr.sin_addr) != 1) {
        fprintf(stderr, "invalid listen ip: %s\n", listen_ip);
        goto error;
    }

    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        goto error;
    }

    last_recv_ns = realtime_ns();

    printf("listening on %s:%d\n", listen_ip, listen_port);

    char buf[2048];
    char control[512];
    struct iovec iov = {
        .iov_base = buf,
        .iov_len = sizeof(buf),
    };
    struct msghdr msg;
    memset(&msg, 0, sizeof(msg));
    msg.msg_name = NULL;
    msg.msg_namelen = 0;
    msg.msg_iov = &iov;
    msg.msg_iovlen = 1;
    msg.msg_control = control;
    msg.msg_controllen = sizeof(control);

    struct timespec phc_user_rx = {0};
    int phc_fd = open(PHC_NAME, O_RDONLY);
    if (phc_fd < 0) {
        perror("clock_gettime(PHC)");
        goto error;
    }
    clockid_t phc_clkid = FD_TO_CLOCKID(phc_fd);

    while (!g_stop) {
        ssize_t n = recvmsg(fd, &msg, 0);

        if (n < 0) {
            if (errno == EINTR)
                continue;

            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                uint64_t now_ns = realtime_ns();

                // check idle time and exit if exceeded
                uint64_t idle_ns = now_ns - last_recv_ns;
                if (idle_ns >= (uint64_t)idle_exit_after_ms * 1000000ull) {
                    printf("receiver idle for %d ms, exiting\n", idle_exit_after_ms);
                    break;
                }

                continue;
            }

            perror("recv");
            break;
        }

        last_recv_ns = realtime_ns();

        if ((size_t)n < sizeof(struct meas_hdr_v1)) {
            printf("short payload: %zd\n", n);
            continue;
        }

        uint64_t rx_hw_ns = 0;
        for (struct cmsghdr *cmsg = CMSG_FIRSTHDR(&msg); 
                cmsg != NULL;
                cmsg = CMSG_NXTHDR(&msg, cmsg)
            )
        {
            if (cmsg->cmsg_level == SOL_SOCKET && 
                cmsg->cmsg_type == SO_TIMESTAMPING) {
                struct scm_timestamping *ts = (struct scm_timestamping *)CMSG_DATA(cmsg);
                // ts->ts[0] is software timestamp, ts->ts[2] is hardware timestamp (if available)
                // we can choose to use either, here we just print them for demonstration
                rx_hw_ns = timespec_to_ns(&ts->ts[2]);
            }
        }

        // parse measurement header and log to CSV
        {
            const struct meas_hdr_v1 *mh = (const struct meas_hdr_v1 *)buf;
            uint32_t vb;
            uint64_t t8_ns = 0;

            if (!meas_hdr_v1_basic_ok_user(mh)) {
                printf("bad measurement header\n");
                continue;
            }

            // Get PHC timestamp immediately after receiving
            if (clock_gettime(phc_clkid, &phc_user_rx) != 0) {
                perror("clock_gettime(PHC)");
                goto error;
            }

            vb = meas_get_valid_bitmap(mh);
            t8_ns = realtime_ns();

            // for demonstration, print every 10000th req_id with details
            uint64_t req_id = meas_get_req_id(mh);
            if (req_id % 100000 == 0) {
                printf("req_id=%llu valid=0x%08x flags=0x%04x err=0x%08x clk=%u\n",
                    (unsigned long long)meas_get_req_id(mh),
                    vb,
                    meas_get_flags(mh),
                    meas_get_error_bitmap(mh),
                    meas_get_clock_domain(mh));

                if (vb & MEAS_V_T1)
                    printf("  T1=%llu\n", (unsigned long long)meas_get_t1(mh));
                if (vb & MEAS_V_T2)
                    printf("  T2=%llu\n", (unsigned long long)meas_get_t2(mh));
                if (vb & MEAS_V_T3)
                    printf("  T3=%llu\n", (unsigned long long)meas_get_t3(mh));
                if (vb & MEAS_V_T4)
                    printf("  T4=%llu\n", (unsigned long long)meas_get_t4(mh));
                if (vb & MEAS_V_T5)
                    printf("  T5=%llu\n", (unsigned long long)meas_get_t5(mh));
                if (vb & MEAS_V_T6)
                    printf("  T6=%llu\n", (unsigned long long)meas_get_t6(mh));
                if (vb & MEAS_V_T7)
                    printf("  T7=%llu\n", (unsigned long long)meas_get_t7(mh));
                if (vb & MEAS_V_T8)
                    printf("  T8=%llu\n", (unsigned long long)meas_get_t8(mh));
            }
            
            fprintf(csv,
                    "%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%u,%u,%u,%zd,%llu,%llu\n",
                    (unsigned long long)meas_get_req_id(mh),
                    (unsigned long long)meas_get_t1(mh),
                    (unsigned long long)meas_get_t2(mh),
                    (unsigned long long)meas_get_t3(mh),
                    (unsigned long long)meas_get_t4(mh),
                    (unsigned long long)meas_get_t5(mh),
                    (unsigned long long)meas_get_t6(mh),
                    (unsigned long long)meas_get_t7(mh),
                    (unsigned long long)t8_ns,
                    meas_get_valid_bitmap(mh),
                    meas_get_flags(mh),
                    meas_get_error_bitmap(mh),
                    n,
                    (unsigned long long)rx_hw_ns,
                    (unsigned long long)timespec_to_ns(&phc_user_rx)
                    );
            // fflush(csv); -- optional, can be left to OS buffering
        }
    }

    close(fd);
    fclose(csv);
    cfg_free(&cfg);
    return 0;

error:
    if (fd >= 0) close(fd);
    if (csv) fclose(csv);
    cfg_free(&cfg);
    return 1;
}
