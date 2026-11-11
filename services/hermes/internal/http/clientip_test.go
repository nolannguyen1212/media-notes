package server

import (
	"net/http/httptest"
	"net/netip"
	"testing"
)

func TestClientIP(t *testing.T) {
	trusted := []netip.Prefix{netip.MustParsePrefix("10.42.0.0/16")}

	tests := []struct {
		name       string
		remoteAddr string
		forwarded  []string
		trusted    []netip.Prefix
		want       string
	}{
		{"no trusted proxies uses peer", "10.42.0.181:5000", []string{"203.0.113.9"}, nil, "10.42.0.181"},
		{"untrusted peer ignores header", "198.51.100.7:5000", []string{"203.0.113.9"}, trusted, "198.51.100.7"},
		{"trusted peer uses forwarded client", "10.42.0.181:5000", []string{"203.0.113.9"}, trusted, "203.0.113.9"},
		{"spoofed leftmost hop is ignored", "10.42.0.181:5000", []string{"1.2.3.4, 203.0.113.9"}, trusted, "203.0.113.9"},
		{"trusted hops are skipped", "10.42.0.181:5000", []string{"203.0.113.9, 10.42.0.1"}, trusted, "203.0.113.9"},
		{"multiple header lines", "10.42.0.181:5000", []string{"1.2.3.4", "203.0.113.9"}, trusted, "203.0.113.9"},
		{"missing header falls back to peer", "10.42.0.181:5000", nil, trusted, "10.42.0.181"},
		{"malformed header falls back to peer", "10.42.0.181:5000", []string{"not-an-ip"}, trusted, "10.42.0.181"},
		{"ipv6 client", "10.42.0.181:5000", []string{"2001:db8::1"}, trusted, "2001:db8::1"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("POST", "/graphql", nil)
			req.RemoteAddr = tt.remoteAddr
			for _, v := range tt.forwarded {
				req.Header.Add("X-Forwarded-For", v)
			}
			if got := clientIP(req, tt.trusted); got != tt.want {
				t.Fatalf("clientIP() = %q, want %q", got, tt.want)
			}
		})
	}
}
