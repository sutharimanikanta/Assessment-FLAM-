from sqlalchemy import Column, Integer, Text, String
from sqlalchemy.types import DateTime
from datetime import datetime
from .base import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    command = Column(Text, nullable=False)

    # pending, processing, completed, failed
    status = Column(String, default="pending")
    attempts = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_error = Column(Text, nullable=True)

    # when the job becomes eligible to run again
    next_run_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeadJob(Base):
    __tablename__ = "dead_jobs"

    id = Column(String, primary_key=True)
    command = Column(Text)
    last_error = Column(Text, nullable=True)
    failed_at = Column(DateTime, default=datetime.utcnow)


class Config(Base):
    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
