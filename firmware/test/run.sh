#!/bin/sh
# Build and run the firmware tests. From this directory:  ./run.sh
set -e
cd "$(dirname "$0")"
g++ -std=c++11 -O1 -I. -Istub -o fwtest main.cpp
./fwtest
