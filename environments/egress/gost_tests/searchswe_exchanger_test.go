package exchanger

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	xlogger "github.com/go-gost/x/logger"
)

func searchSWETLS(server *httptest.Server) *tls.Config {
	pool := x509.NewCertPool()
	pool.AddCert(server.Certificate())
	return &tls.Config{RootCAs: pool}
}

func TestSearchSWEDoHCertificateAndPositiveControl(t *testing.T) {
	var queries atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		queries.Add(1)
		io.Copy(w, r.Body)
	}))
	defer server.Close()
	good, err := NewExchanger(server.URL, TLSConfigOption(searchSWETLS(server)), LoggerOption(xlogger.Nop()))
	if err != nil { t.Fatal(err) }
	if reply, err := good.Exchange(context.Background(), []byte("fixture")); err != nil || string(reply) != "fixture" {
		t.Fatalf("positive control: %q %v", reply, err)
	}
	bad, err := NewExchanger(server.URL, LoggerOption(xlogger.Nop()))
	if err != nil { t.Fatal(err) }
	if _, err := bad.Exchange(context.Background(), []byte("must-not-arrive")); err == nil {
		t.Fatal("untrusted DoH certificate accepted")
	}
	if queries.Load() != 1 { t.Fatal("untrusted TLS origin received a DNS payload") }
}

func TestSearchSWEDoHRedirectNeverReachesOtherOrigin(t *testing.T) {
	var reached atomic.Int32
	forbidden := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		reached.Add(1)
		w.WriteHeader(200)
	}))
	defer forbidden.Close()
	redirect := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, forbidden.URL, http.StatusTemporaryRedirect)
	}))
	defer redirect.Close()
	ex, err := NewExchanger(redirect.URL, TLSConfigOption(searchSWETLS(redirect)), LoggerOption(xlogger.Nop()))
	if err != nil { t.Fatal(err) }
	if _, err := ex.Exchange(context.Background(), []byte("must-not-be-redirected")); err == nil {
		t.Fatal("DoH redirect accepted")
	}
	if reached.Load() != 0 { t.Fatal("redirect destination received the query") }
}
