#!/bin/bash
source  ./server/set_env.bash

#TRAFFIC_PATTERNS=("SINGLE" "MULTIPLE")
TRAFFIC_PATTERNS=("FULL")
LINK_RATES=(40 100 120)
PACKET_SIZES=(64 512 1024 1500)
RESULT_DIR="$(pwd)/results/$(date +%Y%m%d_%H%M%S)"
mkdir -p $RESULT_DIR

echo "=== === === Batch Tofino Latency Probe Test === === ==="
for pattern in "${TRAFFIC_PATTERNS[@]}"; do
    for rate in "${LINK_RATES[@]}"; do
        for psize in "${PACKET_SIZES[@]}"; do
            echo "Running test: Pattern=$pattern, Rate=$rate, Packet Size=$psize"
            echo "Results will be stored in: $RESULT_DIR"
            export TRAFFIC_PATTERN=$pattern
            export LINK_RATE=$rate
            export PACKET_SIZE=$psize

            # Run the latency probe test
            # The running must be blocked cause we need different Tofino settings per test
            sudo -E python3 ./server/probe_main.py \
                        --result_dir $RESULT_DIR \
                        --pattern $pattern \
                        --rate $rate \
                        --packet_size $psize \
                        --topo_yaml topo_fully.yaml

            if [ $? -ne 0 ]; then
                echo "Test failed for Pattern=$pattern, Rate=$rate, Packet Size=$psize"
            else
                echo "Test completed for Pattern=$pattern, Rate=$rate, Packet Size=$psize"
            fi

            echo "---------------------------------------------"
        done
    done
done
