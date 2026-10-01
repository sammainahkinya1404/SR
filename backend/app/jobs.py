"""Scheduled jobs (spec Part B §7), runnable without a worker process:

    uv run python -m app.jobs post-recurring     # daily 00:05
    uv run python -m app.jobs credit-reminders   # daily 08:00
    uv run python -m app.jobs snapshot-metrics   # nightly
    uv run python -m app.jobs check-alerts       # nightly, after snapshot-metrics

Schedule them with Windows Task Scheduler (or cron). All are safe to run repeatedly or late:
each recurring occurrence posts once, each invoice gets at most one due and one overdue
reminder, snapshots are upserts, and alert checks reconcile to the current state."""

import argparse
import logging
from datetime import timedelta

from sqlalchemy import select

from app.db import system_session, tenant_session
from app.domain.clock import business_today
from app.domain.metrics import Period
from app.models import Business, RecurringExpense, User
from app.services import alerts, metrics
from app.services.actor import Actor, Role
from app.services.expenses import post_due_recurring
from app.services.reminders import queue_credit_reminders

log = logging.getLogger("app.jobs")


def post_recurring() -> int:
    total = 0
    for business_id in _business_ids():
        with tenant_session(business_id) as session:
            # Post as the business owner; the job has no user of its own.
            owner = session.scalar(
                select(User).where(User.role == Role.OWNER).order_by(User.created_at)
            )
            if owner is None or not session.scalar(select(RecurringExpense.id).limit(1)):
                continue
            posted = post_due_recurring(session, Actor(owner.id, business_id, Role.OWNER))
            total += len(posted)
            log.info("business %s: posted %d recurring expenses", business_id, len(posted))
    return total


def credit_reminders() -> int:
    """Queue SMS reminders for invoices due today or overdue (sending is not integrated yet)."""
    total = 0
    for business_id in _business_ids():
        with tenant_session(business_id) as session:
            business = session.get(Business, business_id)
            queued = queue_credit_reminders(session, business)
            total += len(queued)
            if queued:
                log.info("business %s: queued %d reminders", business_id, len(queued))
    return total


SNAPSHOT_DAYS = 7  # recompute the last week so backdated postings are reflected


def snapshot_metrics() -> int:
    """Cache finished days in metric_snapshots (spec Part B §8)."""
    yesterday = business_today() - timedelta(days=1)
    period = Period(yesterday - timedelta(days=SNAPSHOT_DAYS - 1), yesterday)
    total = 0
    for business_id in _business_ids():
        with tenant_session(business_id) as session:
            total += metrics.snapshot(session, session.get(Business, business_id), period)
    return total


def check_alerts() -> tuple[int, int]:
    opened = resolved = 0
    for business_id in _business_ids():
        with tenant_session(business_id) as session:
            o, r = alerts.run_checks(session, session.get(Business, business_id))
            opened, resolved = opened + o, resolved + r
            if o or r:
                log.info("business %s: %d alerts opened, %d resolved", business_id, o, r)
    return opened, resolved


def _business_ids() -> list:
    with system_session() as session:
        return list(session.scalars(select(Business.id)))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m app.jobs")
    parser.add_argument(
        "job", choices=["post-recurring", "credit-reminders", "snapshot-metrics", "check-alerts"]
    )
    args = parser.parse_args()
    if args.job == "post-recurring":
        log.info("posted %d recurring expenses in total", post_recurring())
    elif args.job == "credit-reminders":
        log.info("queued %d credit reminders in total", credit_reminders())
    elif args.job == "snapshot-metrics":
        log.info("snapshotted %d business-days", snapshot_metrics())
    elif args.job == "check-alerts":
        log.info("alerts: %d opened, %d resolved", *check_alerts())


if __name__ == "__main__":
    main()
