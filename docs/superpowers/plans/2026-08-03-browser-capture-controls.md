# Browser Capture Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make the browser UI display real Python capture state and invoke the existing Enter, Escape, and Q actions.

**Architecture:** Python retains sole ownership of the attached microphone, accepted WAV files, worker queue, and transcript artifacts. A localhost-only standard-library HTTP server calls public lifecycle methods on Application; the Next.js page polls its status and forwards button/keyboard actions to it.

**Tech Stack:** Python 3.10 http.server, existing sounddevice/NumPy pipeline, Next.js 16, React 19, HeroUI.

## Global Constraints

- Bind the control server to 127.0.0.1 only.
- Do not stream raw audio or access browser microphone APIs.
- Do not add Python dependencies.
- UI controls are limited to Save & next (Enter), Retry (Escape), and Stop session (Q).
- Remove simulated timer, waveform, visitor/session count, history, report overlay, and start-session UI.
- Preserve existing CLI keyboard behavior when running feedback-llm without the server command.

---

### Task 1: Expose real capture state and level

**Files:**
- Modify: src/audio/capture.py — CaptureSession state, callback, properties
- Modify: src/cli_app.py — Application lifecycle and action methods
- Test: tests/test_capture_state_machine.py

**Interfaces:**
- Produces: CaptureSession.input_level: float in [0.0, 1.0].
- Produces: Application.start(), accept(), discard(), stop(), and status().
- Application.status() returns session_id, capture_state, current_visitor_id, elapsed_seconds, input_level, and queue items from real backend state.

- [ ] Step 1: Write failing tests.

    def test_capture_input_level_reflects_latest_audio_block(tmp_path):
        capture = CaptureSession(
            input_device=None, preferred_sample_rate=16_000, channels=1,
            block_size=160, queue_max_blocks=2, sessions_audio_dir=tmp_path,
            peak_target_dbfs=-3.0,
        )
        capture._on_audio(np.array([[0.25], [-0.75]], dtype=np.float32), 2, None, None)
        assert capture.input_level == pytest.approx(0.75)

    def test_capture_input_level_is_clamped(tmp_path):
        capture = CaptureSession(...)
        capture._on_audio(np.array([[2.0]], dtype=np.float32), 1, None, None)
        assert capture.input_level == 1.0

- [ ] Step 2: Run uv run pytest tests/test_capture_state_machine.py -k input_level -v.

Expected: FAIL because CaptureSession.input_level does not exist.

- [ ] Step 3: Implement the minimum state. Store the clamped peak from the copied audio block. Refactor Application so start() creates its session, starts capture and the worker, but not the terminal keyboard/render loop. Public action methods share the current handlers, are action-locked, and return status().

- [ ] Step 4: Run uv run pytest tests/test_capture_state_machine.py -v.

Expected: PASS.

- [ ] Step 5: Commit.

    git add src/audio/capture.py src/cli_app.py tests/test_capture_state_machine.py
    git commit -m "feat: expose real capture control state"

### Task 2: Add the localhost control server

**Files:**
- Create: src/control_server.py
- Modify: src/cli_app.py — command parser and main
- Modify: pyproject.toml — script entrypoint if needed
- Test: tests/test_control_server.py

**Interfaces:**
- Consumes the public Application methods from Task 1.
- Produces a server bound to 127.0.0.1:8000:
  - GET /api/status
  - POST /api/capture/accept
  - POST /api/capture/discard
  - POST /api/capture/stop
- Returns JSON. Returns HTTP 409 for an invalid capture state and HTTP 404 for an unknown route.

- [ ] Step 1: Write failing tests.

    def test_status_returns_application_snapshot(running_server):
        response = urlopen("http://127.0.0.1:8000/api/status")
        assert json.load(response)["current_visitor_id"] == "visitor_0001"

    def test_accept_forwards_to_application(running_server, control_app):
        request = Request(
            "http://127.0.0.1:8000/api/capture/accept", method="POST", data=b"{}"
        )
        assert json.load(urlopen(request))["capture_state"] == "recording"
        assert control_app.accept_calls == 1

    def test_unknown_route_returns_not_found(running_server):
        with pytest.raises(HTTPError) as error:
            urlopen(Request("http://127.0.0.1:8000/api/capture/nope", method="POST"))
        assert error.value.code == 404

