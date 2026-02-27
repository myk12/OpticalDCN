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

// Packet headers aggregation
header vartest_h {
    bit<32> experiment_id;
    bit<32> sender_id;
    bit<32> seq_no;
    bit<32>  hop_count;

    // hop1
    bit<64> hop1_ts_ingress;
    bit<64> hop1_ts_egress;
    bit<32> hop1_ingress_port;
    bit<32> hop1_egress_port;

    // hop2
    bit<64> hop2_ts_ingress;
    bit<64> hop2_ts_egress;
    bit<32> hop2_ingress_port;
    bit<32> hop2_egress_port;

    // hop3
    bit<64> hop3_ts_ingress;
    bit<64> hop3_ts_egress;
    bit<32> hop3_ingress_port;
    bit<32> hop3_egress_port;

    // hop4
    bit<64> hop4_ts_ingress;
    bit<64> hop4_ts_egress;
    bit<32> hop4_ingress_port;
    bit<32> hop4_egress_port;
}

struct header_t {
    ethernet_h ethernet;
    ipv4_h     ipv4;
    udp_h      udp;
    tcp_h      tcp;
    vartest_h  vartest;
}

// define custom metadata to hold logical role
struct metadata_t {
    // core logical role of the switch
    // 1-4 = leaf 1-4, 10 = spine elec, 20 = spine optical
    pktgen_timer_header_t pktgen_timer_hdr; // Pktgen timer header
    bit<8> logical_switch_id;
}

// --------------------------------------------
// Ingress Parser
// --------------------------------------------
parser SnosIngressParser(
    packet_in packet,
    out header_t hdr,
    out metadata_t ig_md,
    out ingress_intrinsic_metadata_t ig_intr_md
) {
    TofinoIngressParser() tofino_parser;

    state start {
        tofino_parser.apply(packet, ig_intr_md);

        transition select(ig_intr_md.ingress_port) {
            6: parse_pktgen; // Port 6 is pktgen port
            68: parse_pktgen; // Port 68 is pktgen port (DHCP)
            default: parse_ethernet;
        }
    }

    state parse_pktgen {
        packet.extract(ig_md.pktgen_timer_hdr);
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
        transition parse_vartest;
    }

    state parse_tcp {
        packet.extract(hdr.tcp);
        transition accept;
    }

    state parse_vartest {
        packet.extract(hdr.vartest);
        transition accept;
    }
}

// -------------------------------------------
// Ingress Control: Core Spine-Leaf Logic
// -------------------------------------------
control SnosIngress(
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

    action set_logical_switch(bit<8> switch_id) {
        ig_md.logical_switch_id = switch_id;
    }

    // standard L3 forwarding action
    // parameter: output port
    action ipv4_forward(PortId_t port) {
        // set output port
        ig_intr_tm_md.ucast_egress_port = port;
    }

    action set_port(bit<9> egress_port) {
        ig_intr_tm_md.ucast_egress_port = egress_port;
    }

    //@name("pktgen_seqno_reg")
    //Register<bit<32>, bit<32>>(1) pktgen_seqno_reg;

    // Register to hold pktgen sequence number
    //RegisterAction<bit<32>, bit<32>, bit<32>>(pktgen_seqno_reg) get_and_inc_seqno = {
    //    void apply(inout bit<32> seq_no, out bit<32> returns_val) {
    //        returns_val = seq_no;
    //        seq_no = seq_no + 1;
    //    }
    //};

    //action add_seqno() {
    //    bit<32> current_seqno;
    //    get_and_inc_seqno.execute(0, current_seqno);
    //    hdr.vartest.seq_no = current_seqno;
    //}
    // Table Definitions

    // [Table 1] virtualize mapping of physical port to logical role
    // function: map physical port to logical switch id
    table t_port_mapping {
        key = {
            ig_intr_md.ingress_port: exact;
        }
        actions = {
            set_logical_switch;
            @defaultonly drop;
        }
        size = 256;
        const default_action = drop();
    }

    // [Table 2] unified forwarding table for spine and leaf switches
    // function: lookup this table no matter leaf or spine
    // key: logical_switch_id is included in the key to separate entries for different logical switches
    table t_ipv4_lpm {
        key = {
            ig_md.logical_switch_id: exact;
            hdr.ipv4.dst_addr: lpm;
        }
        actions = {
            ipv4_forward;
            drop;
        }
        size = 4096;
        const default_action = drop();
    }

    table pass_through {
        key = {
            ig_intr_md.ingress_port: exact@name("ingress_port");
        }
        actions = {
            set_port;

            @defaultonly drop;
        }
        size = 256;
    }

    // Apply Logic
    apply {
        // apply pass through table first
        if (pass_through.apply().hit) {
            // if hit, skip further processing
        } else {
            // First, map physical port to logical switch id
            if (hdr.ipv4.isValid()) {

                t_port_mapping.apply();

                // Then, perform L3 forwarding based on logical switch id and dst IP
                t_ipv4_lpm.apply();

            } else {
                // non-ip packet, drop
                drop();
            }
        }

        // if (ig_intr_md.ingress_port == 6 || ig_intr_md.ingress_port == 68) {
        //     // Packet from pktgen port, add sequence number
        //     add_seqno();
        // }

        // second Stamp ingress timestamps if headers are valid
        if (hdr.vartest.isValid()) {
            bit<32> hop_count = hdr.vartest.hop_count;
            bit<64> ingress_ts = (bit<64>) ig_intr_md.ingress_mac_tstamp;
            bit<32> ingress_port = (bit<32>) ig_intr_md.ingress_port;

            if (hop_count == 0) {
                hdr.vartest.hop1_ts_ingress = ingress_ts;
                hdr.vartest.hop1_ingress_port = ingress_port;
            } else if (hop_count == 1) {
                hdr.vartest.hop2_ts_ingress = ingress_ts;
                hdr.vartest.hop2_ingress_port = ingress_port;
            } else if (hop_count == 2) {
                hdr.vartest.hop3_ts_ingress = ingress_ts;
                hdr.vartest.hop3_ingress_port = ingress_port;
            } else if (hop_count == 3) {
                hdr.vartest.hop4_ts_ingress = ingress_ts;
                hdr.vartest.hop4_ingress_port = ingress_port;
            }

            // UDP checksum update for now
            if (hdr.udp.isValid()) {
                hdr.udp.checksum = 0;
            }
        }
    }
}

