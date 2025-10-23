#include <linux/ip.h>
#include <linux/udp.h>
#include <asm/unaligned.h>

int mqnic_pull_seq_from_udp(struct sk_buff *skb, u32 *seq_out)
{
    // Ensure we have network + transport headers
    if (skb->protocol == htons(ETH_P_IP)) {
        if (!pskb_may_pull(skb, sizeof(struct iphdr))) {
            return -EINVAL;
        }

        if (ip_hdr(skb)->protocol != IPPROTO_UDP) {
            return -EPROTO;
        }
    } else {
        return -EPROTO;
    }

    int off = skb_transport_offset(skb) + sizeof(struct udphdr);
    __be32 be_seq;
    const __be32 *p = skb_header_pointer(skb, off, sizeof(be_seq), &be_seq);
    if (!p) return -EINVAL;

    *seq_out = be32_to_cpu(*p);
    return 0;
}
