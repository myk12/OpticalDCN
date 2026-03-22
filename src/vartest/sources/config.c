#include "config.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *xstrdup(const char *s)
{
    size_t n = strlen(s) + 1;
    char *p = (char *)malloc(n);
    if (!p)
        return NULL;
    memcpy(p, s, n);
    return p;
}

static char *trim(char *s)
{
    char *end;

    while (*s && isspace((unsigned char)*s))
        s++;

    if (*s == '\0')
        return s;

    end = s + strlen(s) - 1;
    while (end > s && isspace((unsigned char)*end))
        *end-- = '\0';

    return s;
}

static bool cfg_add(struct cfg *cfg, const char *section, const char *key, const char *value)
{
    struct cfg_entry *new_entries;
    struct cfg_entry *e;

    new_entries = (struct cfg_entry *)realloc(
        cfg->entries, (cfg->count + 1) * sizeof(*cfg->entries));
    if (!new_entries)
        return false;

    cfg->entries = new_entries;
    e = &cfg->entries[cfg->count];

    e->section = xstrdup(section ? section : "");
    e->key = xstrdup(key);
    e->value = xstrdup(value);

    if (!e->section || !e->key || !e->value)
        return false;

    cfg->count++;
    return true;
}

bool cfg_load(const char *path, struct cfg *cfg)
{
    FILE *fp;
    char line[1024];
    char current_section[128] = "";

    cfg->entries = NULL;
    cfg->count = 0;

    fp = fopen(path, "r");
    if (!fp)
        return false;

    while (fgets(line, sizeof(line), fp)) {
        char *s = trim(line);

        if (*s == '\0' || *s == '#' || *s == ';')
            continue;

        if (*s == '[') {
            char *r = strchr(s, ']');
            if (!r)
                continue;
            *r = '\0';
            snprintf(current_section, sizeof(current_section), "%s", trim(s + 1));
            continue;
        }

        {
            char *eq = strchr(s, '=');
            char *key;
            char *value;

            if (!eq)
                continue;

            *eq = '\0';
            key = trim(s);
            value = trim(eq + 1);

            if (!cfg_add(cfg, current_section, key, value)) {
                fclose(fp);
                return false;
            }
        }
    }

    fclose(fp);
    return true;
}

void cfg_free(struct cfg *cfg)
{
    size_t i;

    if (!cfg)
        return;

    for (i = 0; i < cfg->count; i++) {
        free(cfg->entries[i].section);
        free(cfg->entries[i].key);
        free(cfg->entries[i].value);
    }

    free(cfg->entries);
    cfg->entries = NULL;
    cfg->count = 0;
}

const char *cfg_get_string(const struct cfg *cfg,
                           const char *section,
                           const char *key,
                           const char *default_value)
{
    size_t i;

    for (i = 0; i < cfg->count; i++) {
        if (strcmp(cfg->entries[i].section, section) == 0 &&
            strcmp(cfg->entries[i].key, key) == 0) {
            return cfg->entries[i].value;
        }
    }

    return default_value;
}

int cfg_get_int(const struct cfg *cfg,
                const char *section,
                const char *key,
                int default_value)
{
    const char *v = cfg_get_string(cfg, section, key, NULL);
    if (!v)
        return default_value;
    return atoi(v);
}

unsigned long long cfg_get_ull(const struct cfg *cfg,
                               const char *section,
                               const char *key,
                               unsigned long long default_value)
{
    const char *v = cfg_get_string(cfg, section, key, NULL);
    if (!v)
        return default_value;
    return strtoull(v, NULL, 10);
}
