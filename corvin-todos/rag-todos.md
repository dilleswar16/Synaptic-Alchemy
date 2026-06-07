RAG — Concepts, Patterns, and Corvin's Position
Part 1: What RAG Actually Is
RAG stands for Retrieval-Augmented Generation. The core idea is simple: instead of relying on what the LLM memorized during training, you retrieve relevant information at query time and inject it into the prompt.


WITHOUT RAG:
  User: "What caused the PartnerAPIs outage?"
  LLM: [guesses from training data — knows nothing about your system]

WITH RAG:
  User: "What caused the PartnerAPIs outage?"
  Retrieval: [fetches 3 similar past incidents, runbook, site knowledge]
  LLM: [answers using actual retrieved evidence]
RAG solves four problems that pure LLMs cannot:

Problem	How RAG solves it
Training cutoff	Retrieve fresh, up-to-date data at query time
Hallucination	Ground claims in retrieved evidence
Private data	Your data never needs to be in training — just the retrieval index
Infinite knowledge	Store unlimited knowledge externally; retrieve only what's needed
The Three Generations of RAG
RAG has evolved through three distinct generations. Understanding each is essential because most teams implement Gen 1 and think they're done.

Generation 1: Naive RAG
The original architecture. Simple, effective for basic cases, breaks quickly at scale.


INDEXING (offline, done once):
  Document → Split into chunks → Embed each chunk → Store in vector DB

RETRIEVAL (online, per query):
  User query → Embed query → Search vector DB → Return top-k chunks

AUGMENTATION:
  [System prompt] + [top-k chunks] + [user query] → LLM → Answer
The 5 naive RAG failure modes:

Chunking mismatch — chunks are the wrong size. Too small: no coherent context. Too large: relevant info diluted by noise.
Embedding model mismatch — the model that embeds queries is different from the one that embedded documents. Similarity scores are meaningless.
Top-k is wrong — k=3 misses critical context; k=20 floods the prompt with irrelevant noise.
No filtering — retrieval returns results from wrong tenant, wrong service, wrong time period.
Context at the wrong position — retrieved chunks are placed at the end of the prompt, where LLMs pay least attention.
Generation 2: Advanced RAG
Adds intelligence before retrieval (query transformation), during retrieval (hybrid search, re-ranking), and after retrieval (compression, citation tracking).


PRE-RETRIEVAL (query transformation):
  ┌─ Query Rewriting: fix typos, expand abbreviations
  ├─ HyDE: generate a hypothetical answer, embed that instead of the query
  ├─ Query Expansion: add synonyms and related terms
  ├─ Step-back Prompting: ask a broader question first to retrieve context
  └─ Query Decomposition: break complex query into sub-queries

RETRIEVAL:
  ┌─ Hybrid Search: BM25 (keyword) + semantic vector search, merged with RRF
  ├─ Metadata Filtering: filter by service, date, environment BEFORE similarity
  └─ MMR: Maximal Marginal Relevance — diverse results, not just similar ones

POST-RETRIEVAL:
  ┌─ Re-ranking: cross-encoder re-scores the top-k results more accurately
  ├─ Context Compression: compress chunks to only the sentences that are relevant
  └─ Citation Tracking: record which chunk each claim came from
The most important advanced technique: HyDE


# Normal RAG — embed the alert text as the query:
query = "PartnerAPIs 503 errors, high latency, pod restarts"
query_embedding = embed(query)  # Matches keywords, misses semantic meaning

# HyDE — generate a hypothetical answer first, embed that:
hypothetical_doc = llm("Write a brief root cause analysis for: " + query)
# → "Likely cause: memory pressure causing OOM kills, 
#    resulting in pod restart loop and service degradation."
hypo_embedding = embed(hypothetical_doc)  # Matches semantically similar past RCAs
HyDE works because a past RCA document and a hypothetical RCA answer live in the same embedding space. An alert message lives in a completely different space.

Generation 3: Modular / Agentic RAG
Retrieval is no longer a single pre-generation step. The agent decides when, what, and how many times to retrieve.


