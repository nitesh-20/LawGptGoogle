from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from google.cloud import firestore
from google.api_core.exceptions import GoogleAPIError
import logging
import os
import re
import google.generativeai as genai

# ---------------- CONFIG ----------------

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "genial-smoke-478804-t1")
FIRESTORE_COLLECTION = "acts"
MAX_SCAN_DOCS = 2000
MAX_RESULTS = 20
SNIPPET_CHARS = 400
GEMINI_MODEL_NAME = "gemini-1.5-flash"
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "us-central1")

# ---------------- LOGGING ----------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lawgpt-backend")

# ---------------- APP & DB ----------------

app = FastAPI(
    title="LAW-GPT Backend",
    description="Legal search backend using Firestore + PDFs data + Gemini",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For hackathon; restrict later if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    db = firestore.Client(project=PROJECT_ID)
    logger.info("Firestore client initialized for project %s", PROJECT_ID)
except Exception as e:  # noqa: BLE001
    logger.exception("Failed to initialize Firestore client: %s", e)
    db = None

# ---------------- MODELS ----------------


class SearchRequest(BaseModel):
    query: str


class SearchResult(BaseModel):
    act_name: Optional[str] = None
    title: Optional[str] = None
    page_no: Optional[int] = None
    snippet: Optional[str] = None
    score: Optional[float] = None


class SearchResponse(BaseModel):
    query: str
    keywords: List[str]
    results: List[SearchResult]


class ExplainRequest(BaseModel):
    query: str
    max_results: int = 5


class ExplainResponse(BaseModel):
    query: str
    keywords: List[str]
    used_results: List[SearchResult]
    explanation: str


# ---------------- HELPERS ----------------


def extract_keywords(text: str) -> list[str]:
    """Query se simple keywords nikalta hai."""
    words = re.findall(r"[A-Za-z]+", text.lower())
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "into", "have", "has",
        "shall", "will", "been", "were", "was", "are", "your", "you", "hereby", "such",
        "any", "other", "their", "thereof", "law", "section", "article", "acts"
    }
    filtered = [w for w in words if w not in stop and len(w) > 3]
    return list(dict.fromkeys(filtered))[:5]   # unique + cleaned


def compute_basic_score(text: str, keywords: List[str]) -> int:
    """Very simple relevance score: count distinct keyword hits in text."""
    text_lower = text.lower()
    hits = 0
    for kw in keywords:
        if kw in text_lower:
            hits += 1
    return hits


# New helper: rough detection whether answer should be Hinglish or English

def detect_hinglish_preference(text: str) -> str:
    """Very rough check: return 'hinglish' or 'english' based on query language."""
    t = text.lower()
    hindi_markers = [
        "kya", "kaise", "hai", "nahi", "nhai", "kyun", "kyunki", "matlab",
        "samjha", "samjhao", "batao", "agar", "toh", "aisa", "waise", "yaar",
    ]
    hits = sum(1 for w in hindi_markers if w in t)
    return "hinglish" if hits >= 2 else "english"


def search_law_internal(query: str) -> SearchResponse:
    """Core search logic reused by /search-law and /explain-law."""
    if db is None:
        logger.error("Firestore client is not initialized")
        raise HTTPException(status_code=500, detail="Firestore not initialized")

    keywords = extract_keywords(query)
    logger.info("Search query='%s' -> keywords=%s", query, keywords)

    if not keywords:
        return SearchResponse(query=query, keywords=[], results=[])

    try:
        docs_iter = db.collection(FIRESTORE_COLLECTION).stream()
    except GoogleAPIError as e:  # noqa: PERF203
        logger.exception("Error reading from Firestore: %s", e)
        raise HTTPException(status_code=503, detail="Error accessing Firestore")

    results: list[SearchResult] = []
    scanned = 0

    try:
        for d in docs_iter:
            scanned += 1
            if scanned > MAX_SCAN_DOCS:
                logger.warning("Scan limit reached (%d docs). Stopping early.", MAX_SCAN_DOCS)
                break

            data = d.to_dict() or {}
            full_text = str(data.get("text") or "")
            if not full_text:
                continue

            score = compute_basic_score(full_text, keywords)
            if score <= 0:
                continue

            snippet = full_text[:SNIPPET_CHARS]
            results.append(
                SearchResult(
                    act_name=data.get("act_name"),
                    title=data.get("title"),
                    page_no=data.get("page_no"),
                    snippet=snippet,
                    score=float(score),
                )
            )

        results.sort(
            key=lambda r: ((r.score or 0.0) * -1, r.page_no if r.page_no is not None else 0)
        )
        limited_results = results[:MAX_RESULTS]

        logger.info(
            "Search done: query='%s', scanned=%d, matched=%d, returned=%d",
            query,
            scanned,
            len(results),
            len(limited_results),
        )

        return SearchResponse(query=query, keywords=keywords, results=limited_results)
    except GoogleAPIError as e:  # noqa: PERF203
        logger.exception("Error while streaming Firestore docs: %s", e)
        raise HTTPException(status_code=503, detail="Error reading from Firestore")


