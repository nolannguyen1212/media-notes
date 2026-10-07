import {
	ApolloClient,
	ApolloLink,
	HttpLink,
	InMemoryCache,
} from "@apollo/client";
import { onError } from "@apollo/client/link/error";
import { clearSession, getSession } from "@/lib/session";

// VITE_HERMES_URL is empty locally (relative /graphql, same-origin) and
// set at build time for the Kubernetes deployment (cross-origin, direct
// to hermes's Ingress).
const hermesUrl = import.meta.env.VITE_HERMES_URL ?? "";
const httpLink = new HttpLink({ uri: `${hermesUrl}/graphql` });

const authLink = new ApolloLink((operation, forward) => {
	const session = getSession();
	if (session) {
		operation.setContext(({ headers = {} }) => ({
			headers: {
				...headers,
				Authorization: `Bearer ${session.token}`,
			},
		}));
	}
	return forward(operation);
});

// hermes never returns an HTTP 401 for a bad/expired session — it flags
// the request unauthenticated and lets public operations (register, login)
// still resolve (services/hermes/internal/auth/auth.go), so resolvers that
// require a principal surface it as a GraphQL error with
// extensions.code === "UNAUTHENTICATED" (errors.go). Catching it here is
// the one place the whole app needs to know that.
let onUnauthenticated: (() => void) | null = null;
export function setUnauthenticatedHandler(handler: () => void) {
	onUnauthenticated = handler;
}

const errorLink = onError(({ graphQLErrors }) => {
	if (
		graphQLErrors?.some((err) => err.extensions?.code === "UNAUTHENTICATED")
	) {
		clearSession();
		onUnauthenticated?.();
	}
});

export const apolloClient = new ApolloClient({
	link: ApolloLink.from([errorLink, authLink, httpLink]),
	cache: new InMemoryCache({
		typePolicies: {
			Content: { keyFields: ["mediaId"] },
			MediaProgress: { keyFields: ["mediaId"] },
			// PromptSetting has no id field (its natural key is
			// (user, section), and the user is implicit from the session) —
			// without this, updatePromptSetting's result normalizes nowhere,
			// so the promptSettings list query keeps serving the pre-save
			// value until a full reload. keyFields: ["section"] gives it a
			// stable identity so the mutation result and the list share one
			// cache entry.
			PromptSetting: { keyFields: ["section"] },
			// mediaList/trashedMedia are true page-replacement pagination
			// (see _protected._index.tsx's cursor stack), not infinite
			// scroll — every fetch, including a cursor'd one, is a distinct
			// page that should replace its own cache slot outright. No
			// custom keyArgs/merge needed: Apollo already caches each
			// distinct (cursor, pageSize, search) argument combination
			// separately by default.
		},
	}),
});
