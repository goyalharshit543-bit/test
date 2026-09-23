/* ============================================================
 *  drone_controller.cpp — Smart Drone flight controller (C++)
 *  ============================================================
 *  This is the "on-board firmware" of each simulated drone. The
 *  Python fleet simulator streams one state line per tick over
 *  stdin; this program runs the control maths a real flight
 *  controller would run and streams back one command line:
 *
 *  INPUT  (9 numbers, whitespace separated):
 *      cur_lat cur_lng cur_alt tgt_lat tgt_lng tgt_alt battery max_speed dt
 *  OUTPUT (space separated):
 *      heading speed vspeed alt_cmd [$PXCTL,...*checksum]
 *
 *  C++ parts : PID loops (speed & altitude) + mission logic
 *  C part    : NMEA-style telemetry encoder (telemetry.c)
 * ============================================================ */
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

#include "navigation.h"
#include "pid.h"
#include "telemetry.h"

namespace {

double clampd(double v, double lo, double hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

const double CRUISE_ALT_M = 60.0;   /* matches backend/fleet.py  */

} /* namespace */

int main() {
    std::cout << std::fixed << std::setprecision(4);

    PID speed_pid(0.60, 0.05, 0.12, 6.0);   /* accelerates toward desired speed */
    PID alt_pid(0.45, 0.02, 0.10, 4.0);     /* altitude hold / climb / descend  */

    double last_speed = 0.0;
    std::string line;

    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;

        std::istringstream ss(line);
        double cur_lat, cur_lng, cur_alt, tgt_lat, tgt_lng, tgt_alt;
        double battery, max_speed, dt;
        if (!(ss >> cur_lat >> cur_lng >> cur_alt >> tgt_lat >> tgt_lng >> tgt_alt >>
              battery >> max_speed >> dt)) {
            std::cout << "ERR parse\n";
            continue;
        }
        const double dt_c = dt > 0.0 ? dt : 0.5;

        /* ── 1. where is the target? ─────────────────────────── */
        Nav nav = navigate(cur_lat, cur_lng, tgt_lat, tgt_lng);

        /* ── 2. speed loop: accelerate, brake before arrival ─── */
        double desired = 0.0;
        if (nav.distance_m > 1.5) {
            if (nav.distance_m < 25.0) {
                desired = clampd(nav.distance_m * 0.5, 1.0, max_speed);
            } else {
                desired = clampd(2.0 + 0.45 * nav.distance_m, 2.5, max_speed);
            }
        }
        double speed = last_speed +
                       clampd(speed_pid.update(desired, last_speed, dt_c),
                              -8.0 * dt_c, 8.0 * dt_c);
        speed = clampd(speed, 0.0, max_speed);
        if (nav.distance_m <= 1.5) speed = 0.0;
        last_speed = speed;

        /* ── 3. altitude loop: cruise high, descend near target ── */
        const double alt_set =
            (nav.distance_m > 40.0) ? CRUISE_ALT_M : tgt_alt;
        const double vspeed =
            clampd(alt_pid.update(alt_set, cur_alt, dt_c), -3.0, 3.0);

        /* ── 4. telemetry packet via the C module ────────────── */
        const double values[6] = {nav.bearing_deg, speed, vspeed,
                                  alt_set, battery, nav.distance_m};
        char telemetry[128];
        if (px_build_telemetry(values, 6, telemetry, sizeof(telemetry)) != 0) {
            telemetry[0] = '\0';
        }

        std::cout << nav.bearing_deg << " " << speed << " " << vspeed << " "
                  << alt_set << " " << telemetry << "\n";
        std::cout.flush();
    }
    return 0;
}
