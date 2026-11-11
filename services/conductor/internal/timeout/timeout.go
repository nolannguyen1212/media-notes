// Package timeout computes conductor's per-step deadlines. It holds no
// state; internal/store persists the computed deadline_at and
// ExpireTimedOutSteps sweeps steps past it.
package timeout

import (
	"time"

	"github.com/nolannguyen1212/media-notes/services/conductor/internal/workflow"
)

// deadlines gives every step type a generous ceiling for its slowest
// realistic provider call (Whisper transcription of a long recording,
// LLM enrichment, TTS synthesis, FFmpeg frame extraction) plus queueing
// time under load. These are launch defaults, not measured SLOs — ADR 0007
// leaves per-provider timeout tuning to worker-side local limits; this is
// conductor's outer bound for detecting a step that will never report
// back.
var deadlines = map[string]time.Duration{
	workflow.StepTranscribe:   15 * time.Minute,
	workflow.StepSummary:      5 * time.Minute,
	workflow.StepKeywords:     5 * time.Minute,
	workflow.StepKeypoints:    5 * time.Minute,
	workflow.StepNotes:        5 * time.Minute,
	workflow.StepSummaryAudio: 5 * time.Minute,
	workflow.StepThumbnail:    3 * time.Minute,
}

const defaultDeadline = 5 * time.Minute

// DeadlineFor returns how long a dispatched step of stepType may run
// before ExpireTimedOutSteps treats it as failed.
func DeadlineFor(stepType string) time.Duration {
	if d, ok := deadlines[stepType]; ok {
		return d
	}
	return defaultDeadline
}
