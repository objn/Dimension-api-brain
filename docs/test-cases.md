# API Test Cases

> **Base URL:** `http://localhost:8000/llm`
> **Auth:** All endpoints require `Authorization: Bearer <JWT_TOKEN>` header
> **Response Format:** `{ "success": true, "data": { ... } }`

---

## Table of Contents

1. [Job API](#1-job-api)
2. [Daemon & Worker Pool Behavior Tests](#2-daemon--worker-pool-behavior-tests)

---

> **Note:** Node Embedding HTTP endpoints (`/nodes/{node_id}/embed`, `/nodes/search`, etc.) have been removed.
> The embedding pipeline is now only accessible via the **Job API** with `job_type: "node_content_embedding"`.
> The Job Daemon still runs embedding tasks in the background when jobs are scheduled.

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

## 2. Daemon & Worker Pool Behavior Tests

### 2.1 Daemon picks up scheduled job

> **Proof:** สร้าง job ที่ job_start_time = now → daemon จะ activate ภายใน poll interval

1. Create job with `job_start_time` = now
2. Poll `GET /llm/jobs/{job_id}/status` every second
3. Expect transition to `PROCESSING` within `JOB_POLL_INTERVAL` seconds

**Proof checklist:**
- [ ] Job moves from `PENDING` → `PROCESSING` automatically
- [ ] `job_actived` changes to `true`
- [ ] No manual API call needed to start the job

### 2.2 Future-scheduled job not picked up early

> **Proof:** job ที่ job_start_time อยู่ในอนาคต ไม่ถูก activate ก่อนเวลา

1. Create job with `job_start_time` = now + 10 minutes
2. Check status after 30 seconds
3. Expect still `PENDING`

**Proof checklist:**
- [ ] Job remains `PENDING` until `job_start_time`
- [ ] `job_actived` stays `false`

### 2.3 Worker pool full → break_off_time

> **Proof:** เมื่อ worker เต็ม daemon จะหยุด poll ชั่วคราว

1. Create `JOB_WORKER_NUM` + 2 jobs (all with `job_start_time` = now)
2. First `JOB_WORKER_NUM` jobs should activate
3. Remaining jobs stay `PENDING` until a worker finishes

**Proof checklist:**
- [ ] Max concurrent `PROCESSING` jobs = `JOB_WORKER_NUM`
- [ ] Excess jobs wait in `PENDING`
- [ ] After a job completes, queued job activates on next poll

### 2.4 Race condition prevention

> **Proof:** atomic claim ป้องกัน double-activation

1. Same job should not be activated twice
2. Check via `GET /llm/jobs/{job_id}/history` → only ONE `PROCESSING` entry

**Proof checklist:**
- [ ] No duplicate `PROCESSING` transitions in history
- [ ] `UPDATE WHERE job_result='PENDING'` ensures atomic claim

### 2.5 Orphan recovery on restart

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
