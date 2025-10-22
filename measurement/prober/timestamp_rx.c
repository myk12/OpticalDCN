// rx_ts_sqe.c - receive UDP;
// parse seq from payload; print RX HW timestamp

#define _GNU_SOURCE
#include <arpa/inet.h>
#include <getopt.h>
#include <linux/net_tstamp.h>
#include <linux/sockios.h>
#include <net/if.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>

#define PHC_NAME ("/dev/ptp6")
#define CLOCKFD (3)
#define FD_TO_CLOCKID(fd) ((clockid_t)((((unsigned int)~(fd)) << 3) | CLOCKFD))

#define LOG_FILE_NAME ("ts_probe_rx.csv")

static int hwtstamp_enable_rx(int fd, const char *ifname)
{
    struct ifreq ifr = {0};
    struct hwtstamp_config cfg = {0};
    strncpy(ifr.ifr_name, ifname, sizeof(ifr.ifr_name) - 1);
    cfg.flags = 0;
    cfg.tx_type = HWTSTAMP_TX_OFF;
    cfg.rx_filter = HWTSTAMP_FILTER_ALL;
    ifr.ifr_data = (void *)&cfg;
    if (ioctl(fd, SIOCSHWTSTAMP, &ifr) < 0)
    {
        perror("Failed to enable hw tsstamp.");
        return -1;
    }

    return 0;
}

static int enable_timestamping(int fd)
{
    int flags = SOF_TIMESTAMPING_RX_HARDWARE |
                SOF_TIMESTAMPING_SOFTWARE |
                SOF_TIMESTAMPING_RAW_HARDWARE;

    if (setsockopt(fd, SOL_SOCKET, SO_TIMESTAMPING, &flags, sizeof(flags)) < 0)
    {
        perror("Failed to enable interface timestamping");
        return -1;
    }
    return 0;
}

static long long ns(const struct timespec *t)
{
    return (long long)t->tv_sec * 1000000000LL + t->tv_nsec;
}

static void usage(const char *prog)
{
    fprintf(stderr, "usage: %s [-1] <ifname> <bind_ip> <bind_port>\n", prog);
}

int main(int argc, char **argv)
{
    printf("=*=*=*=*=*=*= start timestamping rx =*=*=*=*=*=*=\n");
    int opt, once = 0;
    while ((opt = getopt(argc, argv, "1")) != -1)
    {
        if (opt == '1')
        {
            once = 1;
        }
        else
        {
            usage(argv[0]);
            return -1;
        }
    }

    if (argc - optind < 3)
    {
        usage(argv[0]);
        return -1;
    }

    const char *ifname = argv[optind + 0];
    const char *bind_ip = argv[optind + 1];
    int bind_port = atoi(argv[optind + 2]);

    //---------------------------------------------
    //          Prepare Socket
    //---------------------------------------------
    printf("- creating and initializing socket\n");
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0)
    {
        perror("Failed to create socket");
        return -2;
    }

    // printf("- binding socket to device %s\n", ifname);
    if (setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, ifname, strlen(ifname)) < 0)
    {
        perror("Failed to set socketopt");
        return -3;
    }

    // printf("- enabling timestamp\n");
    if (hwtstamp_enable_rx(fd, ifname) < 0)
    {
        perror("failed to enable hardware timestamping");
        return -4;
    }
    if (enable_timestamping(fd) < 0)
    {
        perror("failed to enable timestamping.");
        return -4;
    }

    struct sockaddr_in baddr = {0};
    baddr.sin_family = AF_INET;
    baddr.sin_port = htons(bind_port);

    inet_pton(AF_INET, bind_ip, &baddr.sin_addr);
    if (bind(fd, (struct sockaddr *)&baddr, sizeof(baddr)) < 0)
    {
        perror("Failed to bind socket");
        return -5;
    }

    //-----------------------------------------------
    //              PHC
    //-----------------------------------------------
    // open PHC and create a clockid bound to the NIC's PTP clock
    int phc_fd = open(PHC_NAME, O_RDONLY);
    if (phc_fd < 0)
    {
        perror("failed to open PHC");
        return -4;
    }
    clockid_t phc_clkid = FD_TO_CLOCKID(phc_fd);

    //------------------------------------------------
    //              LOG FILE
    //------------------------------------------------
    FILE *log_file = fopen(LOG_FILE_NAME, "w");
    if (!log_file)
    {
        perror("failed to open log file");
        return -7;
    }
    // header
    fprintf(log_file, "pkt_seq,pkt_size,t_user_rx_ns,t_hw_rx_ns\n");
    fflush(log_file);

    //------------------------------------------------
    //              Receiving Packet
    //------------------------------------------------
    printf("- start receiving message\n");
    uint8_t buf[2048];
    char cbuf[CMSG_SPACE(sizeof(struct timespec[3]))];
    struct iovec iov = {0};
    struct msghdr msg = {0};
    struct sockaddr_in src = {0};
    struct timespec t_user_rx = {0}, t_hw_rx = {0};
    uint32_t pkt_seq = 0;
    msg.msg_iov = &iov;
    msg.msg_iovlen = 1;

    while (1)
    {
        iov.iov_base = buf;
        iov.iov_len = sizeof(buf);
        msg.msg_name = &src;
        msg.msg_namelen = sizeof(src);
        msg.msg_control = cbuf;
        msg.msg_controllen = sizeof(cbuf);

        ssize_t n = recvmsg(fd, &msg, 0);
        if (n < 0)
        {
            perror("failed to recvmsg");
            return -7;
        }

        // record software receive timestamp
        clock_gettime(phc_clkid, &t_user_rx);

        struct cmsghdr *c;
        for (c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg, c))
        {
            if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_TIMESTAMPING)
            {
                struct timespec *ts = (struct timespec *)CMSG_DATA(c);
                t_hw_rx = ts[2];
            }
        }

        if (n >= 4)
        {
            uint32_t be;
            memcpy(&be, buf, 4);
            pkt_seq = ntohl(be);
        }

        char sip[INET_ADDRSTRLEN] = {0};
        inet_ntop(AF_INET, &src.sin_addr, sip, sizeof(sip));

        printf("[RX][%u] t_user_rx=%ld.%09ld, t_hw_rx=%ld.%09ld\n", pkt_seq,
                t_user_rx.tv_sec, t_user_rx.tv_nsec,
                t_hw_rx.tv_sec, t_hw_rx.tv_nsec);
        fprintf(log_file, "%u,%u,%lld,%lld\n", pkt_seq, 100, ns(&t_user_rx), ns(&t_hw_rx));
        fflush(log_file);
        if (once) break;
    }

    return 0;
}
