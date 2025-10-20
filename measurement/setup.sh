#!/bin/bash
echo \n"=== === === FPGA Smart Loop Test === === ==="\n
## VARIABLES
log_info() {
    local MESSAGE=$1
    local TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    local LOG_FILE="/var/log/my_script.log"
    local COLOR=$(tput setaf 2)  # green
    local RESET=$(tput sgr0)

    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE" || { echo "Cannot create log file"; exit 1; }
    echo "${COLOR}$TIMESTAMP [INFO] $MESSAGE${RESET}" | tee -a "$LOG_FILE"
}

log_error() {
    local MESSAGE=$1
    local TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    local LOG_FILE="/var/log/my_script.log"
    local COLOR=$(tput setaf 1)  # red
    local RESET=$(tput sgr0)

    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE" || { echo "Cannot create log file"; exit 1; }
    echo "${COLOR}$TIMESTAMP [ERROR] $MESSAGE${RESET}" | tee -a "$LOG_FILE" >&2  # 输出到 stderr
}

# network namespace
NS1="fpganic_p1"
NS2="fpganic_p2"

# interface/fpga port name
PORTNAME1="enp202s0np0"
PORTNAME2="enp202s0np1"

# designated IP
IP_ADDR1="10.0.0.1/24"
IP_ADDR2="10.0.0.2/24"

## 1. Check for if NIC driver is loaded and interfaces is created
log_info "[1] Check if NIC driver is loaded."
if ! lsmod | grep -q "mqnic"; then
    log_error "NIC driver is not loaded."
    exit 1
else
    log_info "NIC driver mqnic.ko loaded OK."
fi

## 2. Create network namespce if not exists
log_info "[2] Prepare Network Namespace."
for ns in "$NS1" "$NS2"; do
    if ! ip netns list | grep -q $ns; then
        log_info "- creating network namespace $ns..."
        sudo ip netns add $ns
        if [ $? -ne 0 ]; then
            log_error "- Failed to create namespace $ns. Exiting."
            exit 1
        fi
    else
        log_info "- network space $ns exists."
    fi
done

## 3. Assign network interface to netowrk namespace if haven't
log_info "[3] Assgin interface to ns and IP to interface."
for pair in "$PORTNAME1 $NS1 $IP1" "$PORTNAME2 $NS2 $IP2"; do
    read -r port ns ip <<< "$pair"
    if ! ip link show "$port" &> /dev/null; then
        log_error "Interface $port does not exist. Please check the interface name."
        exit 1
    fi

    # move interface to specified network namespace
    current_ns=$(ip link show "$port" | grep -o "netns:[0-9]\+" | cut -d: -f2)
    if [ -n "$current_ns" ]; then
        target_ns_id=$(ip netns identify "$(ip netns exec "$ns" readlink /proc/self/ns/net)" 2>/dev/null)
        if [ "$current_ns" = "$target_ns_id" ]; then
            log_info "Interface $port is already in namespace $ns."
        else
            log_info "Moving interface $port to namespace $ns..."
            sudo ip link set "$port" netns "$ns" || { log_error "Failed to move interface $port to namespace $ns"; exit 1; }
        fi
    else
        log_info "Moving interface $port to namespace $ns..."
        sudo ip link set "$port" netns "$ns" || { log_error "Failed to move interface $port to namespace $ns"; exit 1; }
    fi

    # assign IP address
    sudo ip netns exec "$ns" ip addr show "$port" | grep -q "$ip" && {
        log_info "IP $ip is already configured on interface $port in namespace $ns."
    } || {
        log_info "Configuring IP $ip on interface $port in namespace $ns..."
        sudo ip netns exec "$ns" ip addr add "$ip" dev "$port" || { log_error "Failed to add IP $ip on interface $port"; exit 1; }
        sudo ip netns exec "$ns" ip link set "$port" up || { log_error "Failed to bring up interface $port"; exit 1; }
        log_info "Interface $port in namespace $ns configured with IP $ip."
    }
done

## 4. Test connectivity
log_info "Testing connectivity between $IP1 and $IP2..."
sudo ip netns exec "$NS1" ping -c 3 "$IP2"
if [ $? -eq 0 ]; then
    log_info "Ping from $NS1 ($IP1) to $NS2 ($IP2) succeeded."
else
    log_error "Ping from $NS1 ($IP1) to $NS2 ($IP2) failed."
fi

sudo ip netns exec "$NS2" ping -c 3 "$IP1"
if [ $? -eq 0 ]; then
    info "Ping from $NS2 ($IP2) to $NS1 ($IP1) succeeded."
else
    error "Ping from $NS2 ($IP2) to $NS1 ($IP1) failed."
fi
