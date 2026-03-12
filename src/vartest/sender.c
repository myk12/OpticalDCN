/* sender.c
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>

#include "meas_hdr_user.h"

#define REQ_NUM 100

static uint64_t mono_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

int main(int argc, char **argv)
{
    int fd;
    struct sockaddr_in addr;
    uint8_t buf[sizeof(struct meas_hdr_v1) + 64];
    struct meas_hdr_v1 *mh = (struct meas_hdr_v1 *)buf;
    uint64_t req_id = 1;

    if (argc != 3) {
        fprintf(stderr, "usage: %s <dst_ip> <dst_port>\n", argv[0]);
        return 1;
    }

    meas_hdr_v1_init(mh, req_id, MEAS_CLK_HOST_MONO, mono_ns());
    memcpy(buf + sizeof(*mh), "hello", 5);

    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        return 1;
    }

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)atoi(argv[2]));
    if (inet_pton(AF_INET, argv[1], &addr.sin_addr) != 1) {
        fprintf(stderr, "invalid ip\n");
        close(fd);
        return 1;
    }

    for (int i=0; i<REQ_NUM; i++) {
        mh->req_id = meas_cpu_to_be64(req_id++);
        mh->T1 = meas_cpu_to_be64(mono_ns());

        if (sendto(fd, buf, sizeof(*mh) + 5, 0,
                   (struct sockaddr *)&addr, sizeof(addr)) < 0) {
            perror("sendto");
            close(fd);
            return 1;
        }

        printf("sent req_id=%llu T1=%llu\n",
               (unsigned long long)meas_get_req_id(mh),
               (unsigned long long)meas_get_t1(mh));

        usleep(100000);  // 100ms
    }

    close(fd);
    return 0;
}