def call_gemini(query: str, results: List[SearchResult]) -> str:
    """Call Gemini via API key client to get a Hinglish explanation."""
    api_key = os.getenv("GOOGLE_GENAI_API_KEY")
    if not api_key:
        logger.error("GOOGLE_GENAI_API_KEY not set")
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(GEMINI_MODEL_NAME)

    context_parts: List[str] = []
    for r in results:
        label = f"{r.act_name or ''} - {r.title or ''} (Page {r.page_no})".strip()
        part = f"=== Source ===\nTitle: {label}\nSnippet:\n{r.snippet}\n"
        context_parts.append(part)

    context_text = "\n\n".join(context_parts) if context_parts else "No matching law text found."

    prompt = f"""
You are a helpful Indian legal explainer bot for laypersons.

User query:
[START_USER_QUERY]
{query}
[END_USER_QUERY]

Relevant law snippets (may contain multiple pages and acts):
{context_text}

Task:
1. In 3-5 lines, explain in very simple friendly Hinglish (mix of Hindi and English) what the law is saying with respect to the query.
2. Then give bullet points in Hinglish summarizing the most important points and which page/section they roughly relate to (if visible from the snippet).
3. Be very clear that this is NOT legal advice.

Style:
- Use short sentences.
- Avoid very heavy legal jargon, explain in plain language.
- Address the user as "aap" or "tum" in a polite conversational tone.

Important:
- If information is not clearly present, say that details are not fully clear and the user should check the bare act or consult a lawyer.
- End with this exact disclaimer sentence:
"Ye information educational purpose ke liye hai, legal advice nahi."
"""

    try:
        response = model.generate_content(prompt)
        # google-generativeai responses usually have .text or .candidates[0].content.parts
        text = getattr(response, "text", None) or ""
        if not text and getattr(response, "candidates", None):
            parts = response.candidates[0].content.parts
            text = "".join(p.text for p in parts if hasattr(p, "text"))
        text = (text or "").strip()
        if not text:
            logger.warning("Gemini returned empty text")
            raise HTTPException(status_code=502, detail="Gemini did not return any explanation")
        return text
    except Exception as e:  # noqa: BLE001
        logger.exception("Error calling Gemini via API key: %s", e)
        raise HTTPException(status_code=503, detail="Error calling Gemini service")


# ---------------- ROUTES ----------------


@app.get("/")
def root():
    return {
        "service": "LAW-GPT Backend",
        "description": "Search Indian laws using PDFs + Firestore + Gemini Hinglish explanations.",
        "docs_url": "/docs",
        "health": "/ping",
    }


@app.get("/ping")
def ping():
    return {"message": "LAW-GPT backend running 🚀"}


@app.get("/test-firestore")
def test_firestore():
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore not initialized")

    try:
        doc_ref = db.collection("test_collection").document("sample")
        doc_ref.set({"hello": "world"})
        snap = doc_ref.get()
        return {"status": "ok", "data": snap.to_dict()}
    except GoogleAPIError as e:  # noqa: PERF203
        logger.exception("Firestore test failed: %s", e)
        raise HTTPException(status_code=503, detail="Error accessing Firestore")


@app.post("/search-law", response_model=SearchResponse)
def search_law(body: SearchRequest):
    return search_law_internal(body.query)


