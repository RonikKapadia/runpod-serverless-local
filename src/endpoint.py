# Imports
import asyncio
import socket
import logging

log = logging.getLogger("uvicorn.error")
log.setLevel(logging.INFO)

import httpx
from pydantic import BaseModel

# Docker imports
import docker
from docker.models.containers import Container
from docker.models.networks import Network
from docker.errors import APIError, NotFound
from docker.types import DeviceRequest

# Docker
client = docker.from_env()

# Local imports
from .utils import time_ms
from .job import Job, JobStatus
from .worker import Worker, WorkerStatus

# Schema
from .schema import RunSyncRequest, RunRequest
from .schema import RunSyncResponse, RunResponse, StatusResponse, CancelResponse, HealthResponse

# Endpoint config
class BuildConfig(BaseModel):
    context: str
    dockerfile: str | None = None
    target: str | None = None

class EndpointConfig(BaseModel):
    endpoint_id: str
    image: str | None = None
    build: BuildConfig | None = None
    volumes: list[str] | None = None
    environment: dict[str, str] | None = None
    gpu: bool = False

    min_workers: int = 1
    max_workers: int = 1
    worker_cooldown: float = 10.0
    execution_timeout_ms: int = 600000
    low_priority: bool = False
    ttl_ms: int = 86400000