SELF-RAG:
  LLM decides: "Do I need to retrieve? Yes/No"
  After retrieval: "Is this chunk relevant? Yes/No"
  After generation: "Is my answer grounded in evidence? Yes/No"

ITERATIVE RAG:
  Generate → check if confident → if not, retrieve more → regenerate → repeat

CORRECTIVE RAG (CRAG):
  Retrieve → evaluate relevance of results → if poor, trigger web search fallback

RAPTOR (Recursive Abstractive Processing):
  Chunk documents → cluster → summarize each cluster → 
  embed summaries → retrieval at multiple abstraction levels

GraphRAG:
  Build knowledge graph from documents → traverse relationships → 
  combine graph traversal with semantic search
The Key Technical Components You Must Know
Chunking Strategies
How you split documents determines everything downstream.

Strategy	How	Best For
Fixed-size	Every 512 tokens with 50-token overlap	Simple, fast — baseline
Sentence-based	Split on ., !, ?	Prose documents, Q&A
Semantic chunking	Split where embedding similarity drops	Mixed documents
Recursive splitting	Split on \n\n, then \n, then	Code, markdown
Hierarchical	Parent chunk + child sub-chunks	Long runbooks, policies
Proposition	Each chunk = one atomic fact	High-precision retrieval
The hierarchical strategy is critical for Corvin. A 50-page runbook should not be a single chunk. It should be: Runbook > Section > Procedure > Step. Retrieve at the step level, but show the section for context.

Embedding Models
The embedding model converts text into a dense vector. Similarity between two texts = cosine similarity of their vectors.


"Memory exhaustion"   → [0.12, -0.84, 0.33, ...]  (1536 dimensions)
"OOM kill"            → [0.11, -0.82, 0.31, ...]  (very close → high similarity)
"Network timeout"     → [0.67,  0.22, -0.44, ...]  (far away → low similarity)
"Pod restart loop"    → [0.09, -0.79, 0.35, ...]  (moderately close)
Models ranked:

Model	Dimensions	Best Use
text-embedding-3-large (OpenAI)	3072	Highest quality, general
text-embedding-3-small (OpenAI)	1536	Good quality, cheaper
text-embedding-ada-002 (OpenAI)	1536	Legacy, still widely used
azure/text-embedding-3-large	3072	Azure-hosted equivalent
sentence-transformers/all-mpnet	768	Self-hosted, good for code
Critical rule: Use the same embedding model for indexing and retrieval. Mixing models produces garbage similarity scores.

Vector Databases & Indexing Algorithms
Vector databases store embeddings and serve approximate nearest-neighbour searches.

The main options:

DB	Type	Best For
pgvector	Postgres extension	Already have Postgres, want simplicity
Pinecone	Managed cloud	No infra management, high scale
Weaviate	Self-hosted/cloud	Hybrid search built-in
Chroma	Embedded	Development, small datasets
FAISS	Library (not a DB)	In-memory, research
Milvus	Self-hosted	Massive scale
Indexing algorithms inside vector DBs:

HNSW (Hierarchical Navigable Small World) — fast search, good recall, higher memory. Default in pgvector.
IVF (Inverted File Index) — lower memory, slower but scalable to billions of vectors.
Flat — exact search, no approximation. Only for small datasets (<100K).
Hybrid Search
Pure semantic search misses exact matches. Pure keyword search misses synonyms. Hybrid search combines both.


Query: "PartnerAPIs OOM kill"

BM25 (keyword/TF-IDF):
  Results: docs containing exact words "OOM", "kill", "PartnerAPIs"
  Score: based on term frequency × inverse document frequency

Semantic (vector):
  Results: docs semantically similar to "memory exhaustion, pod restart"
  Score: cosine similarity of embeddings

Fusion (RRF — Reciprocal Rank Fusion):
  final_score = 1/(k + bm25_rank) + 1/(k + semantic_rank)
  Merged, de-duplicated, re-ranked list
Why RRF? BM25 and semantic scores are on different scales and can't be added directly. RRF uses rank position instead of raw score — robust and parameter-free.

