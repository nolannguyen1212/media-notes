package server

import (
	"math"
	"net"
	"net/http"
	"strconv"

	"github.com/nolannguyen1212/media-notes/services/hermes/internal/limits"
)

// corsMiddleware sets the headers needed for a cross-origin browser
// client (web, on its own domain) to call /graphql directly, and
// short-circuits OPTIONS preflight requests with a bare 204. No
// Access-Control-Allow-Credentials: auth is a Bearer token sent via the
// Authorization header (see internal/auth), never a cookie, so there's
// no cookie-domain/SameSite problem to solve. A blank allowedOrigin
// disables header injection entirely (same-origin deployments, e.g. the
// local dev proxy, need none of this).
func corsMiddleware(allowedOrigin string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		if allowedOrigin == "" {
			return next
		}
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Access-Control-Allow-Origin", allowedOrigin)
			w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
			w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// clientIPMiddleware attaches the caller's IP to the request context, for
// rate-limit keys on pre-authentication operations that have no user id
// yet (register, login).
func clientIPMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		next.ServeHTTP(w, r.WithContext(limits.ContextWithClientIP(r.Context(), clientIP(r))))
	})
}

func clientIP(r *http.Request) string {
	if host, _, err := net.SplitHostPort(r.RemoteAddr); err == nil {
		return host
	}
	return r.RemoteAddr
}

// rateLimitSignalMiddleware attaches a limits.Signal to the request
// context and wraps the ResponseWriter so that, if a resolver denies the
// request (limits.MarkRateLimited), the first byte gqlgen writes carries
// a true 429 status and Retry-After header (ADR 0004) instead of
// GraphQL's usual 200-with-errors. gqlgen's resolver execution is
// decoupled from its transport, so this is the only point that sees both
// the resolver's denial and the raw ResponseWriter.
func rateLimitSignalMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx, signal := limits.ContextWithSignal(r.Context())
		sw := &signalWriter{ResponseWriter: w, signal: signal}
		next.ServeHTTP(sw, r.WithContext(ctx))
	})
}

type signalWriter struct {
	http.ResponseWriter
	signal      *limits.Signal
	wroteHeader bool
}

func (w *signalWriter) WriteHeader(status int) {
	if w.wroteHeader {
		return
	}
	w.wroteHeader = true
	if w.applySignal() {
		return // the signal already forced 429; don't also send the caller's status.
	}
	w.ResponseWriter.WriteHeader(status)
}

func (w *signalWriter) Write(b []byte) (int, error) {
	if !w.wroteHeader {
		w.wroteHeader = true
		w.applySignal()
	}
	return w.ResponseWriter.Write(b)
}

// applySignal sets Retry-After and forces a 429 status if a resolver
// denied the request, reporting whether it did. It must run before any
// header is flushed, i.e. only from within WriteHeader/Write, and only
// once per response.
func (w *signalWriter) applySignal() bool {
	hit, retryAfter := w.signal.Hit()
	if !hit {
		return false
	}
	seconds := int(math.Ceil(retryAfter.Seconds()))
	if seconds < 1 {
		seconds = 1
	}
	w.Header().Set("Retry-After", strconv.Itoa(seconds))
	w.ResponseWriter.WriteHeader(http.StatusTooManyRequests)
	return true
}