// -------------------------------------------
// Ingress Deparser - keep it simple
// -------------------------------------------
control SnosIngressDeparser(
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
        packet.emit(hdr.vartest);
    }
}

// -------------------------------------------
// Egress Parser & Deparser
// -------------------------------------------
parser SnosEgressParser(
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
        transition parse_vartest;
    }

    state parse_tcp {
        packet.extract(hdr.tcp);
        transition accept;
    }

    state parse_vartest {
        packet.extract(hdr.vartest);
        transition accept;
    }
}

// -------------------------------------------
// Egress Control: Timestamping Logic
// -------------------------------------------
control SnosEgress(
    inout header_t hdr,
    inout metadata_t eg_md,
    in egress_intrinsic_metadata_t eg_intr_md,
    in egress_intrinsic_metadata_from_parser_t eg_intr_from_prsr,
    inout egress_intrinsic_metadata_for_deparser_t eg_intr_md_for_dprsr,
    inout egress_intrinsic_metadata_for_output_port_t eg_intr_md_for_oport
) {
    apply {
        if (hdr.vartest.isValid()) {
            bit<32> hop_count = hdr.vartest.hop_count;
            bit<64> egress_ts = (bit<64>) eg_intr_from_prsr.global_tstamp;
            bit<32> egress_port = (bit<32>) eg_intr_md.egress_port;

            if (hop_count == 0) {
                hdr.vartest.hop1_ts_egress = egress_ts;
                hdr.vartest.hop1_egress_port = egress_port;
            } else if (hop_count == 1) {
                hdr.vartest.hop2_ts_egress = egress_ts;
                hdr.vartest.hop2_egress_port = egress_port;
            } else if (hop_count == 2) {
                hdr.vartest.hop3_ts_egress = egress_ts;
                hdr.vartest.hop3_egress_port = egress_port;
            } else if (hop_count == 3) {
                hdr.vartest.hop4_ts_egress = egress_ts;
                hdr.vartest.hop4_egress_port = egress_port;
            }

            // increment hop count
            hdr.vartest.hop_count = hop_count + 1;

            // UDP checksum update for now
            if (hdr.udp.isValid()) {
                hdr.udp.checksum = 0;
            }
        }
    }
}

control SnosEgressDeparser(
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
        packet.emit(hdr.vartest);
    }
}

// -------------------------------------------
// Main Pipeline and Switch Declaration
// -------------------------------------------
Pipeline(SnosIngressParser(),
    SnosIngress(),
    SnosIngressDeparser(),
    SnosEgressParser(),
    SnosEgress(),
    SnosEgressDeparser()) pipe;

Switch(pipe) main;
