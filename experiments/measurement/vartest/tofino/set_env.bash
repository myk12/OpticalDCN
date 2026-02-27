#!/bin/bash
# Project environment bootstrap. Source this:  source tofino/set_env.bash
SDE_PATH=/home/p4/bf-sde-9.12.0/
BUILD_TOOL_PATH=/home/p4/tools/

# Point this to your SDE
export SDE=$SDE_PATH
# Point this to your SDE install root
export SDE_INSTALL=${SDE_INSTALL:-$SDE_PATH/install}
# Point this to your SDE build tools
export BUILD_TOOL=$BUILD_TOOL_PATH

# Common paths (adapt to your environment/version)
export PATH="$SDE_INSTALL/bin:$PATH"
export LD_LIBRARY_PATH="$SDE_INSTALL/lib:$SDE_INSTALL/lib64:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$SDE_INSTALL/lib/python3.10/site-packages:${PYTHONPATH:-}"

# Convenience: project root
export PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"

# Defaults
export P4_PROG=${P4_PROG:-ts_pipeline}
export P4_DIR=${P4_DIR:-$PROJ_ROOT/p4}
export P4_BUILD=${P4_BUILD:-$P4_DIR/build}
export TOPO_YAML=${TOPO_YAML:-$PROJ_ROOT/tofino/topo.yaml}
export PKTGEN_APP_ID=${PKTGEN_APP_ID:-1}
export PKTGEN_PORT_ID=${PKTGEN_PORT_ID:-6}

export PATTERN=${PATTERN:-"SINGLE"} # SINGLE, MULTI, BURST
export RATE=${RATE:-10} # in Gbps
export PACKET_SIZE=${PACKET_SIZE:-128} # in bytes

# Take args from command line to override defaults
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --pattern)
      PATTERN="$2"
      shift # past argument
      shift # past value
      ;;
    --rate)
      RATE="$2"
      shift # past argument
      shift # past value
      ;;
    --packet_size)
      PACKET_SIZE="$2"
      shift # past argument
      shift # past value
      ;;
    --topo_yaml)
      TOPO_YAML=$PROJ_ROOT/tofino/"$2"
      shift # past argument
      shift # past value
      ;;
    *)    # unknown option
      echo "Unknown option: $1"
      shift # past argument
      ;;
  esac
done

# Save as a json file for other scripts to read
echo "{\"SDE\":\"$SDE\",
\"SDE_INSTALL\":\"$SDE_INSTALL\",
\"PROJ_ROOT\":\"$PROJ_ROOT\",
\"P4_PROG\":\"$P4_PROG\",
\"P4_DIR\":\"$P4_DIR\",
\"P4_BUILD\":\"$P4_BUILD\",
\"TOPO_YAML\":\"$TOPO_YAML\",
\"PKTGEN_APP_ID\":\"$PKTGEN_APP_ID\",
\"PKTGEN_PORT_ID\":\"$PKTGEN_PORT_ID\",
\"PATTERN\":\"$PATTERN\",
\"RATE\":\"$RATE\",
\"PACKET_SIZE\":\"$PACKET_SIZE\"}" > /tmp/tofino_env.json

# Print summary
echo "Environment setup complete. Summary:"
echo "+ SDE=$SDE"
echo "+ SDE_INSTALL=$SDE_INSTALL"
echo "+ PROJ_ROOT=$PROJ_ROOT"
echo "+ P4_PROG=$P4_PROG"
echo "+ P4_DIR=$P4_DIR"
echo "+ P4_BUILD=$P4_BUILD"
echo "+ BUILD_TOOL=$BUILD_TOOL"
