import os
import time
import click

from flam.db.base import Base, engine, get_session
from flam.queue_manager import (
    enqueue,
    list_jobs,
    summarize_jobs,
    list_dead_jobs,
    retry_dead_job,
    delete_job,
)
from flam.worker_manager import start_workers, stop_workers
from flam.config import set_config, get_config

# ensure tables exist
Base.metadata.create_all(bind=engine)


@click.group()
def cli():
    """queuectl command line controller"""
    pass


# Enqueue
@cli.command("enqueue")
@click.option("--id", "job_id", required=True, help="Job ID")
@click.option("--command", required=True, help="Command to execute")
@click.option(
    "--max-retries", type=int, default=None, help="Override per-job max retries"
)
@click.option("--replace", is_flag=True, help="If job exists, replace it")
def enqueue_cmd(job_id, command, max_retries, replace):
    s = get_session()
    try:
        enqueue(job_id, command, s, replace=replace, max_retries=max_retries)
    except ValueError as e:
        click.echo(str(e))
        raise SystemExit(1)
    click.echo(f"Enqueued job {job_id}")


# Jobs admin
@cli.group("jobs")
def jobs_group():
    """Job admin commands"""
    pass

@jobs_group.command("delete")
@click.argument("job_id")
def jobs_delete(job_id):
    s = get_session()
    ok = delete_job(job_id, s)
    click.echo("deleted" if ok else "not found")


# Worker
@cli.group()
def worker():
    pass


@worker.command("start")
@click.option("--count", default=1, help="Number of workers to start")
def worker_start(count):
    start_workers(count)


@worker.command("stop")
def worker_stop():
    stop_workers()


# Status
@cli.command("status")
def status_cmd():
    s = get_session()
    summary = summarize_jobs(s)

    hb_dir = "data"
    live = 0
    now = time.time()
    if os.path.exists(hb_dir):
        for name in os.listdir(hb_dir):
            if name.startswith("worker-") and name.endswith(".hb"):
                path = os.path.join(hb_dir, name)
                try:
                    # consider worker alive if heartbeat written in last 10s
                    if now - os.path.getmtime(path) < 10:
                        live += 1
                except Exception:
                    pass

    click.echo(f"Workers: {live if live else 0} active")
    for k, v in summary.items():
        click.echo(f"{k}: {v}")


# List
@cli.command("list")
@click.option("--state", default=None, help="pending|processing|completed|failed")
def list_cmd(state):
    s = get_session()
    for j in list_jobs(s, state):
        click.echo(
            f"{j.id} | {j.command} | {j.status} | attempts={j.attempts} | next_run_at={j.next_run_at}"
        )


# DLQ
@cli.group()
def dlq():
    pass


@dlq.command("list")
def dlq_list_cmd():
    s = get_session()
    for d in list_dead_jobs(s):
        click.echo(f"{d.id} | {d.command} | {d.last_error} | failed_at={d.failed_at}")

@dlq.command("retry")
@click.argument("job_id")
def dlq_retry_cmd(job_id):
    s = get_session()
    ok = retry_dead_job(job_id, s)
    if ok:
        click.echo(f"Moved job {job_id} back to queue")
    else:
        click.echo("Not found")

# Config
@cli.group()
def config():
    pass

@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set_cmd(key, value):
    set_config(key, value)
    click.echo(f"{key}={value}")

@config.command("get")
@click.argument("key")
def config_get_cmd(key):
    val = get_config(key)
    click.echo(val if val is not None else "")

if __name__ == "__main__":
    cli()
