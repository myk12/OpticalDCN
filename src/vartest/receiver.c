/* receiver.c
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>

#include "meas_hdr_user.h"

int main(int argc, char **argv)
{
    int fd;
    struct sockaddr_in addr;
    uint8_t buf[2048];

    if (argc != 2) {
        fprintf(stderr, "usage: %s <listen_port>\n", argv[0]);
        return 1;
    }

    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        return 1;
    }

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)atoi(argv[1]));
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(fd);
        return 1;
    }

    for (;;) {
        ssize_t n = recv(fd, buf, sizeof(buf), 0);
        if (n < 0) {
            perror("recv");
            break;
        }

        if ((size_t)n < sizeof(struct meas_hdr_v1)) {
            printf("short payload: %zd\n", n);
            continue;
        }

        {
            const struct meas_hdr_v1 *mh = (const struct meas_hdr_v1 *)buf;
            uint32_t vb;

            if (!meas_hdr_v1_basic_ok_user(mh)) {
                printf("bad measurement header\n");
                continue;
            }

            vb = meas_get_valid_bitmap(mh);

            printf("req_id=%llu valid=0x%08x flags=0x%04x err=0x%08x\n",
                   (unsigned long long)meas_get_req_id(mh),
                   vb,
                   meas_get_flags(mh),
                   meas_get_error_bitmap(mh));

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
            if (vb & MEAS_V_S1)
                printf("  S1=%llu\n", (unsigned long long)meas_get_s1(mh));
            if (vb & MEAS_V_S2)
                printf("  S2=%llu\n", (unsigned long long)meas_get_s2(mh));
            if (vb & MEAS_V_SRC_DEV_ID)
                printf("  src_dev_id=%u\n", meas_get_src_dev_id(mh));
            if (vb & MEAS_V_SW_ID)
                printf("  sw_id=%u\n", meas_get_sw_id(mh));
            if (vb & MEAS_V_QUEUE_META)
                printf("  queue_meta=0x%08x\n", meas_get_queue_meta(mh));
        }
    }

    close(fd);
    return 0;
}
