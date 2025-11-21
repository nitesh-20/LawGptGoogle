# LawGPT / Legal Nexus Keeper – Setup & Usage Guide

Live Working Link: https://law-gpt-1c925.firebaseapp.com/
Blog Link: https://medium.com/@iamshreedshrivastava/lawgpt-architecting-the-agentic-future-of-justice-in-india-a-blueprint-for-scale-and-impact-dde591c65845
Register for Code Vipassana sessions
Join the meetup group Datapreneur Social
Sign up to become Google Cloud Innovator

This workspace has **two main application projects** plus an **advanced agentic routing layer**:

1. **Backend – lawgpt-backend** (FastAPI + Firestore, production API)
2. **Frontend – legal-nexus-keeper** (React + Vite app, deployed on Firebase Hosting)
3. **Advanced Agents / MCP Router – external-lawgpt** (next‑gen architecture used for intent routing and multi‑agent orchestration)

Together they provide:

- Ingestion of Indian law PDFs into **Google Firestore**
- Stable REST API endpoints to **search laws** and **explain** legal queries
- A modern web UI with **Legal Search** and **Legal Assistant (chatbot)** that use real data (no demo data)
- A **v2 agentic design** (in `external-lawgpt`) that adds intent detection, tool‑based agents, and a central router over the same legal corpus.

---

## 1. Folder Structure

At the top level:

```text
Lawgpt/
├─ lawgpt-backend/         # FastAPI backend + PDF ingestion (v1 production API)
├─ legal-nexus-keeper/     # React/Vite frontend (Legal Nexus UI)
└─ external-lawgpt/        # Advanced LawGpt v2: MCP-style router + agents
```

### 1.1 Backend – `lawgpt-backend/`

Key files:

- `main.py` – FastAPI app, Firestore connection, REST APIs:
  - `GET /ping` – health check
  - `GET /test-firestore` – Firestore connectivity test
  - `POST /search-law` – search ingested acts/judgments
  - `POST /explain-law` – generate explanation using search results
- `ingest_pdf.py` – script to read PDFs from `pdfs/` and push text into Firestore collection `acts`.
- `requirements.txt` – Python dependencies.
- `pdfs/` – folder containing all Indian law PDFs (bare acts, judgments, etc.).

### 1.2 Frontend – `legal-nexus-keeper/`

Key content:

- `src/pages/`
  - `Search.tsx` – **Legal Search page**. Calls backend `/search-law` and shows real Firestore results.
  - `Chatbot.tsx` – **Legal Assistant**. Calls backend `/explain-law` for legal Q&A.
  - Other pages: Dashboard, Cases, Documents, Drafting, etc. (UI shell around core features).
- `src/utils/` – helpers for API calls (e.g. `chatUtils.ts`).
- `public/` – favicon, OG image, redirects, etc.

### 1.3 Advanced Agents & MCP Router – `external-lawgpt/`

This folder contains the **v2 architecture** of LawGpt, brought into this monorepo for research and future integration.

Key pieces:

- `services/main_router.py`
  - Central **MCP‑style router** service (FastAPI).
  - Endpoints:
    - `GET /health` – health/status of router and configured agents.
    - `POST /chat` – single entrypoint that detects user intent and routes to underlying agents.
    - `POST /search-law` – advanced search API using keyword extraction and Firestore.
    - `POST /explain-law` – explanation API built on top of Firestore + Gemini.
  - Responsibilities:
    - Uses **GeminiClient** (`utils/gemini_client.py`) to detect intent and complexity from the user query.
    - Decides whether the request is primarily **legal search** (case/act retrieval) or **legal‑ai** (analysis & drafting).
    - Calls downstream agent services in parallel via async HTTP (`call_agent_service`).
    - Merges results, examples:
      - In `legal_search` mode → returns ranked cases/snippets and a summary.
      - In `legal_ai` mode → combines case search results + analysis agent output into a single response.

- Agent services (`services/legal_search_agent.py`, `services/legal_ai_agent.py`):
  - Encapsulate specific capabilities behind a clean interface so the router can treat them as **tools/agents**.
  - `legal_search_agent` focuses on:
    - Case and act retrieval over Firestore (and optionally BigQuery),
    - Query expansion, topic/jurisdiction filtering.
  - `legal_ai_agent` focuses on:
    - Deep analysis, argument building, summarisation, and drafting using Gemini.

- Shared utilities under `external-lawgpt/utils/`:
  - `gemini_client.py` – wrapper around the Gemini API with reusable prompts.
  - `firestore_client.py` – encapsulates Firestore access for acts and cases.
  - `keyword_extractor.py` – extracts domain‑specific keywords and filters legal stop‑words.
  - `language_detector.py` – detects Hinglish vs English preference.
  - `logger.py` – consistent structured logging across services.

