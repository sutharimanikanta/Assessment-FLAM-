from datetime import datetime
from sqlalchemy import and_, or_
from flam.db.models import Job, DeadJob


def enqueue(job_id, command, session, replace=False, max_retries=None):
    """
    Add a job to the queue.
    If replace=True and a job with the same id exists, delete & re-add it.
    """
    existing = session.query(Job).filter_by(id=job_id).first()
    if existing:
        if not replace:
            raise ValueError(f"Job '{job_id}' already exists.")
        session.delete(existing)
        session.commit()

    job = Job(
        id=job_id,
        command=command,
        status="pending",
        attempts=0,
        last_error=None,
        next_run_at=None,
        created_at=datetime.utcnow(),
        max_retries=max_retries,
    )
    session.add(job)
    session.commit()
    print(f"[ENQUEUE] Job {job_id} added.")


def delete_job(job_id, session):
    """
    Delete a job from active queue (if present).
    """
    j = session.query(Job).filter_by(id=job_id).first()
    if not j:
        return False
    session.delete(j)
    session.commit()
    return True


def list_jobs(session, state=None):
    q = session.query(Job)
    if state:
        q = q.filter(Job.status == state)
    return q.order_by(Job.created_at.asc()).all()


def summarize_jobs(session):
    return {
        "total": session.query(Job).count(),
        "pending": session.query(Job).filter(Job.status == "pending").count(),
        "processing": session.query(Job).filter(Job.status == "processing").count(),
        "completed": session.query(Job).filter(Job.status == "completed").count(),
        "failed": session.query(Job).filter(Job.status == "failed").count(),
    }


def list_dead_jobs(session):
    return session.query(DeadJob).order_by(DeadJob.failed_at.desc()).all()

def move_to_dead(job, session):
    """
    Move a failed job (exhausted retries) into DeadJob and remove from Job.
    """
    session.add(
        DeadJob(
            id=job.id,
            command=job.command,
            last_error=job.last_error,
            failed_at=datetime.utcnow(),
        )
    )
    session.delete(job)
    session.commit()

def retry_dead_job(job_id, session):
    dj = session.query(DeadJob).filter_by(id=job_id).first()
    if not dj:
        return None
    session.add(
        Job(
            id=dj.id,
            command=dj.command,
            status="pending",
            attempts=0,
            last_error=None,
            next_run_at=None,
            created_at=datetime.utcnow(),
        )
    )
    session.delete(dj)
    session.commit()
    return True


def claim_next_job(session):
    """
    Atomically claim the next runnable job.
    Runnable: status='pending' AND (next_run_at is null OR next_run_at <= now)
    """
    now = datetime.utcnow()
    candidate = (
        session.query(Job)
        .filter(
            and_(
                Job.status == "pending",
                or_(Job.next_run_at == None, Job.next_run_at <= now),
            )
        )
        .order_by(Job.created_at.asc())
        .first()
    )

    if not candidate:
        return None

    updated = (
        session.query(Job)
        .filter(and_(Job.id == candidate.id, Job.status == "pending"))
        .update({Job.status: "processing"}, synchronize_session=False)
    )
    session.commit()

    if updated == 1:
        return session.query(Job).filter_by(id=candidate.id).first()
    return None
