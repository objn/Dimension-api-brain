# API Test Cases

> **Base URL:** `http://localhost:8000/llm`
> **Auth:** All endpoints require `Authorization: Bearer <JWT_TOKEN>` header
> **Response Format:** `{ "success": true, "data": { ... } }`

---

## Table of Contents

1. [Job API](#1-job-api)
2. [Node Embedding API](#2-node-embedding-api)
3. [RAG Search & Retrieve API](#3-rag-search--retrieve-api)
4. [End-to-End Flow](#4-end-to-end-flow-embed--search)

---

## 1. Job API

### 1.1 Create Job

> **Proof:** สร้าง Job แล้ว status ต้องเป็น PENDING, daemon จะ activate เมื่อ job_start_time ถึง

```
POST /llm/jobs
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body:**
```json
{
  "job_type": "node_content_embedding",
  "job_start_time": "2026-02-11T12:01:00Z",
  "metadata_json": {
    "node_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "force_reembed": false
  },
  "content_to_summarize": "Embedding node content"
}
```

**Expected Response (201):**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "job_type": "node_content_embedding",
    "job_start_time": "2026-02-11T12:01:00Z",
    "job_end_time": null,
    "job_actived": false,
    "job_result": "PENDING",
    "created_at": "...",
    "created_by": "<user_id>",
    "metadata": {
      "metadata_id": "<UUID>",
      "metadata_json": { "node_id": "...", "force_reembed": false }
    }
  }
}
```

**Proof checklist:**
- [ ] `job_result` = `"PENDING"`
- [ ] `job_actived` = `false`
- [ ] `job_end_time` = `null`
- [ ] `job_start_time` matches request
- [ ] `job_type` = `"node_content_embedding"`
- [ ] `metadata` record created with matching `metadata_json`

---

### 1.2 Create Job (immediate start — no job_start_time)

> **Proof:** ไม่ส่ง job_start_time → default = now + 1 min → daemon จะ pick up ภายใน 1 นาที

```
POST /llm/jobs
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body:**
```json
{
  "job_type": "node_content_embedding",
  "metadata_json": {
    "node_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
  }
}
```

**Expected Response (201):**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "job_type": "node_content_embedding",
    "job_start_time": "<now + ~1 minute>",
    "job_result": "PENDING",
    "job_actived": false
  }
}
```

**Proof checklist:**
- [ ] `job_start_time` ≈ current time + 1 minute
- [ ] After ~1 minute + poll interval, job should transition to `PROCESSING`

---

### 1.3 Create Job (invalid job_type)

> **Proof:** job_type ที่ไม่อยู่ใน Enum ต้อง reject

```
POST /llm/jobs
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body:**
```json
{
  "job_type": "invalid_type",
  "metadata_json": {}
}
```

**Expected Response (422):**
```json
{
  "detail": [
    {
      "msg": "Input should be 'node_content_embedding'",
      "type": "enum"
    }
  ]
}
```

**Proof checklist:**
- [ ] Status code = `422`
- [ ] Error message references valid enum values

---

### 1.4 Get All Jobs

```
GET /llm/jobs
Authorization: Bearer <TOKEN>
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "count": 2,
    "jobs": [
      {
        "job_id": "<UUID>",
        "job_type": "node_content_embedding",
        "job_result": "PENDING",
        "job_start_time": "...",
        "job_end_time": null,
        "job_actived": false
      }
    ]
  }
}
```

**Proof checklist:**
- [ ] Returns only jobs owned by the authenticated user
- [ ] `count` matches array length

---

### 1.5 Get All Jobs with Metadata

```
GET /llm/jobs/metadata
Authorization: Bearer <TOKEN>
```

**Proof checklist:**
- [ ] Each job includes `metadata` object (or `null`)
- [ ] `metadata.metadata_json` contains original job parameters

---

### 1.6 Get Active Jobs

> **Proof:** ดึงเฉพาะ job ที่ status เป็น PENDING หรือ PROCESSING

```
GET /llm/jobs/active
Authorization: Bearer <TOKEN>
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "count": 1,
    "jobs": [
      {
        "job_id": "<UUID>",
        "job_type": "node_content_embedding",
        "status": "PROCESSING",
        "job_start_time": "...",
        "job_actived": true
      }
    ]
  }
}
```

**Proof checklist:**
- [ ] No `SUCCESS`, `FAILED`, `CANCELLED`, `INTERRUPTED` jobs in result
- [ ] Only `PENDING` and/or `PROCESSING` jobs returned

---

### 1.7 Get Job by ID

```
GET /llm/jobs/{job_id}
Authorization: Bearer <TOKEN>
```

**Proof checklist:**
- [ ] Returns specific job with full metadata
- [ ] `404` if job_id doesn't exist
- [ ] `403` if job belongs to different user

---

### 1.8 Get Job Status + Progress

> **Proof:** ดู progress ของ job ที่กำลังทำงาน

```
GET /llm/jobs/{job_id}/status
Authorization: Bearer <TOKEN>
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "job_type": "node_content_embedding",
    "status": "PROCESSING",
    "job_start_time": "...",
    "job_actived": true,
    "metadata": {
      "stage": "EMBEDDING",
      "progress": 65,
      "message": "Embedded 10/15 chunks"
    }
  }
}
```

**Proof checklist:**
- [ ] Progress updates during PROCESSING (poll multiple times)
- [ ] `stage` transitions: `INIT → CHUNKING → COMPARING → EMBEDDING → STORING → COMPLETED`

---

### 1.9 Get Job History

> **Proof:** ดู status transition history

```
GET /llm/jobs/{job_id}/history
Authorization: Bearer <TOKEN>
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "current_status": "SUCCESS",
    "history": [
      { "status": "PENDING", "timestamp": "...", "data": null },
      { "status": "PROCESSING", "timestamp": "...", "data": { "activated_at": "..." } },
      { "status": "SUCCESS", "timestamp": "...", "data": { "completed_at": "..." } }
    ]
  }
}
```

**Proof checklist:**
- [ ] History array is chronologically ordered
- [ ] Contains all status transitions

---

### 1.10 Cancel Pending Job

> **Proof:** ยกเลิก job ที่ยังไม่เริ่ม (PENDING only)

```
PATCH /llm/jobs/{job_id}/cancel
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body (optional):**
```json
{
  "reason": "No longer needed"
}
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "job_result": "CANCELLED",
    "job_end_time": "<timestamp>"
  }
}
```

