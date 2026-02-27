// Timestamp experiment pipeline (minimal, P4_16)
// - Ingress stamps ingress MAC/global timestamps into a custom ts header
// - A forward table maps exp_id -> (egress_port, qid)
// - Egress stamps egress global timestamp

#include <core.p4>
#if __TARGET_TOFINO__ == 2
#include <t2na.p4>
#else
#include <tna.p4>
#endif

#include "include/headers.p4"
#include "include/util.p4"

#define ETHERTYPE_IPV4 0x0800
#define IP_PROTOCOL_UDP 17
#define IP_PROTOCOL_TCP 6
#define EXP_UDP_PORT 17777  // UDP dst port for experiment packets

// Custom timestamp header for experiments
// Choose 64-bit for robustness (platform timestamps are often >=48 bits)
typedef bit<64> ts64_t;
typedef bit<16> port_t;

header ts_h {
    bit<16> exp_id;             // experiment id / pattern id
    bit<32> seq;               // sequence number assigned by generator
    ts64_t  ingress_mac_ts;     // ingress MAC timestamp (hardware)
    ts64_t  ingress_global_ts;  // ingress global timestamp (parser stage)
    ts64_t  egress_global_ts;   // egress global timestamp
    port_t ingress_port;       // ingress port id
    port_t egress_port;        // egress port id
}

// Packet headers aggregation
struct header_t {
    ethernet_h ethernet;
    ipv4_h     ipv4;
    udp_h      udp;
    tcp_h      tcp;
    ts_h       ts;
}

// User metadata
struct metadata_t {
    pktgen_timer_header_t pktgen_timer_hdr; // Pktgen timer header
}