Re-ranking
The first retrieval is approximate. Re-ranking applies a more expensive but more accurate model to re-score the top-k results.


Step 1 — Fast Retrieval: top-20 candidates from vector search (fast, approximate)
Step 2 — Re-ranking:     cross-encoder scores each of the 20 for (query, chunk) pair
Step 3 — Final:          top-5 of the re-ranked results
Cross-encoder vs bi-encoder:

Bi-encoder (what vector search uses): embed query separately, embed doc separately, compare. Fast but approximate.
Cross-encoder (what re-ranking uses): feed query + doc together into the model. It attends across both. Slower but dramatically more accurate.
Popular re-rankers: Cohere Rerank, cross-encoder/ms-marco-MiniLM, bge-reranker.

RAG Evaluation: RAGAS
Without evaluation, you don't know if RAG is helping or hurting. RAGAS is the standard framework.

Metric	Question it answers	How measured
Faithfulness	Is the answer grounded in retrieved context?	Claims in answer ÷ claims in context
Answer Relevance	Does the answer address the question?	Embedding similarity of question ↔ answer
Context Precision	Are retrieved chunks actually relevant?	Proportion of retrieved chunks used
Context Recall	Did we retrieve all needed information?	Claims in ground truth ÷ claims in context
Answer Correctness	Is the answer factually correct?	Requires ground truth labels
The key insight: Context Precision and Faithfulness together tell you if RAG is adding noise (low precision) or if the LLM is ignoring good context (low faithfulness). Fix the weaker one first.

Part 2: Corvin's RAG — Complete Analysis
What Corvin IS Touching (Partially)
1. Multi-source knowledge injection in prompt_builder.py

Corvin assembles a layered system prompt with 6 context sections:


# prompt_builder.py
sections = [
    "## Site Knowledge\n\n" + site_knowledge,       # Infrastructure facts
    "## Relevant Runbook\n\n" + runbook_content,     # Operational procedures
    "## Learnings from Past Incidents\n\n" + ...,    # Accumulated patterns
    "## Predictive Penalties\n\n" + ...,             # Missed predictions
    "## Operator Context\n\n" + request.description, # Human input
    "## Similar Past Incidents\n\n" + past_md,       # Historical RCAs
]
This is conceptually correct RAG — retrieve context from multiple knowledge sources, inject before generation. But the retrieval mechanism for each source is weak (see anti-patterns below).

2. Historical incident retrieval via get_similar_incidents()

The repository queries past incidents and the prompt builder injects the top-3. An agent tool (get_similar_incidents) also exposes this to the Corvin Command Center. The pattern — retrieve historical cases, inject as context — is exactly what RAG is for.

3. Jaccard similarity in similarity_network.py

The similarity network uses a 3-signal scoring model (service match 40%, RCA text Jaccard 40%, time proximity 20%). This is a hand-crafted retrieval model — not semantic, but it is a form of similarity-based retrieval.

4. Feature 7 pgvector config (planned, not implemented)


similarity:
  backend: pgvector
  top_k_default: 5
  min_similarity_threshold: 0.72
  index_on_completion: true
The configuration, test stub, and fallback auto-detection logic all exist. Feature 7 is the intended path to true semantic RAG.

5. Metadata pre-filtering

get_similar_incidents() filters by service_name and environment before any similarity scoring. This is correct — metadata filtering should narrow the candidate set before semantic search runs.

What's MISSING
1. No embedding model — anywhere.

The biggest gap. There are zero calls to any embedding API in the entire codebase. pgvector is configured but has no embedding pipeline feeding it. Every similarity comparison is either SQL (recency) or Jaccard (keyword overlap). There is no semantic understanding of what "similar" means.


# What needs to exist (doesn't):
def index_completed_investigation(rca: RCAOutput):
    text = f"{rca.summary} {rca.root_cause}"
    embedding = litellm.embedding(model="azure/text-embedding-3-large", input=text)
    db.execute("UPDATE rca_outputs SET embedding = ? WHERE request_id = ?",
               [embedding.data[0].embedding, rca.request_id])
