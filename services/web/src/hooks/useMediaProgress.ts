import { print } from "graphql";
import { useEffect, useRef, useState } from "react";
import {
	MediaProgressDocument,
	type MediaProgressQuery,
} from "@/graphql/generated/graphql";
import { TERMINAL_MEDIA_STATUSES } from "@/lib/constants";
import { getSession } from "@/lib/session";

// Hand-rolled per ADR 0005 (docs/adr/0005-progress-update-delivery.md):
// Apollo's built-in pollInterval can express none of visibility/offline
// pause, version-gated cache merge, or Retry-After-aware backoff, so this
// bypasses Apollo entirely and talks to hermes's /graphql with a plain
// fetch, reusing the generated query document as the single source of
// truth for its shape.

export type MediaProgressEntry = MediaProgressQuery["mediaProgress"][number];

const BASE_INTERVAL_MS = 3000;
const MAX_INTERVAL_MS = 30_000;
const QUERY = print(MediaProgressDocument);
const HERMES_URL = import.meta.env.VITE_HERMES_URL ?? "";

type PollResult = {
	data?: MediaProgressQuery;
	errorCode?: string;
	retryAfterSeconds?: number;
	ok: boolean;
};

async function pollOnce(ids: string[]): Promise<PollResult> {
	const session = getSession();
	let res: Response;
	try {
		res = await fetch(`${HERMES_URL}/graphql`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				...(session ? { Authorization: `Bearer ${session.token}` } : {}),
			},
			body: JSON.stringify({ query: QUERY, variables: { ids } }),
		});
	} catch {
		return { ok: false };
	}

	const retryAfterHeader = res.headers.get("Retry-After");
	let body: {
		data?: MediaProgressQuery;
		errors?: Array<{
			extensions?: { code?: string; retryAfterSeconds?: number };
		}>;
	} | null = null;
	try {
		body = await res.json();
	} catch {
		return { ok: false };
	}

	const firstError = body?.errors?.[0];
	if (res.status === 429 || firstError?.extensions?.code === "RATE_LIMITED") {
		const seconds =
			firstError?.extensions?.retryAfterSeconds ??
			(retryAfterHeader ? Number(retryAfterHeader) : undefined);
		return { ok: false, errorCode: "RATE_LIMITED", retryAfterSeconds: seconds };
	}
	if (firstError) {
		return { ok: false, errorCode: firstError.extensions?.code };
	}
	if (!res.ok || !body?.data) {
		return { ok: false };
	}
	return { ok: true, data: body.data };
}

function isTerminal(entry: MediaProgressEntry | undefined): boolean {
	return entry != null && TERMINAL_MEDIA_STATUSES.has(entry.status);
}

export type UseMediaProgressOptions = {
	/** Called once when a poll reports UNAUTHENTICATED; polling stops permanently. */
	onAuthError?: () => void;
};

/**
 * Polls hermes's mediaProgress for every id in `ids` that hasn't reached a
 * terminal status yet, following ADR 0005's client contract exactly:
 * 3s interval, pause while hidden/offline with an immediate refetch on
 * resume, version-gated cache merge, 3s-30s exponential backoff on failure
 * (reset to 3s on success), Retry-After overriding the backoff on a 429,
 * and a full stop on authentication failure.
 */
export function useMediaProgress(
	ids: string[],
	options: UseMediaProgressOptions = {},
) {
	const [progress, setProgress] = useState<Map<string, MediaProgressEntry>>(
		new Map(),
	);
	const progressRef = useRef(progress);
	progressRef.current = progress;

	const idsKey = ids.join(",");
	const onAuthErrorRef = useRef(options.onAuthError);
	onAuthErrorRef.current = options.onAuthError;

	useEffect(() => {
		const trackedIds = idsKey ? idsKey.split(",") : [];
		if (trackedIds.length === 0) return;

		let stopped = false;
		let timer: ReturnType<typeof setTimeout> | null = null;
		let interval = BASE_INTERVAL_MS;

		const clearTimer = () => {
			if (timer) {
				clearTimeout(timer);
				timer = null;
			}
		};

		function pendingIds(): string[] {
			return trackedIds
				.filter((id) => !isTerminal(progressRef.current.get(id)))
				.slice(0, 50);
		}

		function schedule(delayMs: number) {
			clearTimer();
			if (stopped) return;
			timer = setTimeout(tick, delayMs);
		}

		async function tick() {
			if (stopped) return;
			if (
				typeof document !== "undefined" &&
				(document.hidden ||
					(typeof navigator !== "undefined" && navigator.onLine === false))
			) {
				return; // resumed by the visibility/online listeners below
			}

			const idsToPoll = pendingIds();
			if (idsToPoll.length === 0) return;

			const result = await pollOnce(idsToPoll);
			if (stopped) return;

			if (!result.ok) {
				if (result.errorCode === "UNAUTHENTICATED") {
					stopped = true;
					clearTimer();
					onAuthErrorRef.current?.();
					return;
				}
				if (
					result.errorCode === "RATE_LIMITED" &&
					result.retryAfterSeconds != null
				) {
					// Retry-After is an explicit server directive: it can exceed
					// the general 30s backoff cap, per ADR 0005.
					interval = Math.max(
						result.retryAfterSeconds * 1000,
						BASE_INTERVAL_MS,
					);
				} else {
					const nextBase = Math.min(interval * 2, MAX_INTERVAL_MS);
					const jitter = 0.85 + Math.random() * 0.3;
					interval = Math.min(Math.round(nextBase * jitter), MAX_INTERVAL_MS);
				}
				schedule(interval);
				return;
			}

			interval = BASE_INTERVAL_MS;
			const entries = result.data?.mediaProgress ?? [];
			if (entries.length > 0) {
				setProgress((prev) => {
					const next = new Map(prev);
					for (const entry of entries) {
						const existing = next.get(entry.mediaId);
						if (!existing || entry.version > existing.version) {
							next.set(entry.mediaId, entry);
						}
					}
					progressRef.current = next;
					return next;
				});
			}

			if (pendingIds().length > 0) schedule(interval);
		}

		function handleResume() {
			if (stopped) return;
			clearTimer();
			tick();
		}

		if (pendingIds().length > 0) tick();

		document.addEventListener("visibilitychange", handleResume);
		window.addEventListener("online", handleResume);

		return () => {
			stopped = true;
			clearTimer();
			document.removeEventListener("visibilitychange", handleResume);
			window.removeEventListener("online", handleResume);
		};
	}, [idsKey]);

	return progress;
}
