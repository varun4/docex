# Progress

- Build step complete: added rule in `AGENTS.md` to update `progress.md` after each build step.
- Build step complete: added Step 1 context for designing the document ingestion system.
- Step 1 context: defined Component 1 as a tenant-isolated ingestion and digestion pipeline covering full ingestion of existing documents and delta ingestion for create/update/delete changes.
- Step 1 decisions: use idempotent processing by document version/hash, maintain versioned document records in a catalog, attach citation-ready provenance metadata at chunk level, and include reliability controls (retries, dead-letter handling, and per-tenant monitoring).
- Build step complete: added inference layer design to `DESIGN.md` covering query orchestration and retrieval, grounded LLM answer generation, and citation/source-link response construction.
- Inference decisions: tenant-scoped query API, retrieval with reranking and evidence assembly, grounded-only generation with insufficient-evidence fallback, and sentence/claim-level citation mapping with source metadata links.
- Build step complete: rewrote `DESIGN.md` into a compact end-state design with three sections: component design and interactions, RAG design and data model, and API design and models.
- Build step complete: finalized ingestion format support in design for `txt`, `pdf`, `docx`, and `xlsx` (including multi-sheet spreadsheet anchors for citations).
- Build step complete: updated design for folder-based client separation during ingestion and delta sync.
- Tenant-folder decisions: each tenant is bound to a dedicated source `root_path`; full and delta processing are scoped to that folder; delta cursors are tracked per tenant folder.
- Build step complete: committed current design and progress updates to git (`e485762`).
- Build step status: push to `origin/main` failed due missing SSH key authorization (`Permission denied (publickey)`).
