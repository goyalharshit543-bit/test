#include "navigation.h"

#include <cmath>

static const double EARTH_M = 6371000.0;
static const double PI = 3.14159265358979323846;

static double deg2rad(double d) { return d * PI / 180.0; }

double haversine_m(double lat1, double lng1, double lat2, double lng2) {
    double p1 = deg2rad(lat1), p2 = deg2rad(lat2);
    double dphi = deg2rad(lat2 - lat1);
    double dlmb = deg2rad(lng2 - lng1);
    double a = std::sin(dphi / 2.0) * std::sin(dphi / 2.0) +
               std::cos(p1) * std::cos(p2) *
                   std::sin(dlmb / 2.0) * std::sin(dlmb / 2.0);
    if (a > 1.0) a = 1.0;
    return 2.0 * EARTH_M * std::asin(std::sqrt(a));
}

double bearing_deg(double lat1, double lng1, double lat2, double lng2) {
    double p1 = deg2rad(lat1), p2 = deg2rad(lat2);
    double dlmb = deg2rad(lng2 - lng1);
    double y = std::sin(dlmb) * std::cos(p2);
    double x = std::cos(p1) * std::sin(p2) -
               std::sin(p1) * std::cos(p2) * std::cos(dlmb);
    double brng = std::atan2(y, x) * 180.0 / PI;
    while (brng < 0.0) brng += 360.0;
    while (brng >= 360.0) brng -= 360.0;
    return brng;
}

Nav navigate(double cur_lat, double cur_lng, double tgt_lat, double tgt_lng) {
    Nav nav;
    nav.distance_m = haversine_m(cur_lat, cur_lng, tgt_lat, tgt_lng);
    nav.bearing_deg =
        (nav.distance_m > 0.01) ? bearing_deg(cur_lat, cur_lng, tgt_lat, tgt_lng) : 0.0;
    return nav;
}
