# How to Use the LLM Service

This guide explains how to use the Dimension API Brain LLM Service: authentication, conversations, chat (single agent and panel), RAG with citations, and document import.

**Base URL:** `http://localhost:8000` (or your deployment URL; if behind a reverse proxy, use prefix e.g. `/llm`)

**Response format:** Successful responses are `{ "status": true, "resultData": { ... } }`. Errors return `status: false` and error details in `resultData`.

---

## 1. Authentication

All endpoints require a JWT Bearer token.

- **Header:** `Authorization: Bearer <JWT_TOKEN>`
- The token must contain a `user_id` claim (UUID string). Obtain the token from your authentication service.

Example:

```
GET /agents
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 2. Agents

- **List agents:** `GET /agents` — Returns agents you can use (your own + public).
- **Get one agent:** `GET /agents/{agent_id}` — Use `agent_id` in chat requests.

Agents define the AI persona via `agent_prompt`. You choose one agent per chat message (or multiple in panel chat).

---

## 3. Conversations

- **Create conversation:** `POST /conversations`  
  Body: `{ "message_content": "First message or topic", "llm_provider": "openai" }`  
  Creates a conversation and sets its topic (optionally generated from the first message).

- **List conversations:** `GET /conversations`
- **Get conversation (with messages):** `GET /conversations/{conversation_id}`
- **Rename:** `PATCH /conversations/{conversation_id}` — Body: `{ "conversation_topic": "New topic" }`
- **Delete:** `DELETE /conversations/{conversation_id}`

---

## 4. Chat (single agent)

**Endpoint:** `POST /conversations/chat`

**Body:**

```json
{
  "conversation_id": "<UUID>",
  "message_content": "Your question or message",
  "agent_id": "<UUID>",
  "llm_provider": "openai",
  "use_rag": false,
  "workspace_id": null,
  "attach": { "nodes": [], "files": [] },
  "max_reasoning_loops": 1,
  "rag_top_k": 5
}
```

- **use_rag:** If `true`, the service runs **semantic search** over node_vector (by similarity), selects the **top-k chunks** (see `rag_top_k`), injects them into context, and returns **citations** in the response (source node/chunk and snippet). When `use_rag` is true, send **workspace_id** (current workspace) to scope search to nodes in that workspace. If **cross-lingual search** is enabled (see §6), queries in one language can also retrieve chunks with similar meaning in the other language (Thai/English).
- **workspace_id:** Optional UUID of the current workspace. When `use_rag` is true, send this to scope semantic search to nodes in the workspace.
- **attach:** Optional explicit context (each gets a citation):
  - **nodes:** List of node UUIDs to attach (full content injected and cited).
  - **files:** List of file UUIDs to attach (parsed and injected, cited).
- **max_reasoning_loops:** Max reasoning steps before answering (default 1). Set to 2 or more to have the model reason step-by-step (up to N steps) before giving the final answer.
- **rag_top_k:** When `use_rag` is true, number of **top chunks by similarity** to retrieve from node_vector (default 5, max 20). The service selects the k best-matching chunks for context.

**Note:** `max_history` is hardcoded (10) in the backend.

**Response:** Includes `user_message`, `agent_response`, `citations` (when RAG or attach was used). Citations reference `source_type`, `node_id`/`file_id`, `snippet`, and for RAG chunks `similarity`. **If `citations` is empty:** ensure `use_rag` is true and nodes are embedded (run document process + embedding job), or attach at least one node/file; RAG uses a permissive similarity threshold so chunks are returned when data exists.

---

## 5. Panel chat (multiple agents)

**Endpoint:** `POST /conversations/chat/panel`

**Body:**

```json
{
  "conversation_id": "<UUID>",
  "message_content": "Your message",
  "agent_ids": ["<agent_uuid_1>", "<agent_uuid_2>"],
  "llm_provider": "openai",
  "max_history": 10
}
```

One user message is stored; each agent in `agent_ids` responds. The response contains `user_message` and `agent_responses`: a list of `{ "agent_id", "agent_name", "message" }`.

---

## 6. RAG search (standalone)

**Endpoint:** `POST /rag/search`

**Body:**

```json
{
  "query": "Natural language search query",
  "limit": 10,
  "min_similarity": 0.7,
  "scope_node_ids": null
}
```

Returns semantic search results over embedded node chunks: `node_id`, `chunk_id`, `node_content_md_chunk`, `similarity`. Use this to test RAG or build custom flows.

**Cross-lingual search:** When enabled, the service translates the query to the other supported language (Thai ↔ English) and merges results so that content with **similar meaning in a different language** is also found (e.g. searching in English can return Thai chunks that mean the same). This is controlled by:

- **RAG_CROSS_LINGUAL_ENABLED** (env, default `true`) — Set to `false` to disable query translation and use single-language search only.
- **RAG_QUERY_TRANSLATE_LLM_PROVIDER** (env, default `openai`) — LLM provider used to translate the query (e.g. `openai`, `gemini`, `anthropic`).

---

## 7. Document import and processing

### 7.1 Upload a file

**Endpoint:** `POST /documents/import`

- **Content-Type:** `multipart/form-data`
- **Body:** One file field (e.g. `file`) with a file attachment.
**Allowed types:** `.docx`, `.pdf`, `.jpg`, `.jpeg`, `.png`

**Response:** `file_id`, `file_name`, `file_size`, `mime_type`, `file_path`, `created_at`. Import only stores the file; call `POST /documents/{file_id}/process` to parse and create nodes.

### 7.2 Process document (parse, reformat, create node, embed)

**Endpoint:** `POST /documents/{file_id}/process`

Processing runs **asynchronously**: the API registers a job and returns immediately. A **job daemon** (running with the app) picks up the job and runs parsing, node creation, and optional embedding. Poll `GET /jobs/{job_id}` for status; when `status` is `SUCCESS`, the job metadata contains `node_id`, `node_name`, and optionally `embedding_job_id`.

**Body:**

```json
{
  "workspace_id": "YOUR-WORKSPACE-UUID",
  "reformat_options": ["summarize", "to_bullet_points"],
  "llm_provider": "openai",
  "create_node": true,
  "max_pages_per_call": 5
}
```

Send header **`Authorization: Bearer <token>`** when `create_node` is true (for main backend `/nodes` and `/relations`).

- **reformat_options:** Optional list; you can select one or more or none:
  - **rearrange** — Reorder sections for clarity
  - **fill_missing_ai** — Fill obvious gaps with AI
  - **to_bullet_points** — Convert paragraphs to bullets
  - **to_table** — Format tabular content as markdown tables
  - **summarize** — Add a short summary (e.g. at top or in node description)

- **create_node:** If `true`, a Node is created with the (optionally reformatted) text and an **embedding job** is started. When the process job completes, metadata includes `embedding_job_id` to poll for embedding completion.

- **Extraction (always LLM-heavy for accuracy):** **PDF** and **images** (`.jpg`/`.jpeg`/`.png`) are read with a **vision LLM**. **DOCX** is parsed locally, then the text is always passed through an **LLM refinement** step (`apply_llm_extract`) before optional reformat.
- **max_pages_per_call:** For **PDF** vision extraction, pages per LLM request (default 5, max 20). Use 1 for OCR-style (one page per call). Use 5–10 for fewer API calls on large docs.

**Response:** `202 Accepted` with `file_id`, `job_id` (process job). `node_id` and `node_name` are `null` until the job completes; then they appear in `GET /jobs/{job_id}` metadata.

**JobTypes:** The job type `process_document` must exist in the `JobTypes` table. If you get a foreign-key error when creating the job, run:
`INSERT INTO "JobTypes" ("Job_type_id") VALUES ('process_document') ON CONFLICT DO NOTHING;`

**Scanned PDFs:** PDFs are handled primarily via **vision LLM** (not Tesseract-first). Ensure your LLM provider supports vision for PDF page images.

---

## 8. Job status (process and embedding)

Document processing and node embedding run as background jobs. Poll for status and result:

- **Get job (status + metadata):** `GET /jobs/{job_id}`  
  Returns full job record: `status` (e.g. `PENDING`, `PROCESSING`, `SUCCESS`, `FAILED`) and `metadata`. When status is `SUCCESS`, metadata includes `node_id`, `node_name`, and optionally `embedding_job_id` (for embedding job created when `create_node: true`).

- **Get job status (lightweight):** `GET /jobs/{job_id}/status`  
  Returns `status` and optional progress metadata (`stage`, `progress`).

- **Get all jobs:** `GET /jobs` or `GET /jobs/metadata`

Once the process job is `SUCCESS`, the node exists; if an embedding job was started, poll `GET /jobs/{embedding_job_id}` until that job is `SUCCESS` so the node’s content is searchable via RAG (chat with `use_rag: true` or `POST /rag/search`).

---

## 9. Tool messages (optional)

To record a tool call result in a conversation (e.g. for agentic flows):

- **Record tool call:** `POST /conversations/chat/tool`  
  Body: `{ "conversation_id", "tool_name", "tool_input", "tool_output" }`

- **Get agent response after tool:** `POST /conversations/chat/tool/respond?conversation_id=...&agent_id=...`

---

## 10. Postman collection

A Postman collection is provided for all API endpoints.

- **Location:** `docs/postman/Dimension-API-Brain.postman_collection.json`
- **Import in Postman:** File → Import → select the JSON file.
- **Environment:** The collection uses **Authorization → Bearer Token** with the variable `token`. Set collection or environment variables: `base_url` (e.g. `http://localhost:8000`), `token` (your JWT), and optionally `workspace_id`, `conversation_id`, `agent_id`, `file_id`, `job_id` for requests that use them.

---

## Quick reference

| Action              | Method | Endpoint                          |
|---------------------|--------|-----------------------------------|
| List agents         | GET    | /agents                           |
| Create conversation | POST   | /conversations                    |
| Chat (single agent) | POST   | /conversations/chat               |
| Panel chat          | POST   | /conversations/chat/panel          |
| RAG search          | POST   | /rag/search                       |
| Import document     | POST   | /documents/import                 |
| Process document    | POST   | /documents/{file_id}/process      |
| Job status          | GET    | /jobs/{job_id}/status             |
