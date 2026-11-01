// Offline transport fixture. CONNECT targets never select arbitrary sockets:
// approved fixture names map only to fixed loopback listeners in this container.
package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

var output sync.Mutex
var eventFile string

func event(fields map[string]any) {
	output.Lock()
	defer output.Unlock()
	if eventFile != "" {
		data, _ := json.Marshal(fields)
		file, err := os.OpenFile(eventFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
		if err != nil {
			panic(err)
		}
		defer file.Close()
		if _, err := file.Write(append(data, '\n')); err != nil {
			panic(err)
		}
		return
	}
	_ = json.NewEncoder(os.Stdout).Encode(fields)
}

type settings struct {
	Username  string `json:"username"`
	Password  string `json:"password"`
	Cert      string `json:"cert"`
	Key       string `json:"key"`
	DohCert   string `json:"doh_cert"`
	DohKey    string `json:"doh_key"`
	Events    string `json:"events"`
	DirectAPI bool   `json:"direct_api"`
}

type observedListener struct {
	net.Listener
	port string
}

func (listener observedListener) Accept() (net.Conn, error) {
	conn, err := listener.Listener.Accept()
	if err == nil {
		event(map[string]any{"kind": "tcp_accept", "port": listener.port})
	}
	return conn, err
}

func dnsReply(query []byte, address, ipv6 net.IP) ([]byte, string, uint16, error) {
	if len(query) < 17 || binary.BigEndian.Uint16(query[4:6]) != 1 {
		return nil, "", 0, fmt.Errorf("invalid fixture question")
	}
	labels, pos := []string{}, 12
	for pos < len(query) && query[pos] != 0 {
		n := int(query[pos])
		pos++
		if n > 63 || pos+n >= len(query) {
			return nil, "", 0, fmt.Errorf("invalid fixture label")
		}
		labels = append(labels, string(query[pos:pos+n]))
		pos += n
	}
	if pos+5 > len(query) {
		return nil, "", 0, fmt.Errorf("short fixture question")
	}
	typ := binary.BigEndian.Uint16(query[pos+1 : pos+3])
	name := strings.Join(labels, ".")
	response := append([]byte(nil), query[:pos+5]...)
	binary.BigEndian.PutUint16(response[2:4], 0x8180)
	for i := 6; i < 12; i++ {
		response[i] = 0
	}
	if name == "nx.example" {
		response[3] |= 3
		return response, name, typ, nil
	}
	var data []byte
	if typ == 1 {
		data = address.To4()
	} else if typ == 28 {
		data = ipv6.To16()
	}
	if data != nil {
		response[7] = 1
		owner := []byte{0xc0, 0x0c}
		if name == "alias.example" {
			canonical := []byte("\x07allowed\x07example\x00")
			response[7] = 2
			response = append(response, 0xc0, 0x0c, 0, 5, 0, 1, 0, 0, 0, 1, 0, byte(len(canonical)))
			response = append(response, canonical...)
			owner = canonical
		}
		response = append(response, owner...)
		response = append(response, 0, byte(typ), 0, 1, 0, 0, 0, 1, 0, byte(len(data)))
		response = append(response, data...)
	}
	return response, name, typ, nil
}

func serve(path, role string) {
	data, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	var cfg settings
	if err := json.Unmarshal(data, &cfg); err != nil {
		panic(err)
	}
	eventFile = cfg.Events
	if err := os.WriteFile("/tmp/fixture-"+role+".pid", []byte(fmt.Sprint(os.Getpid())), 0600); err != nil {
		panic(err)
	}
	addresses, err := net.InterfaceAddrs()
	if err != nil {
		panic(err)
	}
	var address net.IP
	for _, item := range addresses {
		ip := item.(*net.IPNet).IP
		if ip.To4() != nil && !ip.IsLoopback() {
			address = ip
		}
	}
	quiet := log.New(io.Discard, "", 0)
	apiHandler := func(kind string) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			event(map[string]any{"kind": kind, "host": r.Host, "path": r.URL.Path, "protocol": r.Proto})
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		}
	}
	api := &http.Server{Addr: "127.0.0.1:19443", ErrorLog: quiet, Handler: apiHandler("api")}
	doh := &http.Server{Addr: "127.0.0.1:18443", ErrorLog: quiet, Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		query, _ := io.ReadAll(io.LimitReader(r.Body, 65536))
		_, pollution := os.Stat("/tmp/pollute")
		answer := append(net.IP(nil), address...)
		if pollution == nil {
			answer[len(answer)-1] = 254 // unused, same internal subnet; never an external address
		}
		ipv6 := net.ParseIP("2001:db8::1")
		_, pollution6 := os.Stat("/tmp/pollute6")
		if pollution6 == nil {
			ipv6 = net.ParseIP("2001:db8::bad")
		}
		reply, name, typ, err := dnsReply(query, answer, ipv6)
		if err != nil {
			http.Error(w, "invalid fixture query", 400)
			return
		}
		event(map[string]any{"kind": "dns", "name": name, "type": typ, "polluted": pollution == nil,
			"polluted_aaaa": pollution6 == nil, "aaaa": ipv6.String()})
		if name == "redirect.example" {
			http.Redirect(w, r, "https://blocked.example/dns-query", 307)
			return
		}
		if name == "timeout.example" {
			time.Sleep(12 * time.Second)
			return
		}
		w.Header().Set("Content-Type", "application/dns-message")
		_, _ = w.Write(reply)
	})}
	proxy := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		expected := "Basic " + base64.StdEncoding.EncodeToString([]byte(cfg.Username+":"+cfg.Password))
		ok := r.Header.Get("Proxy-Authorization") == expected
		event(map[string]any{"kind": "proxy", "target": r.Host, "auth_ok": ok})
		if !ok || r.Method != "CONNECT" {
			w.Header().Set("Proxy-Authenticate", `Basic realm="fixture"`)
			w.WriteHeader(407)
			return
		}
		target := map[string]string{"allowed.example:443": "127.0.0.1:19443", "allowed.example:8443": "127.0.0.1:19443", "allowed.example:9443": "127.0.0.1:19443", "resolver.example:443": "127.0.0.1:18443",
			"wrong-resolver.example:443": "127.0.0.1:18443"}[r.Host]
		if target == "" {
			w.WriteHeader(403)
			return
		}
		upstream, err := net.DialTimeout("tcp", target, time.Second)
		if err != nil {
			http.Error(w, "fixture unavailable", 503)
			return
		}
		defer upstream.Close()
		client, buffered, err := w.(http.Hijacker).Hijack()
		if err != nil {
			return
		}
		defer client.Close()
		_, _ = buffered.WriteString("HTTP/1.1 200 Connection established\r\n\r\n")
		_ = buffered.Flush()
		done := make(chan struct{})
		go func() { _, _ = io.Copy(upstream, buffered); _ = upstream.Close(); close(done) }()
		_, _ = io.Copy(client, upstream)
		_ = client.Close()
		<-done
	})
	type endpoint struct {
		server *http.Server
		secure bool
		role   string
	}
	endpoints := []endpoint{{api, true, "api"}, {doh, true, "doh"}, {&http.Server{Addr: ":18080", Handler: proxy, ErrorLog: quiet}, false, "proxy"},
		{&http.Server{Addr: ":18480", Handler: proxy, ErrorLog: quiet}, true, "proxy"}}
	if cfg.DirectAPI {
		endpoints = append(endpoints, endpoint{&http.Server{Addr: ":9443", Handler: apiHandler("api-direct"), ErrorLog: quiet}, true, "api"})
	}
	for _, item := range endpoints {
		if role != "all" && role != item.role {
			continue
		}
		listener, err := net.Listen("tcp", item.server.Addr)
		if err != nil {
			panic(err)
		}
		_, port, _ := net.SplitHostPort(item.server.Addr)
		listener = observedListener{Listener: listener, port: port}
		go func(server *http.Server, listener net.Listener, secure bool) {
			if secure {
				cert, key := cfg.Cert, cfg.Key
				if server == doh && cfg.DohCert != "" {
					cert, key = cfg.DohCert, cfg.DohKey
				}
				_ = server.ServeTLS(listener, cert, key)
			} else {
				_ = server.Serve(listener)
			}
		}(item.server, listener, item.secure)
	}
	event(map[string]any{"kind": "ready", "role": role, "pid": os.Getpid()})
	select {}
}

