#!/bin/bash
# servers
servers_name= (
    "inet-p4lab-14"
    "inet-p4lab-13"
    "inet-p4lab-12"
    "inet-p4lab-11"
)

ssh_user=${TESTBED_USER}
ssh_password=${TESTBED_PASSWD}

# insert ARP entries for all servers
arp_entries= (
  "10.0.1.1 00:0a:35:06:50:94"
  "10.0.1.2 00:0a:35:06:50:95"
  "10.0.1.3 00:0a:35:06:09:24"
  "10.0.1.4 00:0a:35:06:09:25"
  "10.0.2.1 00:0a:35:06:0b:84"
  "10.0.2.2 00:0a:35:06:0b:85"
  "10.0.2.3 00:0a:35:06:09:3c"
  "10.0.2.4 00:0a:35:06:09:3d"
  "10.0.3.1 00:0a:35:06:0b:72"
  "10.0.3.2 00:0a:35:06:0b:73"
  "10.0.3.3 00:0a:35:06:09:9c"
  "10.0.3.4 00:0a:35:06:09:9d"
  "10.0.4.1 00:0a:35:06:09:8a"
  "10.0.4.2 00:0a:35:06:09:8b"
  "10.0.4.3 00:0a:35:06:09:30"
  "10.0.4.4 00:0a:35:06:09:31"
)

# ssh into each server and add the ARP entries
for server in "${servers_name[@]}"; do
    echo "Configuring ARP entries on server: $server"
    for entry in "${arp_entries[@]}"; do
        ip_addr=$(echo $entry | awk '{print $1}')
        mac_addr=$(echo $entry | awk '{print $2}')
        sshpass -p "$ssh_password" ssh -o StrictHostKeyChecking=no "$ssh_user@$server" "sudo ip neigh add $ip_addr lladdr $mac_addr dev eth0 nud permanent" &
    done
    wait
    echo "ARP entries configured on server: $server"
done
echo "All ARP entries have been configured on all servers."
