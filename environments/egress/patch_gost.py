"""Exact, fail-closed source transformations for go-gost/x v0.10.9 only.

Invoked by the reproducible build, never applied to system-installed Harbor.
Each replacement must match once; upstream drift aborts the build.
"""

from pathlib import Path
import sys


def replace(root, name, before, after):
    path = root / name
    text = path.read_text()
    if text.count(before) != 1:
        raise RuntimeError(f"Pinned GOST source mismatch: {name}")
    path.write_text(text.replace(before, after))


def apply(root):
    # Check every H2 stream, including pooled-connection requests, before
    # constructing or forwarding an upstream request.
    name = "internal/util/sniffing/sniffer_h2.go"
    replace(root, name, '\t"github.com/go-gost/core/logger"',
            '\t"github.com/go-gost/core/bypass"\n\t"github.com/go-gost/core/logger"')
    replace(root, name, "\t\t\ttransport:       tr,", "\t\t\ttransport:       tr,\n\t\t\tbypass: ho.bypass,\n\t\t\tservice: ho.service,\n\t\t\tnetwork: network,")
    replace(root, name, "type h2Handler struct {", "type h2Handler struct {\n\tbypass bypass.Bypass\n\tservice string\n\tnetwork string")
    replace(root, name, "func (h *h2Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {", """func (h *h2Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if h.bypass != nil && h.bypass.Contains(r.Context(), h.network, normalizeHost(r.Host, "443"), bypass.WithService(h.service)) {
		w.WriteHeader(http.StatusForbidden)
		return
	}""")

    # Defense in depth: every red-handler dial checks the FINAL hostname:port,
    # not just whichever protocol-specific sniffer dispatched to it.
    replace(root, "handler/redirect/tcp/handler.go", """				ro.Host = address

				var buf bytes.Buffer""", """				ro.Host = address
				if h.options.Bypass != nil && h.options.Bypass.Contains(ctx, network, address, bypass.WithService(h.options.Service)) {
					return nil, xbypass.ErrBypass
				}

				var buf bytes.Buffer""")

    # Transparent HTTP/1 keep-alive is bound to the initial origin. Do not
    # forward a changed Host on its socket (even when both names are allowed).
    replace(root, "internal/util/sniffing/sniffer_http.go", """		if shouldClose, err := h.httpRoundTrip(ctx, xio.NewReadWriteCloser(br, conn, conn), cc, req, readTimeout, ro, &pStats, log); err != nil || shouldClose {""", """		nextHost := normalizeHost(req.Host, "80")
		if nextHost != host || (ho.bypass != nil && ho.bypass.Contains(ctx, network, nextHost, bypass.WithService(ho.service))) {
			return xbypass.ErrBypass
		}
		if shouldClose, err := h.httpRoundTrip(ctx, xio.NewReadWriteCloser(br, conn, conn), cc, req, readTimeout, ro, &pStats, log); err != nil || shouldClose {""")

    # A configured DNS policy must not be skipped for non-IN questions. Reject
    # unsupported messages outright rather than handing arbitrary DNS payloads
    # to a trusted DoH resolver. Normal unfiltered GOST DNS use is unchanged.
    replace(root, "handler/dns/handler.go", """	if h.options.Bypass != nil && mq.Question[0].Qclass == dns.ClassINET {""", """	if h.options.Bypass != nil {
		unsupported := len(mq.Question) != 1 || mq.Response || mq.Opcode != dns.OpcodeQuery || mq.Question[0].Qclass != dns.ClassINET
		unsupported = unsupported || (mq.Question[0].Qtype != dns.TypeA && mq.Question[0].Qtype != dns.TypeAAAA) || len(mq.Answer) != 0 || len(mq.Ns) != 0 || len(mq.Extra) > 1
		if !unsupported && len(mq.Extra) == 1 {
			opt, ok := mq.Extra[0].(*dns.OPT)
			unsupported = !ok || opt.Hdr.Name != "." || opt.Version() != 0 || len(opt.Option) != 0
		}
		if unsupported {
			mr = (&dns.Msg{}).SetRcode(&mq, dns.RcodeRefused)
			return h.packResponse(mr)
		}""")

    # The resolver is privileged infrastructure, not an arbitrary HTTP grant.
    # A redirect must not forward its DNS payload to another destination.
    replace(root, "resolver/exchanger/exchanger.go", """		ex.client = &http.Client{
			Timeout: options.timeout,""", """		ex.client = &http.Client{
			CheckRedirect: func(req *http.Request, via []*http.Request) error { return http.ErrUseLastResponse },
			Timeout: options.timeout,""")


if __name__ == "__main__":
    apply(Path(sys.argv[1]))
