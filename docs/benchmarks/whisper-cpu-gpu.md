# Whisper CPU and GPU Benchmark

- Date: 2026-07-25
- Status: Accepted

## Question

Should the initial `conductor-worker` deployment run faster-whisper on CPU or
GPU?

This report records a reproducible local CPU baseline and the maintainer's
independent production-GPU measurement. The raw GPU environment and samples
were not captured in this repository, so the reported ratio is evidence for
the deployment decision rather than a reproducible capacity baseline.

## Environment

| Item | Value |
| --- | --- |
| Machine | Apple MacBook Pro |
| CPU | Apple M1 Pro, ARM64 |
| GPU | Apple M1 Pro, 14 Metal cores |
| Operating system | macOS, Darwin 25.5.0 |
| Python | CPython 3.9.6 |
| faster-whisper | 1.2.1 |
| CTranslate2 | 4.8.1 |
| Model | `base` |
| Decode settings | beam size 5 |
| CPU compute types | `int8`, `float32`, `int8_float32` |

CTranslate2's prebuilt binaries support ARM64 CPUs, while its documented GPU
backend requires an NVIDIA GPU. The faster-whisper requirements likewise
specify CUDA, cuBLAS, and cuDNN for GPU execution:

- <https://opennmt.net/CTranslate2/hardware_support.html>
- <https://github.com/SYSTRAN/faster-whisper#requirements>

An attempted CUDA model initialization failed before inference with:

```text
ValueError: This CTranslate2 package was not compiled with CUDA support
```

The Metal GPU was therefore not relabeled as a GPU benchmark result.

## Workload

macOS generated an 11.28-second English speech sample at 175 words per minute.
FFmpeg repeated and converted it into a two-minute, mono, 16 kHz PCM WAV:

```text
duration: 120.000000 seconds
size: 3,840,078 bytes
sha256: 590a768230b7e83479eaf916548543706eab3f216969f1c301aa9b6824bc773f
```

Each configuration loaded one model, transcribed the source clip as a warm-up,
then transcribed the same two-minute file three times in the same process.
Every segments iterator was fully consumed because faster-whisper starts
inference lazily.

The repeated synthetic speech is suitable for checking local throughput and
the benchmark procedure. It is not representative enough to compare word
error rate, production media mix, long-audio memory behavior, or tail latency.

## Results

Lower real-time factor (RTF) is faster. RTF is mean transcription wall time
divided by 120 seconds of audio.

| Device | Compute | Raw wall times | Mean | Standard deviation | RTF | Max RSS |
| --- | --- | --- | --- | --- | --- | --- |
| CPU | `int8` | 28.14 s, 31.73 s, 39.13 s | 33.00 s | 5.60 s | 0.275 | 839 MB |
| CPU | `float32` | 50.49 s, 47.19 s, 39.88 s | 45.85 s | 5.43 s | 0.382 | 887 MB |
| GPU | Maintainer's production configuration | Raw samples not recorded | 17× faster than CPU | — | — | — |

On this workload and machine, CPU `int8` mean wall time was 28.0% lower than
`float32`, or 1.39 times as fast. Both configurations completed faster than
real time.

Variance was high: 17.0% coefficient of variation for `int8` and 11.8% for
`float32`. The decoder also produced varying segment boundaries for the
repeated synthetic input. These measurements are not precise enough for
capacity commitments or a quality tradeoff.

The project maintainer separately measured the actual GPU deployment and
reported that it transcribes 17 times faster than CPU. Hardware, model,
compute type, corpus, raw wall times, variance, memory, and word-error-rate
were not supplied. This report preserves that provenance instead of deriving
unsupported absolute GPU values from the ratio.

## Decision

Use GPU execution for production Whisper workers. Keep CPU `int8` as the
local-development and bounded fallback configuration. The accepted 17×
measured speedup is sufficient for this backend choice; no further GPU
benchmark is required for it.

This ratio is not a production capacity or cost model. Worker concurrency,
queue limits, autoscaling thresholds, instance sizing, and provider objectives
must use deployment telemetry rather than extrapolating from the local CPU
workload or the speedup ratio.
