// tx_ts_seq.c - send UDP packet(s) with a seq number;
// print TX HW timestamp
#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>

#include <time.h>  // clock_gettime, struct timespec
#include <fcntl.h> // open()

#include <arpa/inet.h>  // inet_pthon
#include <netinet/in.h> // sockaddr_in, IPPROTO_*
#include <net/if.h>     // struct ifreq
#include <sys/ioctl.h>  // ioctl
#include <sys/socket.h> // socket, sendmsg, recvmsg, CMSG_*

#include <linux/sockios.h>    // SIOCSHWTSTAMP
#include <linux/net_tstamp.h> // struct hwtstamp_config, SOF_TIMESTAMPING_*
#include <linux/errqueue.h>   // struct sock_extended_err, SO_EE_ORIGIN_TIMESTAMPING

#define LOG_FILE_NAME ("ts_probe_tx.csv")

#define PHC_NAME ("/dev/ptp6")
#define CLOCKFD (3)
#define FD_TO_CLOCKID(fd) ((clockid_t) ((((unsigned int)~(fd)) << 3) | CLOCKFD))

static int hwtstamp_enable_tx(int fd, const char *ifname)
{
    printf("- %s\n", __FUNCTION__);
    struct ifreq ifr = {0};
    struct hwtstamp_config cfg = {0};
    strncpy(ifr.ifr_name, ifname, sizeof(ifr.ifr_name) - 1);
    cfg.flags = 0;
    cfg.tx_type = HWTSTAMP_TX_ON;
    cfg.rx_filter = HWTSTAMP_FILTER_NONE;
    ifr.ifr_data = (void *)&cfg;
    if (ioctl(fd, SIOCSHWTSTAMP, &ifr) < 0)
    {
        perror("SIOCSHWTSTAMP (TX)");
        return -1;
    }

    return 0;
}

static int enable_timestamping(int fd)
{
    printf("- %s\n", __FUNCTION__);
    int flags = SOF_TIMESTAMPING_TX_HARDWARE |
                SOF_TIMESTAMPING_TX_SOFTWARE |
                SOF_TIMESTAMPING_SOFTWARE |
                SOF_TIMESTAMPING_RAW_HARDWARE |
                SOF_TIMESTAMPING_OPT_TSONLY |
                SOF_TIMESTAMPING_OPT_ID |
                SOF_TIMESTAMPING_TX_ACK;

    if (setsockopt(fd, SOL_SOCKET, SO_TIMESTAMPING, &flags, sizeof(flags)) < 0)
    {
        perror("SO_TIMESTAMPING");
        return -1;
    }

    // open socket receive err function
    int on = 1;
    if (setsockopt(fd, SOL_IP, IP_RECVERR, &on, sizeof(on)) < 0)
    {
        perror("IP_RECEVERR");
        return -2;
    }

    return 0;
}

static long long ns(const struct timespec *t)
{
    return (long long)t->tv_sec*1000000000LL + t->tv_nsec;
}

static void usage(const char *prog)
{
    fprintf(stderr, "usage: %s [-n count] <ifname> <src_ip> <dst_ip> <dst_port>\n", prog);
}

int main(int argc, char **argv)
{
    printf("=*=*=*=*=*=*= start timestamping tx =*=*=*=*=*=*=\n");
    int opt, count = 1;

    //-------------------------------------------------
    //          parse commandline arguments
    //-------------------------------------------------
    while ((opt = getopt(argc, argv, "n:")) != -1)
    {
        if (opt == 'n')
        {
            count = atoi(optarg);
        }
        else
        {
            usage(argv[0]);
            return 1;
        }
    }
    if (argc - optind < 4)
    {
        usage(argv[0]);
        return 1;
    }

    const char *ifname = argv[optind + 0];
    const char *src_ip = argv[optind + 1];
    const char *dst_ip = argv[optind + 2];
    int dst_port = atoi(argv[optind + 3]);

    //--------------------------------------------------
    //       socket creation and initialization
    //--------------------------------------------------
    printf("- creating and initialinzing socket\n");
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0)
    {
        perror("failed to create socket.");
        return -1;
    }

    // bind to the specific interface/device
    //printf("- bind socket to device %s\n", ifname);
    if (setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, ifname, strlen(ifname)) < 0)
    {
        perror("unable to bind on device");
        return -2;
    }

    // bind source addr to socket
    //printf("- bind socket to addr\n");
    struct sockaddr_in saddr = {0};
    saddr.sin_family = AF_INET;
    saddr.sin_port = htons(0);
    inet_pton(AF_INET, src_ip, &saddr.sin_addr);
    if (bind(fd, (struct sockaddr *)&saddr, sizeof(saddr)) < 0)
    {
        perror("failed to bind socket on addr.");
        return -4;
    }

    // destination address
    struct sockaddr_in daddr = {0};
    daddr.sin_family = AF_INET;
    daddr.sin_port = htons(dst_port);
    inet_pton(AF_INET, dst_ip, &daddr.sin_addr);

    // connect to the UDP socket
    if (connect(fd, (struct sockaddr *)&daddr, sizeof(daddr)) < 0)
    {
        perror("failed to connect peer");
        return -5;
    }

    // enable hardware timestamp
    printf("- enabling timestamping\n");
    if (hwtstamp_enable_tx(fd, ifname) != 0)
    {
        perror("failed to enable hardware timestamp.");
        return -3;
    }

    if (enable_timestamping(fd) < 0)
    {
        perror("failed to enable software timestamp.");
        return -3;
    }

    //--------------------------------------------------
    //          PHC
    //--------------------------------------------------
    // open PHC and create a clockid bound to the NIC's PTP clock
    int phc_fd = open(PHC_NAME, O_RDONLY);
    if (phc_fd < 0)
    {
        perror("failed to open PHC");
        return -4;
    }
    clockid_t phc_clkid = FD_TO_CLOCKID(phc_fd);

    // construct payload: [0..3]=seq (BE), [4..]=padding
    uint8_t buf[256] = {0};
    struct iovec iov = {0};
    struct msghdr msg = {0};
    iov.iov_base = buf;
    iov.iov_len = sizeof(buf);
    msg.msg_name = NULL;
    msg.msg_namelen = 0;
    msg.msg_iov = &iov;
    msg.msg_iovlen = 1;

    // user space sent ts
    struct timespec t_user_tx = {0};

    //-------------------------------------------------
    //          LOG FILE
    //-------------------------------------------------
    FILE *log_file = fopen(LOG_FILE_NAME, "w");
    if (!log_file)
    {
        perror("failed to create log file");
        return -5;
    }
    // header
    fprintf(log_file, "pkt_seq,pkt_size,t_user_tx_ns\n");
    fflush(log_file);

    // send packets
    printf("- start sending packets\n");
    for (uint32_t seq = 1; seq <= (uint32_t)count; seq++)
    {
        // write seq in network byte order
        uint32_t be = htonl(seq);
        memcpy(buf, &be, sizeof(be));
    
        // get current time and read "now" in PHC domain
        clock_gettime(phc_clkid, &t_user_tx);

        if (sendmsg(fd, &msg, 0) < 0)
        {
            perror("failed to send msg.");
            return -5;
        }
        //printf("- - packet sent seq:%d,ts:%ld.%ld\n", seq, t_user_tx.tv_sec, t_user_tx.tv_nsec);

        printf("[TX][%u] t_user_tx=%ld.%09ld\n", seq,
                (long)t_user_tx.tv_sec, t_user_tx.tv_nsec);
        fprintf(log_file,"%u,%d,%lld\n", seq,100,ns(&t_user_tx));
        fflush(stdout);
    }
    return 0;
}
