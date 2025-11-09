# queuectl

A lightweight, persistent background job queue system with retry logic, dead-letter queue (DLQ), and multi-worker support. Built with Python, SQLAlchemy, and SQLite.

## Overview

**queuectl** is a simple yet robust job queue that enables asynchronous command execution with fault tolerance. Jobs are persisted to disk, survived across restarts, and automatically retried with exponential backoff on failure. Failed jobs exceeding retry limits are moved to a dead-letter queue for manual inspection and recovery.

### Key Features

- **Persistent Storage**: SQLite-backed queue survives process restarts
- **Multi-Worker Support**: Run multiple concurrent worker processes
- **Exponential Backoff**: Configurable retry delays for failed jobs
- **Dead-Letter Queue (DLQ)**: Failed jobs are isolated for manual review and retry
- **CLI Interface**: Simple command-line tools for queue management
- **Job Lifecycle Tracking**: Monitor jobs through all execution states
- **Heartbeat Monitoring**: Detect active workers via filesystem heartbeats

### Job Lifecycle

```
┌─────────┐
│ PENDING │────────┐
└────┬────┘        │
     │             │
     ▼             │
┌────────────┐     │ (retry with backoff)
│ PROCESSING │     │
└─────┬──────┘     │
      │            │
   ┌──┴───┐        │
   │      │        │
   ▼      ▼        │
SUCCESS  FAIL──────┤
   │      │        │
   ▼      │        │
┌───────────┐      │ (max retries exceeded)
│ COMPLETED │      │
└───────────┘      ▼
              ┌────────┐
              │  DLQ   │
              └────────┘
```

**States**:
- **pending**: Waiting to be claimed by a worker
- **processing**: Currently being executed by a worker
- **completed**: Successfully finished
- **failed**: Temporarily failed, eligible for retry
- **DLQ**: Permanently failed after exhausting retries

---

## Architecture

### Components

1. **CLI (`cli.py`)**: Command-line interface for queue operations
2. **Worker Manager (`worker_manager.py`)**: Spawns and manages worker processes
3. **Worker (`worker.py`)**: Background processes that claim and execute jobs
4. **Queue Manager (`queue_manager.py`)**: Job lifecycle operations (enqueue, claim, retry)
5. **Executor (`executor.py`)**: Runs shell commands and captures output
6. **Database Layer (`db/`)**: SQLAlchemy models and session management
7. **Config (`config.py`)**: Key-value configuration storage

### How It Works

1. **Job Submission**: Jobs are added to the database with `pending` status
2. **Job Claiming**: Workers atomically claim jobs using SQL UPDATE with row-level locking
3. **Execution**: Worker runs the command via subprocess, captures stdout/stderr
4. **Success Path**: Job marked `completed`, removed from active queue
5. **Failure Path**: 
   - Increment attempt counter
   - Calculate backoff delay: `min(backoff_base ^ attempts, max_backoff_cap)`
   - If attempts < max_retries: schedule next run with `next_run_at`
   - If attempts ≥ max_retries: move to DLQ
6. **Retry Logic**: Workers skip jobs where `next_run_at > current_time`

### Concurrency Safety

- SQLite's row-level locking prevents duplicate job claiming
- Workers use heartbeat files to signal liveness
- Graceful shutdown on SIGINT/SIGTERM

---

## Installation & Setup

### Prerequisites

- Python 3.8+
- pip

### Install Dependencies

Install the package in editable mode (recommended for development):

```bash
pip install -e .
```

This installs all dependencies (SQLAlchemy, Click) and makes the `queuectl` command available system-wide.

For testing:
```bash
pip install pytest
```
### Two-Terminal Architecture Explained
Why Your Queue System Needs Two Terminals
Your background job queue system requires two separate terminals because it follows the client-server pattern where workers run as persistent background processes while you need an active terminal to issue commands.
This is standard practice for all production job queue systems like:

Celery (Python)
Sidekiq (Ruby)
Bull/BullMQ (Node.js)
Redis Queue (RQ) (Python)


The Two-Terminal Model
TerminalPurposeStatusTerminal ARuns the worker processes (background processors)Must stay open - Workers continuously poll for jobsTerminal BCommand center for job management (enqueue, status, DLQ, etc.)Interactive - Execute commands as needed

Why This Architecture is Necessary
1. Workers Run in an Infinite Loop
When you start workers, they execute code like this:
pythonwhile not _shutdown.is_set():
    job = claim_next_job(session)
    if job:
        execute(job)
    time.sleep(0.1)  # Poll every 100ms