**Proof checklist:**
- [ ] Only works on `PENDING` jobs
- [ ] `job_result` changes to `CANCELLED`
- [ ] `job_end_time` is set
- [ ] Returns `400` if job is already `PROCESSING` or terminal

---

### 1.11 Interrupt Running Job

> **Proof:** หยุด job ที่กำลัง process อยู่

```
PATCH /llm/jobs/{job_id}/interrupt
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body (optional):**
```json
{
  "reason": "User requested cancellation"
}
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "job_result": "INTERRUPTED",
    "job_end_time": "<timestamp>"
  }
}
```

**Proof checklist:**
- [ ] Only works on `PROCESSING` / `RUNNING` jobs
- [ ] `job_result` changes to `INTERRUPTED`
- [ ] Returns `400` if job is `PENDING` (use cancel instead)

---

### 1.12 Stop Job (Unified)

> **Proof:** auto-detect: PENDING → cancel, PROCESSING → interrupt

```
PATCH /llm/jobs/{job_id}/stop
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body (optional):**
```json
{
  "reason": "Cleanup"
}
```

**Proof checklist:**
- [ ] If `PENDING` → `CANCELLED`
- [ ] If `PROCESSING` → `INTERRUPTED`
- [ ] Returns `400` if already terminal (`SUCCESS`, `FAILED`, etc.)

---

### 1.13 Delete Job

```
DELETE /llm/jobs/{job_id}
Authorization: Bearer <TOKEN>
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "message": "Job deleted successfully",
    "job_id": "<UUID>"
  }
}
```

**Proof checklist:**
- [ ] Job and metadata deleted from DB
- [ ] `404` on subsequent GET
- [ ] `403` if not owner

---

## 2. Node Embedding API

### 2.1 Start Embedding

> **Proof:** สร้าง embedding job สำหรับ node → daemon จะ activate และ run pipeline

```
POST /llm/nodes/{node_id}/embed
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body (optional):**
```json
{
  "force_reembed": false
}
```

**Expected Response (202):**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "node_id": "<node_id>",
    "status": "PENDING",
    "message": "Embedding job started"
  }
}
```

**Proof checklist:**
- [ ] Status code = `202 Accepted` (async)
- [ ] Job created in DB with `job_type = "node_content_embedding"`
- [ ] `404` if `node_id` doesn't exist
- [ ] `403` if node belongs to different user
- [ ] After daemon poll interval → job activates (check via status endpoint)

