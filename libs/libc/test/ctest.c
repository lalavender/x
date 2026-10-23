#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <limits.h>
#include <strings.h>

static int cmp_int(const void *left, const void *right) {
    int a = *(const int *)left;
    int b = *(const int *)right;
    return (a > b) - (a < b);
}

typedef struct { int key; int value; } pair_t;

static int cmp_pair(const void *left, const void *right) {
    const pair_t *a = (const pair_t *)left;
    const pair_t *b = (const pair_t *)right;
    return (a->key > b->key) - (a->key < b->key);
}

int main(void) {
    int failures = 0;
    char overlap[9] = "abcdefgh";
    memmove(overlap + 1, overlap, 7);
    if (memcmp(overlap, "aabcdefg", 8) != 0) { printf("memmove forward\n"); failures += 1; }
    char back[9] = "abcdefgh";
    memmove(back, back + 1, 7);
    if (memcmp(back, "bcdefghh", 8) != 0) { printf("memmove backward\n"); failures += 1; }
    char fill[4];
    memset(fill, 0x1ff, 4);
    if ((unsigned char)fill[0] != 0xff) { printf("memset\n"); failures += 1; }
    if (memcmp("abc", "abd", 3) >= 0) { printf("memcmp\n"); failures += 1; }
    if (memchr("abc", 'b', 3) == NULL) { printf("memchr\n"); failures += 1; }
    if (strcmp("abc", "abc") != 0 || strcmp("abc", "abd") >= 0) { printf("strcmp\n"); failures += 1; }
    if (strncmp("abcdef", "abcxyz", 3) != 0) { printf("strncmp\n"); failures += 1; }
    char copy[8];
    strcpy(copy, "hi");
    if (strcmp(copy, "hi") != 0) { printf("strcpy\n"); failures += 1; }
    char padded[6];
    strncpy(padded, "ab", 5);
    if (padded[2] != 0 || padded[4] != 0) { printf("strncpy\n"); failures += 1; }
    char joined[8] = "hi";
    strcat(joined, "!");
    if (strcmp(joined, "hi!") != 0) { printf("strcat\n"); failures += 1; }
    char limited[8] = "hi";
    strncat(limited, "world", 2);
    if (strcmp(limited, "hiwo") != 0) { printf("strncat\n"); failures += 1; }
    if (strchr("a/b/c", '/') == NULL || strchr("a/b/c", '/')[2] != '/') { printf("strchr\n"); failures += 1; }
    if (strrchr("a/b/c", '/')[1] != 'c') { printf("strrchr\n"); failures += 1; }
    if (strstr("hello world", "world")[0] != 'w') { printf("strstr\n"); failures += 1; }
    if (strnlen("abcdef", 3) != 3) { printf("strnlen\n"); failures += 1; }
    if (atoi("  -42xyz") != -42) { printf("atoi\n"); failures += 1; }
    /* 饱和值只有本模块的实现会给出，用来确认 C 侧确实调到 yh 实现。 */
    if (atoi("99999999999999999999") != 2147483647) { printf("atoi saturation\n"); failures += 1; }
    char *end = NULL;
    if (strtol("  -0x1fz", &end, 0) != -31 || end == NULL || *end != 'z') { printf("strtol hex\n"); failures += 1; }
    if (strtol("42abc", &end, 10) != 42 || *end != 'a') { printf("strtol dec\n"); failures += 1; }
    if (strtol("1012", &end, 2) != 5 || *end != '2') { printf("strtol base2\n"); failures += 1; }
    if (strtol("0755", &end, 0) != 493) { printf("strtol octal\n"); failures += 1; }
    if (strtol("  +xy", &end, 10) != 0 || end == NULL || *end != ' ') { printf("strtol none\n"); failures += 1; }
    if (strtol("42", &end, 1) != 0 || *end != '4') { printf("strtol base invalid\n"); failures += 1; }
    if (strtol("9223372036854775808", &end, 10) != LONG_MAX) { printf("strtol saturate high\n"); failures += 1; }
    if (strtol("-9223372036854775809", &end, 10) != LONG_MIN) { printf("strtol saturate low\n"); failures += 1; }
    if (atol("  -123") != -123) { printf("atol\n"); failures += 1; }
    if (abs(-5) != 5 || abs(5) != 5) { printf("abs\n"); failures += 1; }
    if (labs(-9) != 9 || llabs(-9) != 9) { printf("labs\n"); failures += 1; }
    if (strspn("abcabc", "abc") != 6 || strspn("abcx", "abc") != 3) { printf("strspn\n"); failures += 1; }
    if (strcspn("abcx", "x") != 3 || strcspn("abc", "xyz") != 3) { printf("strcspn\n"); failures += 1; }
    if (strpbrk("hello", "lo") == NULL || strpbrk("hello", "lo")[0] != 'l') { printf("strpbrk\n"); failures += 1; }
    if (strpbrk("hello", "xyz") != NULL) { printf("strpbrk miss\n"); failures += 1; }
    if (strcasecmp("AbC", "aBc") != 0 || strcasecmp("abc", "ABD") >= 0) { printf("strcasecmp\n"); failures += 1; }
    if (strncasecmp("aBcD", "abX", 2) != 0 || strncasecmp("aBcD", "abX", 3) >= 0) { printf("strncasecmp\n"); failures += 1; }
    if (strtoul("0xffffffffffffffff", &end, 16) != ULONG_MAX) { printf("strtoul hex\n"); failures += 1; }
    if (strtoul("-1", &end, 10) != ULONG_MAX) { printf("strtoul wrap\n"); failures += 1; }
    if (strtoul("18446744073709551616", &end, 10) != ULONG_MAX) { printf("strtoul saturate\n"); failures += 1; }
    if (strtoul("42", &end, 10) != 42) { printf("strtoul plain\n"); failures += 1; }
    if (atoll("  -77") != -77) { printf("atoll\n"); failures += 1; }
    int values[6] = {9, 2, 7, 1, 5, 3};
    qsort(values, 6, sizeof(int), cmp_int);
    if (values[0] != 1 || values[1] != 2 || values[5] != 9) { printf("qsort\n"); failures += 1; }
    int key = 5;
    int *hit = (int *)bsearch(&key, values, 6, sizeof(int), cmp_int);
    if (hit == NULL || *hit != 5) { printf("bsearch hit\n"); failures += 1; }
    int absent = 42;
    if (bsearch(&absent, values, 6, sizeof(int), cmp_int) != NULL) { printf("bsearch miss\n"); failures += 1; }
    pair_t pairs[3] = {{2, 20}, {1, 10}, {3, 30}};
    qsort(pairs, 3, sizeof(pair_t), cmp_pair);
    if (pairs[0].key != 1 || pairs[2].value != 30) { printf("qsort pairs\n"); failures += 1; }
    pair_t wanted = {3, 0};
    pair_t *pair_hit = (pair_t *)bsearch(&wanted, pairs, 3, sizeof(pair_t), cmp_pair);
    if (pair_hit == NULL || pair_hit->value != 30) { printf("bsearch pairs\n"); failures += 1; }
    char bounded[8];
    if (strlcpy(bounded, "hello", sizeof(bounded)) != 5 || bounded[4] != 'o' || bounded[5] != '\0') { printf("strlcpy\n"); failures += 1; }
    if (strlcpy(bounded, "truncate", 4) != 8 || bounded[3] != '\0') { printf("strlcpy cut\n"); failures += 1; }
    char merged[8] = "ab";
    if (strlcat(merged, "cd", sizeof(merged)) != 4 || merged[3] != 'd' || merged[4] != '\0') { printf("strlcat\n"); failures += 1; }
    char tight[4] = "ab";
    if (strlcat(tight, "cd", 3) != 4 || tight[2] != '\0') { printf("strlcat cut\n"); failures += 1; }
    if (failures == 0) { printf("c-abi libc ok\n"); }
    return failures;
}