func client(mode, destination, ca string) error {
	pem, err := os.ReadFile(ca)
	if err != nil {
		return err
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(pem) {
		return fmt.Errorf("invalid fixture CA")
	}
	transport := &http.Transport{TLSClientConfig: &tls.Config{RootCAs: pool}, ForceAttemptHTTP2: mode != "held-h1"}
	port, authority := "443", "allowed.example"
	if mode == "get-alt-port" {
		port, authority = "8443", "allowed.example:8443"
	}
	if mode == "get-fallback" {
		port, authority = "9443", "allowed.example:9443"
	}
	if mode == "get-ip6" {
		transport.DialContext = func(ctx context.Context, _, address string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "tcp6", address)
		}
	}
	if destination != "-" {
		transport.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "tcp", net.JoinHostPort(destination, port))
		}
	}
	defer transport.CloseIdleConnections()
	c := &http.Client{Transport: transport, Timeout: 5 * time.Second}
	get := func(path string) error {
		r, err := c.Get("https://" + authority + path)
		if err != nil {
			return err
		}
		defer r.Body.Close()
		body, err := io.ReadAll(r.Body)
		if err != nil || r.StatusCode != 200 || string(body) != `{"ok":true}` {
			return fmt.Errorf("invalid fixture API response")
		}
		event(map[string]any{"kind": "response", "protocol": r.Proto, "path": path})
		return nil
	}
	if err := get("/before"); err != nil {
		return err
	}
	if strings.HasPrefix(mode, "held-") {
		event(map[string]any{"kind": "ready"})
		deadline := time.Now().Add(time.Minute)
		for time.Now().Before(deadline) {
			if _, err := os.Stat("/tmp/release"); err == nil {
				_ = get("/after") // Only the origin log decides revocation success.
				return nil
			}
			time.Sleep(50 * time.Millisecond)
		}
		return fmt.Errorf("fixture release timeout")
	}
	return nil
}