---

### 2.2 Start Embedding (Force Re-embed)

> **Proof:** force_reembed=true ลบ chunk เก่าทั้งหมด แล้วสร้างใหม่

```
POST /llm/nodes/{node_id}/embed
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body:**
```json
{
  "force_reembed": true
}
```

**Proof checklist:**
- [ ] All existing chunks soft-deleted
- [ ] New chunks created with new embeddings
- [ ] `chunks_deleted > 0` in result metadata (after completion)

---

### 2.3 Get Embedding Job Status

> **Proof:** ติดตาม progress ของ embedding pipeline

```
GET /llm/nodes/{node_id}/embed/status/{job_id}
Authorization: Bearer <TOKEN>
```

**Expected Response (200) — while processing:**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "node_id": "<node_id>",
    "status": "PROCESSING",
    "stage": "EMBEDDING",
    "progress": 45,
    "message": "Embedded 5/11 chunks",
    "result": null
  }
}
```

**Expected Response (200) — after completion:**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "node_id": "<node_id>",
    "status": "SUCCESS",
    "stage": "COMPLETED",
    "progress": 100,
    "message": "Embedding complete",
    "result": {
      "chunks_created": 11,
      "chunks_deleted": 0,
      "chunks_unchanged": 0,
      "total_chunks": 11,
      "processing_time_seconds": 4.52
    }
  }
}
```

**Proof checklist:**
- [ ] `stage` follows: `INIT → CHUNKING → COMPARING → EMBEDDING → STORING → COMPLETED`
- [ ] `progress` increases over time (0 → 100)
- [ ] Final `result` contains chunk statistics

---

### 2.4 Cancel Embedding Job

```
DELETE /llm/nodes/{node_id}/embed/{job_id}
Authorization: Bearer <TOKEN>
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "job_id": "<UUID>",
    "node_id": "<node_id>",
    "status": "INTERRUPTED",
    "message": "Embedding job cancelled"
  }
}
```

**Proof checklist:**
- [ ] Job transitions to `INTERRUPTED`
- [ ] `400` if job already completed

---

### 2.5 Get Node Chunks

> **Proof:** ดู chunks ที่ถูกสร้างจาก embedding pipeline

```
GET /llm/nodes/{node_id}/chunks?include_embeddings=false&include_deleted=false
Authorization: Bearer <TOKEN>
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "node_id": "<node_id>",
    "node_name": "Python Basics",
    "total_chunks": 5,
    "chunks": [
      {
        "chunk_id": "<UUID>",
        "order": 0,
        "content": "Title: Python Basics\nDescription: An intro to Python",
        "content_hash": "abc123...",
        "chunk_type": "metadata",
        "created_at": "..."
      },
      {
        "chunk_id": "<UUID>",
        "order": 1,
        "content": "# Variables\nPython uses dynamic typing...",
        "content_hash": "def456...",
        "chunk_type": "content",
        "created_at": "..."
      }
    ]
  }
}
```

**Proof checklist:**
- [ ] `order=0` is metadata chunk (node_name + node_desc)
- [ ] `order=1+` are content chunks (from node_content_md)
- [ ] `content_hash` is consistent for same content
- [ ] `include_embeddings=true` returns embedding vectors (1536 floats)
- [ ] `include_deleted=true` includes soft-deleted chunks with `deleted_at`

---

### 2.6 Get Chunk by ID

```
GET /llm/nodes/chunks/{chunk_id}?include_embedding=false
Authorization: Bearer <TOKEN>
```

**Proof checklist:**
- [ ] Returns single chunk with content and metadata
- [ ] `404` if chunk doesn't exist or is soft-deleted

---

## 3. RAG Search & Retrieve API

### 3.1 Semantic Search (Global)

> **Proof:** ค้นหา content จาก embedding ทุก nodes ด้วย cosine similarity

```
POST /llm/nodes/search
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body:**
```json
{
  "query": "How to define variables in Python",
  "limit": 10,
  "similarity_threshold": 0.7,
  "include_content": true,
  "include_metadata_chunks": true
}
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "query": "How to define variables in Python",
    "total_results": 3,
    "results": [
      {
        "node_id": "<UUID>",
        "node_name": "Python Basics",
        "node_desc": "Introduction to Python programming",
        "chunk_id": "<UUID>",
        "chunk_order": 1,
        "chunk_type": "content",
        "similarity": 0.8921,
        "content": "Variables in Python are created when you assign a value..."
      },
      {
        "node_id": "<UUID>",
        "node_name": "Python Data Types",
        "chunk_id": "<UUID>",
        "chunk_order": 0,
        "chunk_type": "metadata",
        "similarity": 0.7845,
        "content": "Title: Python Data Types\nDescription: Overview of data types"
      }
    ]
  }
}
```

