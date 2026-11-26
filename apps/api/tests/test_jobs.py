from sqlalchemy import select

from ringlark import jobs
from ringlark.worker import run_once
from sendora_core.jobs import Worker
from sendora_core.models import Job


def test_worker_runs_every_job_kind_once_and_does_not_double_schedule(ctx, seeded):
    w = Worker(ctx.factory, jobs.make_handlers(ctx))
    n = run_once(ctx, w)
    with ctx.factory() as s:
        kinds = {j.kind: j.status for j in s.scalars(select(Job))}
    assert set(kinds) == set(jobs.INTERVALS) and set(kinds.values()) == {"done"} and n == len(jobs.INTERVALS)
    assert run_once(ctx, w) == 0
