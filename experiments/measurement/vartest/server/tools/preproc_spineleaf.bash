#!/bin/bash
# --- Configurable parameters ---
RESULTS_DIR="../results/spineleaf_vartest"
OUTPUT_FILE="hop_latency.csv"

FILTER_PATTERN="spineleaf_probe_results_partial_1766277893*.csv"

# --- Preprocessing script ---
echo "packet_id, hop1_latency_ns, hop2_latency_ns" > ${RESULTS_DIR}/${OUTPUT_FILE}

count=0

for file in ${RESULTS_DIR}/${FILTER_PATTERN}; do
    [ -e "$file" ] || continue
    echo "Processing file: $file"
    awk -F, '
    BEGIN {
        OFS = ",";
    }
    NR > 1 {
        id = $1_$2;
        idx = $4;   # hop idx
        ts = $5;    # ingress_ts in ns

        if (idx == 0) t0[id] = ts;
        else if (idx == 1) t1[id] = ts;
        else if (idx == 2) {
            # calculate hop latencies when hop0 and hop1 timestamps are available
            if (id in t0 && id in t1) {
                hop1_latency = t1[id] - t0[id];
                hop2_latency = ts - t1[id];
                print id, hop1_latency, hop2_latency;

                # remove entries to save memory
                delete t0[id];
                delete t1[id];
            }
        }
    }
    ' "$file" >> ${RESULTS_DIR}/${OUTPUT_FILE}
    count=$((count + 1))
done

echo "Processed ${count} files. Results saved to ${RESULTS_DIR}/${OUTPUT_FILE}."
        