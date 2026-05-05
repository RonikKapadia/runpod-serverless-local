from enum import Enum
from docker.models.containers import Container

# Worker Status
class WorkerStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"

# Worker
class Worker:
    def __init__(self, worker_id: str, docker_container: Container, status: WorkerStatus):
        self.worker_id = worker_id
        self.docker_container = docker_container
        self.status = status