// ---------------------------
// Ingress Parser
// ---------------------------
parser IngressParser(
    packet_in pkt,
    out header_t hdr,
    out metadata_t ig_md,
    out ingress_intrinsic_metadata_t ig_intr_md
) {
    TofinoIngressParser() tofino_parser;

    state start {
        tofino_parser.apply(pkt, ig_intr_md);

        transition select(ig_intr_md.ingress_port) {
            6: parse_pktgen; // Port 6 is pktgen port
            68: parse_pktgen; // Port 68 is pktgen port (DHCP)
            default: parse_ethernet;
        }
    }

    state parse_pktgen {
        pkt.extract(ig_md.pktgen_timer_hdr);
        transition parse_ethernet;
    }

    state parse_ethernet {
        pkt.extract(hdr.ethernet);
        transition select(hdr.ethernet.ether_type) {
            ETHERTYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    state parse_ipv4 {
        pkt.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            IP_PROTOCOL_UDP: parse_udp;
            IP_PROTOCOL_TCP: parse_tcp;
            default: accept;
        }
    }

    state parse_udp {
        pkt.extract(hdr.udp);
        // Only extract ts header when UDP dst_port matches experiment port
        transition select(hdr.udp.dst_port) {
            EXP_UDP_PORT: parse_ts; // EXP_UDP_PORT (control-plane should use this)
            default: accept;
        }
    }

    state parse_tcp {
        pkt.extract(hdr.tcp);
        transition accept;
    }

    state parse_ts {
        pkt.extract(hdr.ts);
        transition accept;
    }
}

// ---------------------------
// Ingress Control
// ---------------------------
control Ingress(
    inout header_t hdr,
    inout metadata_t ig_md,
    in ingress_intrinsic_metadata_t ig_intr_md,
    in ingress_intrinsic_metadata_from_parser_t ig_intr_prsr_md,
    inout ingress_intrinsic_metadata_for_deparser_t ig_intr_dprsr_md,
    inout ingress_intrinsic_metadata_for_tm_t ig_intr_tm_md
) {

    DirectCounter<bit<32>>(CounterType_t.PACKETS) hit_counter;

    action drop() {
        ig_intr_dprsr_md.drop_ctl = 0x1;
    }

    // Set egress port based on ingress port and increment hit counter
    action set_port(bit<9> egress_port) {
        ig_intr_tm_md.ucast_egress_port = egress_port;
        // Increment hit counter register
        hit_counter.count();
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
        counters = hit_counter;
    }

    /*
    // Table: forward background traffic based on app_id
    DirectCounter<bit<32>>(CounterType_t.PACKETS) forward_bg_hit_counter;
    
    action mark_bg() {
        // Increment hit counter register
        forward_bg_hit_counter.count();
    }

    action set_bg_port(bit<9> egress_port) {
        ig_intr_tm_md.ucast_egress_port = egress_port;
        // Increment hit counter register
        forward_bg_hit_counter.count();
    }

    table bg_forward {
        key = {
            ig_md.pktgen_timer_hdr.app_id: exact@name("app_id");
        }
        actions = {
            mark_bg;
            set_bg_port;
            @defaultonly drop;
        }
        size = 256;
        counters = forward_bg_hit_counter;
    }
    */

    apply {
        pass_through.apply();

        // Stamp ingress timestamps if headers are valid
        if (hdr.ts.isValid()) {
            hdr.ts.ingress_port = (port_t)ig_intr_md.ingress_port;
            hdr.ts.egress_port = (port_t)ig_intr_tm_md.ucast_egress_port;
            hdr.ts.ingress_mac_ts = (ts64_t) ig_intr_md.ingress_mac_tstamp;
            hdr.ts.ingress_global_ts = (ts64_t) ig_intr_prsr_md.global_tstamp;

            // UDP checksum update for now
            hdr.udp.checksum = 0;
        }

        // Default queue id 0 before table decides
        ig_intr_tm_md.qid = 0;
    }
}

// ---------------------------
// Ingress Deparser
// ---------------------------
control IngressDeparser(
    packet_out pkt,
    inout header_t hdr,
    in metadata_t ig_md,
    in ingress_intrinsic_metadata_for_deparser_t ig_intr_dprsr_md
) {
    apply {
        pkt.emit(hdr.ethernet);
        pkt.emit(hdr.ipv4);
        pkt.emit(hdr.udp);
        pkt.emit(hdr.ts);
    }
}

// ---------------------------
// Egress Parser
// ---------------------------
parser EgressParser(
    packet_in pkt,
    out header_t hdr,
    out metadata_t eg_md,
    out egress_intrinsic_metadata_t eg_intr_md
) {
    TofinoEgressParser() tofino_parser;

    state start {
        tofino_parser.apply(pkt, eg_intr_md);
        transition parse_ethernet;
    }

    state parse_ethernet {
        pkt.extract(hdr.ethernet);
        transition select(hdr.ethernet.ether_type) {
              ETHERTYPE_IPV4: parse_ipv4;
              default: accept;
        }

    }

    state parse_ipv4 {
        pkt.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            IP_PROTOCOL_UDP: parse_udp;
            IP_PROTOCOL_TCP: parse_tcp;
            default: accept;
        }
    }

    state parse_udp {
        pkt.extract(hdr.udp);
        transition select(hdr.udp.dst_port) {
            EXP_UDP_PORT: parse_ts; // EXP_UDP_PORT (control-plane should use this)
            default: accept;
        }
    }

    state parse_tcp {
        pkt.extract(hdr.tcp);
        transition accept;
    }

    state parse_ts {
        pkt.extract(hdr.ts);
        transition accept;
    }
}

// ---------------------------
// Egress Control
// ---------------------------
control Egress(
    inout header_t hdr,
    inout metadata_t eg_md,
    in egress_intrinsic_metadata_t eg_intr_md,
    in egress_intrinsic_metadata_from_parser_t eg_intr_from_prsr,
    inout egress_intrinsic_metadata_for_deparser_t eg_intr_md_for_dprsr,
    inout egress_intrinsic_metadata_for_output_port_t eg_intr_md_for_oport
) {
    apply {
        if (hdr.ts.isValid()) {
            hdr.ts.egress_port = (port_t)eg_intr_md.egress_port;
            hdr.ts.egress_global_ts = (ts64_t) eg_intr_from_prsr.global_tstamp;

            // UDP checksum update for now
            hdr.udp.checksum = 0;
        }
    }
}

// ---------------------------
// Egress Deparser
// ---------------------------
control EgressDeparser(
    packet_out pkt,
    inout header_t hdr,
    in metadata_t eg_md,
    in egress_intrinsic_metadata_for_deparser_t eg_intr_dprsr_md
) {
    apply {
        pkt.emit(hdr.ethernet);
        pkt.emit(hdr.ipv4);
        pkt.emit(hdr.udp);
        pkt.emit(hdr.ts);
    }
}

Pipeline(IngressParser(),
         Ingress(),
         IngressDeparser(),
         EgressParser(),
         Egress(),
         EgressDeparser()) pipe;

Switch(pipe) main;
