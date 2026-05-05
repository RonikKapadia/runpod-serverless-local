from typing import Any
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel, Field

# Job Status
class JobStatus(str, Enum):
    IN_QUEUE = "IN_QUEUE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"

# Job
class Job(BaseModel):    
    # id
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    worker_id: str | None = None

    # config
    execution_timeout_ms: int
    low_priority: bool
    ttl_ms: int
    webhook: str | None = None

    # data
    input: dict
    output: Any | None = None

    # status
    status: JobStatus

    # time
    create_time_ms: int
    start_time_ms: int | None = None
    finish_time_ms: int | None = None