- [ ] Step 2: Run uv run pytest tests/test_control_server.py -v.

Expected: FAIL because src.control_server does not exist.

- [ ] Step 3: Implement the minimum BaseHTTPRequestHandler dispatch. It must serialize status/action responses, reject invalid transitions with 409, and bind only to localhost. Add feedback-llm serve: it loads existing configuration and adapter, starts Application, serves requests until interrupted, then always shuts Application down. Do not start the terminal keyboard listener in serve mode.

- [ ] Step 4: Run uv run pytest tests/test_control_server.py -v and uv run pytest -q.

Expected: PASS.

- [ ] Step 5: Commit.

    git add src/control_server.py src/cli_app.py pyproject.toml tests/test_control_server.py
    git commit -m "feat: add local browser control API"

### Task 3: Replace the simulated operator page

**Files:**
- Modify: ui/app/page.tsx
- Modify: ui/components/AudioVisualizer.tsx
- Modify: ui/components/KeyboardShortcutsModal.tsx
- Delete: ui/components/ReportOverlay.tsx
- Delete: ui/components/SessionHistoryDrawer.tsx
- Create: ui/app/page.test.tsx
- Modify: ui/package.json and ui/package-lock.json

**Interfaces:**
- Consumes the four endpoints from Task 2.
- Produces a single capture surface driven by CaptureStatus response data and a shared runAction(path) callback used by both buttons and keyboard shortcuts.

- [ ] Step 1: Write failing UI tests.

    it("renders the backend visitor and elapsed time", async () => {
        server.use(http.get("http://127.0.0.1:8000/api/status", () =>
            HttpResponse.json({
                capture_state: "recording",
                current_visitor_id: "visitor_0007",
                elapsed_seconds: 12,
                input_level: 0.7,
                queue: [],
                session_id: "session_test",
            }),
        ));
        render(<Home />);
        expect(await screen.findByText("visitor_0007")).toBeInTheDocument();
        expect(screen.getByLabelText("12 seconds recorded")).toBeInTheDocument();
    });

    it("forwards Enter to the accept endpoint", async () => {
        render(<Home />);
        await userEvent.keyboard("{Enter}");
        expect(await screen.findByText("visitor_0008")).toBeInTheDocument();
    });

- [ ] Step 2: Run cd ui; npm test -- page.test.tsx.

Expected: FAIL because there is no test runner and the page still owns simulated state.

- [ ] Step 3: Add only the test tooling needed for this page. Replace the local timer, visitor counter, session archive, generated waveform animation, report, history, N, R, and H controls with CaptureStatus fetched from GET /api/status at mount and every 250 ms. A single runAction POST must update the displayed status with the action response. Render waveform bar heights solely from input_level. Show the local API error state if it cannot be reached.

- [ ] Step 4: Run cd ui; npm test -- --run and npm run build.

Expected: PASS.

- [ ] Step 5: Commit.

    git add ui/app/page.tsx ui/components/AudioVisualizer.tsx ui/components/KeyboardShortcutsModal.tsx ui/app/page.test.tsx ui/package.json ui/package-lock.json
    git rm ui/components/ReportOverlay.tsx ui/components/SessionHistoryDrawer.tsx
    git commit -m "feat: connect operator UI to local capture API"

### Task 4: Document and verify the real workflow

**Files:**
- Modify: README.md — Operator UI

**Interfaces:**
- Documents the two local commands: uv run feedback-llm serve and cd ui && npm run dev.

- [ ] Step 1: Update the README with these operator steps:

    1. Start the microphone backend: uv run feedback-llm serve.
    2. Start the browser UI: cd ui && npm run dev.
    3. Open http://localhost:3000. Enter, Escape, and Q now control the attached microphone through Python.

- [ ] Step 2: Run uv run pytest -q, cd ui; npm test -- --run, and npm run build.

Expected: PASS. With Python stopped, opening the UI must show a local-service unavailable error rather than sample data.

- [ ] Step 3: Commit.

    git add README.md
    git commit -m "docs: explain browser capture controls"

