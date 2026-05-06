# Resume Parser API — Production Deployment Notes

> A complete reference for the work done turning a local FastAPI service into a deployed, observable, continuously-deployed AI service on Azure. Written for spaced-repetition review.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Concepts Learned](#3-concepts-learned)
4. [The Commands](#4-the-commands)
5. [The Dockerfile, Annotated](#5-the-dockerfile-annotated)
6. [The CI/CD Workflow, Annotated](#6-the-cicd-workflow-annotated)
7. [Debugging Stories](#7-debugging-stories)
8. [Mental Models Worth Keeping](#8-mental-models-worth-keeping)
9. [Self-Quiz for Spaced Repetition](#9-self-quiz-for-spaced-repetition)

---

## 1. Project Overview

A FastAPI service that extracts structured `CandidateProfile` objects from raw resume text using Google Gemini, with `instructor` enforcing a Pydantic schema as the response format. Containerized with Docker, deployed to Azure App Service (Linux containers) via a private Azure Container Registry, instrumented with Application Insights for full observability (auto-instrumented requests/dependencies plus custom OpenTelemetry metrics for token usage and failure rates), and continuously deployed via GitHub Actions on every push to `main`.

**The path:** local FastAPI → containerized → Azure resources → live URL → telemetry → CI/CD → custom metrics.

---

## 2. Architecture

### Runtime architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User / curl                              │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Azure App Service (West Europe)                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │   Front door (TLS termination, port 443 → container)      │  │
│  └───────────────────┬───────────────────────────────────────┘  │
│                      │                                           │
│  ┌───────────────────▼───────────────────────────────────────┐  │
│  │                  Container (port 8000)                     │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │           uvicorn --workers 2                        │  │  │
│  │  │  ┌──────────────┐  ┌──────────────┐                 │  │  │
│  │  │  │   Worker 1   │  │   Worker 2   │                 │  │  │
│  │  │  │   FastAPI    │  │   FastAPI    │                 │  │  │
│  │  │  │   /healthz   │  │   /healthz   │                 │  │  │
│  │  │  │   /extract   │  │   /extract   │                 │  │  │
│  │  │  └──────┬───────┘  └──────┬───────┘                 │  │  │
│  │  └─────────┼─────────────────┼─────────────────────────┘  │  │
│  │            └────────┬────────┘                            │  │
│  └─────────────────────┼─────────────────────────────────────┘  │
└────────────────────────┼─────────────────────────────────────────┘
                         │
                         ├──── Gemini API (Google) ──── extraction
                         │
                         └──── Azure Monitor ──────── telemetry
                              (Application Insights)
                              ↑
                              ├── auto-instrumented requests/deps
                              ├── Python logger output
                              └── custom OpenTelemetry metrics
```

### Code layering

```
schemas.py           ─┐
                      ├─ Domain layer (pure data)
api_models.py        ─┘

extraction_service.py ─── Business logic (calls Gemini, emits metrics)

main.py              ─── HTTP transport (FastAPI, exception → response mapping)

config.py            ─── Configuration (pydantic-settings)
```

**The principle:** each layer depends only on layers below it. `extraction_service` doesn't know about HTTP. `main.py` doesn't know about Gemini's API shape. Schemas don't know about anything.

### Azure resource hierarchy

```
Subscription (billing)
└── Resource Group: resume-parser-rg-n (UK South metadata)
    ├── Azure Container Registry: resumeparseracrn (UK South)
    ├── App Service Plan: resume-parser-plan-n (West Europe, B1 Linux)
    │   └── Web App: resume-parser-app-n (pulls image from ACR)
    ├── Log Analytics Workspace: resume-parser-logs-n (West Europe)
    └── Application Insights: resume-parser-insights-n (West Europe)
```

Resource groups are **logical** — resources inside can live in any region. The RG's "location" is just where its metadata is stored.

---

## 3. Concepts Learned

### 3.1 Web servers, ASGI, and concurrency

| Term | What it is |
|------|------------|
| **WSGI** | Old Python spec for synchronous web apps (Flask, old Django). One thread per request. |
| **ASGI** | Modern spec supporting `async`/`await`, WebSockets, lifespan events. FastAPI uses ASGI. |
| **Uvicorn** | An ASGI *server*. Speaks HTTP, runs your app, async-native. |
| **Gunicorn** | A *process manager* with web-server features. Originally WSGI, can run ASGI via worker classes. |

**The decision made:** uvicorn directly with `--workers 2`, no gunicorn. In container deployments, the orchestrator (App Service) handles supervision gunicorn used to provide.

**Workers vs threads vs async** — three different things that compose:
- Workers = processes (CPU parallelism, crash isolation)
- Threads = within-process concurrency for sync handlers (FastAPI threadpool)
- Async = within-thread concurrency for I/O-bound code

Two workers × ~40 threads each = ~80 concurrent in-flight requests before queueing.

**Resources:**
- [ASGI specification](https://asgi.readthedocs.io/en/latest/) — the actual spec
- [FastAPI documentation: Concurrency](https://fastapi.tiangolo.com/async/) — how FastAPI mixes sync/async
- [Uvicorn documentation](https://www.uvicorn.org/) — server reference
- [Real Python: Async IO](https://realpython.com/async-io-python/) — solid intro to Python's async model

---

### 3.2 Docker fundamentals

| Term | What it is |
|------|------------|
| **Dockerfile** | The recipe — text file with build instructions |
| **Image** | The frozen result — layered filesystem with app + deps |
| **Container** | A running instance of an image — isolated process |
| **Layer** | Each Dockerfile instruction creates one. Cached. Order matters. |
| **Build context** | The directory you point `docker build` at |
| **Registry** | A server that stores images (Docker Hub, ACR) |

**Key idioms learned:**

- **The dependency-layer trick**: copy `requirements.txt` and `pip install` *before* copying app code. Code changes don't bust the dependency cache.
- **Image tags are addresses**: `registry.example.com/image:tag` — the part before the first `/` routes the push/pull.
- **glibc vs musl**: use `python:3.12-slim-bookworm` (Debian, glibc-based) for Python apps. Avoid Alpine (musl) — pre-built Python wheels target glibc.
- **PID 1 and signal handling**: use `CMD ["uvicorn", ...]` (exec form, JSON array). Shell form wraps in `/bin/sh -c`, traps SIGTERM, doesn't propagate it.
- **Run as non-root**: create `appuser`, switch with `USER appuser` before `CMD`. Limits blast radius if compromised.

**Resources:**
- [Docker official tutorial](https://docs.docker.com/get-started/) — comprehensive starter
- [Dockerfile best practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/) — official guidance
- [Play with Docker](https://labs.play-with-docker.com/) — browser-based Docker sandbox, free
- [Docker Curriculum](https://docker-curriculum.com/) — solid learn-by-doing tutorial

---

### 3.3 Azure resource model

```
Subscription (billing boundary)
└── Resource Group (logical container, deployment boundary)
    ├── App Service Plan (the VM/compute capacity — what you pay for)
    │   └── Web App (your running app, uses the Plan's compute)
    ├── Azure Container Registry (private image store)
    └── (others: Key Vault, Application Insights, etc.)
```

**Plan vs Web App** — the decoupling matters: multiple Web Apps can share one Plan. Resize Plan without touching Web App. Move Web App between Plans.

**Key insights:**
- Resource groups are **logical**, not regional. Resources inside can live anywhere.
- Pay-as-you-go subscriptions have **per-region quotas per SKU family**. Hit a quota limit → pivot regions or request increase.
- Each Azure-to-Azure interaction has an identity question: managed identity > service principal > admin credentials, in order of strongest to weakest security posture.

**Resources:**
- [Azure App Service overview](https://learn.microsoft.com/en-us/azure/app-service/overview) — start here
- [Azure CLI reference](https://learn.microsoft.com/en-us/cli/azure/) — every `az` command documented
- [Azure architecture center](https://learn.microsoft.com/en-us/azure/architecture/) — patterns and reference architectures
- [Microsoft Learn: AZ-204](https://learn.microsoft.com/en-us/training/courses/az-204t00) — developer certification path, free to study

---

### 3.4 Secrets management

| Tier | What it is | When to use |
|------|------------|-------------|
| **App Settings** | Key-value pairs injected as env vars at container start | MVP. What's used here. |
| **Key Vault** | Dedicated secrets service with separate RBAC + audit logging | Real users / compliance |
| **Managed Identity** | Resource has its own Azure identity, granted RBAC roles | Eliminates stored credentials entirely |

**The principle:** simplest tier that meets your threat model. Climb leftward to right as the project hardens. Migration paths preserve env-var consumption in code.

**Resources:**
- [Azure Key Vault concepts](https://learn.microsoft.com/en-us/azure/key-vault/general/basic-concepts)
- [Key Vault references in App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references) — exact upgrade path
- [Managed identities overview](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)

---

### 3.5 Health checks: liveness vs readiness

- **Liveness** = "is the process alive?" Failure → restart container.
- **Readiness** = "is it ready to serve traffic?" Failure → take out of load balancer.

`/healthz` here is a **liveness check**: returns 200 fast, doesn't touch Gemini, doesn't depend on `instructor_client`. **Health checks should be boring** — a check that depends on Gemini turns Google's outage into your restart loop.

**Resources:**
- [Kubernetes probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — best explainer of the conceptual model, even outside k8s

---

### 3.6 Pydantic & pydantic-settings

- **Pydantic** = runtime data validation via type hints. Defines schemas as Python classes.
- **pydantic-settings** = reads config from env vars, `.env` files, secrets stores. Validates at startup.

**Key insight:** `env_file=".env"` is a *fallback*. Real env vars (from Azure App Service) win over the file. Same code works locally and in production with zero changes.

**Resources:**
- [Pydantic v2 documentation](https://docs.pydantic.dev/latest/) — primary reference
- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — config-specific
- [Pydantic v2 migration guide](https://docs.pydantic.dev/latest/migration/) — useful if you see v1 patterns in tutorials

---

### 3.7 Instructor + structured LLM output

`instructor` patches LLM clients to enforce a Pydantic schema as the response format. With Gemini, you get:
- Type-safe extraction
- Automatic retries when output fails validation
- Clean `InstructorRetryException` when retries exhaust

**Schema design philosophy worth keeping:** schemas describe what data *can* be, not what you wish it would be. Over-constrained required fields cause retry-induced hallucination. Use nullable fields with explicit null-fallback instructions in field descriptions.

**Resources:**
- [Instructor documentation](https://python.useinstructor.com/) — official docs with patterns
- [Instructor concepts: retries](https://python.useinstructor.com/concepts/retrying/) — how the retry loop works
- [Pydantic field descriptions as prompt instructions](https://python.useinstructor.com/concepts/prompting/) — micro-prompt pattern

---

### 3.8 Application Insights & OpenTelemetry

Three telemetry types:

| Type | What | App Insights table | Example |
|------|------|--------------------|---------|
| **Traces (spans)** | Operations with start/end | `requests`, `dependencies` | "this HTTP request took 1.8s" |
| **Logs** | Discrete text events | `traces` | "extraction failed after retries" |
| **Metrics** | Numerical measurements | `customMetrics` | "tokens used per request" |

App Insights' table naming is confusing: **`traces` = log messages**, not request traces (which live in `requests`). Microsoft's terminology predates OpenTelemetry's; never got renamed.

**Severity levels** in App Insights `traces`:

| severityLevel | Python equivalent |
|---|---|
| 0 | `logger.debug` |
| 1 | `logger.info` |
| 2 | `logger.warning` |
| 3 | `logger.error` |
| 4 | `logger.critical` |

**Metric types:**
- `Counter` — monotonically increasing (failure counts, request counts)
- `Histogram` — value distributions (latency, token counts)

**Custom metrics emitted in this project:**
- `extraction.duration_ms` — histogram, attributes: `model`, `status`
- `extraction.prompt_tokens` — histogram, attributes: `model`
- `extraction.completion_tokens` — histogram, attributes: `model`
- `extraction.failures` — counter, attributes: `model`, `reason` (`retry_exhausted` | `validation`)

**Principle:** proliferate *attributes* on a small set of well-named metrics, not metric names.

**Resources:**
- [Azure Monitor OpenTelemetry distro overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-overview)
- [OpenTelemetry Python documentation](https://opentelemetry.io/docs/languages/python/) — vendor-neutral fundamentals
- [KQL tutorial](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/tutorials/learn-common-operators) — the query language used in App Insights Logs
- [App Insights data model](https://learn.microsoft.com/en-us/azure/azure-monitor/app/data-model-complete) — what each table contains

---

### 3.9 GitHub Actions CI/CD

**Mental model:** GitHub spins up a fresh Ubuntu VM per workflow run. The VM is empty. Your workflow tells it what to do. Most workflows start with `actions/checkout@v4` to clone the repo onto the runner.

**Anatomy:**
- `name` — friendly name in UI
- `on` — trigger (push, PR, schedule, manual)
- `jobs` — units that run in parallel or with deps
- `runs-on` — runner OS
- `steps` — sequential actions
  - `uses` references published actions
  - `run` executes shell commands

**Tagging strategy used:** commit SHA. Always unique, always traceable, impossible to forget, impossible to collide. Plus a `latest` tag for human convenience.

**Secrets pattern:**
- Build-time secrets (ACR auth, Azure auth) → GitHub Secrets
- Runtime secrets (API keys) → App Service App Settings

**Service principal for Azure auth:** a non-human Azure identity scoped to your resource group. The runner authenticates as it.

**Resources:**
- [GitHub Actions documentation](https://docs.github.com/en/actions) — start here
- [GitHub Actions Marketplace](https://github.com/marketplace?type=actions) — reusable actions
- [Azure GitHub Actions](https://learn.microsoft.com/en-us/azure/developer/github/) — Azure-specific patterns
- [OIDC federation for GitHub Actions](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect) — production-grade auth upgrade path

---

### 3.10 GitOps / Infrastructure as Code

Workflows live inside the repo (`.github/workflows/*.yml`) because **deployment is part of the code**. Versioned, reviewable, branchable, revertible. Same principle generalizes to Terraform, Bicep, ARM templates, Helm charts, etc.

**Resources:**
- [What is GitOps?](https://about.gitlab.com/topics/gitops/) — concept overview
- [Terraform learn](https://developer.hashicorp.com/terraform/tutorials) — most popular IaC tool
- [Bicep documentation](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/) — Azure-native IaC

---

## 4. The Commands

Organized by phase. Every command actually used.

### 4.1 Local Docker

```bash
# Verify Docker is running
docker --version
docker info

# Build the image
docker build -t resume-parser:0.1 .

# List local images (Windows: findstr; Linux/Mac: grep)
docker images | findstr resume-parser

# Run the container locally
docker run --rm -p 8000:8000 -e GEMINI_API_KEY='...' resume-parser:0.1

# Inspect env var inside a running container (debugging)
docker run --rm -it -e VAR='value' --entrypoint /bin/bash IMAGE -c 'echo $VAR'
```

### 4.2 Azure CLI setup

```bash
az --version
az login                                    # opens browser
az account show                             # which subscription
az account set --subscription "<id>"        # switch sub
az resource list --resource-group RG --output table  # ground-truth verify
```

### 4.3 Create Azure resources

```bash
# Resource Group
az group create --name resume-parser-rg-n --location uksouth

# Azure Container Registry
az acr create \
  --resource-group resume-parser-rg-n \
  --name resumeparseracrn \
  --sku Basic \
  --admin-enabled true

# App Service Plan (Linux, B1)
az appservice plan create \
  --resource-group resume-parser-rg-n \
  --name resume-parser-plan-n \
  --sku B1 \
  --is-linux \
  --location westeurope

# Web App (placeholder image, will be reconfigured)
az webapp create \
  --resource-group resume-parser-rg-n \
  --plan resume-parser-plan-n \
  --name resume-parser-app-n \
  --deployment-container-image-name resumeparseracrn.azurecr.io/resume-parser:0.1
```

### 4.4 Push image to ACR

```bash
# Authenticate
az acr login --name resumeparseracrn

# Tag for registry
docker tag resume-parser:0.1 resumeparseracrn.azurecr.io/resume-parser:0.1

# Push
docker push resumeparseracrn.azurecr.io/resume-parser:0.1

# Verify
az acr repository list --name resumeparseracrn --output table
az acr repository show-tags --name resumeparseracrn --repository resume-parser --output table
```

### 4.5 Configure Web App container + env vars

```bash
# Capture ACR credentials (PowerShell)
$ACR_USER = az acr credential show --name resumeparseracrn --query "username" -o tsv
$ACR_PASS = az acr credential show --name resumeparseracrn --query "passwords[0].value" -o tsv

# Set container config (image + registry credentials)
az webapp config container set \
  --resource-group resume-parser-rg-n \
  --name resume-parser-app-n \
  --container-image-name resumeparseracrn.azurecr.io/resume-parser:0.X \
  --container-registry-url https://resumeparseracrn.azurecr.io \
  --container-registry-user $ACR_USER \
  --container-registry-password $ACR_PASS

# Set runtime env vars (App Settings)
az webapp config appsettings set \
  --resource-group resume-parser-rg-n \
  --name resume-parser-app-n \
  --settings \
    GEMINI_API_KEY='<key>' \
    GEMINI_MODEL=gemini-2.5-flash \
    LOG_LEVEL=INFO \
    WEBSITES_PORT=8000 \
    APPLICATIONINSIGHTS_CONNECTION_STRING='<connection-string>'
```

### 4.6 Verify and observe

```bash
# Web App resource state
az webapp show --resource-group RG --name APP --query "state" --output tsv

# Current container config
az webapp config container show --resource-group RG --name APP --output table

# Current app settings
az webapp config appsettings list --resource-group RG --name APP --output table

# Streaming logs (uses Kudu /logstream)
az webapp log tail --resource-group RG --name APP

# Snapshot logs (more reliable when streaming fails)
az webapp log download --resource-group RG --name APP --log-file logs.zip

# Hit the live URL
curl https://APP.azurewebsites.net/healthz
```

### 4.7 App Insights resources

```bash
# Log Analytics Workspace (storage layer)
az monitor log-analytics workspace create \
  --resource-group resume-parser-rg-n \
  --workspace-name resume-parser-logs-n \
  --location westeurope

# App Insights (linked to workspace)
az monitor app-insights component create \
  --app resume-parser-insights-n \
  --location westeurope \
  --resource-group resume-parser-rg-n \
  --workspace resume-parser-logs-n

# Get connection string
az monitor app-insights component show \
  --app resume-parser-insights-n \
  --resource-group resume-parser-rg-n \
  --query connectionString \
  --output tsv
```

### 4.8 Service principal for GitHub Actions

```bash
az ad sp create-for-rbac \
  --name "github-resume-parser-deployer" \
  --role contributor \
  --scopes /subscriptions/<sub-id>/resourceGroups/resume-parser-rg-n \
  --sdk-auth
# Returns JSON. Whole blob → AZURE_CREDENTIALS in GitHub Secrets.
```

### 4.9 Lifecycle management

```bash
# Pause Web App (Plan still bills)
az webapp stop --resource-group RG --name APP

# Resume
az webapp start --resource-group RG --name APP

# Force restart (after config change that didn't auto-apply)
az webapp restart --resource-group RG --name APP

# Nuclear option — delete EVERYTHING
az group delete --resource-group RG --yes --no-wait
```

### 4.10 KQL queries that are actually useful

```kusto
// Recent requests
requests
| where timestamp > ago(1h)
| project timestamp, name, resultCode, duration
| order by timestamp desc

// Recent warnings/errors
traces
| where timestamp > ago(1h)
| where severityLevel >= 2
| project timestamp, message, severityLevel
| order by timestamp desc

// Custom metrics summary
customMetrics
| where timestamp > ago(15m)
| where name startswith "extraction."
| summarize 
    count = count(),
    avg_value = avg(value),
    p95_value = percentile(value, 95)
    by name
| order by name

// Logs joined to their parent request (very useful)
traces
| where timestamp > ago(1h)
| where severityLevel >= 2
| project timestamp, message, severityLevel, operation_Id
| join kind=leftouter (
    requests
    | project operation_Id, request_name=name, request_url=url, resultCode
) on operation_Id
| order by timestamp desc
```

---

## 5. The Dockerfile, Annotated

```dockerfile
# Base image: Python 3.12 on slim Debian (glibc-based, ~150 MB).
# NOT alpine — musl libc breaks pre-built Python wheels.
FROM python:3.12-slim-bookworm

# Force unbuffered stdout (logs appear immediately) and skip .pyc files
# (useless in immutable containers).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Standard convention. Don't put code in / or /home.
WORKDIR /app

# THE CACHE TRICK: copy requirements first, install, THEN copy app code.
# Code changes don't bust the dependency-install layer. ~20s saved per build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app. Only this layer rebuilds on code changes.
COPY . .

# Run as non-root. Limits blast radius if compromised.
# Combined into one RUN to avoid an extra layer.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Documentation only — doesn't actually open the port.
EXPOSE 8000

# Exec form (JSON array). Critical for signal handling — uvicorn becomes
# PID 1 and receives SIGTERM directly. Shell form would trap signals in /bin/sh.
# --host 0.0.0.0 (NOT 127.0.0.1) — listen on all interfaces, otherwise
# nothing outside the container can reach it.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

### .dockerignore

```
.git/
.gitignore
.env                 # CRITICAL: never bake secrets into images
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
.venv/
venv/
tests/
*.md
Dockerfile
.dockerignore
```

---

## 6. The CI/CD Workflow, Annotated

`.github/workflows/deploy.yml`:

```yaml
name: Build and Deploy to Azure App Service

# Triggers on every push to main. Add PRs later if you want preview builds.
on:
  push:
    branches: [main]

# Workflow-level vars. Centralize values used in multiple steps.
env:
  IMAGE_NAME: resume-parser
  RESOURCE_GROUP: resume-parser-rg-n

jobs:
  deploy:
    # Free Ubuntu VM, fresh per run, destroyed after.
    runs-on: ubuntu-latest

    steps:
      # Runner starts empty. Clone the repo onto it.
      - name: Checkout code
        uses: actions/checkout@v4

      # Authenticate runner to Azure as the service principal.
      # AZURE_CREDENTIALS is the JSON blob from `az ad sp create-for-rbac --sdk-auth`.
      - name: Log in to Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      # Authenticate Docker to ACR using admin credentials.
      - name: Log in to Azure Container Registry
        uses: azure/docker-login@v2
        with:
          login-server: ${{ secrets.ACR_LOGIN_SERVER }}
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      # Build with TWO tags:
      # - commit SHA (immutable, traceable)
      # - 'latest' (mutable, human convenience)
      - name: Build and tag image
        run: |
          docker build -t ${{ secrets.ACR_LOGIN_SERVER }}/${{ env.IMAGE_NAME }}:${{ github.sha }} .
          docker tag ${{ secrets.ACR_LOGIN_SERVER }}/${{ env.IMAGE_NAME }}:${{ github.sha }} ${{ secrets.ACR_LOGIN_SERVER }}/${{ env.IMAGE_NAME }}:latest

      - name: Push image to ACR
        run: |
          docker push ${{ secrets.ACR_LOGIN_SERVER }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          docker push ${{ secrets.ACR_LOGIN_SERVER }}/${{ env.IMAGE_NAME }}:latest

      # Point App Service at the new SHA tag. This auto-triggers a restart.
      # Registry credentials are already configured in App Service from setup —
      # we only update the image reference per deploy.
      - name: Update App Service to use new image
        run: |
          az webapp config container set \
            --resource-group ${{ env.RESOURCE_GROUP }} \
            --name ${{ secrets.WEBAPP_NAME }} \
            --container-image-name ${{ secrets.ACR_LOGIN_SERVER }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
```

### GitHub Secrets required

| Secret | Value |
|---|---|
| `AZURE_CREDENTIALS` | JSON blob from `az ad sp create-for-rbac --sdk-auth` |
| `ACR_LOGIN_SERVER` | `resumeparseracrn.azurecr.io` |
| `ACR_USERNAME` | `resumeparseracrn` |
| `ACR_PASSWORD` | From `az acr credential show` |
| `WEBAPP_NAME` | `resume-parser-app-n` |

**Build-time secrets** (above) → GitHub Secrets.
**Runtime secrets** (`GEMINI_API_KEY`, `APPLICATIONINSIGHTS_CONNECTION_STRING`) → App Service App Settings.
Each tier holds only what it needs.

---

## 7. Debugging Stories

Each one is a self-contained mini-case-study. Worth re-reading; the lessons generalize.

### 7.1 Docker Desktop wasn't running

**Symptom:** `error during connect: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.`

**Diagnosis:** the named pipe is the Windows IPC channel between Docker CLI and Docker Engine (running inside Docker Desktop's Linux VM). "File not found" means the engine isn't there.

**Fix:** start Docker Desktop, wait for the whale icon to settle.

**Lesson:** read the error message *literally*. "Pipe not found" means "the thing on the other end of the pipe isn't running."

---

### 7.2 App Service Plan silently didn't create

**Symptom:** told to create RG, ACR, Plan. All "succeeded." Later command failed with "The plan doesn't exist."

**Diagnosis:** ran `az resource list` and only saw 1 resource. The Plan command had multi-line continuation with `^` but possibly missing on one line, executing as incomplete and not actually creating the resource.

**Fix:** re-ran the Plan create, hit a quota error this time, pivoted regions.

**Lesson:** **"succeeded" is not the same as "exists."** Always verify with a list/show query when something downstream complains.

---

### 7.3 Azure quota error

**Symptom:** `Operation cannot be completed without additional quota. Current Limit (Basic VMs): 0`.

**Diagnosis:** new pay-as-you-go subscriptions have per-region SKU quotas. UK South had 0 Basic VMs.

**Fix:** retried in West Europe, where quota was non-zero. Created cross-region setup (RG in UK South metadata, Plan in West Europe).

**Lesson:** quota errors are common in cloud, not bugs. Pivot regions or request increases. Cross-region resource groups are fine — the RG is logical.

---

### 7.4 504 Gateway Timeout on `az webapp log tail`

**Symptom:** log tail returned 504 from `<app>.scm.azurewebsites.net/logstream`.

**Diagnosis:** the `scm` subdomain is Kudu, App Service's diagnostic side-channel. Kudu couldn't stream logs because the container was failing to start (the typo bug below).

**Fix:** switched to `az webapp log download` for snapshot logs.

**Lesson:** when one observability tool fails, switch tools — don't fight it. Always have a fallback path.

---

### 7.5 The `azurecr.io` typo

**Symptom:** container failed to pull. Logs: `lookup resumeparseracrn.io: no such host`.

**Diagnosis:** image name was set to `resumeparseracrn.io/...` instead of `resumeparseracrn.azurecr.io/...`. DNS correctly reported the (truncated) hostname doesn't exist.

**Fix:** ran `az webapp config container show` to see actual stored value, then corrected with `container set`.

**Lessons:**
- **Read errors literally**, not figuratively. "No such host" = "wrong hostname." Not a network bug.
- **Verify state before changing it.** Don't fix-then-test if the typo is still in place.
- This kind of bug is why infrastructure-as-code (Terraform, Bicep) is valuable — identifiers composed programmatically.

---

### 7.6 Push happened on a stale auth token

**Symptom:** told App Service to use `0.2`, container pull failed with `manifest unknown` and `unauthorized`.

**Diagnosis:** ran `az acr repository show-tags` — only `0.1` was in ACR. The push for `0.2` either never ran or failed silently. Likely cause: `az acr login` token expires after ~3 hours.

**Fix:** `az acr login` again, push again, verify tag in ACR.

**Lesson:** **never let a 'command that should have worked' become a downstream assumption.** After every state-changing command, verify with a state-reading command. The principle: trust no command's exit code; verify with a read.

---

### 7.7 Connection string mangled in copy-paste

**Symptom:** `ValueError: Invalid instrumentation key. It should be a valid UUID.`

**Diagnosis:** locally reproduced the error, then carefully looked at the connection string. The first segment of the UUID had 7 hex characters instead of 8 — the portal copy operation had dropped one character.

**Fix:** re-grabbed via the portal's copy-to-clipboard button (not manual select).

**Lessons:**
- **Local-first debugging.** Reproducing in a fast feedback loop > debugging on cloud.
- **"I'm passing X. The system says X is invalid. Therefore the system is wrong"** — almost always wrong. X isn't what you think X is.
- **Always paste long credentials into a visible scratchpad first.** Visual verification is cheap.

---

### 7.8 FastAPI auto-instrumentation didn't fire

**Symptom:** Logs flowed to App Insights, but `requests` table was empty after deploy.

**Diagnosis:** `configure_azure_monitor` claims to auto-instrument FastAPI, but timing dependencies on import order can prevent the patch from attaching. Logs (which hook into Python's logging module) worked; request tracing (which patches FastAPI) didn't.

**Fix:** added explicit `FastAPIInstrumentor.instrument_app(app)` after FastAPI app creation.

**Lessons:**
- Monkey-patching is implicit; explicit instrumentation is reliable.
- When logs work but traces don't, you have two pipelines — debug them separately.

---

### 7.9 Warning logs missing because the path didn't run

**Symptom:** wrote `logger.warning` in `extract_text`'s exception handler, never saw it in App Insights `traces`.

**Diagnosis:** the test request didn't actually trigger `InstructorRetryException`. No exception → no warning → nothing to log.

**Fix:** confirmed by checking widened time window for prior logs, then noticed the warning code path simply didn't execute.

**Lesson:** when telemetry is missing, ask first whether the code path that *generates* the telemetry actually ran.

---

### 7.10 The seven debugging principles distilled

From the stories above, the principles in pure form:

1. **Verify upstream state explicitly.** Don't trust "succeeded."
2. **Read errors literally.** The message usually tells you exactly what's wrong.
3. **Bisect.** When confused, test locally. Reduce variables.
4. **When one tool fails, switch tools.** Don't fight observability.
5. **Local feedback loops > cloud feedback loops.** Always.
6. **What you're sending isn't always what you think.** Verify input boundaries.
7. **No telemetry ≠ broken telemetry.** Maybe the path didn't run.

---

## 8. Mental Models Worth Keeping

### 8.1 Layered architecture
Each layer depends only on layers below it. Domain (schemas) → service (extraction) → transport (HTTP). Cross-cutting concerns (config, observability) sit alongside, not above.

### 8.2 Observability has tiers
**The first thing observability needs to be reliable about is itself.** When App Insights breaks, you need a lower-level fallback (container logs). Never let observability be your only telemetry path.

### 8.3 Health checks are boring on purpose
The more a health check does, the more ways it can lie to you. A liveness check should fail only for reasons a restart could fix. External dependencies belong in real endpoints, not health probes.

### 8.4 Secrets management is a spectrum
App Settings → Key Vault references → Managed Identity. Use the simplest tier that meets your threat model. Migration paths preserve env-var consumption in code.

### 8.5 Identity is everywhere in cloud
Every resource-to-resource interaction asks "who is this acting as?" Admin credentials → service principals → managed identities, in order of weakest to strongest security posture.

### 8.6 Image tags are addresses
The hostname before the first `/` is where the pull goes. Authentication URL is separate from routing. Tags should be immutable in practice (commit SHA), even though Docker doesn't enforce it.

### 8.7 The dependency-layer trick
Docker layers cache from the first changed layer downward. Put rarely-changing things first. `COPY requirements.txt; pip install` before `COPY . .`. Saves 20+ seconds per rebuild.

### 8.8 Workers, threads, and async are three things
- Workers = processes (CPU parallelism, isolation)
- Threads = within-process concurrency for sync handlers
- Async = within-thread concurrency for I/O

They compose. Knowing which tool addresses which kind of bottleneck is senior-grade.

### 8.9 Defensive emission for telemetry
Telemetry code should never crash business logic. Guard against `None`, missing values, and exceptions. The metric is secondary; the request is primary.

### 8.10 Metric attributes > metric names
One metric `extraction.failures` with attribute `reason=retry_exhausted | validation` is better than two metrics `extraction.retry_failures` and `extraction.validation_failures`. Attributes let you slice; names just multiply.

### 8.11 GitOps: deployment is code
Your deployment process belongs in version control alongside the code that needs it. Versioned, reviewable, branchable, revertible. Portal clicks are none of those things.

### 8.12 Fail fast when failure is cheap
Don't pre-flight-check actions that are free to attempt and informative when they fail. The error message is usually the diagnosis.

---

## 9. Self-Quiz for Spaced Repetition

Use these for review. Answer from memory; check yourself against the relevant section.

### Conceptual

1. What's the difference between WSGI and ASGI? Which does FastAPI use, and why does that matter for an LLM-calling endpoint?
2. Why is `--workers 2` enough for this service? What controls per-worker concurrency?
3. Why is `python:3.12-slim-bookworm` preferred over `python:3.12-alpine` for Python apps?
4. What's the difference between liveness and readiness checks? Which is `/healthz`, and why doesn't it depend on the instructor client?
5. What does `--admin-enabled true` on ACR enable, and what's the production-grade upgrade path away from it?
6. Why is App Service Plan a separate resource from the Web App? What flexibility does this give you?
7. What does App Insights' `traces` table contain? What about `requests`? Why is the naming confusing?
8. When would you use a `Counter` vs a `Histogram` in OpenTelemetry?
9. Why is commit SHA preferred over manual versioning for image tags?
10. What's the difference between build-time and runtime secrets? Where does each live?

### Operational

11. If you change a single line in `main.py` and run `docker build`, which layers re-run and which are cached?
12. What env var tells App Service which container port to forward traffic to?
13. What happens if you set `WEBSITES_PORT=8080` but uvicorn binds to 8000?
14. Why use exec form `CMD ["uvicorn", ...]` instead of shell form `CMD uvicorn ...`?
15. After config changes via `az webapp config container set`, do you need to restart the app explicitly?
16. If `az webapp log tail` returns 504, what alternative log retrieval methods do you have?
17. What does `${{ github.sha }}` evaluate to in a workflow? Why is it useful as an image tag?
18. What's the role of the service principal in CI/CD? Why not use your personal credentials?

### Debugging scenarios

19. Container shows "Application Error" page. What's your first move? Second?
20. App Insights shows requests but no logs. Where do you look?
21. App Insights shows logs but no requests. Different problem — what's the likely cause?
22. The image you pushed yesterday isn't being pulled by App Service. Hypotheses?
23. `az acr repository show-tags` shows a tag, but App Service can't pull it. Possible causes?
24. Your local container fails on import with "Invalid instrumentation key." What's the diagnostic sequence?

### KQL

25. Write a KQL query that returns p95 latency of `/api/v1/extract` over the last 24 hours, broken down by hour.
26. Write a KQL query that joins traces (logs) with requests on `operation_Id`.
27. How would you find all warnings in the last hour, ordered by most recent?

### Mental models

28. State the principle behind "the first thing observability needs to be reliable about is itself."
29. Why are metric attributes preferred over multiplying metric names?
30. State why "succeeded" doesn't mean "exists" in cloud APIs, and the corresponding habit.

---

## End

This document is a snapshot of one project's worth of learning. Re-read it when context-switching back, when starting a similar deployment, or when an interview is coming up. Every command listed here was run, every concept was hit, every debugging story actually happened.

The goal isn't to memorize. It's to recognize, when something similar comes up, *"I've seen this shape before."* That's all senior engineering really is.