2. No chunking of knowledge documents.

Site knowledge and runbooks are loaded as complete files and injected wholesale:


site_knowledge = loader.load_site_knowledge(service_name)  # entire file
runbook_content = loader.load_matching_runbooks(...)         # entire matched runbook
If these files are large, 70% of the injected content is irrelevant to the current incident. No chunking, no relevance scoring, no "retrieve only the relevant section."

3. No hybrid search.

The planned pgvector path is pure semantic. There's no BM25 layer for exact keyword matching. An incident with a very specific error code (ECONNRESET_0x8003) would be retrieved poorly by semantic search (rare term, unusual embedding) but perfectly by BM25.

4. No re-ranking.

Even when pgvector is implemented, the top-k results will be returned by cosine distance alone. No cross-encoder re-ranking to promote the most relevant result above the merely similar ones.

5. No HyDE (Hypothetical Document Embedding).

The query being embedded for retrieval will be the raw investigation request: "PartnerAPIs, prod, alert: high 5xx rate". This is an alert message — it lives in a completely different embedding space from past RCA documents. The retrieval will perform poorly because the query and the indexed documents are semantically unlike.

The fix is HyDE: generate a short hypothetical RCA summary from the alert first, then embed that for retrieval. A hypothetical RCA lives in the same embedding space as real past RCAs.

6. No context compression before injection.

Retrieved content goes directly into the prompt. If similar_incident_3 has 800 tokens of RCA detail but only 50 tokens are relevant to the current case, all 800 tokens consume context budget and potentially confuse the model.

7. No citation tracking.

The RCA output has an evidence_references field but it references the raw evidence bundle (elastic logs, AKS metrics) — not the retrieved knowledge documents. There is no way to tell: which past incident influenced the RCA? Which runbook section was used? Which site knowledge claim was cited?

8. No indexing pipeline for evidence.

The 42 elastic log lines are passed as a raw blob. These are the most directly relevant pieces of information in the entire pipeline, yet they have no retrieval structure. In a mature RAG system, log records would be embedded at collection time so that the LLM can ask targeted retrieval queries against them: "find log entries containing ERROR and OOMKilled in the last 30 minutes."

9. No RAG evaluation (RAGAS or equivalent).

There is no measurement of:

Is the retrieved context actually being used in the RCA? (Context Precision)
Did retrieval miss relevant past incidents? (Context Recall)
Is the RCA faithful to the retrieved + live evidence? (Faithfulness)
Anti-Patterns in Corvin's Current RAG
Anti-pattern 1: Recency = Relevance (the SQL RAG trap)


# repository.py — what currently runs:
SELECT * FROM investigation_requests
WHERE service_name = 'PartnerAPIs' AND environment = 'prod'
ORDER BY completed_at DESC
LIMIT 3
This retrieves the 3 most recent incidents for the same service — not the 3 most similar. A service that has had a network timeout last week and an OOM kill two weeks ago will inject the network timeout as "similar context" for a new OOM incident. The retrieved context is actively misleading.

Anti-pattern 2: Jaccard on RCA text ≠ Semantic Similarity


# similarity_network.py
jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
"Memory exhaustion" and "OOM kill" share zero tokens → Jaccard = 0.0 (not similar).
They are semantically identical in the SRE domain. Jaccard cannot capture synonymy, domain terminology, or paraphrase. Two incidents with the same root cause described in different words score as unrelated.

Anti-pattern 3: Whole-file Knowledge Injection Without Relevance Scoring


# prompt_builder.py
site_knowledge = loader.load_site_knowledge(service_name)
sections.append(f"## Site Knowledge\n\n{site_knowledge}")
If site_knowledge has 4000 tokens and only the 200 tokens about memory configuration are relevant to an OOM incident, you've spent 3800 tokens on noise. For a P1 incident at 3am, every wasted token is latency and cost. Worse, irrelevant context has been shown to decrease LLM accuracy ("distraction tokens" in the literature).

Anti-pattern 4: Similar Incidents Injected at the End of the Prompt


