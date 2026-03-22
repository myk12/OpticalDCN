
#ifndef CONFIG_H
#define CONFIG_H

#include <stdbool.h>
#include <stddef.h>

struct cfg_entry {
    char *section;
    char *key;
    char *value;
};

struct cfg {
    struct cfg_entry *entries;
    size_t count;
};

bool cfg_load(const char *path, struct cfg *cfg);
void cfg_free(struct cfg *cfg);

const char *cfg_get_string(const struct cfg *cfg,
                           const char *section,
                           const char *key,
                           const char *default_value);

int cfg_get_int(const struct cfg *cfg,
                const char *section,
                const char *key,
                int default_value);

unsigned long long cfg_get_ull(const struct cfg *cfg,
                               const char *section,
                               const char *key,
                               unsigned long long default_value);

#endif  /* CONFIG_H */
