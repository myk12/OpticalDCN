/* ===============================================================
 *         Spine-Leaf Topology P4 Program for Tofino Switch
 * ===============================================================
 * This P4 program implements a basic spine-leaf switching logic
 * for a Tofino switch in a spine-leaf topology.
 * The program classifies packets based on their ingress port
 * to determine whether they are from leaf switches or spine switches,
 * and forwards them accordingly.
 * =============================================================== */

#include <core.p4>
#if __TARGET_TOFINO__ == 2
#include <t2na.p4>
#else
#include <tna.p4>
#endif

#include "include/headers.p4"
#include "include/util.p4"

//--------------------------------------------
// Constants and Type Definitions
//--------------------------------------------
#define ETHERTYPE_IPV4 0x0800
#define IP_PROTOCOL_UDP 17
#define IP_PROTOCOL_TCP 6

/* ****** Modes *******
 * MODE_L2: simple L2 forwarding based on dst MAC
 * MODE_CLOS_L3: CLOS-style L3 forwarding with logical switch id and hash-based spine selection
 * MODE_NOPAXOS: L3 forwarding following NOPaxos design (not implemented in this code)
 */
const bit<8> MODE_L2 = 0;
const bit<8> MODE_CLOS_L3 = 1;
const bit<8> MODE_NOPAXOS = 2;

/* Ingress kinds (where packet comes from) */
const bit<8> K_UNKNOWN          = 0;
const bit<8> K_LEAF_DOWNLINK    = 1; // leaf even ports: servers/FPGAs -> leaf switch
const bit<8> K_LEAF_UPLINK      = 2; // leaf odd ports: leaf switch -> spine
const bit<8> K_SPINE_PORT       = 3; // spine ports -> leaf uplinks

/* Topology parameters */
const bit<8> NUM_LEAFS = 4;
const bit<8> NUM_SPINES = 2;

/* ------------------------------
 * Header and Metadata Definitions
 * -------------------------------------------- */

header nopaxos_t {
    bit<16> magic; // Magic number to identify NOPaxos packets
    bit<16> epoch; // Epoch number for NOPaxos
    bit<32> seq_num; // Sequence number for NOPaxos
    bit<32> shard;
    bit<16> flags;
}

struct header_t {
    ethernet_h ethernet;
    ipv4_h     ipv4;
    udp_h      udp;
    tcp_h      tcp;
    nopaxos_t  nopaxos; // Optional NOPaxos header, only valid if magic number matches
}

struct metadata_t {
    /* Mode selection */
    bit<8> mode; // 0 = MODE_L2, 1 = MODE_CLOS_L3, 2 = MODE_NOPAXOS
    bit<8> mode_key; // Key for mode selection table (can be extended for more complex mode selection)

    /* Port classification metadata */
    bit<8> ingress_kind;    // K_UNKNOWN, K_LEAF_DOWNLINK, K_LEAF_UPLINK, K_SPINE_PORT
    bit<8> ingress_leaf;    // if ingress_kind is K_LEAF_DOWNLINK or K_LEAF_UPLINK, which leaf switch it is (1-4)
    bit<8> ingress_spine;   // if ingress_kind is K_SPINE_PORT, which spine switch it is (1-2)

    /* Destination classification metadata */
    bit<8> dst_leaf;        // if destination is a leaf, which leaf switch it is (1-4)
    PortId_t dst_downlink_port; // if destination is a leaf, which downlink port to forward to

    /* ECMP-like spine selection metadata */
    bit<32> hash_seed;      // seed for hash calculation for spine selection
    bit<8> selected_spine;  // selected spine switch based on hash

    pktgen_timer_header_t pktgen_timer_hdr; // Pktgen timer header

    /* NOPaxos metadata (for MODE_NOPAXOS) */
    bit<8> is_nopaxos_req;
    bit<32> nopaxos_shard;
    bit<16> nopaxos_epoch;
    bit<32> nopaxos_seq_num;
    MulticastGroupId_t nopaxos_multicast_group; // Multicast group for NOPaxos replication
}

/* --------------------------------------------
 * Stateful objects (Registers, Meters, etc.)
 * -------------------------------------------- */
const bit<32> NUM_SHARDS = 16; // Example number of shards for NOPaxos
Register<bit<32>, bit<32>>(NUM_SHARDS) seq_num_reg; // For NOPaxos: stores the latest sequence number for each shard
const bit<32> EPOCH_SLOTS = 1; // Number of slots for epoch number (can be extended for more complex epoch management)
Register<bit<16>, bit<32>>(EPOCH_SLOTS) epoch_reg; // For NOPaxos: stores the current epoch number (can be extended for more complex epoch management)

