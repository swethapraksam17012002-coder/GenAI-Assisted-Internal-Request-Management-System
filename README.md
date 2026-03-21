# ⚡ NEXUS SDLC — AI-Assisted Internal Request Management System

> **GenAI Architect Design** | LangGraph · CrewAI · AutoGen · RAG · LangSmith  
> Version 1.0 | Extra Security: OAuth2 + JWT + Rate Limiting + OWASP Headers

---

## 🏗 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER (React 18)                                      │
│  React Router v6 · Zustand · TanStack Query · SSE · Recharts        │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTPS / JWT Bearer Token
┌─────────────────────────▼───────────────────────────────────────────┐
│  API GATEWAY (FastAPI)                                              │
│  OAuth2 Password Flow · JWT RS256 · Rate Limiter · OWASP Headers    │
│  CORS Whitelist · CSRF Tokens · Account Lockout · Scope-Based RBAC  │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────────┐
│  AGENT ORCHESTRATION (LangGraph State Machine)                      │
│  INGEST → ANALYSE → ENRICH → GENERATE → QUALITY → SLA → PERSIST    │
│  Self-correcting loop: QualityGuard < 60 → retry NoteGenerator (×3) │
└────────┬─────────────┬──────────────┬──────────────────────────────-┘
         │             │              │
    ┌────▼────┐   ┌────▼────┐   ┌────▼─────┐
    │ CrewAI  │   │ AutoGen │   │ LangSmith│
    │ 4 agents│   │ 3 agents│   │ Tracing  │
    └─────────┘   └─────────┘   └──────────┘
┌─────────────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                         │
│  SQLite/PostgreSQL (SQLAlchemy async) · ChromaDB (HNSW RAG)         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔐 Security Features (Extra Implementation)

### Authentication & Authorization
| Feature | Implementation |
|---------|---------------|
| **OAuth2 Password Flow** | `/api/auth/token` — RFC 6749 compliant |
| **JWT Access Tokens** | HS256, 30-min expiry, JTI tracking |
| **JWT Refresh Tokens** | 7-day, single-use rotation on refresh |
| **Scope-Based RBAC** | `read`, `write`, `admin`, `agents:exec`, `rag:admin` |
| **Token Blacklisting** | JTI blacklist on logout / password change |
| **Account Lockout** | 5 failed attempts → 15-minute lockout |
| **Password Strength** | 8+ chars, uppercase, digit, special char enforced |
| **CSRF Protection** | SameSite cookie + token header validation |
| **Bcrypt Hashing** | 12 rounds; passlib |

### Rate Limiting
| Endpoint Group | Limit |
|----------------|-------|
| Auth endpoints | **10 req/min** per IP |
| All other API  | **100 req/min** per IP |
| Algorithm | Token bucket with burst tolerance |
| Headers | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` |

### OWASP HTTP Security Headers
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'; ...
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cache-Control: no-store (auth & sensitive endpoints)
```

### Additional Security
- **Input sanitisation** — Pydantic v2 strict mode on all endpoints
- **SQL injection prevention** — SQLAlchemy ORM only, zero raw SQL
- **Trusted hosts** — `TrustedHostMiddleware` blocks Host-header injection
- **CORS whitelist** — Exact origin matching, no wildcards
- **Server fingerprint removal** — `Server` and `X-Powered-By` headers stripped
- **Non-root Docker** — Container runs as UID 1000
- **Immutable audit log** — No UPDATE/DELETE ever on `audit_logs` table

---

## � Technology Stack

### 🎨 Frontend Stack
| Technology | Version | Purpose |
|------------|---------|---------|
| **React** | 18+ | Core UI framework with hooks and concurrent features |
| **React Router** | v6 | Client-side routing and navigation |
| **Zustand** | 4+ | Lightweight state management |
| **TanStack Query** | v4 | Server state management and caching |
| **Recharts** | 2+ | Data visualization and analytics charts |
| **TailwindCSS** | 3+ | Utility-first CSS framework |
| **Vite** | 4+ | Build tool and development server |
| **TypeScript** | 5+ | Type-safe JavaScript development |

### ⚙️ Backend Stack
| Technology | Version | Purpose |
|------------|---------|---------|
| **FastAPI** | 0.104+ | High-performance async web framework |
| **Python** | 3.9+ | Core programming language |
| **SQLAlchemy** | 2.0+ | Async ORM with modern features |
| **Alembic** | 1.12+ | Database migration tool |
| **Pydantic** | v2 | Data validation and serialization |
| **PyJWT** | 2.8+ | JWT token handling |
| **Passlib** | 1.7+ | Password hashing with bcrypt |
| **httpx** | 0.25+ | Async HTTP client for API calls |

### 🗄️ Database Stack
| Technology | Version | Purpose |
|------------|---------|---------|
| **PostgreSQL** | 13+ | Primary relational database (production) |
| **SQLite** | 3.40+ | Development and testing database |
| **ChromaDB** | 0.4+ | Vector database for RAG and embeddings |
| **Redis** | 7+ | Caching and session storage (optional) |
| **HNSW** | Built-in | Approximate nearest neighbor search |

