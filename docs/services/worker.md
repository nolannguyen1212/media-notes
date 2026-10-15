# Worker (`conductor-worker`)

Stateless Python Kafka consumer pool that executes processing steps. It owns
no database: text results go to content, thumbnails to media, and audio
bytes to MinIO with their metadata in content.

## Structure

```text
src/main.py        startup, provider wiring, consumer loop
src/events.py      topics, consumer group, message decoding
src/dispatch.py    routes a step command to its handler, classifies failures
src/handlers/      transcribe, summary, keywords, keypoints, notes,
                   summary_audio, thumbnail, audio_job
src/providers/     whisper (faster-whisper), llm, tts (edge-tts), thumbnail (FFmpeg)
src/clients/       gRPC clients for media and content, MinIO client
src/limits.py      per-capability semaphores and step timeout
src/errors.py      retriable and terminal error classes
tests/
```

## Steps

| Step | Provider | Result written to |
| --- | --- | --- |
| `transcribe` | faster-whisper, run locally (`WHISPER_MODEL`, default `base`) | content `StoreTranscript` |
| `summary`, `keywords`, `keypoints`, `notes` | LLM | content `Store*` |
| `summary_audio` | edge-tts | MinIO object, then content `StoreSummaryAudioMetadata` |
| `generate_thumbnail` (video only) | FFmpeg, 320×180 WebP | MinIO object, then media `RegisterDerivative` |
| standalone `script` / `audio` jobs | LLM / edge-tts | content `CompleteScriptDraft` / `CompleteStandaloneAudio` |

LLM steps append the user's prompt override for that option, when one was
sent with the step command. `summary_audio` uses the command's `voice`,
falling back to `WORKER_TTS_VOICE`.

## Standalone audio flow

<img src="../diagrams/audio-job.svg" alt="Standalone audio" width="460">

## LLM providers

`LLM_PROVIDER` picks the primary provider: `1` is Gemini (`GEMINI_MODEL`),
`2` is Hugging Face (`HF_MODEL`), and `2` is the default. If the primary
raises, the others are tried in order. ADR 0007 rejects this silent
fallback; see its implementation status.

## Execution rules

- Consumes `mn.processing.step.requested.v1` and `mn.audio.job.requested.v1`
  in consumer group `conductor-worker-steps`.
- Each step takes a per-capability semaphore (`WORKER_MAX_CONCURRENT_WHISPER`
  1, `_GEMINI` 4, `_TTS` 2, `_THUMBNAIL` 2) and has a deadline of
  `WORKER_STEP_TIMEOUT_SECONDS` (600s).
- The Kafka offset is committed only after the owning service accepted the
  result. The owning service publishes the completion event; the worker
  never does.
- A failure is classified as retriable or terminal; unknown errors count as
  retriable. The worker publishes only the error code and attempt to
  `mn.processing.step.failed.v1`, and conductor decides whether to retry.
  Audio jobs report failure directly through `FailStandaloneAudioJob`.
- No media bytes or long text go through Kafka.

## Not implemented

- Aggregate provider quotas across replicas (ADR 0007); each replica only
  bounds itself.
- A production TTS provider; edge-tts has no quota or SLA.
