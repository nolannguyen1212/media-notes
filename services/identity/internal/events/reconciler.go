package events

import (
	"context"
	"log/slog"
	"time"
)

// OverdueReconciler republishes outbox events for pending deletion
// operations older than olderThan, bounded by limit. account.Service
// implements it.
type OverdueReconciler interface {
	ReconcileOverdueDeletions(ctx context.Context, olderThan time.Duration, limit int) (int, error)
}

// Reconciler periodically republishes deletion-requested events for
// operations that have been pending too long, covering lost or failed
// outbox publications. It intentionally has no DLQ, feature flag, or
// dry-run mode: those are rollout concerns (ADR 0006) that
// assume downstream owners already exist to reconcile against.
type Reconciler struct {
	account   OverdueReconciler
	logger    *slog.Logger
	olderThan time.Duration
	batchSize int
}

// NewReconciler returns a Reconciler that treats a pending operation as
// overdue once it is older than olderThan, processing at most batchSize
// operations per tick.
func NewReconciler(account OverdueReconciler, logger *slog.Logger, olderThan time.Duration, batchSize int) *Reconciler {
	return &Reconciler{account: account, logger: logger, olderThan: olderThan, batchSize: batchSize}
}

// Run ticks every interval until ctx is canceled.
func (r *Reconciler) Run(ctx context.Context, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			r.tick(ctx)
		}
	}
}

func (r *Reconciler) tick(ctx context.Context) {
	n, err := r.account.ReconcileOverdueDeletions(ctx, r.olderThan, r.batchSize)
	if err != nil {
		r.logger.ErrorContext(ctx, "reconcile overdue deletions", "error", err)
		return
	}
	if n > 0 {
		r.logger.InfoContext(ctx, "republished overdue deletion operations", "count", n)
	}
}
