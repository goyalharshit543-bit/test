#ifndef TELEMETRY_H
#define TELEMETRY_H

#ifdef __cplusplus
extern "C" {
#endif

/* Build a NMEA-style telemetry packet from flight values:
 *   $PXCTL,v1,v2,...*CS
 * where CS is the two-hex-digit XOR checksum of the chars between
 * '$' and '*'. Returns 0 on success, -1 if the buffer is too small. */
int px_build_telemetry(const double *values, int count, char *out, int out_size);

#ifdef __cplusplus
}
#endif

#endif /* TELEMETRY_H */