**Proof checklist:**
- [ ] Results sorted by `similarity` descending
- [ ] All results have `similarity >= 0.7` (threshold)
- [ ] `chunk_type` correctly labeled (`metadata` / `content`)
- [ ] Results come from multiple nodes (cross-node search)
- [ ] `include_content=false` → `content` is `null`
- [ ] `include_metadata_chunks=false` → no `chunk_order=0` results

---

### 3.2 Search Within Node

> **Proof:** ค้นหาภายใน node เดียว

```
GET /llm/nodes/{node_id}/search?query=variables&limit=5&include_metadata=true
Authorization: Bearer <TOKEN>
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "node_id": "<node_id>",
    "node_name": "Python Basics",
    "query": "variables",
    "total_results": 2,
    "results": [
      {
        "chunk_id": "<UUID>",
        "chunk_order": 1,
        "chunk_type": "content",
        "content": "Variables in Python...",
        "similarity": 0.9102
      }
    ]
  }
}
```

**Proof checklist:**
- [ ] All results belong to the specified `node_id`
- [ ] `include_metadata=false` → no `chunk_order=0` results
- [ ] `404` if node doesn't exist

---

### 3.3 Find Related Nodes

> **Proof:** หา node ที่คล้ายกันโดยเทียบ metadata chunk (order=0)

```
GET /llm/nodes/{node_id}/related?limit=10&similarity_threshold=0.5
Authorization: Bearer <TOKEN>
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "source_node_id": "<node_id>",
    "total_results": 3,
    "related_nodes": [
      {
        "node_id": "<UUID>",
        "node_name": "Python Data Types",
        "node_desc": "Overview of Python data types",
        "similarity": 0.8512
      },
      {
        "node_id": "<UUID>",
        "node_name": "JavaScript Variables",
        "node_desc": "How variables work in JS",
        "similarity": 0.6230
      }
    ]
  }
}
```

**Proof checklist:**
- [ ] Source node is NOT in results
- [ ] All results have `similarity >= 0.5` (threshold)
- [ ] Results sorted by `similarity` descending
- [ ] Returns empty array if node has no embedding yet

---

### 3.4 Hybrid Search (Keyword + Semantic)

> **Proof:** ผสม keyword matching กับ semantic similarity

