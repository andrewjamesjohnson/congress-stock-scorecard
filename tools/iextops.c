/* iextops: one day of IEX's free historical TOPS feed (HIST, pcapng, gunzipped on stdin) down to what the
   scorecard needs: each symbol's last regular-session trade, and five-minute marks for a few funds (SPY).

       curl -s <TOPS 1.6 link> | gzip -dc | tools/iextops SPY > day.json

   Regular session = between IEX's own "start of regular market hours" (R) and "end" (M) system events, no
   extended-hours trades. "last" is the last round-lot trade (odd lots don't set the last sale), "last_any"
   counts odd lots too. It stops reading at M, so curl and gzip stop too. "complete": false = the stream
   ended before M (a broken download): never cache that.

   Spec: IEX TOPS v1.6 (Trade Report 0x54, System Event 0x53), IEX-TP v1 (protocol 0x8003).
   Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical
   Data Terms of Use (https://www.iex.io/legal/hist-data-terms).
*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CAP (1 << 16)
#define MARKS 79                     /* 9:30 to 16:00 in five-minute steps, and the 16:00 close */
#define WATCH 8

typedef struct {
    uint64_t sym;
    int used;
    int64_t last, last_ts, any, any_ts, open, hi, lo;
    uint64_t vol;
    uint32_t n;
} Row;

static Row tab[CAP];
static uint64_t watch[WATCH];
static int64_t marks[WATCH][MARKS];
static int nwatch = 0;
static int64_t t_open = 0, t_close = 0;

static uint64_t sym8(const char *s) {
    char b[8];
    memset(b, ' ', 8);
    memcpy(b, s, strlen(s) < 8 ? strlen(s) : 8);
    uint64_t v;
    memcpy(&v, b, 8);
    return v;
}

static Row *row(uint64_t s) {
    uint64_t h = (s * 0x9E3779B97F4A7C15ull) >> 48;
    size_t i = (size_t)h & (CAP - 1);
    while (tab[i].used && tab[i].sym != s) i = (i + 1) & (CAP - 1);
    if (!tab[i].used) {
        tab[i].used = 1;
        tab[i].sym = s;
        tab[i].lo = INT64_MAX;
        tab[i].hi = INT64_MIN;
    }
    return &tab[i];
}

static uint16_t le16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static int64_t le64(const uint8_t *p) { uint64_t v; memcpy(&v, p, 8); return (int64_t)v; }
static uint16_t be16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }

static int done = 0;

static void message(const uint8_t *m, uint16_t len) {
    if (len < 10) return;
    if (m[0] == 0x53) {                                   /* System Event */
        if (m[1] == 'R') t_open = le64(m + 2);
        if (m[1] == 'M') { t_close = le64(m + 2); done = 1; }
        return;
    }
    if (m[0] != 0x54 || len < 30 || !t_open) return;      /* Trade Report, regular hours only */
    uint8_t flags = m[1];
    if (flags & 0x40) return;                             /* extended hours */
    int64_t ts = le64(m + 2);
    uint64_t s;
    memcpy(&s, m + 10, 8);
    uint32_t size = le32(m + 18);
    int64_t px = le64(m + 22);
    if (px <= 0) return;
    Row *r = row(s);
    r->n++;
    r->vol += size;
    if (!r->open) r->open = px;
    if (px > r->hi) r->hi = px;
    if (px < r->lo) r->lo = px;
    r->any = px;
    r->any_ts = ts;
    if (!(flags & 0x20)) { r->last = px; r->last_ts = ts; }   /* round lots set the last sale */
    for (int w = 0; w < nwatch; w++) {
        if (watch[w] != s) continue;
        int64_t k = (ts - t_open) / 300000000000LL + 1;     /* mark k = the price at 9:30 + 5k minutes */
        if (k < 1) k = 1;
        if (k >= MARKS) k = MARKS - 1;
        if (!(flags & 0x20)) marks[w][k] = px;
    }
}

