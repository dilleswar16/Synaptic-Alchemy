# 08 — Proposal: retrieval-augmented knowledge base (RAG)

**Status:** proposal for a later phase. Today Keigan may use LangChain, LangGraph and direct model APIs, but no vector database is provisioned.
This document describes what Keigan does now, why it will hit limits, and the proposed RAG design so the switch is a contained change.

## 1. What Keigan does today (no vector store)

1. **AI digests at upload:** every document (Copilot Markdown, PDF, architecture image description) is summarised into a structured digest (components, APIs, dependencies, failure modes, operational commands). Digests are small and always included for the relevant services.
2. **Chunking with headings:** documents are split on headings into ~500-token chunks stored in `knowledge_chunk` with normalised term frequencies.
3. **Lexical retrieval (BM25) in Python:** at investigation/chat time, chunks of the application are scored against the query (incident summary, symptoms, service names, error templates). Top chunks fill the knowledge token budget.
4. **Topology:** a compiled, reviewed model of the application, always included in compact form.

This works well for tens of documents per application because the application scope is small and error messages share vocabulary with code documentation.

## 2. Where it will hit limits

- Synonyms and paraphrase ("connection pool exhausted" vs "no available connections in HikariCP").
- Cross-lingual retrieval (Japanese runbooks, English logs).
- Hundreds of documents per application or organisation-wide knowledge (CMDB, EI portal, enterprise knowledge API).
- Retrieval of past incidents and postmortems by similarity ("we've seen this before").

## 3. Proposed design

```
Ingestion (worker job digest_knowledge_document → embed_knowledge_chunks)
  document → extract → chunk (heading-aware, 400–600 tokens, 15 % overlap) → PII mask → embed → upsert {chunk_id, application_id, service_id, document_category, language, text, vector}
Retrieval (KnowledgeService.build_grounding_context)
  query → (optional) query rewrite (fast model, adds synonyms + Japanese/English variants)
        → hybrid search: vector top-k (k=20) ∪ BM25 top-k (k=20), filtered by application_id (+ service_ids)
        → reciprocal rank fusion → re-rank (cross-encoder or LLM re-rank of top 20 → 6) → token budget packing with source labels [K1]…
```

| Decision | Proposal | Alternatives |
|---|---|---|
| Vector store | **Azure AI Search** (hybrid search, semantic ranker, security filters, managed in Azure) | PostgreSQL `pgvector` (reuse Keigan DB; simplest ops), Azure Cosmos DB vector search |
| Embedding model | Azure OpenAI `text-embedding-3-large` (3072 dims, multilingual) via the same gateway (`LlmGateway.embed_texts`) | `text-embedding-3-small` for cost |
| Security trimming | Filter on `application_id` from the user's readable set at query time; never cross-application by default | — |
| Freshness | Re-embed on document replace; nightly sweep for stale (> 90 days) | — |
| Past incidents | Index postmortems and confirmed RCAs as a separate `incident_memory` collection → "similar past incidents" in investigations | — |
| Evaluation | Golden set of 30 questions per pilot application; measure recall@6 and answer faithfulness before/after | — |

## 4. Code impact (contained)

- `KnowledgeService.build_grounding_context()` keeps its signature; internally selects `LexicalRetriever` (today) or `HybridRetriever` (RAG) by `KNOWLEDGE_RETRIEVAL_MODE=lexical|hybrid`.
- New `integrations/vector_store_client.py` (Azure AI Search or pgvector implementation behind one interface).
- `LlmGateway.embed_texts()` added (provider-neutral via LangChain embeddings).
- `knowledge_chunk` gains `embedding_status`, `embedding_model_name`, `embedded_at` (vectors live in the vector store, not in the Keigan DB, unless pgvector is chosen).
- One backfill job to embed existing chunks.

## 5. Cost and capacity (indicative)

50 applications × 40 documents × 30 chunks ≈ 60 000 chunks × 500 tokens = 30 M tokens one-off embedding; incremental cost per upload is small.
Azure AI Search Basic/S1 tier is sufficient for this volume.

## 6. Prerequisites to request

1. Azure AI Search service (or pgvector extension on the Keigan PostgreSQL server).
2. Embedding deployment on the internal Azure OpenAI wrapper.
3. Keigan managed identity granted `Search Index Data Contributor` on the index.