```
POST /llm/nodes/search/hybrid
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

**Body:**
```json
{
  "query": "Python function definition",
  "limit": 10,
  "keyword_weight": 0.3,
  "semantic_weight": 0.7
}
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "query": "Python function definition",
    "total_results": 5,
    "keyword_weight": 0.3,
    "semantic_weight": 0.7,
    "results": [
      {
        "node_id": "<UUID>",
        "node_name": "Python Functions",
        "chunk_id": "<UUID>",
        "chunk_order": 1,
        "chunk_type": "content",
        "content": "def my_function():\n    ...",
        "similarity": 0.9201,
        "semantic_score": 0.92,
        "keyword_score": 0.8,
        "combined_score": 0.884
      }
    ]
  }
}
```

**Proof checklist:**
- [ ] `combined_score = (semantic_weight × semantic_score) + (keyword_weight × keyword_score)`
- [ ] Results sorted by `combined_score` descending
- [ ] Keyword matches (exact word) boost results vs pure semantic
- [ ] `keyword_weight + semantic_weight` ≈ 1.0 (recommended)

---

## 4. End-to-End Flow (Embed → Search)

> **Full flow test:** สร้าง embedding แล้วค้นหาด้วย RAG

### Step 1: Embed a node

```
POST /llm/nodes/{node_id}/embed
Authorization: Bearer <TOKEN>
```
```json
{ "force_reembed": false }
```

→ Save `job_id` from response

### Step 2: Poll until complete

```
GET /llm/nodes/{node_id}/embed/status/{job_id}
Authorization: Bearer <TOKEN>
```

→ Repeat every 2-3 seconds until `status = "SUCCESS"`

### Step 3: Verify chunks created

```
GET /llm/nodes/{node_id}/chunks
Authorization: Bearer <TOKEN>
```

→ Confirm `total_chunks > 0`

### Step 4: Semantic search

```
POST /llm/nodes/search
Authorization: Bearer <TOKEN>
```
```json
{
  "query": "<content related to the embedded node>",
  "limit": 5,
  "similarity_threshold": 0.5
}
```

→ Expect the embedded node to appear in results

### Step 5: Find related nodes

```
GET /llm/nodes/{node_id}/related?limit=5
Authorization: Bearer <TOKEN>
```

→ Returns nodes with similar content

### Step 6: Re-embed (idempotent)

```
POST /llm/nodes/{node_id}/embed
Authorization: Bearer <TOKEN>
```
```json
{ "force_reembed": false }
```

→ After completion, `chunks_unchanged` should be > 0, `chunks_created` = 0 (no changes)

### Step 7: Force re-embed

```
POST /llm/nodes/{node_id}/embed
Authorization: Bearer <TOKEN>
```
```json
{ "force_reembed": true }
```

→ After completion, all chunks deleted and recreated

**End-to-End Proof checklist:**
- [ ] Step 1: Job created with `PENDING`
- [ ] Step 2: Job transitions `PENDING → PROCESSING → SUCCESS`
- [ ] Step 3: Chunks exist with `order=0` (metadata) + `order=1+` (content)
- [ ] Step 4: Search returns the node with similarity > threshold
- [ ] Step 5: Related nodes found (if other embedded nodes exist)
- [ ] Step 6: Idempotent → `chunks_unchanged > 0`
- [ ] Step 7: Force → `chunks_deleted > 0`, `chunks_created > 0`

---

## 5. Daemon & Worker Pool Behavior Tests

### 5.1 Daemon picks up scheduled job

> **Proof:** สร้าง job ที่ job_start_time = now → daemon จะ activate ภายใน poll interval

1. Create job with `job_start_time` = now
2. Poll `GET /llm/jobs/{job_id}/status` every second
3. Expect transition to `PROCESSING` within `JOB_POLL_INTERVAL` seconds

**Proof checklist:**
- [ ] Job moves from `PENDING` → `PROCESSING` automatically
- [ ] `job_actived` changes to `true`
- [ ] No manual API call needed to start the job

### 5.2 Future-scheduled job not picked up early

> **Proof:** job ที่ job_start_time อยู่ในอนาคต ไม่ถูก activate ก่อนเวลา

1. Create job with `job_start_time` = now + 10 minutes
2. Check status after 30 seconds
3. Expect still `PENDING`

**Proof checklist:**
- [ ] Job remains `PENDING` until `job_start_time`
- [ ] `job_actived` stays `false`

### 5.3 Worker pool full → break_off_time

> **Proof:** เมื่อ worker เต็ม daemon จะหยุด poll ชั่วคราว

1. Create `JOB_WORKER_NUM` + 2 jobs (all with `job_start_time` = now)
2. First `JOB_WORKER_NUM` jobs should activate
3. Remaining jobs stay `PENDING` until a worker finishes

**Proof checklist:**
- [ ] Max concurrent `PROCESSING` jobs = `JOB_WORKER_NUM`
- [ ] Excess jobs wait in `PENDING`
- [ ] After a job completes, queued job activates on next poll

### 5.4 Race condition prevention

> **Proof:** atomic claim ป้องกัน double-activation

1. Same job should not be activated twice
2. Check via `GET /llm/jobs/{job_id}/history` → only ONE `PROCESSING` entry

**Proof checklist:**
- [ ] No duplicate `PROCESSING` transitions in history
- [ ] `UPDATE WHERE job_result='PENDING'` ensures atomic claim

### 5.5 Orphan recovery on restart

> **Proof:** job ที่อยู่ใน PROCESSING ตอน server crash จะถูก reset เป็น PENDING

1. Create and activate a job (status = `PROCESSING`)
2. Restart server
3. Check job status after startup

**Proof checklist:**
- [ ] Previously `PROCESSING` jobs reset to `PENDING`
- [ ] `job_actived` reset to `false`
- [ ] Daemon picks them up again after restart

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JOB_WORKER_NUM` | `3` | Max concurrent workers in thread pool |
| `JOB_POLL_INTERVAL` | `5` | Daemon poll interval (seconds) |
| `JOB_WORKER_BREAK_OFF_TIME` | `30` | Sleep duration when workers full (seconds) |