// --------------------------------------------
// Ingress Parser
// --------------------------------------------
parser IngressParser(
    packet_in packet,
    out header_t hdr,
    out metadata_t ig_md,
    out ingress_intrinsic_metadata_t ig_intr_md
) {
    TofinoIngressParser() tofino_parser;

    state start {
        tofino_parser.apply(packet, ig_intr_md);

        // Here we handle pktgen headers based on ingress port
        transition select(ig_intr_md.ingress_port) {
            6: parse_pktgen; // Port 6 is pktgen port
            68: parse_pktgen; // Port 68 is pktgen port (DHCP)
            default: parse_ethernet;
        }
    }

    // if it's from pktgen port, extract pktgen header
    state parse_pktgen {
        packet.extract(ig_md.pktgen_timer_hdr);
        transition parse_ethernet;
    }

    // normal ethernet parsing
    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.ether_type) {
            ETHERTYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    // IPv4 parsing
    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            IP_PROTOCOL_UDP: parse_udp;
            IP_PROTOCOL_TCP: parse_tcp;
            default: accept;
        }
    }

    // UDP parsing
    state parse_udp {
        packet.extract(hdr.udp);
        transition accept;
    }

    // TCP parsing
    state parse_tcp {
        packet.extract(hdr.tcp);
        transition accept;
    }
}