func main() {
	if strings.HasPrefix(os.Args[1], "delayed-") {
		os.Args[1] = strings.TrimPrefix(os.Args[1], "delayed-")
		event(map[string]any{"kind": "started"})
		deadline := time.Now().Add(time.Minute)
		for {
			if _, err := os.Stat("/tmp/begin"); err == nil {
				break
			}
			if time.Now().After(deadline) {
				panic("fixture start timeout")
			}
			time.Sleep(50 * time.Millisecond)
		}
	}
	if os.Args[1] == "serve" {
		serve(os.Args[2], "all")
		return
	}
	if strings.HasPrefix(os.Args[1], "serve-") {
		serve(os.Args[2], strings.TrimPrefix(os.Args[1], "serve-"))
		return
	}
	if strings.HasPrefix(os.Args[1], "dns-") {
		parts := strings.Split(os.Args[1], "-")
		resolver := &net.Resolver{PreferGo: true, StrictErrors: true, Dial: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, parts[1], os.Args[2])
		}}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		addresses, err := resolver.LookupIP(ctx, parts[2], os.Args[3]+".")
		event(map[string]any{"kind": "resolved", "ok": err == nil && len(addresses) > 0, "addresses": addresses})
		return
	}
	if os.Args[1] == "resolve" {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_, err := net.DefaultResolver.LookupIPAddr(ctx, os.Args[2])
		event(map[string]any{"kind": "resolved", "ok": err == nil})
		return
	}
	if err := client(os.Args[1], os.Args[2], os.Args[3]); err != nil {
		event(map[string]any{"kind": "client_error", "error": err.Error()})
		os.Exit(1)
	}
}
