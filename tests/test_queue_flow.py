import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from flam.db.base import Base
from flam.db.models import Job, DeadJob
from flam.queue_manager import (
    enqueue,
    list_jobs,
    list_dead_jobs,
    retry_dead_job,
    move_to_dead,
    claim_next_job,
)
from flam.config import set_config, get_float


@pytest.fixture()
def session():
    print("\n[SETUP] Creating in-memory DB")
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_enqueue_and_list(session):
    print("\n[TEST] Enqueue job1")
    enqueue("job1", "echo test", session)
    jobs = list_jobs(session)
    print("[DEBUG] Jobs in DB:", [(j.id, j.status) for j in jobs])
    assert len(jobs) == 1
    assert jobs[0].id == "job1"
    assert jobs[0].status == "pending"


def test_multiple_enqueue_and_filter_by_state(session):
    print("\n[TEST] Enqueue multiple jobs and test all lifecycle states")
    enqueue("j1", "echo A", session)  # pending
    enqueue("j2", "echo B", session)  # processing
    enqueue("j3", "echo C", session)  # completed
    enqueue("j4", "echo D", session)  # failed
    enqueue("j5", "echo E", session)  # dead
    job2 = session.query(Job).filter_by(id="j2").first()
    job2.status = "processing"
    job3 = session.query(Job).filter_by(id="j3").first()
    job3.status = "completed"
    job4 = session.query(Job).filter_by(id="j4").first()
    job4.status = "failed"
    job4.last_error = "temporary"
    job5 = session.query(Job).filter_by(id="j5").first()
    move_to_dead(job5, session)
    session.commit()
    pending = list_jobs(session, state="pending")
    processing = list_jobs(session, state="processing")
    completed = list_jobs(session, state="completed")
    failed = list_jobs(session, state="failed")
    dead = list_dead_jobs(session)
    print("[DEBUG] pending:", [(j.id, j.status) for j in pending])
    print("[DEBUG] processing:", [(j.id, j.status) for j in processing])
    print("[DEBUG] completed:", [(j.id, j.status) for j in completed])
    print("[DEBUG] failed:", [(j.id, j.status) for j in failed])
    print("[DEBUG] DLQ:", [(j.id, j.command) for j in dead])
    assert len(pending) == 1 and pending[0].id == "j1"
    assert len(processing) == 1 and processing[0].id == "j2"
    assert len(completed) == 1 and completed[0].id == "j3"
    assert len(failed) == 1 and failed[0].id == "j4"
    assert len(dead) == 1 and dead[0].id == "j5"


def test_retry_logic_schedules_next_run(session):
    print("\n[TEST] Retry scheduling")
    set_config("backoff_base", "2")
    enqueue("jobX", "fail_cmd", session)
    job = session.query(Job).filter_by(id="jobX").first()
    job.status = "pending"
    job.attempts = 1
    delay = get_float("backoff_base", 2.0) ** job.attempts
    job.next_run_at = datetime.utcnow() + timedelta(seconds=delay)
    session.commit()
    assert job.next_run_at is not None
    print("[DEBUG] next_run_at:", job.next_run_at)


def test_worker_does_not_claim_job_before_next_run(session):
    print("\n[TEST] Job should not be claimed before next_run_at")
    enqueue("jobY", "cmd", session)
    job = session.query(Job).filter_by(id="jobY").first()
    job.next_run_at = datetime.utcnow() + timedelta(seconds=100)  # Future
    session.commit()
    claimed = claim_next_job(session)
    assert claimed is None


def test_failed_job_moves_to_dlq(session):
    print("\n[TEST] Failed job → DLQ")
    enqueue("job3", "invalid_cmd", session)
    job = session.query(Job).filter_by(id="job3").first()
    job.attempts = job.max_retries
    job.last_error = "fail"
    session.commit()
    move_to_dead(job, session)
    assert session.query(Job).filter_by(id="job3").first() is None
    assert session.query(DeadJob).filter_by(id="job3").first() is not None


def test_retry_from_dlq(session):
    print("\n[TEST] Retry job from DLQ")
    dj = DeadJob(id="job4", command="echo hi", last_error="fail")
    session.add(dj)
    session.commit()
    retry_dead_job("job4", session)
    assert session.query(Job).filter_by(id="job4").first() is not None
    assert session.query(DeadJob).filter_by(id="job4").first() is None


def test_concurrent_claim_safety(session):
    print("\n[TEST] No duplicate job claiming")
    enqueue("jobZ", "echo hello", session)
    job1 = claim_next_job(session)
    assert job1 is not None
    job2 = claim_next_job(session)
    assert job2 is None