- Configuration & deployment:
  - `config/settings.py` – central configuration (Gemini model names, service URLs, API keys, project IDs, etc.).
  - `Dockerfile.router`, `Dockerfile.search` – container images for router and search agent.
  - `deployment/deploy.sh`, `deploy_with_credentials.sh` – example deploy scripts for GCP.



---

## 2. Prerequisites

- **OS:** macOS (works on Linux/Windows with small command changes)
- **Python:** 3.10+ (you are using a `.venv` already – good)
- **Node.js:** v18+ recommended
- **Google Cloud Project:** `genial-smoke-478804-t1`
- **Firestore:** enabled in the project
- **Service account JSON:** downloaded as `genial-smoke-478804-t1-f987e2d0d75f.json`

---

## 3. Backend Setup (`lawgpt-backend`)

### 3.1 Create & activate virtualenv (if not already)

From the `lawgpt-backend` folder:

```bash
cd /Users/niteshsahu/Desktop/Lawgpt/lawgpt-backend
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate    # Windows PowerShell/cmd
```

### 3.2 Install dependencies

```bash
pip install -r requirements.txt
```

### 3.3 Place service account JSON

Place your Google service account file here:

```text
/Users/niteshsahu/Desktop/Lawgpt/lawgpt-backend/genial-smoke-478804-t1-f987e2d0d75f.json
```

### 3.4 Set environment variables (per terminal session)

In the same terminal where you will run Uvicorn:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/Users/niteshsahu/Desktop/Lawgpt/lawgpt-backend/genial-smoke-478804-t1-f987e2d0d75f.json"
export GOOGLE_CLOUD_PROJECT="genial-smoke-478804-t1"
```

> On Windows PowerShell, use:
>
> ```powershell
> $env:GOOGLE_APPLICATION_CREDENTIALS = "C:\\path\\to\\genial-smoke-478804-t1-f987e2d0d75f.json"
> $env:GOOGLE_CLOUD_PROJECT = "genial-smoke-478804-t1"
> ```

### 3.5 Run the FastAPI server

```bash
cd /Users/niteshsahu/Desktop/Lawgpt/lawgpt-backend
uvicorn main:app --reload
```

You should see a log like:

```text
INFO:lawgpt-backend:Firestore client initialized for project genial-smoke-478804-t1
```

The backend will be available at: **http://127.0.0.1:8000**

### 3.6 Test backend via Swagger UI

Open:

- http://127.0.0.1:8000/docs

Use:

1. `GET /ping` – should return `{"status": "ok"}`.
2. `GET /test-firestore` – verifies Firestore access.
3. `POST /search-law` – with body, e.g.:

   ```json
   { "query": "right to privacy data protection" }
   ```

4. `POST /explain-law` – with body, e.g.:

   ```json
   { "query": "What is the right to privacy under Indian law?" }
   ```

If these work, Firestore + backend are correctly configured.

---

## 4. PDF Ingestion (`ingest_pdf.py`)

Before search will return useful results, the PDFs in `pdfs/` need to be indexed into Firestore.

Typical flow (only after env vars are set and virtualenv is active):

```bash
cd /Users/niteshsahu/Desktop/Lawgpt/lawgpt-backend
source .venv/bin/activate

