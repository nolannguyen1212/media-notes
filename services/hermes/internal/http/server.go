// Package server assembles hermes's HTTP surface: the GraphQL endpoint
// and health checks, and the middleware chain in front of them
// (docs/services/hermes.md's control flow: HTTP -> body/auth/rate
// middleware -> resolver). Named "server", not "http", so callers don't
// have to alias every net/http import.
package server

import (
	"log/slog"
	"net/http"

	gqlhandler "github.com/99designs/gqlgen/graphql/handler"
	"github.com/99designs/gqlgen/graphql/playground"

	"github.com/nolannguyen1212/media-notes/services/hermes/internal/app"
	"github.com/nolannguyen1212/media-notes/services/hermes/internal/auth"
	graphqlpkg "github.com/nolannguyen1212/media-notes/services/hermes/internal/graphql"
	"github.com/nolannguyen1212/media-notes/services/hermes/internal/limits"
)

// NewMux returns hermes's top-level HTTP handler: health endpoints, a
// GraphQL Playground for operators, and /graphql behind the full
// middleware chain.
func NewMux(cfg app.Config, resolver *graphqlpkg.Resolver, validator auth.SessionValidator, health *app.Health, logger *slog.Logger) *http.ServeMux {
	mux := http.NewServeMux()
	health.RegisterRoutes(mux)

	schema := graphqlpkg.NewExecutableSchema(graphqlpkg.Config{Resolvers: resolver})
	srv := gqlhandler.NewDefaultServer(schema)
	srv.SetErrorPresenter(errorPresenter(logger))

	var graphqlHandler http.Handler = srv
	graphqlHandler = clientIPMiddleware(graphqlHandler)
	graphqlHandler = auth.Middleware(validator, cfg.SessionCookieName)(graphqlHandler)
	graphqlHandler = rateLimitSignalMiddleware(graphqlHandler)
	graphqlHandler = limits.BodyLimitMiddleware(cfg.GraphQLBodyLimitBytes)(graphqlHandler)
	graphqlHandler = corsMiddleware(cfg.CORSAllowedOrigin)(graphqlHandler)

	mux.Handle("/graphql", graphqlHandler)
	mux.Handle("/", playground.Handler("hermes", "/graphql"))

	return mux
}
