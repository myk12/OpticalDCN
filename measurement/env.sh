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

