#include "pid.h"

PID::PID(double kp, double ki, double kd, double i_max)
    : kp_(kp), ki_(ki), kd_(kd), i_max_(i_max),
      integral_(0.0), prev_err_(0.0), first_(true) {}

void PID::reset() {
    integral_ = 0.0;
    prev_err_ = 0.0;
    first_ = true;
}

double PID::update(double setpoint, double measurement, double dt) {
    if (dt <= 0.0) dt = 0.001;

    const double err = setpoint - measurement;

    /* integral with anti-windup clamp */
    integral_ += err * dt;
    double i_term = ki_ * integral_;
    if (i_term > i_max_) { i_term = i_max_; integral_ = i_max_ / ki_; }
    if (i_term < -i_max_) { i_term = -i_max_; integral_ = -i_max_ / ki_; }

    /* derivative (skipped on the first step to avoid a spike) */
    double d_term = 0.0;
    if (!first_) d_term = kd_ * (err - prev_err_) / dt;
    first_ = false;
    prev_err_ = err;

    return kp_ * err + i_term + d_term;
}