@app.post("/explain-law", response_model=ExplainResponse)
def explain_law(body: ExplainRequest):
    """Firestore-based explanation that formats like GPT/Gemini with EN/Hinglish style."""
    
    # If Firestore is not available, provide a fallback response
    if db is None:
        logger.warning("Firestore unavailable, providing fallback response")
        keywords = extract_keywords(body.query)
        
        # Generate a helpful fallback explanation
        fallback_explanation = f"""
Aapne poocha: "{body.query}"

**Database Connection Issue**: Currently Firestore database se connection nahi ho pa raha, lekin main aapko general legal information de sakta hun:

Indian Legal System ke bare mein:
- **Constitution of India**: Hamara supreme law hai
- **IPC (Indian Penal Code)**: Criminal offences define karta hai
- **CrPC (Criminal Procedure Code)**: Criminal cases ka procedure batata hai
- **CPC (Civil Procedure Code)**: Civil cases ka procedure hai

**Common Legal Terms**:
- **Section**: Kisi Act ka specific provision
- **Article**: Constitution mein specific clause
- **Bare Act**: Original act without commentary

**Next Steps**:
1. Backend server configuration check kariye
2. Firestore credentials setup kariye
3. Ya phir specific legal resource consult kariye

**Disclaimer**: Ye information educational purpose ke liye hai, legal advice nahi. Specific legal advice ke liye qualified lawyer se consult kariye.
        """
        
        return ExplainResponse(
            query=body.query,
            keywords=keywords,
            used_results=[],
            explanation=fallback_explanation.strip(),
        )
    
    search_response = search_law_internal(body.query)
    keywords = search_response.keywords
    results = search_response.results

    if not results:
        logger.info("No search results found for query='%s' in /explain-law", body.query)
        explanation_text = (
            "No clear match was found in the indexed bare acts/pages for this query.\n\n"
            "Try the following:\n"
            "- Type the exact name of the Act (for example: 'Digital Personal Data Protection Act 2023').\n"
            "- If you know it, also mention the section/article number (for example: 'Section 43 IT Act')."
        )
        return ExplainResponse(
            query=body.query,
            keywords=keywords,
            used_results=[],
            explanation=explanation_text,
        )

    max_results = min(body.max_results, MAX_RESULTS)
    used_results = results[:max_results]

    # Decide answer style: English or Hinglish based on query
    style = detect_hinglish_preference(body.query)

    # Collect a small set of act names to mention up-front
    main_acts = sorted({(r.act_name or "").strip() for r in used_results if r.act_name})[:3]
    acts_text = ", ".join(a for a in main_acts if a)

    if style == "hinglish":
        intro = (
            f"Tumne poocha: \"{body.query}\"\n\n"
            "Jo bare acts aur judgments mile hain, unko dekh kar simplified explanation ye hai:\n"
        )
        if acts_text:
            intro += f"Ye mainly in Acts/judgments se related hai: {acts_text}.\n\n"
    else:
        intro = (
            f"You asked: \"{body.query}\"\n\n"
            "Based on the bare acts and case law pages found in your documents, here is a simplified explanation:\n"
        )
        if acts_text:
            intro += f"This mainly relates to these Acts/judgments: {acts_text}.\n\n"

    # Bullet points based on top results
    bullet_lines: list[str] = []
    for r in used_results[:8]:
        title = (r.act_name or "").strip()
        if r.title:
            title = f"{title} – {r.title}" if title else r.title
        page = f"(Page {r.page_no})" if r.page_no is not None else ""
        snippet = (r.snippet or "").strip().replace("\n", " ")
        snippet = snippet[:220]

        if style == "hinglish":
            bullet_lines.append(
                f"- {title} {page}: simple words me roughly ye bataya gaya hai ki \"{snippet}\""
            )
        else:
            bullet_lines.append(
                f"- {title} {page}: in simple terms, this passage is talking about \"{snippet}\""
            )

    bullets_text = "\n".join(bullet_lines)

    # No extra important-notes/disclaimer block now
    explanation_text = intro + bullets_text

    return ExplainResponse(
        query=body.query,
        keywords=keywords,
        used_results=used_results,
        explanation=explanation_text,
    )