### 🤖 AI & ML Stack
| Technology | Version | Purpose |
|------------|---------|---------|
| **LangGraph** | 0.0.26+ | AI pipeline state machine orchestration |
| **CrewAI** | 0.28+ | Multi-agent collaboration framework |
| **AutoGen** | 0.2.16+ | Specialized code quality agents |
| **LangSmith** | SDK | AI tracing and monitoring |
| **LangChain** | 0.1.0+ | AI/LLM integration utilities |
| **Ollama** | Client | Local LLM inference server |
| **Sentence Transformers** | 2.2+ | Text embeddings for RAG |
| **OpenAI API** | v1 | Cloud LLM backup (optional) |

### 🔒 Security Stack
| Technology | Purpose |
|------------|---------|
| **OAuth2 Password Flow** | RFC 6749 compliant authentication |
| **JWT RS256** | Token-based authentication |
| **bcrypt** | Secure password hashing (12 rounds) |
| **OWASP Headers** | Security hardening middleware |
| **Rate Limiting** | Token bucket algorithm |
| **CSRF Protection** | Cross-site request forgery prevention |

### 📊 Monitoring & Observability
| Technology | Purpose |
|------------|---------|
| **LangSmith** | AI pipeline tracing and monitoring |
| **Python Logging** | Structured application logging |
| **Prometheus** | Metrics collection (optional) |
| **Grafana** | Visualization dashboards (optional) |
| **Sentry** | Error tracking (optional) |

---

## �🚀 Quick Start

### 1. Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: set SECRET_KEY and optionally OPENAI_API_KEY

uvicorn app.main:app --reload --port 8000
```

### 2. Frontend
```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### 3. Docker Compose (full stack)
```bash
cp backend/.env.example .env
docker-compose up --build
```

---

## 📡 API Endpoints (40+)

### Auth
```
POST /api/auth/register          — Create account
POST /api/auth/token             — OAuth2 login → JWT pair
POST /api/auth/refresh           — Rotate refresh token
POST /api/auth/logout            — Revoke access token
GET  /api/auth/me                — Authenticated user profile
GET  /api/auth/csrf-token        — CSRF token for SPA
```

### Requests
```
POST   /api/requests/            — Create + trigger AI pipeline
GET    /api/requests/            — List with filters/search/pagination
GET    /api/requests/{id}        — Full detail + follow-ups + audit
PATCH  /api/requests/{id}        — Update (Draft/Reviewed only)
DELETE /api/requests/{id}        — Delete (Draft/Cancelled only)
POST   /api/requests/{id}/review         — → Reviewed
POST   /api/requests/{id}/approve        — → Approved (read-only)
POST   /api/requests/{id}/complete       — → Completed
POST   /api/requests/{id}/cancel         — → Cancelled
POST   /api/requests/{id}/followups      — Add comment
PATCH  /api/requests/{id}/followups/{fid}/complete
POST   /api/requests/{id}/regenerate-ai  — Re-run AI pipeline
GET    /api/requests/{id}/audit          — Immutable audit trail
GET    /api/requests/{id}/stream         — SSE live agent progress
```

### AI Agents
```
GET  /api/agents/status           — All framework health
POST /api/agents/code-quality     — AutoGen 3-agent analysis
GET  /api/agents/checklist        — Default 10-item checklist
POST /api/agents/rag/search       — Semantic knowledge search
GET  /api/agents/rag/stats        — ChromaDB collection stats
POST /api/agents/rag/index        — Index approved request
DELETE /api/agents/rag/purge      — Purge collection (admin)
POST /api/agents/test-pipeline    — Dry-run pipeline
GET  /api/agents/executions       — Execution history
```

### Dashboard & Analytics
```
GET /api/dashboard/stats          — KPIs (total, open, overdue, SLA%)
GET /api/dashboard/trend          — N-day request count trend
GET /api/analytics/by-status      — Status breakdown
GET /api/analytics/by-priority    — Priority distribution
GET /api/analytics/by-type        — Type breakdown
GET /api/analytics/by-channel     — Channel analysis
GET /api/analytics/sla            — SLA compliance report
```

---

## 🤖 AI Pipeline (LangGraph State Machine)

```
INGEST → ANALYSE → ENRICH → GENERATE ──→ QUALITY ──→ SLA_CALC → PERSIST
                                 ↑          |
                                 └── retry ─┘ (if score < 60, max 3×)
```

| Node | Agent | Framework |
|------|-------|-----------|
| ingest | Text cleaner | LangChain Tool |
| analyse | RequestAnalyzer | CrewAI |
| enrich | RAG retrieval | LangChain + ChromaDB |
| generate | NoteGenerator | CrewAI |
| quality | QualityGuard | CrewAI |
| sla_calc | SLACalculator | CrewAI |
| observe | Tracer | LangSmith |