# prompt_builder.py — order of sections:
1. Site Knowledge
2. Relevant Runbook
3. Learnings
4. Predictive Penalties
5. Operator Context    ← human input
6. Similar Past Incidents  ← LAST
Research on LLM attention ("Lost in the Middle", Liu et al. 2023) shows models attend most strongly to the beginning and end of the context. Historical incident patterns — the most actionable retrieved knowledge — are in last position, which should mean high attention, but they're sandwiched between operator context and the closing delimiter. More critically, site knowledge and runbooks (which are far less incident-specific) are at the beginning, getting disproportionate attention.

The correct ordering for maximum retrieval utility:


1. System role definition
2. Similar Past Incidents  ← most relevant retrieved knowledge
3. Relevant Runbook section ← procedural knowledge
4. Operator Context        ← ground truth from human
5. Site Knowledge          ← background context
6. Evidence summary        ← the actual data to analyze
Anti-pattern 5: No Relevance Threshold on Injection

If get_similar_incidents() returns 3 results and one of them is a completely unrelated incident (same service name, totally different failure mode), it still gets injected. There is no similarity score threshold — inject = True as long as the query returns rows. An irrelevant past incident injected into a P1 RCA is a precision problem that actively degrades output quality.

Anti-pattern 6: Evidence Bundle as RAG Candidate

The 42 elastic log lines are passed as raw data to the RCA generator — not as a retrievable knowledge base. The LLM processes all 42 logs regardless of relevance. If 35 of them are INFO-level heartbeats and only 7 are ERROR/WARN lines relevant to the incident, the model must process 5x more noise than signal. RAG on the evidence bundle (embed + retrieve the relevant log entries) would dramatically improve RCA precision.

Patterns That COULD Be Used
1. HyDE for Past Incident Retrieval — High ROI, Low Effort


def retrieve_similar_incidents_hyde(request: InvestigationRequest) -> list[dict]:
    # Step 1: Generate hypothetical RCA summary
    hypo_rca = litellm.completion(
        model="azure/gpt-4.1-mini",
        messages=[{
            "role": "user",
            "content": f"In 2 sentences, what is the likely root cause of: {request.description}"
        }]
    ).choices[0].message.content
    
    # Step 2: Embed the hypothetical RCA (not the alert text)
    embedding = litellm.embedding(model="azure/text-embedding-3-large", input=hypo_rca)
    
    # Step 3: pgvector cosine similarity against indexed past RCAs
    return db.execute(
        "SELECT * FROM rca_outputs ORDER BY embedding <=> ? LIMIT 5",
        [embedding.data[0].embedding]
    )
HyDE would work out of the box once Feature 7 pgvector is implemented. The hypothetical RCA approach matches Corvin's domain perfectly because every investigation produces an RCA — the index is already the right document type.

2. Hierarchical Chunking for Runbooks


runbook-partner-apis.md
  └── Section: "High 5xx Error Rate"         ← parent chunk (embed summary)
        └── Step 1: Check pod logs            ← child chunk (embed full text)
        └── Step 2: Check upstream dependency ← child chunk
        └── Step 3: Roll back if recent deploy ← child chunk
Retrieve at the step level (most specific), but display the section level (broader context). This solves the whole-file injection problem without losing procedural coherence.

3. Self-RAG — LLM Decides When to Retrieve

The Corvin Command Center agent already has a get_similar_incidents tool. Self-RAG formalizes this: add a retrieve_runbook_section(query) and retrieve_site_knowledge(query) tool so the LLM can pull exactly the knowledge it needs, exactly when it needs it — rather than injecting all knowledge upfront in the system prompt.


# Tools for Self-RAG pattern:
{"name": "retrieve_runbook_section",
 "description": "Search the operational runbooks for procedures relevant to a specific error or condition.",
 "parameters": {"query": "string — describe what you are looking for"}}

{"name": "retrieve_past_rca",
 "description": "Find past incident RCAs semantically similar to the current failure pattern.",
 "parameters": {"incident_description": "string"}}
