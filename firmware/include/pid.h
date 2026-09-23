#ifndef PID_H
#define PID_H

/* Generic PID controller with anti-windup — used for the speed and
 * altitude loops of the drone flight controller. */
class PID {
public:
    PID(double kp, double ki, double kd, double i_max);

    void reset();
    /* One control step: setpoint vs measurement, dt in seconds. */
    double update(double setpoint, double measurement, double dt);

private:
    double kp_, ki_, kd_;
    double i_max_;      /* clamp for the integral contribution */
    double integral_;
    double prev_err_;
    bool   first_;
};

#endif /* PID_H */