// -------------------------------------------
// Ingress Control: Core Spine-Leaf Logic
// -------------------------------------------
control Ingress(
    inout header_t hdr,
    inout metadata_t ig_md,
    in ingress_intrinsic_metadata_t ig_intr_md,
    in ingress_intrinsic_metadata_from_parser_t ig_intr_prsr_md,
    inout ingress_intrinsic_metadata_for_deparser_t ig_intr_dprsr_md,
    inout ingress_intrinsic_metadata_for_tm_t ig_intr_tm_md) {

    // Define Actions
    action drop() {
        ig_intr_dprsr_md.drop_ctl = 0x1;
    }

    action set_port_role(bit<8> kind, bit<8> leaf_id, bit<8> spine_id) {
        ig_md.ingress_kind = kind;
        ig_md.ingress_leaf = leaf_id;
        ig_md.ingress_spine = spine_id;
    }

    action set_ucast_port(PortId_t port) {
        ig_intr_tm_md.ucast_egress_port = port;
    }

    action set_mode(bit<8> mode) {
        ig_md.mode = mode;
    }

    /* MODE_L2: simple L2 forwarding based on dst MAC */
    action l2_forward(PortId_t port) {
        ig_intr_tm_md.ucast_egress_port = port;
    }

    action l2_drop() {
        drop();
    }

    /* MODE_CLOS_L3: CLOS-style L3 forwarding with logical switch id and hash-based spine selection */
    action set_dst(bit<8> dst_leaf, PortId_t dst_downlink_port) {
        ig_md.dst_leaf = dst_leaf;
        ig_md.dst_downlink_port = dst_downlink_port;
    }

    /* leaf uplink selection: hash-based ECMP */
    action set_selected_spine(bit<8> spine_id) {
        ig_md.selected_spine = spine_id;
    }

    action set_leaf_uplink_port(PortId_t uplink_port) {
        ig_intr_tm_md.ucast_egress_port = uplink_port;
    }

    /* Spine forwarding: forward to selected spine port */
    action set_spine_egress_port(PortId_t spine_port) {
        ig_intr_tm_md.ucast_egress_port = spine_port;
    }

    /* MODE_NOPAXOS: L3 forwarding following NOPaxos design (not implemented in this code) */
    action mark_nopaxos_req(bit<32> shard, bit<16> epoch, bit<32> seq_num) {
        ig_md.is_nopaxos_req = 1;
        ig_md.nopaxos_shard = shard;
        ig_md.nopaxos_epoch = epoch;
        ig_md.nopaxos_seq_num = seq_num;
    }

    action clear_nopaxos_metadata() {
        ig_md.is_nopaxos_req = 0;
        ig_md.nopaxos_shard = 0;
        ig_md.nopaxos_epoch = 0;
        ig_md.nopaxos_seq_num = 0;
    }

    action set_multicast_group(MulticastGroupId_t mcast_grp) {
        ig_md.nopaxos_multicast_group = mcast_grp;
        ig_intr_tm_md.mcast_grp_a = mcast_grp;
    }

    /* Allocate seq/epoch and stamp nopaxos header.
     * NOTE: This is a mimimal "data-plane" sequencer for NOPaxos, 
     * which does not guarantee consistency across multiple switches 
     * or multiple pipelines in the same switch.
     */
    action nopaxos_sequencer() {
        bit<16> ep;
        ep = epoch_reg.read(0);
        ig_md.nopaxos_epoch = ep;

        bit<32> cur = seq_num_reg.read(ig_md.nopaxos_shard);
        ig_md.nopaxos_seq_num = cur;
        seq_num_reg.write(ig_md.nopaxos_shard, cur + 1);

        // Set magic number to identify NOPaxos packets and shard id
        hdr.nopaxos.setValid();
        hdr.nopaxos.magic = 0xBEEF; // example magic number
        hdr.nopaxos.shard = ig_md.nopaxos_shard;
        hdr.nopaxos.epoch = ig_md.nopaxos_epoch;
        hdr.nopaxos.seq_num = ig_md.nopaxos_seq_num;
        hdr.nopaxos.flags = 0; // can be used for additional info (e.g., request type)
    }

    /* -------------------------------------------
     *   Tables
     * ---------------------------------------- */
    
    // Port role mapping: dev_port -> (ingress_kind, leaf_id, spine_id)
    table t_port_role {
        key = {
            ig_intr_md.ingress_port: exact;
        }
        actions = {
            set_port_role;
            drop;
            NoAction;
        }
        size = 64;
        default_action = drop();
    }

    // Mode table: mode_key -> mode
    table t_mode {
        key = {
            ig_md.mode_key: exact;
        }
        actions = {
            set_mode;
            NoAction;
        }
        size = 1;
        default_action = set_mode(MODE_L2); // default to MODE_L2
    }

    // L2 forwarding table: dst MAC -> egress port
    table t_l2_forward {
        key = {
            hdr.ethernet.dst_addr: exact;
        }
        actions = {
            l2_forward;
            l2_drop;
            NoAction;
        }
        size = 1024;
        default_action = l2_drop();
    }

    // CLOS L3 forwarding: dst leaf -> (dst downlink port)
    table t_dst_mac_classify {
        key = {
            hdr.ethernet.dst_addr: exact;
        }
        actions = {
            set_dst;
        }
        size = 1024;
        default_action = set_dst(0, 0); // default to invalid leaf and port
    }

    // leaf uplink selection: (ingress leaf, selected spine) -> uplink dev_port
    table t_leaf_uplink_select {
        key = {
            ig_md.ingress_leaf: exact;
            ig_md.selected_spine: exact;
        }
        actions = {
            set_leaf_uplink_port;
        }
        size = 64;
        default_action = set_leaf_uplink_port(0); // default to invalid port
    }

    // spine forwarding: (ingress spine, dst leaf) -> downlink dev_port
    table t_spine_forward {
        key = {
            ig_md.ingress_spine: exact;
            ig_md.dst_leaf: exact;
        }
        actions = {
            set_spine_egress_port;
        }
        size = 64;
        default_action = set_spine_egress_port(0); // default to invalid port
    }

    /* NOPaxos request classify:
     * - simplest: match UDP dst port
     */
    table t_nopaxos_classify {
        key = {
            hdr.ipv4.isValid() : exact;
            hdr.udp.isValid() : exact;
            hdr.udp.dst_port: exact;
        }
        actions = {
            mark_nopaxos_req;
            clear_nopaxos_metadata;
            NoAction;
        }
        size = 64;
        default_action = clear_nopaxos_metadata();
    }

    /* Replica multicast mapping: (shard) -> multicast group */
    table t_replica_multicast {
        key = {
            ig_md.nopaxos_shard: exact;
        }
        actions = {
            set_multicast_group;
        }
        size = 1024;
        default_action = set_multicast_group(0); // default to invalid group
    }

    /* Hash helpers for spine selection */
    Hash<bit<32>>(HashAlgorithm_t.CRC32) crc32_hash;

    // Ingress processing logic
    apply {
        // defaults
        ig_md.mode_key = 0;
        ig_md.ingress_kind = K_UNKNOWN;
        ig_md.ingress_leaf = 0;
        ig_md.ingress_spine = 0;
        ig_md.dst_leaf = 0;
        ig_md.dst_downlink_port = 0;
        ig_md.selected_spine = 0;
        ig_md.hash_seed = 0;
        ig_md.is_nopaxos_req = 0;
        ig_md.nopaxos_shard = 0;
        ig_md.nopaxos_epoch = 0;
        ig_md.nopaxos_seq_num = 0;
        ig_md.nopaxos_multicast_group = 0;

        // 1. Identify ingress port role
        t_port_role.apply();

        // 2. Determine processing mode
        t_mode.apply();

        if (!hdr.ethernet.isValid()) {
            // If no Ethernet header, drop the packet
            drop();
            return;
        }

        // 3. MODE_L2: simple L2 forwarding
        if (ig_md.mode == MODE_L2) {
            t_l2_forward.apply();
            return;
        }

        // Common processing for MODE_CLOS_L3 and MODE_NOPAXOS: classify destination and select spine
        t_dst_mac_classify.apply();

        // Optionally classify NOPaxos requests (for MODE_NOPAXOS)
        if (hdr.ipv4.isValid() && (hdr.udp.isValid() || hdr.tcp.isValid())) {
            t_nopaxos_classify.apply();
        }

        // 4. MODE_CLOS_L3: CLOS-style L3 forwarding
        if (ig_md.mode == MODE_CLOS_L3) {
            if (ig_md.ingress_kind == K_LEAF_DOWNLINK) {
                // Packets from leaf downlink: select spine uplink based on hash
                if (ig_md.dst_leaf == ig_md.ingress_leaf) {
                    // Destination is in the same leaf, forward to downlink port
                    set_ucast_port(ig_md.dst_downlink_port);
                } else {
                    // Destination is in a different leaf, select spine uplink
                    // Simple hash: XOR of src/dst IP and ports (if valid)
                    bit<32> hash_value = crc32_hash.get({
                        hdr.ethernet.src_addr,
                        hdr.ethernet.dst_addr,
                        hdr.ipv4.src_addr,
                        hdr.ipv4.dst_addr
                    });

                    // pick spine 1 or 2 based on hash value
                    bit<1> sel = (bit<1>)(hash_value & 1); // simple LSB-based selection for 2 spines
                    bit<8> spine_id = (bit<8>)(sel) + 1; // spine_id = 1 or 2
                    set_selected_spine(spine_id);
                    t_leaf_uplink_select.apply();
                }

                return;
            }

            if (ig_md.ingress_kind == K_SPINE_PORT) {
                // Packets from spine: forward to correct leaf downlink
                t_spine_forward.apply();
                return;
            }

            if (ig_md.ingress_kind == K_LEAF_UPLINK) {
                // Packets from leaf uplink that is spine 
                set_ucast_port(ig_md.dst_downlink_port); // forward back to the same port (loopback to spine)
                return;
            }

            // For unknown ingress kind, drop the packet
            drop();
            return;
        }

        // 5. MODE_NOPAXOS: NOPaxos-style L3 forwarding (not fully implemented)
        // Not implemented in this code, but the general idea would be:
        // - Classify NOPaxos requests using t_nopaxos_classify
        // - For NOPaxos requests, use nopaxos_sequencer to assign sequence numbers and epochs
        // - Use t_replica_multicast to determine multicast group for replication

        // For any other mode, drop the packet
        drop();
    }
}