python ingest_pdf.py
```

What it does (high level):

- Reads all `.pdf` files from `pdfs/` directory.
- Extracts text and splits into chunks/pages.
- Writes each chunk as a document into Firestore collection **`acts`** with fields like:
  - `act_name`
  - `title`
  - `page_no`
  - `content` / `snippet`

Once ingested, `search_law_internal()` in `main.py` can:

- Fetch documents from `acts` collection
- Score them by matching with the query
- Return the best matches to `/search-law` and `/explain-law`.

---

## 5. Frontend Setup (`legal-nexus-keeper`)

### 5.1 Install dependencies

In a **separate terminal**:

```bash
cd /Users/niteshsahu/Desktop/Lawgpt/legal-nexus-keeper
npm install
```

### 5.2 Run the Vite dev server

```bash
npm run dev
```

By default, the app will run at something like:

- http://localhost:8081  (port may vary; check the terminal output)

### 5.3 Frontend pages and how they talk to backend

#### 5.3.1 Legal Search – `Search.tsx`

- Text you type in the search bar is sent to:

  ```http
  POST http://127.0.0.1:8000/search-law
  ```

- Request body:

  ```json
  { "query": "<your search text>" }
  ```

- Response shape:

  ```json
  {
    "query": "...",
    "keywords": ["..."],
    "results": [
      {
        "act_name": "...",
        "title": "...",
        "page_no": 1,
        "snippet": "...",
        "score": 0.9
      }
    ]
  }
  ```

- `Search.tsx` uses `results` to render cards showing:
  - Title / Act name
  - Page number
  - Snippet text
  - A relevance bar based on `score`

**Note:** All previous demo/sample search data has been removed; only backend data is shown.

#### 5.3.2 Legal Assistant (Chatbot) – `Chatbot.tsx`

- The chat input sends your question to:

  ```http
  POST http://127.0.0.1:8000/explain-law
  ```

- Request body:

  ```json
  { "query": "<your legal question>", "max_results": 5 }
  ```

- Backend combines:
  - `search_law_internal()` results
  - Optional Gemini-style reasoning / explanation
  - Hinglish/English friendly formatting

- Response includes `explanation` text, which is shown as the assistant’s message in the chat UI.

- You can also upload documents via the chat UI; they are shown in the interface, but the core legal reasoning is driven by Firestore data and backend logic.

---

## 6. Typical Development Workflow

1. **Start backend** (with virtualenv + env vars):

   ```bash
   cd /Users/niteshsahu/Desktop/Lawgpt/lawgpt-backend
   source .venv/bin/activate
   export GOOGLE_APPLICATION_CREDENTIALS="/Users/niteshsahu/Desktop/Lawgpt/lawgpt-backend/genial-smoke-478804-t1-f987e2d0d75f.json"
   export GOOGLE_CLOUD_PROJECT="genial-smoke-478804-t1"
   uvicorn main:app --reload
   ```

2. **Ingest/update PDFs** when new acts/judgments are added:

   ```bash
   python ingest_pdf.py
   ```

3. **Start frontend** in another terminal:

   ```bash
   cd /Users/niteshsahu/Desktop/Lawgpt/legal-nexus-keeper
   npm run dev
   ```

4. **Use the app:**
   - Open Vite URL in browser.
   - Go to **Legal Search** page → run queries like:
     - `right to privacy data protection`
     - `digital personal data protection act consent`
   - Go to **Legal Assistant** page → ask natural questions.

---

## 7. Troubleshooting

### 7.1 Firestore not initialized / 500 from `/search-law`

Symptoms:

- Swagger or frontend shows:

  ```json
  { "detail": "Firestore not initialized" }
  ```

Fix:

1. Ensure service account JSON exists at the path used by `GOOGLE_APPLICATION_CREDENTIALS`.
2. Re-export env vars **in the same terminal** before running Uvicorn.
3. Restart backend.

### 7.2 CORS issues (browser cannot call backend)

- The FastAPI app in `main.py` is already configured with CORS to allow `http://localhost:*`.
- If you change ports or domains, update allowed origins in the CORS config inside `main.py`.

### 7.3 No search results

- Confirm `ingest_pdf.py` has been run successfully.
- Check Firestore console → `acts` collection has documents.
- Try a simpler query that you know exists in one of the PDFs.

---

## 8. High-Level Architecture

The overall system now has **two layers**:

1. **Core v1 stack (currently wired to the UI)**
   - Data ingestion → Firestore (`lawgpt-backend/ingest_pdf.py`).
   - REST API → `/search-law`, `/explain-law` in `lawgpt-backend/main.py`.
   - Frontend → `legal-nexus-keeper` React app that calls these endpoints.

2. **Advanced v2 agentic stack (MCP‑style, in `external-lawgpt/`)**
   - **Main Router** (`services/main_router.py`):
     - Detects intent (search vs analysis) using Gemini.
     - Fans out requests to **Legal Search Agent** and **Legal AI Agent**.
     - Aggregates/merges responses into a single ChatResponse with diagnostics and sources.
   - **Agents as tools**:
     - `legal_search_agent` – wraps Firestore search, topic/jurisdiction filters, and ranking.
     - `legal_ai_agent` – wraps Gemini reasoning, drafting, and structured analysis.
   - **Shared tooling** (`utils/*`): Gemini client, Firestore client, language & keyword utilities.

This design lets you:

- Keep the current v1 backend + UI completely stable.
- Experiment with more advanced **agentic workflows, routing, and MCP concepts** in `external-lawgpt`.
- Later, gradually swap the frontend or backend endpoints to talk to the router instead of the basic v1 API, without rewriting the whole app.

---

## 9. Notes & Next Steps

- Demo/sample data has been removed from core legal search & chatbot; everything now depends on your **real PDFs + Firestore**.
- The `external-lawgpt` folder gives you a ready‑made blueprint for:
  - Multi‑agent orchestration over legal data.
  - Intent‑aware routing for different modes (case retrieval vs deep analysis).
  - GCP‑ready Dockerfiles and deploy scripts for an MCP‑style router.
- Future work in this repo can include:
  - Pointing the frontend chatbot to the **main router `/chat`** endpoint instead of the basic `/explain-law`.
  - Exposing router/agents as MCP tools to other clients.
  - Adding more agents (e.g. document drafter, compliance checker, argument builder) that plug into the same router.

This README is tailored to the current state of your project on macOS. Adjust paths and commands slightly if you move the project or run on another OS.
# LawGptGoogle
# LawGptGoogle