This blocks the terminal - you cannot type new commands while the loop is running.
2. Workers Must Stay Alive to Process New Jobs
If workers stop, the queue becomes dormant:

New jobs you enqueue just sit in the database
Nothing processes them until workers restart
Defeats the purpose of a "background" job system

3. Real-Time Job Processing
Workers need to continuously monitor the database so that:

Jobs are picked up immediately when enqueued
Retries happen at the scheduled time (next_run_at)
Multiple workers can process jobs concurrently


Step-by-Step Workflow
Terminal A: Start Workers (Background Service)
powershell# Activate environment
& D:/Env/sql/Scripts/Activate.ps1

# Start 2 worker processes
queuectl worker start --count 2
```

**What happens:**
```
Started 2 worker(s): [12345, 12346]
[worker 12345] started. heartbeat=data/worker-12345.hb
[worker 12346] started. heartbeat=data/worker-12346.hb
This terminal is now "busy" - the workers are running and waiting for jobs. Keep it open!

Terminal B: Job Management (Command Center)
Open a new PowerShell window and activate the same environment:
powershell& D:/Env/sql/Scripts/Activate.ps1
Now you can freely execute commands:
Enqueue Jobs
powershellqueuectl enqueue --id job1 --command "timeout /T 2 /NOBREAK"
queuectl enqueue --id job2 --command "echo Processing..."
```

**What happens in Terminal A:**
```
[worker 12345] running job 'job1': timeout /T 2 /NOBREAK
[worker 12346] running job 'job2': echo Processing...
[job job2] STDOUT:
Processing...
[worker 12346] job 'job2' -> completed
Monitor System
powershell# Check how many jobs are in each state
queuectl status

# List all pending jobs
queuectl list --state pending

# See what's currently processing
queuectl list --state processing
Manage Failed Jobs
powershell# View dead-letter queue
queuectl dlq list

# Retry a failed job
queuectl dlq retry job_fail
Configure System
powershellqueuectl config set max-retries 5
queuectl config get backoff-base
```

---

## Visual Architecture
```
┌───────────────────────────────────────────────────────┐
│              Terminal A (Worker Process)              │
│                                                       │
│  queuectl worker start --count 2                      │
│                                                       │
│  [worker 12345] started...                            │
│  [worker 12346] started...                            │
│    Continuously polling database for jobs           │
│    Executing commands as they arrive                │
│    Writing heartbeat files every loop               │
│                                                       │
│    BLOCKED - Cannot type new commands here          │
└───────────────────────────────────────────────────────┘
                        ↕️
              SQLite Database (job.db)
                        ↕️
┌───────────────────────────────────────────────────────┐
│              Terminal B (Control Plane)               │
│                                                       │
│  $ queuectl enqueue --id job1 --command "..."        │
│   Enqueued job job1                                 │
│                                                       │
│  $ queuectl status                                    │
│  Workers: 2 active                                    │
│  total: 10                                            │
│  pending: 3                                           │
│  processing: 2                                        │
│  completed: 5                                         │
│                                                       │
│  $ queuectl dlq list                                  │
│  job_fail | not_a_real_command | ...                  │
│                                                       │
│   FREE - Interactive command prompt available       │
└───────────────────────────────────────────────────────┘

Data Flow Example
Timeline:

T=0s (Terminal B): queuectl enqueue --id task1 --command "echo Start"

Job written to database with status='pending'


T=0.1s (Terminal A, Worker 12345):

Polls database, finds task1
Claims it (sets status='processing')
Executes: echo Start
Prints output: [job task1] STDOUT: Start
Marks as status='completed'


T=0.2s (Terminal B): queuectl status

Queries database
Shows: completed: 1




Stopping Workers Safely
Option 1: Graceful Shutdown (Recommended)
From Terminal B:
powershellqueuectl worker stop
```

**What happens:**
- Sends SIGTERM/SIGINT to all worker PIDs
- Workers finish current jobs before exiting
- Heartbeat files cleaned up
- Workers.pids file deleted

**Terminal A** output:
```
[worker 12345] stopped.
[worker 12346] stopped.
```

### **Option 2: Force Kill**

In **Terminal A**, press:
```
Ctrl + C
What happens:

Immediate shutdown (may interrupt jobs mid-execution)
Jobs in processing state remain stuck
Heartbeat files may not be cleaned up


Why Not Use Background Processes?
You might wonder: "Can't we just run workers in the background and use one terminal?"
Answer: Yes, technically, but it complicates management:
powershell# Start workers in background (Windows)
Start-Job -ScriptBlock { queuectl worker start --count 2 }
Problems:

