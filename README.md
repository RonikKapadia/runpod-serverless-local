# 🚀 RunPod Serverless Local

Run your RunPod Serverless handlers locally with realistic worker management, isolated Docker containers, and dynamic scaling.

## ✨ What Makes This Different?

The official RunPod SDK's `run()` simply executes your handler and waits. **This system emulates the real RunPod platform** — each job spins up in its own isolated Docker container, workers scale between min/max limits, and everything integrates seamlessly with Docker Compose.

### 🎯 Key Features

- **🐳 True Container Isolation** — Every job runs in a fresh Docker container, just like production
- **📊 Dynamic Worker Scaling** — Automatically scales from `min_workers` to `max_workers` based on demand
- **⏱️ Worker Cooldown** — Idle workers gracefully terminate after a configurable cooldown
- **🔌 Docker Compose Native** — Workers appear in Docker Desktop and share networks with your other services
- **🎮 GPU Support** — Pass GPU access through to worker containers
- **🏗️ Hot Reload** — Build handlers from source on startup for rapid development
- **📡 API Compatible** — Drop-in replacement for RunPod's `/run`, `/runsync`, `/status`, `/cancel`, `/health` endpoints

## 🚀 Quick Start

### 1. Build the Server Image

```bash
docker build -t runpod-serverless-local:latest -f Dockerfile .
```

### 2. Create a Docker Compose File

```yaml
services:
  serverless:
    image: runpod-serverless-local:latest
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      ENDPOINTS: >
        [
          {
            "endpoint_id": "my-handler",
            "image": "my-handler-image:latest",
            "min_workers": 1,
            "max_workers": 3,
            "worker_cooldown": 30
          }
        ]
```

### 3. Start It Up

```bash
docker compose up
```

### 4. Submit a Job

```bash
curl -X POST http://localhost:8000/my-handler/runsync \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "Hello, World!"}}'
```

## 📋 How It Works

```
┌─────────────────────────────────────────────────────┐
│  Your Code → API Request → Manager → Docker Worker  │
│                                                      │
│  1. Submit job to /run or /runsync                   │
│  2. Manager finds or creates a worker container      │
│  3. Job executes inside isolated container           │
│  4. Results returned, worker goes idle               │
│  5. Idle worker terminates after cooldown            │
└─────────────────────────────────────────────────────┘
```

Workers show up in Docker Desktop with names like `my-handler-1`, `my-handler-2`, making it easy to monitor logs and debug issues.

## ⚙️ Configuration

Endpoints are configured via the `ENDPOINTS` environment variable as a JSON array:

### Single Endpoint

```json
[
  {
    "endpoint_id": "my-handler",
    "image": "my-handler:latest",
    "min_workers": 1,
    "max_workers": 3,
    "worker_cooldown": 30.0,
    "execution_timeout_ms": 600000,
    "gpu": false
  }
]
```

### Multiple Endpoints 🎯

```json
[
  {
    "endpoint_id": "text-generation",
    "image": "llm-handler:latest",
    "min_workers": 0,
    "max_workers": 2,
    "gpu": true
  },
  {
    "endpoint_id": "image-processing",
    "image": "cv-handler:latest",
    "min_workers": 1,
    "max_workers": 5,
    "worker_cooldown": 60
  },
  {
    "endpoint_id": "data-pipeline",
    "build": {
      "context": "/app/handlers/data-pipeline",
      "dockerfile": "Dockerfile"
    },
    "min_workers": 1,
    "max_workers": 1
  }
]
```

### Configuration Options

| Option                 | Type   | Default      | Description                                            |
| ---------------------- | ------ | ------------ | ------------------------------------------------------ |
| `endpoint_id`          | string | **required** | Unique identifier for the endpoint                     |
| `image`                | string | `null`       | Docker image for workers (required if `build` not set) |
| `build`                | object | `null`       | Build configuration (see below)                        |
| `min_workers`          | int    | `1`          | Minimum workers to keep running                        |
| `max_workers`          | int    | `1`          | Maximum workers allowed                                |
| `worker_cooldown`      | float  | `10.0`       | Seconds before idle workers terminate                  |
| `execution_timeout_ms` | int    | `600000`     | Job timeout in milliseconds                            |
| `low_priority`         | bool   | `false`      | Low priority jobs wait for spare workers               |
| `ttl_ms`               | int    | `86400000`   | How long to keep job results                           |
| `gpu`                  | bool   | `false`      | Enable GPU access                                      |
| `volumes`              | list   | `null`       | Volume mounts (`"/host:/container:mode"`)              |
| `environment`          | dict   | `null`       | Environment variables for workers                      |

