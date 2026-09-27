# Live Feedback Project Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wake a separate background agent after each transcript is saved, let `sarvam-105b` make exactly one native `classify_feedback` tool call, persist project links separately, and expose them through a transcript-first feedback page.

**Architecture:** `ProcessingWorker` emits a transcript-ready callback after writing the existing transcript JSON. A separate `FeedbackAgentWorker` consumes that path, sends transcript state plus catalog state to Sarvam Chat Completions V1, validates exactly one tool call, executes the local `classify_feedback` tool, and writes one classification artifact per visitor. The browser uses one `/api/feedback` request to merge transcripts, classifications, and catalog display data; report generation remains untouched.

**Tech Stack:** Python 3.10+, stdlib threads/queues/JSON/HTTP, Sarvam Chat Completions V1 with `sarvam-105b`, pytest, Next.js 16, React 19, Tailwind v4, existing UI tokens.

**Spec:** `docs/SPEC-feedback-agent.md`

## Global Constraints

- Use `sarvam-105b` through Sarvam Chat Completions V1 native `tools`.
- Accept exactly one tool call named `classify_feedback`; reject text-only, unknown-tool, malformed, or multiple-tool responses.
- Store classifications outside `data/reports` and never alter raw transcript JSON.
- Agent failures must not fail capture or completed transcription.
- Browser feedback data must load with one `GET /api/feedback` request.
- Do not add dependencies or modify the existing report contract.

## Review Focus

- Transcript is saved but the agent API fails: transcript stays completed and a failed classification artifact is visible.
- Sarvam returns multiple tool calls despite `parallel_tool_calls: false`: the job fails safely instead of choosing one.
- One transcript mentions zero, one, or many projects: all valid IDs are preserved once and rendered as links.
- Restart after an interrupted agent call: startup reconciliation retries transcripts missing a classification artifact.
- Empty or malformed project catalog data: the endpoint returns a controlled error and never exposes arbitrary paths.

---

### Task 1: Define and test the single classification tool and Sarvam tool-call parser

**Files:**
- Create: `src/agent/__init__.py`
- Create: `src/agent/feedback_agent.py`
- Create: `tests/test_feedback_agent.py`

**Interfaces:**
- Produces `classify_feedback(feedback_text: str, projects_connections: list[dict]) -> dict` returning `{"project_ids": list[str]}`.
- Produces a Sarvam request builder with one function-tool definition named `classify_feedback`.
- Produces a response parser that accepts exactly one matching tool call and returns parsed arguments.

- [ ] **Step 1: Write failing tests**

```python
def test_classify_feedback_keeps_multiple_unique_known_project_ids():
    result = classify_feedback(
        "The visitor discussed both exhibits.",
        [{"project_id": "ai_museum"}, {"project_id": "vision_assist"}, {"project_id": "ai_museum"}],
    )
    assert result == {"project_ids": ["ai_museum", "vision_assist"]}


def test_parse_tool_call_rejects_multiple_calls():
    with pytest.raises(FeedbackAgentError, match="exactly one"):
        parse_classification_tool_call({"tool_calls": [{}, {}]})
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_feedback_agent.py -q`

Expected: FAIL because the agent module and parser do not exist.

- [ ] **Step 3: Implement the minimal tool and parser**

Validate non-empty feedback text, require each project connection to contain a string `project_id`, deduplicate while preserving order, and parse only a single `classify_feedback` call with valid JSON arguments. Keep Sarvam's `parallel_tool_calls` setting as a request hint, not a correctness guarantee.

- [ ] **Step 4: Run focused and full Python tests**

Run: `pytest tests/test_feedback_agent.py -q`

Expected: PASS.

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent tests/test_feedback_agent.py
git commit -m "feat: add feedback classification tool contract"
```

### Task 2: Add the background agent worker and transcript-ready wake-up

**Files:**
- Modify: `src/storage/data.py`
- Modify: `src/pipeline/worker_v2.py`
- Modify: `src/cli_app.py`
- Modify: `src/agent/feedback_agent.py`
- Modify: `tests/test_worker.py`

**Interfaces:**
- `DataPaths` gains `classifications: Path` and creates `data/classifications`.
- `ProcessingWorker` accepts optional `on_transcript_ready: Callable[[Path], None]` and calls it after transcript write.
- `FeedbackAgentWorker.start()`, `.enqueue(transcript_path)`, and `.stop()` manage a daemon queue worker.

- [ ] **Step 1: Add failing tests**

```python
def test_processing_worker_notifies_agent_after_transcript_write(tmp_path):
    paths = data_paths(tmp_path)
    ready = []
    worker = ProcessingWorker(
        queue=ProcessingQueue(),
        adapter=FakeAdapter(),
        paths=WorkerPaths(paths.normalized, paths.quality, paths.transcripts),
        target_sample_rate=16000,
        target_peak_dbfs=-3.0,
        on_transcript_ready=ready.append,
    )
    item = QueueItem(visitor_id="visitor_0001", raw_audio_path=paths.audio / "visitor_0001.wav")
    result = TranscriptionResult(language="en", text="Useful feedback", segments=[])
    worker._save_transcript("visitor_0001", item, paths.normalized / "visitor_0001.wav", result)
    assert ready == [tmp_path / "transcripts" / "visitor_0001.json"]
