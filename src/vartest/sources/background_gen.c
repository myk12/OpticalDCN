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

#define MAX_PAYLOAD_SIZE 9000

static volatile sig_atomic_t g_stop = 0;

struct thread_arg {
    int thread_id;
    int cpu_id;
    const char *src_ip;
    const char *dst_ip;
    uint16_t dst_port;
    size_t payload_size;
    int duration_sec;
    uint64_t packets_sent;
    uint64_t bytes_sent;
    uint64_t send_errors;
};

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

static void fill_payload(uint8_t *buf, size_t len, int thread_id)
{
    size_t i;
    for (i = 0; i < len; i++)
        buf[i] = (uint8_t)((thread_id + i) & 0xff);
}

static void *sender_thread(void *arg)
{
    struct thread_arg *t = (struct thread_arg *)arg;
    int fd = -1;
    uint8_t *buf = NULL;
    struct sockaddr_in src_addr, dst_addr;
    struct timespec start_ts, now_ts;

    if (pin_thread_to_cpu(t->cpu_id) != 0)
        perror("pthread_setaffinity_np");

    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        t->send_errors++;
        return NULL;
    }

    {
        int sndbuf = 4 * 1024 * 1024;
        setsockopt(fd, SOL_SOCKET, SO_SNDBUF, &sndbuf, sizeof(sndbuf));
    }

    memset(&src_addr, 0, sizeof(src_addr));
    src_addr.sin_family = AF_INET;
    src_addr.sin_port = htons(0);

    if (inet_pton(AF_INET, t->src_ip, &src_addr.sin_addr) != 1) {
        fprintf(stderr, "thread %d: invalid src ip: %s\n", t->thread_id, t->src_ip);
        t->send_errors++;
        close(fd);
        return NULL;
    }

    if (bind(fd, (struct sockaddr *)&src_addr, sizeof(src_addr)) < 0) {
        perror("bind(src)");
        t->send_errors++;
        close(fd);
        return NULL;
    }

    memset(&dst_addr, 0, sizeof(dst_addr));
    dst_addr.sin_family = AF_INET;
    dst_addr.sin_port = htons(t->dst_port);

    if (inet_pton(AF_INET, t->dst_ip, &dst_addr.sin_addr) != 1) {
        fprintf(stderr, "thread %d: invalid dst ip: %s\n", t->thread_id, t->dst_ip);
        t->send_errors++;
        close(fd);
        return NULL;
    }

    buf = (uint8_t *)malloc(t->payload_size);
    if (!buf) {
        perror("malloc");
        t->send_errors++;
        close(fd);
        return NULL;
    }

    fill_payload(buf, t->payload_size, t->thread_id);
    clock_gettime(CLOCK_MONOTONIC, &start_ts);

    while (!g_stop) {
        ssize_t n = sendto(fd, buf, t->payload_size, 0,
                           (struct sockaddr *)&dst_addr, sizeof(dst_addr));
        if (n < 0) {
            if (errno == EINTR)
                continue;
            t->send_errors++;
        } else {
            t->packets_sent++;
            t->bytes_sent += (uint64_t)n;
        }

        clock_gettime(CLOCK_MONOTONIC, &now_ts);
        if ((now_ts.tv_sec - start_ts.tv_sec) >= t->duration_sec)
            break;
    }

    free(buf);
    close(fd);
    return NULL;
}

int main(int argc, char **argv)
{
    const char *cfg_path = (argc >= 2) ? argv[1] : "meas.cfg";
    struct cfg cfg;
    pthread_t *tids = NULL;
    struct thread_arg *args = NULL;
    const char *src_ip;
    const char *dst_ip;
    int threads;
    int payload_size;
    int duration_sec;
    int cpu_base;
    int dst_port;
    uint64_t total_pkts = 0, total_bytes = 0, total_errs = 0;
    int i;

    if (!cfg_load(cfg_path, &cfg)) {
        fprintf(stderr, "failed to load cfg: %s\n", cfg_path);
        return 1;
    }

    src_ip = cfg_get_string(&cfg, "background", "src_ip", NULL);
    dst_ip = cfg_get_string(&cfg, "background", "dst_ip", NULL);
    dst_port = cfg_get_int(&cfg, "background", "dst_port", 9001);
    payload_size = cfg_get_int(&cfg, "background", "payload_size", 1400);
    threads = cfg_get_int(&cfg, "background", "threads", 1);
    duration_sec = cfg_get_int(&cfg, "background", "duration_sec", 10);
    cpu_base = cfg_get_int(&cfg, "background", "cpu_base", -1);

    if (!src_ip || !dst_ip) {
        fprintf(stderr, "background.src_ip and background.dst_ip must be set\n");
        cfg_free(&cfg);
        return 1;
    }

    if (payload_size <= 0 || payload_size > MAX_PAYLOAD_SIZE || threads <= 0) {
        fprintf(stderr, "invalid background config\n");
        cfg_free(&cfg);
        return 1;
    }

    signal(SIGINT, handle_sigint);
    signal(SIGTERM, handle_sigint);

    tids = (pthread_t *)calloc((size_t)threads, sizeof(*tids));
    args = (struct thread_arg *)calloc((size_t)threads, sizeof(*args));
    if (!tids || !args) {
        perror("calloc");
        free(tids);
        free(args);
        cfg_free(&cfg);
        return 1;
    }

    for (i = 0; i < threads; i++) {
        args[i].thread_id = i;
        args[i].cpu_id = (cpu_base >= 0) ? (cpu_base + i) : -1;
        args[i].src_ip = src_ip;
        args[i].dst_ip = dst_ip;
        args[i].dst_port = (uint16_t)dst_port;
        args[i].payload_size = (size_t)payload_size;
        args[i].duration_sec = duration_sec;

        if (pthread_create(&tids[i], NULL, sender_thread, &args[i]) != 0) {
            perror("pthread_create");
            g_stop = 1;
            threads = i;
            break;
        }
    }

    for (i = 0; i < threads; i++)
        pthread_join(tids[i], NULL);

    for (i = 0; i < threads; i++) {
        total_pkts += args[i].packets_sent;
        total_bytes += args[i].bytes_sent;
        total_errs += args[i].send_errors;
    }

    printf("background_gen summary:\n");
    printf("  threads      = %d\n", threads);
    printf("  src_ip       = %s\n", src_ip);
    printf("  dst_ip       = %s\n", dst_ip);
    printf("  dst_port     = %d\n", dst_port);
    printf("  payload_size = %d\n", payload_size);
    printf("  duration_sec = %d\n", duration_sec);
    printf("  total_pkts   = %llu\n", (unsigned long long)total_pkts);
    printf("  total_bytes  = %llu\n", (unsigned long long)total_bytes);
    printf("  total_errs   = %llu\n", (unsigned long long)total_errs);
    if (duration_sec > 0) {
        printf("  approx_gbps  = %.3f\n",
               ((double)total_bytes * 8.0) / ((double)duration_sec * 1e9));
        printf("  approx_mpps  = %.3f\n",
               ((double)total_pkts) / ((double)duration_sec * 1e6));
    }

    free(tids);
    free(args);
    cfg_free(&cfg);
    return 0;
}
