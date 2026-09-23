/* Telemetry packet encoder (plain C module, linked into the C++
 * flight controller) — mirrors what real flight stacks send over
 * their telemetry radio. */
#include "telemetry.h"

#include <stdio.h>
#include <string.h>

int px_build_telemetry(const double *values, int count, char *out, int out_size) {
    char body[96];
    int n = snprintf(body, sizeof(body), "PXCTL");
    if (n < 0) return -1;

    for (int i = 0; i < count; i++) {
        if (n >= (int)sizeof(body) - 16) break;
        int written = snprintf(body + n, sizeof(body) - (size_t)n, ",%.2f", values[i]);
        if (written < 0) return -1;
        n += written;
    }

    unsigned char cs = 0;
    for (size_t i = 0; i < strlen(body); i++) {
        cs ^= (unsigned char)body[i];
    }

    int total = snprintf(out, out_size, "$%s*%02X", body, cs);
    return (total > 0 && total < out_size) ? 0 : -1;
}
