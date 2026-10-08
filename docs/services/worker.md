# Worker

## Scope

Python Kafka consumer-group pool. It is stateless: executes Whisper, Gemini,
FFmpeg and TTS; it owns only bounded local execution. Durable results belong to
Media or Content service.

## Structure

```text
worker/
  consumer.py        # polling, decode, offset commit
  dispatch.py        # step-kind routing
  steps/             # transcribe, summary, keywords, keypoints, notes, audio, thumbnail
  clients/           # gRPC and object-storage clients
  providers/         # Whisper/Gemini/TTS adapters
  limits.py          # semaphore, timeout and quota admission
```

## Handlers

```text
handle_transcribe, handle_summary, handle_keywords, handle_keypoints
handle_notes, handle_summary_audio, handle_thumbnail
handle_script, handle_audio  # standalone audio jobs — see below
```

Each handler validates command IDs/attempt, acquires a bounded capability
semaphore, applies a deadline, reads only required object/content input, invokes
its provider, then calls the owner service to persist the durable result. Commit
the Kafka offset only after that call succeeds. On failure emit only classified
small metadata to `mn.processing.step.failed.v1`.

`handle_summary_audio` selects a voice by falling back through the command's
own `voice` field (conductor's workflow-level `audio_voice`, itself sourced
from the caller's `ConfirmUpload` request) to the pool-wide default in
`WORKER_TTS_VOICE`. There is no per-provider voice validation beyond what the
TTS provider itself rejects.

Workers never choose another worker, track workflow state, publish a successful
completion before persistence, or transfer media/text via Kafka. Before commit,
check authoritative deletion/media state. Test provider timeout, admission
denial, duplicate command, owner unavailable, late result and cancellation.

## Standalone audio generation

Unlike `handle_summary_audio` (which only ever synthesizes a *derived*
summary of an existing media item's transcript), the "Audio" feature lets a
caller paste text directly, or describe what they want and have an LLM
draft narration text first, then synthesize it — entirely independent of
any media item, conductor workflow, or media_id.

- `handle_script` drafts narration text from a loose description via
  `providers.gemini.draft_audio_script` — a plain-prose prompt/response,
  unlike every other Gemini call in this module (no transcript, no JSON
  structure).
- `handle_audio` synthesizes text directly to speech via the same
  `providers/tts.py` edge-tts adapter `handle_summary_audio` uses, uploads
  the object, and commits its metadata.
- Both are dispatched from `mn.audio.job.requested.v1` (content's own
  outbox topic — `content/internal/audiojob` — not conductor's), consumed
  by the same worker pool on the same consumer group as
  `mn.processing.step.requested.v1`. On success each calls content's
  `CompleteScriptDraft`/`CompleteStandaloneAudio` RPC directly; on failure
  each calls `FailStandaloneAudioJob` directly — there is no
  `mn.processing.step.failed.v1` equivalent for a job with no workflow to
  notify.
- content owns the durable rows (`standalone_audio_jobs`, keyed by
  `user_id`, not `media_id`) and the hermes GraphQL surface
  (`draftAudioScript`, `generateStandaloneAudio` mutations;
  `audioJob`/`audioJobs` queries). Jobs are tracked through the same
  `generating`/`completed`/`failed` states every other job in this app
  exposes. The web app's "Audio" nav entry lists them, independent of the
  media library and its trash.
- Not yet wired to billing: generating a script or audio job does not
  reserve or settle credits today, unlike every media-bound processing
  step.
