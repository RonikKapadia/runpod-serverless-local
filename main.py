from contextlib import asynccontextmanager

from fastapi import FastAPI

from src import RunpodServerlessLocal
from src.schema import RunResponse, RunSyncResponse, StatusResponse, CancelResponse, HealthResponse, RunSyncRequest, RunRequest
from config import CONFIG

# Create Runpod Serverless
runpod_serverless_local = RunpodServerlessLocal()

# Add Endpoints
for endpoint_config in CONFIG.ENDPOINTS:
    runpod_serverless_local.create_endpoint(endpoint_config)

# Startup/Shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    runpod_serverless_local.startup()
    yield
    runpod_serverless_local.shutdown()

# App
app = FastAPI(lifespan=lifespan)

# Run sync
@app.post(
    path="/{endpoint_id}/run_sync",
    response_model=RunSyncResponse
)
async def run_sync(
    endpoint_id: str,
    run_sync_request: RunSyncRequest,
):
    endpoint = runpod_serverless_local.get_endpoint(endpoint_id)
    run_sync_response = await endpoint.run_sync(run_sync_request)
    return run_sync_response

# Run
@app.post(
    path="/{endpoint_id}/run",
    response_model=RunResponse
)
async def run(
    endpoint_id: str,
    run_request: RunRequest,
):
    endpoint = runpod_serverless_local.get_endpoint(endpoint_id)
    run_response = await endpoint.run(run_request)
    return run_response

# Status
@app.get(
    path="/{endpoint_id}/status/{job_id}",
    response_model=StatusResponse
)
async def status(
    endpoint_id: str,
    job_id: str,
):
    endpoint = runpod_serverless_local.get_endpoint(endpoint_id)
    status_response = await endpoint.status(job_id)
    return status_response

# Cancel
@app.post(
    path="/{endpoint_id}/cancel/{job_id}",
    response_model=CancelResponse
)
async def cancel(
    endpoint_id: str,
    job_id: str,
):
    endpoint = runpod_serverless_local.get_endpoint(endpoint_id)
    cancel_response = await endpoint.cancel(job_id)
    return cancel_response

# Health
@app.get(
    path="/{endpoint_id}/health",
    response_model=HealthResponse
)
async def health(
    endpoint_id: str,
):
    endpoint = runpod_serverless_local.get_endpoint(endpoint_id)
    health_response = await endpoint.health()
    return health_response

# Main
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)