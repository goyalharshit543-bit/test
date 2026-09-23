#ifndef NAVIGATION_H
#define NAVIGATION_H

/* Great-circle navigation maths for the flight controller. */
struct Nav {
    double distance_m;
    double bearing_deg;   /* 0 = North, 90 = East */
};

Nav navigate(double cur_lat, double cur_lng, double tgt_lat, double tgt_lng);
double haversine_m(double lat1, double lng1, double lat2, double lng2);
double bearing_deg(double lat1, double lng1, double lat2, double lng2);

#endif /* NAVIGATION_H */