// -------------------------------------------
// Ingress Deparser - keep it simple
// -------------------------------------------
control IngressDeparser(
    packet_out packet,
    inout header_t hdr,
    in metadata_t ig_md,
    in ingress_intrinsic_metadata_for_deparser_t ig_intr_dprsr_md
) {
    apply {
        // Emit headers
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.udp);
        packet.emit(hdr.tcp);
    }
}

// -------------------------------------------
// Egress Parser & Deparser
// -------------------------------------------
parser EgressParser(
    packet_in packet,
    out header_t hdr,
    out metadata_t eg_md,
    out egress_intrinsic_metadata_t eg_intr_md
) {
    TofinoEgressParser() tofino_parser;

    state start {
        tofino_parser.apply(packet, eg_intr_md);
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.ether_type) {
              ETHERTYPE_IPV4: parse_ipv4;
              default: accept;
        }

    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            IP_PROTOCOL_UDP: parse_udp;
            IP_PROTOCOL_TCP: parse_tcp;
            default: accept;
        }
    }

    state parse_udp {
        packet.extract(hdr.udp);
        transition accept;
    }

    state parse_tcp {
        packet.extract(hdr.tcp);
        transition accept;
    }
}

// -------------------------------------------
// Egress Control: Timestamping Logic
// -------------------------------------------
control Egress(
    inout header_t hdr,
    inout metadata_t eg_md,
    in egress_intrinsic_metadata_t eg_intr_md,
    in egress_intrinsic_metadata_from_parser_t eg_intr_from_prsr,
    inout egress_intrinsic_metadata_for_deparser_t eg_intr_md_for_dprsr,
    inout egress_intrinsic_metadata_for_output_port_t eg_intr_md_for_oport
) {
    apply {
        // Currently no egress processing is defined
        // This can be extended for egress timestamping or other functions
    }
}

control EgressDeparser(
    packet_out packet,
    inout header_t hdr,
    in metadata_t eg_md,
    in egress_intrinsic_metadata_for_deparser_t eg_intr_dprsr_md
) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.udp);
        packet.emit(hdr.tcp);
    }
}

// -------------------------------------------
// Main Pipeline and Switch Declaration
// -------------------------------------------
Pipeline(IngressParser(),
    Ingress(),
    IngressDeparser(),
    EgressParser(),
    Egress(),
    EgressDeparser()) pipe;
Switch(pipe) main;
