# Smart Drone firmware — C/C++ flight controller
# Build:  make            (run inside the firmware/ folder)
# Result: build/drone_controller(.exe)

CXX      ?= g++
CXXFLAGS  = -std=c++17 -O2 -Wall -Wextra -Iinclude
OUT       = build/drone_controller

SRCS = src/main.cpp src/pid.cpp src/navigation.cpp src/telemetry.c
HDRS = include/pid.h include/navigation.h include/telemetry.h

.PHONY: all clean

all: $(OUT)

$(OUT): $(SRCS) $(HDRS)
	@mkdir -p build
	$(CXX) $(CXXFLAGS) $(SRCS) -o $@

clean:
	rm -rf build
