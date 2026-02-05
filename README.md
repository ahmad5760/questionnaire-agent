# Questionnaire Agent

Minimal full-stack implementation using FastAPI, PostgreSQL, ChromaDB, and Ollama.

## Run
1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a PostgreSQL database (example: `questionnaire`).

3. Configure environment:

```bash
copy .env.example .env
```

4. Ensure Ollama is running and models are pulled:

```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```

5. Start the API:

```bash
uvicorn backend.main:app --reload
```

6. Open `http://localhost:8000` for the UI.

## Use
1. Upload documents in **Document Ingestion**. Supported formats: PDF, DOCX, XLSX, PPTX.
2. Create a project with a name, scope, and questionnaire text (one question per line; `Section:` or `#` lines are treated as section headers).
3. Click **Generate Answers** or enable **Auto-generate answers after parsing**.
4. Review answers in **Question Review** and mark them `CONFIRMED`, `REJECTED`, or `MANUAL_UPDATED`.
5. In **Evaluation Report**, select questions, enter ground-truth answers, then **Run Evaluation** to compare AI vs. human.

## System Design Report

### 1) Product & Data Model Alignment
1. **End-to-end data flow**
   1. Upload document -> parse -> chunk -> embed -> index in Chroma -> store chunk metadata.
   2. Create project -> parse questionnaire -> create questions -> create answer placeholders.
   3. Generate answers -> retrieve relevant chunks -> prompt LLM -> store answer, citations, confidence.
   4. Review -> store manual answer + status transitions for auditability.
   5. Evaluation -> compare AI vs. human -> store per-question and aggregate scores.

2. **Core entities**
   1. `Project`: name, scope, status, config, created/updated timestamps.
   2. `Document`: filename, content type, status, storage path.
   3. `ProjectDocument`: join table for selected-doc scopes.
   4. `Question`: section, order index, text.
   5. `Answer`: AI answer, citations, confidence, manual answer, status, timestamps.
   6. `DocumentChunk`: text, page, bbox, metadata.
   7. `Evaluation`: metrics, status, timestamps.

3. **Enumerations and status transitions**
   1. `ProjectStatus`: `CREATED -> PARSING -> READY -> GENERATING -> REVIEW -> EVALUATING -> EVALUATED`.
   2. `ProjectStatus`: `OUTDATED` when new documents are indexed for `ALL_DOCS` projects.
   3. `AnswerStatus`: `PENDING -> GENERATED -> CONFIRMED/REJECTED/MANUAL_UPDATED` with `MISSING_DATA` and `STALE` as explicit states.

### 2) Document Ingestion & Indexing
1. **Ingestion**
   1. Files are stored in `storage/documents`.
   2. Parser extracts text and page metadata.

2. **Multi-layer index**
   1. Layer 1 (Retrieval): semantic search over chunks for each question.
   2. Layer 2 (Citations): store per-chunk metadata with `document_id`, `chunk_id`, `page`, `bbox`, `text_snippet`.

3. **Outdated projects**
   1. When new documents are indexed, all `ALL_DOCS` projects are marked `OUTDATED` and prior `GENERATED` answers move to `STALE`.

### 3) Questionnaire Parsing & Project Lifecycle
1. **Parsing**
   1. Supports sections via `Section:` or `#` prefixes.
   2. Preserves question order via `order_index`.

2. **Lifecycle**
   1. Create project -> parse questionnaire -> create questions + `PENDING` answers -> mark project `READY`.
   2. If `auto_generate` is enabled, answer generation runs in the background.
   3. Update project config or scope -> mark project `OUTDATED` and answers `STALE` -> optionally auto-regenerate.

### 4) Answer Generation with Citations & Confidence
1. **Behavior**
   1. Retrieve top-k chunks per question with optional document filters.
   2. Build a prompt using question + retrieved context.
   3. Store `ai_answer_text`, `ai_citations`, and `ai_confidence`.

2. **Answerability and fallback**
   1. If no relevant chunks, set `MISSING_DATA` with answerable = false.
   2. If similarity below threshold, set `MISSING_DATA` with answerable = false.

3. **Confidence**
   1. Confidence is derived from chunk similarity scores and persisted per answer.

### 5) Review & Manual Overrides
1. Review actions update `manual_answer_text`, `manual_answerable`, and `status`.
2. Manual answers are preserved alongside AI output for auditability and evaluation.

### 6) Evaluation Framework
1. **Comparison method**
   1. Semantic similarity using embeddings.
   2. Keyword overlap using token intersection.
   3. Overall score = `0.7 * semantic + 0.3 * keyword`.

2. **Output**
   1. Per-question scores and explanations.
   2. Aggregate metrics across the project.

### 7) Optional Chat Extension
1. Chat queries the same indexed corpus and returns citations.
2. Chat does not mutate project or answer statuses.

### 8) Frontend Experience (High-Level)
1. **Screens**
   1. Document management and status tracking.
   2. Project list and project detail.
   3. Question review with AI + manual answers.
   4. Evaluation report with question selection and ground-truth entry.

2. **Key interactions**
   1. Create project, select scope, track status.
   2. Generate and review answers.
   3. Evaluate AI vs. human responses.

## Key Endpoints
1. `POST /documents`: Upload a file and start ingestion.
2. `GET /documents`: List documents and indexing status.
3. `POST /projects`: Create a project and parse questionnaire.
4. `GET /projects`: List projects.
5. `GET /projects/{id}`: Project detail.
6. `PATCH /projects/{id}`: Update config or scope and mark `OUTDATED`.
7. `POST /projects/{id}/generate`: Trigger answer generation.
8. `GET /projects/{id}/questions`: List questions.
9. `GET /projects/{id}/answers`: List answers.
10. `PATCH /answers/{id}/review`: Save manual review and status.
11. `POST /projects/{id}/evaluate`: Run evaluation vs ground truth.
12. `POST /chat`: Ask a retrieval-only question with citations.

## Acceptance Criteria

### A. Documentation Completeness
1. Document includes all 8 scope areas above.
2. Every API endpoint listed is explained in context (create, update, answer, index, status).
3. Data structures in the spec are mapped to system design.

### B. Functional Accuracy
1. Workflow shows: upload -> index -> create project -> generate answers -> review -> evaluation.
2. Answers always include: answerability statement, citations, confidence score.
3. Projects with `ALL_DOCS` become `OUTDATED` when new docs are indexed.

### C. Review & Auditability
1. Manual edits are preserved alongside AI results.
2. Answer status transitions are explicitly described.

### D. Evaluation Framework
1. Clear method for comparing AI vs. human answers.
2. Output includes numeric score and qualitative explanation.

### E. Non-Functional Requirements
1. Async processing and status tracking are described.
2. Error handling, missing data, and regeneration logic are described.

### F. Frontend UX
1. All core user workflows are described.
2. Create/update project.
3. Review answers.
4. Track background status.
5. Compare AI vs. human.
