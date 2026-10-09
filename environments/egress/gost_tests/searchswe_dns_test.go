package dns

import (
	"context"
	"testing"

	"github.com/go-gost/core/chain"
	"github.com/go-gost/core/handler"
	"github.com/go-gost/core/hop"
	"github.com/go-gost/x/resolver/exchanger"
	"github.com/miekg/dns"
)

func TestSearchSWEDNSUnsupportedClassRefused(t *testing.T) {
	h := newInitdHandler(handler.BypassOption(&mockBypass{whitelist: true}))
	for _, class := range []uint16{dns.ClassCHAOS, dns.ClassHESIOD, dns.ClassANY} {
		q := new(dns.Msg).SetQuestion("blocked.example.", dns.TypeA)
		q.Question[0].Qclass = class
		wire, _ := q.Pack()
		response, err := h.request(context.Background(), wire, newRecObj(), nopLog())
		if err != nil { t.Fatal(err) }
		r := new(dns.Msg)
		if err := r.Unpack(response); err != nil { t.Fatal(err) }
		if r.Rcode != dns.RcodeRefused { t.Fatalf("class %d: rcode %d", class, r.Rcode) }
	}
}

func TestSearchSWEDNSNonAddressPayloadRefused(t *testing.T) {
	for _, kind := range []string{"TXT", "answer", "authority", "extra", "edns-payload"} {
		t.Run(kind, func(t *testing.T) {
			reached := 0
			h := newInitdHandler(handler.BypassOption(&mockBypass{whitelist: true}))
			h.hop = &mockHop{selectFn: func(context.Context, ...hop.SelectOption) *chain.Node { return &chain.Node{Name: "fixture"} }}
			h.exchangers = map[string]exchanger.Exchanger{"fixture": &mockExchanger{exchangeFn: func(ctx context.Context, wire []byte) ([]byte, error) {
				reached++
				q := new(dns.Msg)
				if err := q.Unpack(wire); err != nil { return nil, err }
				return new(dns.Msg).SetReply(q).Pack()
			}}}
			// A real exchanger positive, not just an expected client error.
			for _, typ := range []uint16{dns.TypeA, dns.TypeAAAA} {
				if _, err := h.request(context.Background(), packDNSQuery("control.example.", typ), newRecObj(), nopLog()); err != nil { t.Fatal(err) }
			}
			if reached != 2 { t.Fatal("missing A/AAAA positive controls") }
			plainEDNS := new(dns.Msg).SetQuestion("edns.example.", dns.TypeA).SetEdns0(1232, false)
			ednsWire, _ := plainEDNS.Pack()
			if _, err := h.request(context.Background(), ednsWire, newRecObj(), nopLog()); err != nil { t.Fatal(err) }
			if reached != 3 { t.Fatal("empty EDNS positive control failed") }
			q := new(dns.Msg).SetQuestion("allowed.example.", dns.TypeA)
			rr := mustNewRR("blocked.example. 60 IN TXT \"must-not-reach-resolver\"")
			switch kind {
			case "TXT": q.Question[0].Qtype = dns.TypeTXT
			case "answer": q.Answer = []dns.RR{rr}
			case "authority": q.Ns = []dns.RR{rr}
			case "extra": q.Extra = []dns.RR{rr}
			case "edns-payload":
				q.SetEdns0(1232, false)
				q.IsEdns0().Option = append(q.IsEdns0().Option, &dns.EDNS0_LOCAL{Code: 65001, Data: []byte("must-not-reach-resolver")})
			}
			wire, _ := q.Pack()
			response, err := h.request(context.Background(), wire, newRecObj(), nopLog())
			if err != nil { t.Fatal(err) }
			r := new(dns.Msg)
			if err := r.Unpack(response); err != nil { t.Fatal(err) }
			if reached != 3 { t.Fatalf("unsupported payload reached resolver (%d exchanges)", reached) }
			if r.Rcode != dns.RcodeRefused { t.Fatalf("rcode %d", r.Rcode) }
		})
	}
}