4. GraphRAG on Service Topology

Corvin has service topology data (blast radius, dependencies). GraphRAG would build a knowledge graph where:

Nodes = services
Edges = dependencies (calls, data flows)
Properties = past incident history per service
When PartnerAPIs has an incident, GraphRAG would traverse: PartnerAPIs → depends_on → UpstreamService → has_had → [7 past incidents] and surface the upstream correlation patterns that pure semantic search would miss.

5. Corrective RAG (CRAG) on Evidence Quality


# After evidence collection:
evidence_quality_score = evaluate_evidence(evidence_bundle)

if evidence_quality_score < 0.4:
    # Retrieval was insufficient — trigger fallback
    # Option 1: Widen the time window and re-collect
    # Option 2: Lower the similarity threshold and fetch more past incidents
    # Option 3: Flag to human: "Insufficient evidence — please provide more context"
Corvin has the confidence gate but no retrieval fallback. CRAG adds: when collected evidence is poor quality, automatically attempt an alternative retrieval strategy before giving up.

6. RAGAS Evaluation Pipeline


# After each closed investigation where outcome is known:
ragas_eval = evaluate(
    dataset=[{
        "question": request.description,
        "answer": rca.root_cause,
        "contexts": [past_incident_1.root_cause, runbook_section, site_knowledge_chunk],
        "ground_truth": actual_root_cause  # from post-mortem or operator feedback
    }],
    metrics=[faithfulness, answer_relevance, context_precision, context_recall]
)
# Store scores in investigation_requests for trend monitoring
Summary Scorecard — RAG

RAG Component                  Status          Completeness
──────────────────────────────────────────────────────────
Knowledge Source Variety       ✅ Touching      60%  (4 sources injected, not retrieved)
Semantic Embedding             🔴 Missing        0%  (no embedding model called anywhere)
Vector Storage (pgvector)      🟡 Configured    15%  (config + schema planned, not implemented)
Chunking Strategy              🔴 Missing        0%  (whole files injected)
Hybrid Search (BM25+semantic)  🔴 Missing        0%
HyDE Query Transformation      🔴 Missing        0%
Re-ranking                     🔴 Missing        0%
Metadata Pre-filtering         ✅ Present       70%  (service + environment filter in SQL)
Context Compression            🔴 Missing        0%
Citation Tracking              🟡 Partial       20%  (evidence_references on evidence, not retrieved docs)
Evidence RAG (live data)       🔴 Missing        0%  (logs passed raw, not indexed+retrieved)
RAG Evaluation (RAGAS)         🔴 Missing        0%

──────────────────────────────────────────────────────────
Overall RAG Maturity                           ~14%
The honest picture: Corvin has the shape of RAG — it retrieves knowledge and injects it before generation — but the retrieval engine is currently SQL + keyword, not semantic. Feature 7 (pgvector) is the intended fix, but even with pgvector, the anti-patterns (no HyDE, no chunking, no re-ranking, wrong prompt ordering) would limit its effectiveness.

Priority Roadmap for RAG Maturity
Priority	What	Why	Effort
1	Implement embedding pipeline	Feature 7 foundation — embed RCA on completion, store in pgvector	2 days
2	Replace SQL similar_incidents with pgvector cosine search	Eliminates "recency = relevance" anti-pattern	1 day
3	Add similarity threshold before injection	Stop injecting irrelevant past incidents	2 hours
4	Add HyDE to the retrieval query	Dramatically improves retrieval precision for new incidents	1 day
5	Chunk runbooks and site knowledge	Inject only relevant sections, not whole files	2 days
6	Reorder prompt sections	Most relevant retrieved context at beginning	2 hours
7	Add retrieve_runbook_section tool	Self-RAG — agent pulls knowledge on demand	1 day
8	Hybrid search (BM25 + pgvector)	Catches exact matches semantic search misses	2 days
9	RAGAS evaluation on closed investigations	Measure if RAG is actually helping	3 days
Items 1–4 bring RAG maturity from ~14% to ~60%. Items 5–9 complete the mature RAG architecture.