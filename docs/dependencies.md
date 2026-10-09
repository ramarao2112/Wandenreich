# TrustC Dependency Specification & Locks

**Date:** 7 October 2026  
**Platform:** macOS Darwin arm64 / Python 3.9.6  
**Package Manager:** pip / setuptools (PEP 517 build backend `setuptools.build_meta`)  

---

## 1. Runtimes

- **Python Runtime:** Python >= 3.9 (tested and verified on Python 3.9.6)
- **Node.js Runtime:** Node >= 18 (LTS) for Vite 5 + React 18 UI workbench

---

## 2. Dependency Groups

Dependencies are strictly decoupled in `pyproject.toml` so CLI/core remains lightweight without bundling server or development runtimes:

### 2.1 Core Runtime (`dependencies`)
Minimal dependencies required by the compiler and contracts:
- `pydantic>=2.4,<3` (Pydantic v2 data contracts, schema export, model validators)
- `email-validator>=2.0` (RFC email validation for identity fields)
- `lark>=1.1` (LALR(1) parser for TrustSpec language)

### 2.2 Optional Group: Server (`[project.optional-dependencies].server`)
Dependencies required for running the local HTTP/SSE daemon (Stage 6):
- `fastapi>=0.104,<1`
- `uvicorn[standard]>=0.24,<1`

### 2.3 Optional Group: Generated Application (`[project.optional-dependencies].generated-app`)
Dependencies required inside the rendered FastAPI target application (Stage 4 & 5):
- `fastapi>=0.104,<1`
- `uvicorn[standard]>=0.24,<1`
- `sqlalchemy[asyncio]>=2.0,<3`
- `aiosqlite>=0.19`
- `pyjwt>=2.8,<3`

### 2.4 Development & Test Tooling (`[project.optional-dependencies].dev`)
- `pytest>=7.4,<9`
- `pytest-asyncio>=0.21`
- `httpx>=0.25`
- `ruff>=0.1`
- `mypy>=1.7`
- `flake8>=7.0` (documented equivalent lint runner under Windows WDAC)
- `isort>=5.13` (documented equivalent import sorter under Windows WDAC)
- `build>=1.0`
- `wheel>=0.40`

---

## 3. Pinned Lockfile

Exact installed versions are locked in [`requirements.lock`](../requirements.lock):
```text
annotated-types==0.7.0
anyio==4.12.1
backports.asyncio.runner==1.2.0
certifi==2026.7.22
dnspython==2.7.0
email-validator==2.3.0
exceptiongroup==1.3.1
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.20
iniconfig==2.1.0
librt==0.16.0
mypy==1.19.1
mypy_extensions==1.1.0
packaging==26.3
pathspec==1.1.1
pluggy==1.6.0
pydantic==2.13.5
pydantic_core==2.46.5
Pygments==2.21.0
pytest==8.4.2
pytest-asyncio==1.2.0
ruff==0.16.10
tomli==2.4.1
-e .
typing-inspection==0.4.2
typing_extensions==4.16.0
```

---

## 4. Frontend (UI) Dependencies

Defined in [`ui/package.json`](../ui/package.json):
- React 18.2.0
- React-DOM 18.2.0
- Vite 5.0.10
- TypeScript 5.3.3
- Lucide-React 0.300.0