Harder to see worker logs in real-time
More complex to stop workers (need to track job IDs)
No visibility into what's happening
Loses educational value (can't see the queue in action)

For production: Use proper process managers like:

Windows: NSSM, Windows Services
Linux: systemd, supervisord, PM2
Cloud: Docker containers, Kubernetes pods

But for development and testing, two terminals is clearest.

Real-World Analogy
Think of it like a restaurant:
ComponentRestaurant EquivalentWorkers (Terminal A)Kitchen staff - continuously working on ordersJob Queue (Database)Order tickets on the railCLI (Terminal B)Waitstaff taking new orders and checking order status
You need both:

Kitchen staff must keep working (can't stop to take orders)
Waitstaff must be free to interact with customers


Common Mistakes
 Mistake 1: Closing Terminal A
powershell# Terminal A
queuectl worker start --count 2
# User closes this terminal 
Result: Workers killed → No job processing
Mistake 2: Running Workers and Commands in Same Terminal
powershellqueuectl worker start --count 2
# Terminal is now blocked...
# Cannot type: queuectl status 
 Correct Approach
powershell# Terminal A: Start workers (leave running)
queuectl worker start --count 2

# Terminal B: Execute commands freely
queuectl enqueue --id job1 --command "..."
queuectl status
queuectl worker stop  # Stops workers in Terminal A

### Initialize Database

The database is automatically created on first CLI invocation:

```bash
queuectl status
```

This creates `job.db` in the project root with the required schema.

---

## CLI Usage

### Enqueue a Job

Add a job to the queue:

```bash
queuectl enqueue --id job1 --command "timeout /T 2 /NOBREAK"
```

**Output**:
```
[ENQUEUE] Job job1 added.
Enqueued job job1
```

Replace an existing job with the same ID:

```bash
queuectl enqueue --id job1 --command "timeout /T 3 /NOBREAK" --replace
```

**Options**:
- `--id`: Unique job identifier (required)
- `--command`: Shell command to execute (required)
- `--max-retries`: Override default retry limit (optional)
- `--replace`: Replace existing job with same ID (optional)

### Start Workers

Launch background worker processes:

```bash
queuectl worker start --count 3
```

**Output**:
```
Started 3 worker(s): [12345, 12346, 12347]
```

Workers will:
- Poll for pending jobs every 0.1 seconds
- Execute commands and print stdout/stderr
- Write heartbeat files to `data/worker-{PID}.hb`

### Stop Workers

Gracefully terminate all workers:

```bash
queuectl worker stop
```

**Output**:
```
Workers signaled to stop.
```

### Check System Status

View queue summary and active workers:

```bash
queuectl status
```

**Output**:
```
Workers: 3 active
total: 15
pending: 8
processing: 2
completed: 3
failed: 2
```

### List Jobs

Show all jobs or filter by state:

```bash
# List all jobs
queuectl list

# Filter by state
queuectl list --state pending
queuectl list --state processing
queuectl list --state completed
queuectl list --state failed
```

**Output**:
```
job1 | timeout /T 2 /NOBREAK | completed | attempts=0 | next_run_at=None
job2 | bad_command | failed | attempts=2 | next_run_at=2025-11-09 14:32:15.123456
job3 | timeout /T 5 /NOBREAK | processing | attempts=1 | next_run_at=None
```

### Manage Dead-Letter Queue

#### List Failed Jobs

```bash
queuectl dlq list
```

**Output**:
```
job_fail | not_a_real_command | Command not found | failed_at=2025-11-09 14:30:00.123456
job_y | invalid_cmd | Connection timeout | failed_at=2025-11-09 14:28:30.654321
```

#### Retry a Dead Job

Move a job from DLQ back to the active queue:

```bash
queuectl dlq retry job_fail
```

**Output**:
```
Moved job job_fail back to queue
```

### Configure System Parameters

#### Set Configuration

```bash
# Change exponential backoff base
queuectl config set backoff-base 2

# Change default max retries
queuectl config set max-retries 3
```

**Output**:
```
backoff-base=2
```

#### Get Configuration

```bash
queuectl config get max-retries
```

**Output**:
```
3
```

**Available Settings**:
- `backoff-base`: Exponential backoff multiplier (default: 2.0)
- `max-retries`: Maximum retry attempts before DLQ (default: 3)

### Delete a Job

Remove a job from the active queue:

```bash
queuectl jobs delete job1
```

**Output**:
```
deleted
```

---

## Persistence & Fault Tolerance

### Restart Behavior

queuectl is designed to survive process interruptions:

- **Jobs persist**: All job state stored in SQLite database
- **Workers restart cleanly**: Stopped jobs return to `pending` state
- **Retry schedules preserved**: `next_run_at` timestamps respected after restart
- **DLQ maintained**: Failed jobs remain in dead-letter queue

**Example scenario**:
1. Enqueue job with command that takes 30 seconds
2. Worker starts executing (status: `processing`)
3. Kill worker process (Ctrl+C)
4. Job remains in database as `processing`
5. Restart worker → job is not re-claimed (status still `processing`)
6. Manual intervention: delete and re-enqueue, or reset status to `pending`

**Note**: Currently, jobs in `processing` state during worker crash require manual cleanup. Future enhancement could add automatic timeout detection.

### Retry Logic Example

```bash
# Enqueue a job that will fail
queuectl enqueue --id retry_test --command "not_a_real_command"

# Start worker
queuectl worker start
```

**Worker Output**:
```
[worker 12345] running job 'retry_test': not_a_real_command
[job retry_test] STDERR:
'not_a_real_command' is not recognized as an internal or external command
[worker 12345] job 'retry_test' failed (attempts=1); retry in 2.00s
[worker 12345] job 'retry_test' failed (attempts=2); retry in 3.00s
[worker 12345] job 'retry_test' failed (attempts=3); retry in 3.00s
[worker 12345] job 'retry_test' -> DLQ (attempts=3)
```

Delays follow exponential backoff: 2s, 4s, 8s... (capped at 3s by default in worker loop).

---

## Testing

### Run Test Suite

```bash
pytest tests/test_queue_flow.py -v
```

Run with output visibility (shows print statements):

```bash
pytest tests/test_queue_flow.py -s
```

### Test Coverage

The test suite validates:

1. **Basic Enqueue/List**: Jobs added correctly with default state
2. **State Filtering**: Jobs queryable by lifecycle state
3. **Retry Scheduling**: `next_run_at` calculated correctly with exponential backoff
4. **Claim Blocking**: Workers don't claim jobs before scheduled retry time
5. **DLQ Movement**: Jobs exhausting retries moved to dead-letter queue
6. **DLQ Retry**: Dead jobs restored to active queue with reset counters
7. **Concurrent Claims**: No duplicate claiming in race conditions

**Expected Output** (excerpt):
```
test_queue_flow.py::test_enqueue_and_list PASSED
test_queue_flow.py::test_multiple_enqueue_and_filter_by_state PASSED
test_queue_flow.py::test_retry_logic_schedules_next_run PASSED
test_queue_flow.py::test_worker_does_not_claim_job_before_next_run PASSED
test_queue_flow.py::test_failed_job_moves_to_dlq PASSED
test_queue_flow.py::test_retry_from_dlq PASSED
test_queue_flow.py::test_concurrent_claim_safety PASSED
```

### Manual Testing Workflow

```bash
# Terminal 1: Start workers
queuectl worker start --count 3

# Terminal 2: Add jobs
queuectl enqueue --id test1 --command "timeout /T 2 /NOBREAK"
queuectl enqueue --id test2 --command "timeout /T 3 /NOBREAK"
queuectl enqueue --id test3 --command "not_a_real_command"  # Will fail and retry

# Monitor status
queuectl status
queuectl list --state processing
queuectl list --state completed

# Check DLQ after test3 exhausts retries
queuectl dlq list
queuectl dlq retry test3  # Retry the failed job

# Stop workers
queuectl worker stop
```

### Complete Test Scenario

**1. Basic Successful Job**
```bash
# Enqueue a simple job
queuectl enqueue --id job1 --command "timeout /T 2 /NOBREAK"

# Start workers
queuectl worker start --count 2

# Observe execution
queuectl status
queuectl list --state processing
queuectl list --state completed
```

**2. Failed Job → Retry → Exponential Backoff**
```bash
# Enqueue a job that will fail
queuectl enqueue --id job_fail --command "not_a_real_command"

# Watch processing and retries
queuectl status
queuectl list --state failed

# Job will retry with exponential delays: 2s, 4s, 8s...
```

**3. Exhausted Retries → DLQ**
```bash
# Configure retry settings
queuectl config set max-retries 3
queuectl config set backoff-base 2

# Wait for job_fail to exhaust retries and move to DLQ
queuectl dlq list
```

**4. Retry from DLQ**
```bash
queuectl dlq retry job_fail
queuectl list --state pending  # Job reappears with reset counters
```

**5. Test Multiple Workers (No Duplicate Processing)**
```bash
queuectl enqueue --id jobA --command "timeout /T 3 /NOBREAK"
queuectl enqueue --id jobB --command "timeout /T 3 /NOBREAK"
queuectl enqueue --id jobC --command "timeout /T 3 /NOBREAK"

queuectl worker start --count 3
queuectl status
queuectl list --state processing

# Workers should process different jobs — no job processed twice
```

**6. Persistence Across Restart**
```bash
# Stop workers
queuectl worker stop

# Restart workers
queuectl worker start --count 2

# Verify jobs persist
queuectl list --state pending
queuectl list --state completed
queuectl dlq list

# Jobs persist because SQLite stores data in job.db
```

**7. Delete a Stuck Job**
```bash
queuectl jobs delete jobA
```

---

## Design Decisions & Assumptions

### Technology Choices

**SQLite Database**
- **Rationale**: Simple, zero-configuration, embedded database ideal for single-machine deployments
- **Tradeoff**: Not suitable for distributed systems (use PostgreSQL/Redis for multi-node setups)
- **Benefit**: Full ACID compliance, cross-platform, file-based persistence

**Click Framework**
- **Rationale**: Clean CLI interface with minimal boilerplate
- **Benefit**: Built-in help generation, argument parsing, error handling

**Subprocess for Execution**
- **Rationale**: Maximum flexibility—run any shell command
- **Tradeoff**: Security risk if job commands come from untrusted sources
- **Mitigation**: Assume trusted input; add validation layer for production use

### Simplicity Principles

1. **Minimal Dependencies**: Only SQLAlchemy and Click required
2. **Single-Machine Focus**: No network protocols or distributed coordination
3. **File-Based Heartbeats**: Simple liveness detection without complex IPC
4. **UTC Timestamps**: Avoid timezone issues with consistent UTC storage

### Retry Strategy

**Exponential Backoff**
- Formula: `delay = min(backoff_base ^ attempts, max_backoff_cap)`
- Default: 2^n seconds (2s, 4s, 8s, 16s...) capped at 3s in worker loop
- **Rationale**: Prevents thundering herd, gives external dependencies time to recover
- **Configurable**: Both base and cap adjustable per deployment needs

**Why UTC for next_run_at**
- Worker runs in UTC mode (`datetime.now(timezone.utc)`)
- Database stores UTC timestamps
- Avoids DST transitions and timezone conversion bugs

### Limitations & Trade-offs

- **No job priorities**: FIFO ordering only (oldest first)
- **No scheduled/cron jobs**: Only immediate or retry-scheduled execution
- **Limited observability**: Basic stdout/stderr capture, no structured logging
- **Processing state limbo**: Crashed workers leave jobs in `processing` state indefinitely
- **Single database file**: Concurrent write performance limited by SQLite

---

## Optional Enhancements

### High-Priority Improvements

1. **Job Priorities**
   - Add `priority` column to Job model
   - Modify `claim_next_job` to order by priority DESC, then created_at ASC

2. **Scheduled Jobs**
   - Add `scheduled_at` field for future execution
   - Extend claim logic: `AND (scheduled_at IS NULL OR scheduled_at <= now())`

3. **Stale Job Recovery**
   - Add `claimed_at` timestamp when job enters `processing`
   - Background task resets jobs where `processing AND (now - claimed_at) > timeout`

4. **Structured Logging**
   - Replace print statements with Python logging module
   - Add JSON formatter for machine-readable logs
   - Log rotation and archival

### Medium-Priority Features

5. **Web Dashboard**
   - Flask/FastAPI UI to visualize queue state
   - Real-time job monitoring with WebSocket updates
   - Manual job controls (pause, cancel, edit)

6. **Job Dependencies**
   - Define job graphs (job B runs after job A completes)
   - Topological execution ordering

7. **Metrics & Alerting**
   - Prometheus exporter for job counts, latency, error rates
   - PagerDuty/email alerts for DLQ threshold breaches

8. **Result Storage**
   - Store stdout/stderr in database for historical analysis
   - Optional S3/blob storage for large outputs

### Low-Priority Enhancements

9. **Job Timeout Enforcement**
   - Kill jobs exceeding max execution time
   - Configurable per job or globally

10. **Webhook Notifications**
    - POST job status updates to external URLs
    - Completion/failure callbacks

11. **CLI Autocomplete**
    - Shell completion for bash/zsh
    - Interactive job ID selection

12. **Database Migration Tool**
    - Alembic integration for schema versioning
    - Safe upgrades for production systems

---

## License

This project is provided as-is for demonstration purposes.

---

## Support

For questions or issues, please review the code documentation in `flam/` modules or extend the test suite to verify expected behavior.