static void packet(const uint8_t *p, uint32_t cap) {
    if (cap < 14) return;
    uint32_t ip = 14;
    uint16_t et = be16(p + 12);
    if (et == 0x8100 && cap >= 18) { et = be16(p + 16); ip = 18; }
    if (et != 0x0800 || cap < ip + 20) return;
    uint32_t ihl = (p[ip] & 0x0F) * 4;
    if (p[ip + 9] != 17 || cap < ip + ihl + 8) return;  /* UDP */
    uint32_t udp = ip + ihl, at = udp + 8;
    uint32_t ulen = be16(p + udp + 4);
    uint32_t end = udp + ulen;
    if (end > cap) end = cap;
    if (end < at + 40) return;
    const uint8_t *tp = p + at;
    if (le16(tp + 2) != 0x8003) return;                 /* TOPS */
    uint16_t count = le16(tp + 14);
    uint32_t q = at + 40;
    for (uint16_t i = 0; i < count && q + 2 <= end; i++) {
        uint16_t ml = le16(p + q);
        q += 2;
        if (q + ml > end) break;
        message(p + q, ml);
        q += ml;
        if (done) return;
    }
}

static void put_px(int64_t v) {
    if (v == INT64_MAX || v == INT64_MIN || v == 0) { fputs("null", stdout); return; }
    printf("%lld.%04lld", (long long)(v / 10000), (long long)(v % 10000));
}

static void put_sym(uint64_t s) {
    char b[9];
    memcpy(b, &s, 8);
    b[8] = 0;
    for (int i = 7; i >= 0 && b[i] == ' '; i--) b[i] = 0;
    putchar('"');
    for (char *c = b; *c; c++) if (*c != '"' && *c != '\\') putchar(*c);
    putchar('"');
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc && nwatch < WATCH; i++) watch[nwatch++] = sym8(argv[i]);
    static uint8_t buf[1 << 20];
    setvbuf(stdin, NULL, _IOFBF, 1 << 22);
    uint8_t head[8];
    long long blocks = 0;
    while (!done && fread(head, 1, 8, stdin) == 8) {
        uint32_t type = le32(head), blen = le32(head + 4);
        if (blen < 12 || blen - 8 > sizeof buf) { fprintf(stderr, "iextops: bad block %u\n", blen); break; }
        if (fread(buf, 1, blen - 8, stdin) != blen - 8) break;
        blocks++;
        if (type == 6 && blen >= 32) packet(buf + 20, le32(buf + 12) < blen - 32 ? le32(buf + 12) : blen - 32);
    }
    printf("{\"complete\": %s, \"open_ns\": %lld, \"close_ns\": %lld, \"blocks\": %lld,\n \"fields\": [\"last\", \"last_ns\", \"last_any\", \"open\", \"high\", \"low\", \"volume\", \"trades\"],\n \"symbols\": {",
           done ? "true" : "false", (long long)t_open, (long long)t_close, blocks);
    int first = 1;
    for (size_t i = 0; i < CAP; i++) {
        Row *r = &tab[i];
        if (!r->used || !r->n) continue;
        printf(first ? "\n  " : ",\n  ");
        first = 0;
        put_sym(r->sym);
        fputs(": [", stdout); put_px(r->last ? r->last : r->any);
        printf(", %lld, ", (long long)(r->last ? r->last_ts : r->any_ts)); put_px(r->any);
        fputs(", ", stdout); put_px(r->open);
        fputs(", ", stdout); put_px(r->hi);
        fputs(", ", stdout); put_px(r->lo);
        printf(", %llu, %u]", (unsigned long long)r->vol, r->n);
    }
    fputs("},\n \"marks\": {", stdout);
    for (int w = 0; w < nwatch; w++) {
        printf(w ? ",\n  " : "\n  ");
        put_sym(watch[w]);
        fputs(": [", stdout);
        int k1 = 0;
        for (int k = 1; k < MARKS; k++) {
            if (!marks[w][k]) continue;
            printf(k1 ? ", [%d, " : "[%d, ", k * 5);
            put_px(marks[w][k]);
            putchar(']');
            k1 = 1;
        }
        putchar(']');
    }
    puts("}}");
    return done ? 0 : 3;
}