### Build Configuration (Hot Reload) ⚠️

```json
{
  "endpoint_id": "dev-endpoint",
  "build": {
    "context": "/app/my-handler",
    "dockerfile": "Dockerfile",
    "target": "dev"
  }
}
```

> ⚠️ **Warning**: The `build` option rebuilds the image **on every server startup**. This can be slow for large images. Use pre-built images (`image` field) for faster startup in production-like environments.

## 🔧 Local Development with Volume Mounts

For true hot-reload development (code changes without rebuild), you need to mount your handler code through the serverless container to the workers:

```yaml
services:
  serverless:
    image: runpod-serverless-local:latest
    ports:
      - "8000:8000"
    volumes:
      # Required: Docker socket access
      - /var/run/docker.sock:/var/run/docker.sock
      # Mount your handler code into the serverless container
      - ./my-handler:/app/my-handler:ro
    environment:
      ENDPOINTS: >
        [
          {
            "endpoint_id": "dev-handler",
            "image": "my-dev-image:latest",
            "min_workers": 0,
            "max_workers": 2,
            "volumes": ["/app/my-handler:/handler:ro"],
            "environment": {"PYTHONPATH": "/handler"}
          }
        ]
```

How it works:
1. Your host `./my-handler` → mounts to serverless container at `/app/my-handler`
2. Serverless container's `/app/my-handler` → mounts to worker at `/handler`
3. Worker sees live code changes without rebuild

> 📝 **Note**: This is a bit complex due to the "container creating containers" pattern. The path in `volumes` must match where the serverless container sees the code, not your host path.

## 📡 API Reference

| Endpoint                         | Method | Description                                 |
| -------------------------------- | ------ | ------------------------------------------- |
| `/{endpoint_id}/run`             | POST   | Async job — returns immediately with job ID |
| `/{endpoint_id}/runsync`         | POST   | Sync job — waits and returns result         |
| `/{endpoint_id}/status/{job_id}` | GET    | Check job status and output                 |
| `/{endpoint_id}/cancel/{job_id}` | POST   | Cancel a running/queued job                 |
| `/{endpoint_id}/health`          | GET    | Worker and job statistics                   |

### Examples

**Async Job:**
```bash
curl -X POST http://localhost:8000/my-handler/run \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "Hello!"}}'
# → {"id": "abc-123", "status": "IN_QUEUE"}
```

**Check Status:**
```bash
curl http://localhost:8000/my-handler/status/abc-123
# → {"id": "abc-123", "status": "COMPLETED", "output": "..."}
```

**Sync Job:**
```bash
curl -X POST http://localhost:8000/my-handler/runsync \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "Hello!"}}'
# → {"id": "abc-123", "status": "COMPLETED", "output": "...", "delay_time": 1200}
```

## 🐍 Using with RunPod Python SDK

```python
import runpod

# Point to local server
runpod.endpoint_url_base = "http://localhost:8000"
runpod.api_key = "not-needed-locally"

endpoint = runpod.Endpoint("my-handler")

# Submit job
job = endpoint.run({"prompt": "Hello, World!"})

# Get results
output = job.output(timeout=60)
print(output)
```

## 🏗️ Creating a Handler

Standard RunPod handler pattern:

```python
import runpod

def handler(event):
    input_data = event['input']
    prompt = input_data.get('prompt')
    
    # Your processing logic here
    result = f"Processed: {prompt}"
    
    return result

if __name__ == '__main__':
    runpod.serverless.start({'handler': handler})
```

**Dockerfile:**
```dockerfile
FROM python:3.10-slim
RUN pip install runpod
COPY handler.py .
CMD ["python", "-u", "handler.py"]
```

## 🧹 Known Issues

### Worker Containers on Shutdown

Sometimes worker containers don't get cleaned up immediately when you run `docker compose down`. They **will be removed automatically on the next startup** (the server clears old containers with matching labels before creating new ones).

If you need to clean up manually:
```bash
docker ps -a --filter "label=runpod_local_endpoint_id" -q | xargs docker rm -f
```

## 🐛 Troubleshooting

**Workers not starting:**
- Check Docker socket is mounted: `volumes: [/var/run/docker.sock:/var/run/docker.sock]`
- Verify handler image exists: `docker images | grep my-handler`

**Jobs timing out:**
- Check handler logs: `docker logs my-handler-1`
- Increase `execution_timeout_ms` in config

**GPU not working:**
- Enable GPU in Docker Desktop settings
- Install NVIDIA Container Toolkit on Linux
- Set `gpu: true` in endpoint config

## 📝 License

MIT