# Endpoint
class Endpoint:
    def __init__(
        self,
        endpoint_config: EndpointConfig,
    ):
        if (endpoint_config.image is None) and (endpoint_config.build is None):
            raise Exception("Endpoint must have either image or build")

        # Config
        self.endpoint_id = endpoint_config.endpoint_id
        self.docker_image: str = endpoint_config.image # type: ignore
        self.docker_build = endpoint_config.build
        self.docker_volumes = endpoint_config.volumes
        self.docker_gpu = endpoint_config.gpu

        # Workers
        self.workers: dict[str, Worker]
        self.min_workers = endpoint_config.min_workers
        self.max_workers = endpoint_config.max_workers
        self.worker_cooldown = endpoint_config.worker_cooldown

        # Jobs
        self.execution_timeout_ms = endpoint_config.execution_timeout_ms
        self.low_priority = endpoint_config.low_priority
        self.ttl_ms = endpoint_config.ttl_ms

        # Environment
        self.environment = endpoint_config.environment
        if self.environment is None: self.environment = {}
        self.environment['RUNPOD_REALTIME_PORT'] = "8000"

        # Docker
        self.docker_container: Container | None
        self.docker_network: Network
        self.docker_network_created: bool

    def startup(self):
        self.init_docker()
        self.init_workers()
        self.init_jobs()

    def shutdown(self):
        self.clean_docker()
    
    def init_docker(self):
        # Get container
        try:
            self.docker_container = client.containers.get(socket.gethostname())
        except NotFound: self.docker_container = None

        # Get network
        _docker_network = None
        if self.docker_container:
            # Get networks
            networks = list(self.docker_container.attrs['NetworkSettings']['Networks'].keys())
            if len(networks) > 0: _docker_network = client.networks.get(networks[0])

        # Create network
        self.docker_network_created = False
        if not _docker_network:
            try:
                _docker_network = client.networks.create(self.endpoint_id, driver="bridge")
            except APIError as e:
                if "already exists" not in str(e): raise
                _docker_network = client.networks.get(self.endpoint_id)
            self.docker_network_created = True
        
        # Set network
        self.docker_network = _docker_network

        # Connect container
        if self.docker_container and self.docker_network_created:
            self.docker_network.connect(self.docker_container)
        
        # Remove containers
        for container in client.containers.list(all=True, filters={'label': f'runpod_local_endpoint_id={self.endpoint_id}'}):
            container.remove(force=True, v=True)
        
        # Get project
        project = None
        if self.docker_container:
            project = self.docker_container.labels.get("com.docker.compose.project")
        
        # Build image
        if self.docker_build:
            # Get Tag
            if not self.docker_image:
                if project:
                    self.docker_image = f'{project}-{self.endpoint_id}:latest'
                else:
                    self.docker_image = f'{self.endpoint_id}:latest'
            
            # Build
            try:
                log.info(f"Building image: {self.docker_image}")
                image, logs = client.images.build(
                    path=self.docker_build.context,
                    dockerfile=self.docker_build.dockerfile,
                    tag=self.docker_image,
                    target=self.docker_build.target,
                    rm=True,
                    forcerm=True,
                )
                for chunk in logs:
                    if isinstance(chunk, dict) and 'stream' in chunk:
                        log.info(str(chunk['stream']).strip())
                    elif isinstance(chunk, dict) and 'error' in chunk:
                        log.info("ERROR:", chunk['error'])

            except Exception as e:
                raise RuntimeError(f"Failed to build image") from e
    
    def clean_docker(self):
        # Disconnect container
        try:
            if self.docker_container:
                self.docker_network.disconnect(self.docker_container)
        except NotFound: pass

        # Remove containers
        for container in client.containers.list(all=True, filters={'label': f'runpod_local_endpoint_id={self.endpoint_id}'}):
            container.remove(force=True, v=True)
    
        # Remove network
        if self.docker_network_created:
            self.docker_network.remove()
        
    def init_workers(self):
        self.workers: dict[str, Worker] = {}

        # Create workers
        for i in range(self.min_workers):
            worker = self.create_worker()
            self.workers[worker.worker_id] = worker
    
    def create_worker(self):
        # Create worker id
        worker_id = f'{len(self.workers) + 1}'

        # Get project
        project = None
        if self.docker_container:
            project = self.docker_container.labels.get("com.docker.compose.project")
        
        # Create worker labels
        labels = {}
        labels["runpod_local_endpoint_id"] = self.endpoint_id
        labels["com.docker.compose.project"] = "runpod_local"
        if self.docker_container:
            if project: labels["com.docker.compose.project"] = project

        # Create volumes
        volumes = None
        if self.docker_volumes:
            volumes = {}
            for volume in self.docker_volumes:
                # Split
                parts = volume.split(':', 2)

                # Inner and outer
                outer, inner = parts[0], parts[1]
                
                # Mode
                mode = 'rw'
                if len(parts) > 2:
                    mode = parts[2]

                # Add
                volumes[outer] = {
                    'bind': inner,
                    'mode': mode
                }
        
        # Create worker container
        device_request = None
        if self.docker_gpu == True:
            device_request = [
                DeviceRequest(
                    driver="nvidia",
                    count=-1,
                    capabilities=[["gpu"]]
                )
            ]
        docker_container = client.containers.run(
            image=self.docker_image,
            detach=True,
            network=self.docker_network.name,
            name=f'{self.endpoint_id}-{worker_id}',
            labels=labels,
            environment=self.environment,
            volumes=volumes,
            device_requests=device_request
        )

        # Return worker
        return Worker(
            worker_id=worker_id,
            docker_container=docker_container,
            status=WorkerStatus.IDLE
        )
    
    def stop_worker(self, worker_id):
        self.workers[worker_id].docker_container.stop()
        self.workers[worker_id].docker_container.start()

    def remove_worker(self, worker_id):
        if len(self.workers) <= self.min_workers: return
        self.workers[worker_id].docker_container.stop()
        self.workers[worker_id].docker_container.remove(force=True)
        del self.workers[worker_id]

    async def remove_worker_if_idle(self, worker_id, cooldown:float=10.0):
        await asyncio.sleep(cooldown)
        if self.workers[worker_id].status == WorkerStatus.IDLE:
            self.remove_worker(worker_id)
    
    def init_jobs(self):
        self.jobs: dict[str, Job] = {}
    
    def create_job(
        self,
        input,
        execution_timeout_ms: int | None = None,
        low_priority: bool | None = None,
        ttl_ms: int | None = None,
        webhook: str | None = None
    ):
        if execution_timeout_ms is None: execution_timeout_ms = self.execution_timeout_ms
        if low_priority is None: low_priority = self.low_priority
        if ttl_ms is None: ttl_ms = self.ttl_ms
        job = Job(
            execution_timeout_ms=execution_timeout_ms,
            low_priority=low_priority,
            ttl_ms=ttl_ms,
            webhook=webhook,

            input=input,
            status=JobStatus.IN_QUEUE,
            create_time_ms=time_ms(),
        )
        return job
    
    async def acquire_worker(self, low_priority=False):
        # Wait for worker
        while True:
            # If idle worker
            for worker_id in self.workers:
                worker = self.workers[worker_id]
                if worker.status == WorkerStatus.IDLE:
                    worker.status = WorkerStatus.RUNNING
                    return worker

            # If worker can be created
            if low_priority == False:
                if len(self.workers) < self.max_workers:
                    worker = self.create_worker()
                    self.workers[worker.worker_id] = worker
                    worker.status = WorkerStatus.RUNNING
                    return worker
            
            # Wait for 1 second
            await asyncio.sleep(1)
    
    async def submit_job(self, job: Job):
        # Acquire worker
        worker = await self.acquire_worker(job.low_priority)

        # Start job
        job.worker_id = worker.worker_id
        job.status = JobStatus.RUNNING
        job.start_time_ms = time_ms()

        try:
            # Run job
            async with httpx.AsyncClient() as client:
                run_sync_request = RunSyncRequest(input=job.input)

                response = await client.post(
                    f'http://{worker.docker_container.name}:8000/runsync',
                    json=run_sync_request.model_dump(mode='json'),
                    timeout=(job.execution_timeout_ms / 1000),
                )
                if response.status_code != 200: raise RuntimeError("Failed to run job")
                
                run_sync_response = RunSyncResponse.model_validate(response.json())

                job.status = run_sync_response.status
                job.output = run_sync_response.output

        # Timeout
        except httpx.TimeoutException:
            job.status = JobStatus.TIMEOUT

        # Failed
        except Exception as e:
            job.status = JobStatus.FAILED

        # Finish job
        job.worker_id = None
        job.finish_time_ms = time_ms()

        # Notify webhook
        if job.webhook:
            try:
                async with httpx.AsyncClient() as client:
                    status_response = StatusResponse(
                        id=job.job_id,
                        status=job.status,
                        output=job.output,
                        delay_time=job.finish_time_ms - job.create_time_ms,
                        execution_time=job.finish_time_ms - job.start_time_ms
                    )
                    await client.post(
                        job.webhook,
                        json=status_response.model_dump(mode='json')
                    )
            except httpx.HTTPError:
                pass
            
        # Release worker
        worker.status = WorkerStatus.IDLE

        # Remove worker after cooldown if idle
        asyncio.create_task(self.remove_worker_if_idle(worker.worker_id, self.worker_cooldown))
    
    async def stop_job(self, job: Job):
        # Check job
        if not job.worker_id: raise ValueError("Job is not running")
        if job.status != JobStatus.RUNNING: raise ValueError("Job is not running")

        # Check worker
        worker = self.workers[job.worker_id]
        if worker.status != WorkerStatus.RUNNING: raise ValueError("Worker is not running")

        # Stop job
        job.status = JobStatus.CANCELLED
        job.worker_id = None
        job.finish_time_ms = time_ms()

        # Release worker
        worker.status = WorkerStatus.IDLE

        # Stop worker
        worker.docker_container.stop()

        # Remove worker after cooldown if idle
        asyncio.create_task(self.remove_worker_if_idle(worker.worker_id, self.worker_cooldown))

    async def run_sync(self, run_sync_request: RunSyncRequest) -> RunSyncResponse:

        # Create job
        job = self.create_job(
            input=run_sync_request.input,
            execution_timeout_ms=run_sync_request.policy.executionTimeout if run_sync_request.policy else None,
            low_priority=run_sync_request.policy.lowPriority if run_sync_request.policy else None,
            ttl_ms=run_sync_request.policy.ttl if run_sync_request.policy else None,
            webhook=run_sync_request.webhook
        )
        self.jobs[job.job_id] = job
        
        # Run job
        await self.submit_job(job)

        # Return response
        return RunSyncResponse(
            id=job.job_id,
            status=job.status,
            output=job.output,
            delay_time=job.finish_time_ms - job.create_time_ms if job.finish_time_ms else None,
            execution_time=job.finish_time_ms - job.start_time_ms if job.finish_time_ms and job.start_time_ms else None
        )

    async def run(self, run_request: RunRequest) -> RunResponse:

        # Create job
        job = self.create_job(
            input=run_request.input,
            execution_timeout_ms=run_request.policy.executionTimeout if run_request.policy else None,
            low_priority=run_request.policy.lowPriority if run_request.policy else None,
            ttl_ms=run_request.policy.ttl if run_request.policy else None,
            webhook=run_request.webhook
        )
        self.jobs[job.job_id] = job
        
        # Run job
        asyncio.create_task(self.submit_job(job))

        # Return response
        return RunResponse(
            id=job.job_id,
            status=job.status,
        )

    async def status(self, job_id: str) -> StatusResponse:
        # Get job
        job = self.jobs.get(job_id)
        if not job: raise FileNotFoundError("Job not found")

        # Return response
        return StatusResponse(
            id=job.job_id,
            status=job.status,
            output=job.output,
            delay_time=job.finish_time_ms - job.create_time_ms if job.finish_time_ms else None,
            execution_time=job.finish_time_ms - job.start_time_ms if job.finish_time_ms and job.start_time_ms else None
        )
    
    async def cancel(self, job_id: str) -> CancelResponse:
        # Get job
        job = self.jobs.get(job_id)
        if not job: raise FileNotFoundError("Job not found")

        # Cancel job
        await self.stop_job(job)

        # Return response
        return CancelResponse(
            id=job.job_id,
            status=job.status
        )
    
    async def health(self) -> HealthResponse:
        return HealthResponse(
            jobs=HealthResponse.JobsInfo(
                completed=len([job for job in self.jobs.values() if job.status == JobStatus.COMPLETED]),
                failed=len([job for job in self.jobs.values() if job.status in [JobStatus.FAILED, JobStatus.TIMEOUT]]),
                inProgress=len([job for job in self.jobs.values() if job.status == JobStatus.RUNNING]),
                inQueue=len([job for job in self.jobs.values() if job.status == JobStatus.IN_QUEUE]),
                retried=0,
            ),
            workers=HealthResponse.WorkersInfo(
                idle=len([worker for worker in self.workers.values() if worker.status == WorkerStatus.IDLE]),
                running=len([worker for worker in self.workers.values() if worker.status == WorkerStatus.RUNNING]),
            )
        )