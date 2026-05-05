from pydantic import BaseModel
from typing import Any

from .job import JobStatus

### Requests ###

# Run
class RunSyncRequest(BaseModel):
    class Policy(BaseModel):
        executionTimeout: int | None = 600000
        lowPriority: bool | None = False
        ttl: int | None = 86400000
    input: dict
    policy: Policy | None = None
    webhook: str | None = None

# Run
class RunRequest(BaseModel):
    class Policy(BaseModel):
        executionTimeout: int | None = 600000
        lowPriority: bool | None = False
        ttl: int | None = 86400000
    input: dict
    policy: Policy | None = None
    webhook: str | None = None

### Responses ###

# Run Sync
class RunSyncResponse(BaseModel):
    id: str
    status: JobStatus
    output: Any
    delay_time: int | None = None
    execution_time: int | None = None

# Run
class RunResponse(BaseModel):
    id: str
    status: JobStatus

# Status
class StatusResponse(BaseModel):
    id: str
    status: JobStatus
    output: Any
    delay_time: int | None = None
    execution_time: int | None = None

# Cancel
class CancelResponse(BaseModel):
    id: str
    status: JobStatus

# Health
class HealthResponse(BaseModel):
    class JobsInfo(BaseModel):
        completed: int = 0
        failed: int = 0
        inProgress: int = 0
        inQueue: int = 0
        retried: int = 0
    class WorkersInfo(BaseModel):
        idle: int = 0
        running: int = 0
    jobs: JobsInfo = JobsInfo()
    workers: WorkersInfo = WorkersInfo()