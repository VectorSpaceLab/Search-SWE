package sniffing

import (
	"bufio"
	"context"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/go-gost/core/bypass"
	xlogger "github.com/go-gost/x/logger"
	xrecorder "github.com/go-gost/x/recorder"
)

type searchSWEPolicy struct{}
func (*searchSWEPolicy) IsWhitelist() bool { return true }
func (*searchSWEPolicy) Contains(ctx context.Context, network, addr string, opts ...bypass.Option) bool {
	return addr != "allowed.example:443" && addr != "allowed.example:80"
}

type searchSWETransport struct { hosts []string }
func (tr *searchSWETransport) RoundTrip(r *http.Request) (*http.Response, error) {
	tr.hosts = append(tr.hosts, r.Host)
	return &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(strings.NewReader("OK"))}, nil
}

func TestSearchSWEH2PolicyOnEveryStream(t *testing.T) {
	tr := &searchSWETransport{}
	h := &h2Handler{transport: tr, bypass: &searchSWEPolicy{}, service: "test", network: "tcp",
		recorderObject: &xrecorder.HandlerRecorderObject{}, log: xlogger.Nop()}
	for _, host := range []string{"allowed.example", "blocked.example", "allowed.example", "127.0.0.1"} {
		r := httptest.NewRequest("GET", "https://" + host + "/", nil)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		want := 403
		if host == "allowed.example" { want = 200 }
		if w.Code != want { t.Fatalf("host %s: %d, want %d", host, w.Code, want) }
	}
	if strings.Join(tr.hosts, ",") != "allowed.example,allowed.example" { t.Fatal(tr.hosts) }
}

func TestSearchSWEHTTPKeepAliveHostChange(t *testing.T) {
	seen := make(chan string, 4)
	origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen <- r.Host
		w.Header().Set("Content-Length", "2")
		io.WriteString(w, "OK")
	}))
	defer origin.Close()
	client, server := net.Pipe()
	defer client.Close()
	defer server.Close()
	client.SetDeadline(time.Now().Add(5 * time.Second))
	errCh := make(chan error, 1)
	go func() {
		defer server.Close()
		errCh <- (&Sniffer{}).HandleHTTP(context.Background(), "tcp", server,
			WithBypass(&searchSWEPolicy{}), WithLog(xlogger.Nop()),
			WithRecorderObject(&xrecorder.HandlerRecorderObject{}),
			WithDial(func(context.Context, string, string) (net.Conn, error) { return net.Dial("tcp", origin.Listener.Addr().String()) }))
	}()
	io.WriteString(client, "GET / HTTP/1.1\r\nHost: allowed.example\r\n\r\n")
	r, err := http.ReadResponse(bufio.NewReader(client), nil)
	if err != nil { t.Fatal(err) }
	io.Copy(io.Discard, r.Body); r.Body.Close()
	io.WriteString(client, "GET / HTTP/1.1\r\nHost: blocked.example\r\n\r\n")
	if err := <-errCh; err == nil { t.Fatal("host change was accepted") }
	if len(seen) != 1 || <-seen != "allowed.example" { t.Fatal("unexpected upstream request") }
}
