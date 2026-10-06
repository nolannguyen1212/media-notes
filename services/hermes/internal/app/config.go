// Package app holds hermes's process-level concerns: configuration,
// logging, and health state.
package app

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// Config is hermes's runtime configuration, loaded from the environment.
// hermes owns no database; every field either addresses a downstream gRPC
// service or tunes a stateless request boundary (ADR 0004).
type Config struct {
	HTTPAddr string

	IdentityGRPCAddr string
	BillingGRPCAddr  string
	MediaGRPCAddr    string
	ContentGRPCAddr  string

	RedisAddr     string
	RedisPassword string
	RedisDB       int

	// SessionCookieName is the fallback session-token source when a
	// request carries no Authorization: Bearer header — see
	// internal/auth.
	SessionCookieName string

	// CORSAllowedOrigin is the single origin allowed to call /graphql
	// cross-origin (web, served from its own domain). Empty disables
	// CORS header injection entirely — a same-origin deployment (the
	// local dev proxy) needs no CORS headers at all.
	CORSAllowedOrigin string

	// GraphQLBodyLimitBytes bounds request body size, per ADR 0004 (1 MiB).
	GraphQLBodyLimitBytes int64

	// DownstreamTimeout bounds every outbound gRPC call hermes makes,
	// always set below the remaining request deadline it received.
	DownstreamTimeout time.Duration

	ShutdownTimeout time.Duration
	LogLevel        string
}

// LoadConfig reads Config from the environment, applying defaults for
// every field.
func LoadConfig() (Config, error) {
	cfg := Config{
		HTTPAddr: getEnv("HERMES_HTTP_ADDR", ":8086"),

		IdentityGRPCAddr: getEnv("HERMES_IDENTITY_GRPC_ADDR", "localhost:9091"),
		BillingGRPCAddr:  getEnv("HERMES_BILLING_GRPC_ADDR", "localhost:9093"),
		MediaGRPCAddr:    getEnv("HERMES_MEDIA_GRPC_ADDR", "localhost:19095"),
		ContentGRPCAddr:  getEnv("HERMES_CONTENT_GRPC_ADDR", "localhost:9095"),

		RedisAddr:     getEnv("REDIS_ADDR", "localhost:6379"),
		RedisPassword: os.Getenv("REDIS_PASSWORD"),
		RedisDB:       0,

		SessionCookieName: getEnv("HERMES_SESSION_COOKIE_NAME", "mn_session"),
		CORSAllowedOrigin: os.Getenv("HERMES_CORS_ALLOWED_ORIGIN"),

		GraphQLBodyLimitBytes: 1_048_576,
		DownstreamTimeout:     5 * time.Second,

		ShutdownTimeout: 10 * time.Second,
		LogLevel:        getEnv("LOG_LEVEL", "info"),
	}

	if v := os.Getenv("HERMES_GRAPHQL_BODY_LIMIT_BYTES"); v != "" {
		n, err := strconv.ParseInt(v, 10, 64)
		if err != nil {
			return Config{}, fmt.Errorf("HERMES_GRAPHQL_BODY_LIMIT_BYTES: %w", err)
		}
		cfg.GraphQLBodyLimitBytes = n
	}

	if v := os.Getenv("HERMES_DOWNSTREAM_TIMEOUT"); v != "" {
		timeout, err := time.ParseDuration(v)
		if err != nil {
			return Config{}, fmt.Errorf("HERMES_DOWNSTREAM_TIMEOUT: %w", err)
		}
		cfg.DownstreamTimeout = timeout
	}

	if v := os.Getenv("HERMES_SHUTDOWN_TIMEOUT"); v != "" {
		timeout, err := time.ParseDuration(v)
		if err != nil {
			return Config{}, fmt.Errorf("HERMES_SHUTDOWN_TIMEOUT: %w", err)
		}
		cfg.ShutdownTimeout = timeout
	}

	return cfg, nil
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