**Graceful degradation:** System runs 100% deterministic fallback agents when LLM API is unavailable.

---

## 🧪 Running Tests

```bash
cd backend
pytest tests/ -v

# Expected: 17+ tests across auth, requests, code quality, security
```

---

## 📁 Project Structure

```
nexus-sdlc/
├── docs/                              ← 📚 Comprehensive Documentation
│   ├── Functional_Requirements.md    ← Functional specs & use cases
│   ├── Non_Functional_Requirements.md ← Performance, security & scalability
│   └── End_to_End_System_Flow.md     ← Architecture & data flows
├── backend/
│   ├── app/
│   │   ├── main.py                 ← FastAPI app + middleware stack
│   │   ├── core/
│   │   │   ├── config.py           ← All settings (pydantic-settings)
│   │   │   ├── security.py         ← JWT + OAuth2 + CSRF + RBAC
│   │   │   └── database.py         ← Async SQLAlchemy
│   │   ├── middleware/
│   │   │   ├── rate_limiter.py     ← Token bucket rate limiter
│   │   │   └── security_headers.py ← OWASP security headers
│   │   ├── models/
│   │   │   ├── user_model.py       ← User + OAuth fields
│   │   │   ├── request_model.py    ← Request + FollowUp
│   │   │   └── audit_model.py      ← AuditLog + AgentExecution
│   │   ├── api/
│   │   │   ├── auth.py             ← Auth endpoints (register/login/me)
│   │   │   ├── requests.py         ← Request CRUD + workflow + SSE
│   │   │   ├── agents.py           ← Code quality + RAG endpoints
│   │   │   ├── dashboard.py        ← KPIs + trend
│   │   │   └── health.py           ← Health check
│   │   └── services/
│   │       ├── ai_pipeline.py      ← LangGraph orchestrator
│   │       ├── code_quality.py     ← AutoGen 3-agent analysis
│   │       ├── rag_service.py      ← ChromaDB + embeddings
│   │       └── audit_service.py    ← Append-only audit helper
│   ├── tests/
│   │   └── test_nexus.py           ← Full async test suite
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   └── src/
│       └── App.jsx                 ← Full React SPA
├── docker-compose.yml
└── README.md
```

---

## 📚 Documentation

### 📋 Requirements & Architecture
| Document | Description | Format |
|----------|-------------|--------|
| **[Functional Requirements](docs/Functional_Requirements.md)** | Comprehensive functional specifications, use cases, and business rules | Markdown |
| **[Non-Functional Requirements](docs/Non_Functional_Requirements.md)** | Performance, security, scalability, and operational requirements | Markdown |
| **[End-to-End System Flow](docs/End_to_End_System_Flow.md)** | Detailed system architecture, data flows, and process documentation | Markdown |

### 🎯 Key Features Overview
- **🤖 Multi-Framework AI Pipeline**: CrewAI + AutoGen + LangGraph orchestration
- **🔄 Self-Correcting Quality Loop**: Automatic retry with feedback (quality < 60)
- **🔍 Semantic RAG Retrieval**: ChromaDB vector search with HNSW indexing
- **⚡ Real-time Progress Tracking**: Server-Sent Events for live AI pipeline updates
- **🛡️ Enterprise Security**: OAuth2 + JWT + RBAC + OWASP compliance
- **📊 Advanced Analytics**: Real-time dashboards with SLA monitoring
- **🔄 Graceful Degradation**: 100% uptime with deterministic fallback processing

---

## 🏆 GenAI Architect Innovations

| Innovation | Technical Design |
|-----------|-----------------|
| **Multi-Framework AI** | CrewAI + AutoGen + LangGraph — each chosen for optimal problem shape |
| **Self-Correcting Pipeline** | QualityGuard < 60 → retry NoteGenerator with feedback (max 3×) |
| **Agentic RAG** | Human corrections re-embedded with weight=1.5 · Relevance gate 0.4 |
| **Full Observability** | LangSmith traces every token, cost, latency · Fallback to SQLite |
| **Graceful Degradation** | 100% uptime — deterministic rule-based fallback when LLM offline |
| **SSE Live Streaming** | Real-time agent progress streamed to React UI via EventSource |
| **Confidence-Gated Triage** | AI confidence < 0.7 → mandatory human review before SLA clock starts |
| **Semantic Audit Trail** | Every audit entry links to LangSmith trace_id for full AI accountability |


RAG Search Example:

How to search the exact records you already have
1) find REQ-0018520A
Try queries like:

{
  "query": "fix my laptop production today",
  "top_k": 5
}
or

{
  "query": "jane laptop issue production",
  "top_k": 5
}
2)find REQ-E097335A
Try:

{
  "query": "teams microphone not working after windows update",
  "top_k": 5
}
or

{
  "query": "audio issue teams microphone zero input level",
  "top_k": 5
}