```

Also add a worker test proving an agent transport failure writes a failed classification artifact without changing the queue item to failed.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_worker.py -q`

Expected: FAIL because no callback or agent worker exists.

- [ ] **Step 3: Implement the wake-up path**

Create the agent worker with a bounded in-memory queue. On startup, scan completed transcript files and enqueue any visitor without a classification artifact so interrupted work is retried. Read the transcript JSON, load the catalog, call Sarvam with model `os.environ.get("SARVAM_LLM_MODEL", "sarvam-105b")`, execute the one parsed tool call, and atomically write `visitor_NNNN.json` under `data/classifications` with `completed` or `failed` status. Wire the worker into `Application._start_worker()` and stop it after the processing worker.

- [ ] **Step 4: Run focused and full Python tests**

Run: `pytest tests/test_worker.py tests/test_feedback_agent.py -q`

Expected: PASS.

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/storage/data.py src/pipeline/worker_v2.py src/cli_app.py src/agent/feedback_agent.py tests/test_worker.py
git commit -m "feat: wake feedback agent after transcript writes"
```

### Task 3: Expose one transcript-first feedback endpoint

**Files:**
- Modify: `src/operator_server.py`
- Create: `tests/test_feedback_endpoint.py`

**Interfaces:**
- Add `GET /api/feedback`.
- Return `{ "data": { "items": list } }`, sorted newest first, with each item containing `visitor_id`, `text`, `segments`, `classification.status`, and resolved `projects`.

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_feedback_endpoint_joins_one_transcript_to_multiple_projects(tmp_path):
    write_transcript(tmp_path, "visitor_0001", "AI Museum and Vision Assist were clear.")
    write_classification(tmp_path, "visitor_0001", ["ai_museum", "vision_assist"])
    status, body = request_feedback_server(tmp_path)
    assert status == 200
    assert [p["project_id"] for p in body["data"]["items"][0]["projects"]] == ["ai_museum", "vision_assist"]
```

Also test a transcript without classification and an invalid classification ID.

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_feedback_endpoint.py -q`

Expected: FAIL because `/api/feedback` is not registered.

- [ ] **Step 3: Implement the read projection**

Read only `visitor_*.json` from the configured transcripts directory, read classification artifacts from the fixed classifications directory, resolve IDs against the fixed project catalog, and return pending/failed classification states without dropping transcripts. Reuse the server's existing JSON/error response conventions.

- [ ] **Step 4: Run endpoint and full tests**

Run: `pytest tests/test_feedback_endpoint.py tests/test_operator_server.py -q`

Expected: PASS.

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/operator_server.py tests/test_feedback_endpoint.py
git commit -m "feat: expose transcript feedback projection"
```

### Task 4: Build the transcript stack page

**Files:**
- Create: `ui/app/feedback/page.tsx`
- Modify: `ui/app/page.tsx`

**Interfaces:**
- The page makes one `GET /api/feedback` call on mount.
- Each transcript is a keyboard-accessible button/row; selecting it expands the transcript and project links.

- [ ] **Step 1: Implement the minimal page against the endpoint contract**

Render an `AI Museum · KIT` header matching the existing tokens, a left transcript stack ordered newest first, and a detail panel. Show `Classifying…` and `Classification failed` states, render zero-project empty copy, and render every returned project as a link-like button or anchor without making a second request. Add a small navigation link from the capture page to `/feedback`.

- [ ] **Step 2: Run the UI build**

Run: `npm run build` in `ui/`

Expected: PASS with no TypeScript or route errors.

- [ ] **Step 3: Manually verify interaction**

Run the operator server and Next.js dev server, open `/feedback`, confirm all completed transcripts appear, select one, and confirm one transcript with multiple projects shows all project links.

- [ ] **Step 4: Commit**

```bash
git add ui/app/feedback/page.tsx ui/app/page.tsx
git commit -m "feat: add transcript feedback stack"
```

## Final Verification

Run: `pytest -q`

Run: `npm run build` in `ui/`

Confirm the existing capture page, report generation, and report files are unchanged in behavior; only the new agent classification artifacts and feedback page are added.
