#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include "config.h"

#define RX_BUF_SIZE (64 * 1024)

static volatile sig_atomic_t g_stop = 0;

static void handle_sigint(int signo)
{
    (void)signo;
    g_stop = 1;
}

static int pin_thread_to_cpu(int cpu_id)
{
    cpu_set_t cpuset;

    if (cpu_id < 0)
        return 0;

    CPU_ZERO(&cpuset);
    CPU_SET(cpu_id, &cpuset);

    return pthread_setaffinity_np(pthread_self(), sizeof(cpuset), &cpuset);
}

static double diff_sec(const struct timespec *a, const struct timespec *b)
{
    return (double)(a->tv_sec - b->tv_sec) +
           (double)(a->tv_nsec - b->tv_nsec) / 1e9;
}

int main(int argc, char **argv)
{
    const char *cfg_path = (argc >= 2) ? argv[1] : "meas.cfg";
    struct cfg cfg;
    const char *bind_ip;
    int listen_port;
    int duration_sec;
    int cpu_id;
    int report_interval_sec;
    int fd;
    int rcvbuf = 16 * 1024 * 1024;
    uint8_t *buf = NULL;
    struct sockaddr_in bind_addr;
    struct sockaddr_in peer_addr;
    socklen_t addrlen;
    struct timespec start_ts, now_ts, last_report_ts;
    uint64_t packets = 0, bytes = 0, recv_errors = 0;

    if (!cfg_load(cfg_path, &cfg)) {
        fprintf(stderr, "failed to load cfg: %s\n", cfg_path);
        return 1;
    }

    bind_ip = cfg_get_string(&cfg, "background", "bind_ip", NULL);
    listen_port = cfg_get_int(&cfg, "background", "listen_port", 9001);
    duration_sec = cfg_get_int(&cfg, "background", "duration_sec", 10);
    cpu_id = cfg_get_int(&cfg, "background", "cpu_id", -1);
    report_interval_sec = cfg_get_int(&cfg, "background", "report_interval_sec", 1);

    if (!bind_ip) {
        fprintf(stderr, "background.bind_ip must be set\n");
        cfg_free(&cfg);
        return 1;
    }

    signal(SIGINT, handle_sigint);
    signal(SIGTERM, handle_sigint);

    if (pin_thread_to_cpu(cpu_id) != 0)
        perror("pthread_setaffinity_np");

    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        cfg_free(&cfg);
        return 1;
    }

    setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &rcvbuf, sizeof(rcvbuf));

    memset(&bind_addr, 0, sizeof(bind_addr));
    bind_addr.sin_family = AF_INET;
    bind_addr.sin_port = htons((uint16_t)listen_port);

    if (inet_pton(AF_INET, bind_ip, &bind_addr.sin_addr) != 1) {
        fprintf(stderr, "invalid bind ip: %s\n", bind_ip);
        close(fd);
        cfg_free(&cfg);
        return 1;
    }

    if (bind(fd, (struct sockaddr *)&bind_addr, sizeof(bind_addr)) < 0) {
        perror("bind");
        close(fd);
        cfg_free(&cfg);
        return 1;
    }

    buf = (uint8_t *)malloc(RX_BUF_SIZE);
    if (!buf) {
        perror("malloc");
        close(fd);
        cfg_free(&cfg);
        return 1;
    }

    clock_gettime(CLOCK_MONOTONIC, &start_ts);
    last_report_ts = start_ts;

    printf("background_sink listening on %s:%d duration=%d cpu=%d\n",
           bind_ip, listen_port, duration_sec, cpu_id);

    while (!g_stop) {
        ssize_t n;

        addrlen = sizeof(peer_addr);
        n = recvfrom(fd, buf, RX_BUF_SIZE, 0,
                     (struct sockaddr *)&peer_addr, &addrlen);

        if (n < 0) {
            if (errno == EINTR)
                continue;
            perror("recvfrom");
            recv_errors++;
            continue;
        }

        packets++;
        bytes += (uint64_t)n;

        clock_gettime(CLOCK_MONOTONIC, &now_ts);

        if (report_interval_sec > 0 &&
            diff_sec(&now_ts, &last_report_ts) >= (double)report_interval_sec) {
            double total_elapsed = diff_sec(&now_ts, &start_ts);
            printf("[%.3f s] pkts=%llu bytes=%llu errs=%llu avg_gbps=%.3f avg_mpps=%.3f\n",
                   total_elapsed,
                   (unsigned long long)packets,
                   (unsigned long long)bytes,
                   (unsigned long long)recv_errors,
                   (bytes * 8.0) / (total_elapsed * 1e9),
                   (double)packets / (total_elapsed * 1e6));
            last_report_ts = now_ts;
        }

        if ((now_ts.tv_sec - start_ts.tv_sec) >= duration_sec)
            break;
    }

    {
        double elapsed = diff_sec(&now_ts, &start_ts);
        if (elapsed <= 0.0)
            elapsed = 1e-9;

        printf("background_sink summary:\n");
        printf("  bind_ip      = %s\n", bind_ip);
        printf("  listen_port  = %d\n", listen_port);
        printf("  duration_sec = %d\n", duration_sec);
        printf("  packets      = %llu\n", (unsigned long long)packets);
        printf("  bytes        = %llu\n", (unsigned long long)bytes);
        printf("  recv_errors  = %llu\n", (unsigned long long)recv_errors);
        printf("  approx_gbps  = %.3f\n", (bytes * 8.0) / (elapsed * 1e9));
        printf("  approx_mpps  = %.3f\n", (double)packets / (elapsed * 1e6));
    }

    free(buf);
    close(fd);
    cfg_free(&cfg);
    return 0;
}
