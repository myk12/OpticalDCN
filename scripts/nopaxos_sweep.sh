#!/usr/bin/env bash
set -euo pipefail

# =========================
# NOPaxos throughput sweep
# =========================
# Usage:
#   bash scripts/nopaxos_sweep.sh
#
# Outputs:
#   logs/nopaxos_sweep/<timestamp>/
#     - summary.csv
#     - raw_t<threads>.log (per run)
#
# Notes:
# - In NOPaxos bench/client, -t is number of client threads.
# - Total ops ~= n * t.
# - IOPS computed using wall-clock "Completed ... in X seconds" (Finish line).

# ---- config ----
NETNS="${NETNS:-ns_fpga_1_p1}"
CLIENT_BIN="${CLIENT_BIN:-third_party/NOPaxos/bench/client}"
CONF="${CONF:-infra/host_server/nopaxos/cluster.conf}"
MODE="${MODE:-nopaxos}"

# per-thread requests
N="${N:-10000}"

# thread sweep list (space-separated)
T_LIST="${T_LIST:-1 4 8 32 48}"

# Optional: DSCP, delay etc. (leave empty if not used)
EXTRA_ARGS="${EXTRA_ARGS:-}"

# ---- derived paths ----
TS="$(date +%Y%m%d_%H%M%S)"
OUTDIR="logs/nopaxos_sweep/${TS}"
mkdir -p "${OUTDIR}"

CSV="${OUTDIR}/summary.csv"
echo "timestamp,netns,mode,n_per_thread,threads,total_ops,wall_s,iops,median_ns,avg_ns,p90_ns,p95_ns,p99_ns,max_ns,cmd" > "${CSV}"

run_one() {
  local t="$1"
  local raw="${OUTDIR}/raw_t${t}.log"

  local cmd=(sudo ip netns exec "${NETNS}" "${CLIENT_BIN}" -c "${CONF}" -m "${MODE}" -n "${N}" -t "${t}")
  if [[ -n "${EXTRA_ARGS}" ]]; then
    # shellcheck disable=SC2206
    cmd+=(${EXTRA_ARGS})
  fi

  echo "[RUN] t=${t} n=${N} -> ${raw}"
  echo "[CMD] ${cmd[*]}" | tee "${raw}"
  echo "----------------------------------------" >> "${raw}"

  # run
  "${cmd[@]}" 2>&1 | tee -a "${raw}"

  # ---- parse ----
  # Finish line example:
  # Completed 100000 requests in 12.995785 seconds
  local wall_s
  wall_s="$(grep -Eo 'Completed [0-9]+ requests in [0-9]+\.[0-9]+ seconds' "${raw}" | tail -n1 | awk '{print $5}')"
  if [[ -z "${wall_s}" ]]; then
    echo "[ERR] cannot parse wall time from ${raw}" >&2
    return 1
  fi

  # Latency lines examples:
  # Median latency is 118081 ns (118 us)
  # Average latency is 122087 ns (122 us)
  # 90th percentile latency is 134192 ns (134 us)
  # 95th percentile latency is 141379 ns (141 us)
  # 99th percentile latency is 196723 ns (196 us)
  local median_ns avg_ns p90_ns p95_ns p99_ns
  median_ns="$(grep -Eo 'Median latency is [0-9]+ ns' "${raw}" | tail -n1 | awk '{print $4}')"
  avg_ns="$(grep -Eo 'Average latency is [0-9]+ ns' "${raw}" | tail -n1 | awk '{print $4}')"
  p90_ns="$(grep -Eo '90th percentile latency is [0-9]+ ns' "${raw}" | tail -n1 | awk '{print $5}')"
  p95_ns="$(grep -Eo '95th percentile latency is [0-9]+ ns' "${raw}" | tail -n1 | awk '{print $5}')"
  p99_ns="$(grep -Eo '99th percentile latency is [0-9]+ ns' "${raw}" | tail -n1 | awk '{print $5}')"

  # Max latency from "LATENCY total" line:
  # LATENCY total: 105 us 122 us/65 us 4560 us (...)
  # Take 4th field -> max in us (could be "15 ms" in some outputs; handle both)
  local max_tok max_ns
  max_tok="$(grep -Eo 'LATENCY total: .*' "${raw}" | tail -n1 | awk '{print $(NF-6),$(NF-5)}' 2>/dev/null || true)"
  # More robust: parse "LATENCY total:" line and grab the max value+unit right before "("
  # Example tokens: ... 4560 us (....) OR ... 15 ms (....)
  max_tok="$(grep -Eo 'LATENCY total: .*' "${raw}" | tail -n1 | sed -E 's/.* ([0-9]+) (ns|us|ms) \(.*/\1 \2/')"
  if [[ -n "${max_tok}" ]]; then
    local v unit
    v="$(awk '{print $1}' <<< "${max_tok}")"
    unit="$(awk '{print $2}' <<< "${max_tok}")"
    case "${unit}" in
      ns) max_ns="${v}" ;;
      us) max_ns="$(( v * 1000 ))" ;;
      ms) max_ns="$(( v * 1000000 ))" ;;
      *)  max_ns="" ;;
    esac
  fi

  # compute iops = total_ops / wall_s
  local total_ops iops
  total_ops="$(( N * t ))"
  # Use awk for floating division
  iops="$(awk -v ops="${total_ops}" -v s="${wall_s}" 'BEGIN{printf "%.3f", ops/s}')"

  # fallback empty fields if not found
  median_ns="${median_ns:-}"
  avg_ns="${avg_ns:-}"
  p90_ns="${p90_ns:-}"
  p95_ns="${p95_ns:-}"
  p99_ns="${p99_ns:-}"
  max_ns="${max_ns:-}"

  # csv row
  local now
  now="$(date +%Y-%m-%dT%H:%M:%S)"
  echo "${now},${NETNS},${MODE},${N},${t},${total_ops},${wall_s},${iops},${median_ns},${avg_ns},${p90_ns},${p95_ns},${p99_ns},${max_ns},\"${cmd[*]}\"" >> "${CSV}"

  echo "[OK] t=${t} wall=${wall_s}s iops=${iops} median_ns=${median_ns} p99_ns=${p99_ns} max_ns=${max_ns}"
}

echo "[INFO] Writing logs to: ${OUTDIR}"
echo "[INFO] CSV: ${CSV}"
echo "[INFO] Sweep T_LIST: ${T_LIST}"
echo "[INFO] N per thread: ${N}"

for t in ${T_LIST}; do
  run_one "${t}"
done

echo "[DONE] Summary at ${CSV}"