#!/bin/bash

# Environment variables for server namespaces and network interfaces
export NS1="fpganic_p1"
export NS2="fpganic_p2"
export PORTNAME1="enp202s0np0"
export PORTNAME2="enp202s0np1"
export IP_ADDR1="10.0.0.1/24"
export IP_ADDR2="10.0.0.2/24"
export IP1=$(echo $IP_ADDR1 | cut -d'/' -f1)
export IP2=$(echo $IP_ADDR2 | cut -d'/' -f1)
export MAC1="4c:ed:fb:3a:4b:50"
export MAC2="4c:ed:fb:3a:4b:51"

# SSH credentials for Tofino switch
export TOFINO_SSH_USER="p4"
export TOFINO_SSH_HOST="10.0.13.21"
export TOFINO_SSH_PASSWORD="rocks"

# Paths to the switch configuration scripts
export PROJ_ROOT="~/vartest"
export SETUPENV_SCRIPT_PATH="$PROJ_ROOT/tofino/set_env.bash"
export CLEAR_SCRIPT_PATH="$PROJ_ROOT/tofino/bfrt/bfrt_clear_switch.py"
export CONFIG_SCRIPT_PATH="$PROJ_ROOT/tofino/bfrt/bfrt_config_switch.py"

# Summary of the environment variables set
echo "Environment variables set for Tofino switch configuration:"
echo "---------------------------------------------"
echo "Namespace 1: $NS1"
echo "Namespace 2: $NS2"
echo "Port Name 1: $PORTNAME1"
echo "Port Name 2: $PORTNAME2"
echo "IP Address 1: $IP_ADDR1"
echo "IP Address 2: $IP_ADDR2"
echo "MAC Address 1: $MAC1"
echo "MAC Address 2: $MAC2"
echo "Tofino SSH User: $TOFINO_SSH_USER"
echo "Tofino SSH Host: $TOFINO_SSH_HOST"
echo "Setup Environment Script Path: $SETUPENV_SCRIPT_PATH"
echo "Clear Switch Script Path: $CLEAR_SCRIPT_PATH"
echo "Config Switch Script Path: $CONFIG_SCRIPT_PATH"
echo "---------------------------------------------"
