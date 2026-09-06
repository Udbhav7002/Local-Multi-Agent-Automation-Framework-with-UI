# Project Audit: Local-Multi-Agent-Automation-Framework

**Date:** 2026-08-21  
**Auditor:** opencode (nemotron-3-ultra-free)  
**Scope:** Full codebase — security, architecture, code quality, tests, dependencies, CI/CD, Docker

---

## Overview

| Metric | Value |
|--------|-------|
| Python files | 68 (excl. venv) |
| Total LoC | ~8,550 |
| Tests | 64 passing |
| Coverage | 39.96% (threshold: 39%) |
| CI/CD | **None** (no `.github/` directory) |
| Architecture | DI/Factory + Protocol-based, async-first |

---

## 1. Security Audit

### Critical

| # | Issue | File:Line | Status |
|---|-------|-----------|--------|
| S1 | **No `.dockerignore`** — `COPY . .` bakes `.env` (with secrets), `venv/`, `.git/`, `chroma_db/`, `jobs.db` into the image layer | `Dockerfile:14` | **Open** |
| S2 | **Container runs as root** — no `USER` directive in Dockerfile or docker-compose.yml | `Dockerfile`, `docker-compose.yml` | **Open** |
| S3 | **Hardcoded default API key in compose** — `production-secure-key-change-me-32chars` is publicly known; anyone running compose without env override gets a known key | `docker-compose.yml:18` | **Open** |

### High

| # | Issue | File:Line | Status |
|---|-------|-----------|--------|
| S4 | **Docker healthcheck uses `curl` but it's not installed** in `python:3.11-slim` — healthcheck permanently fails | `docker-compose.yml:31`, `Dockerfile` | **Open** |
| S5 | **`read_only: true` rootfs + `settings.json` not volume-mounted** — `config.save()` silently fails on every model swap | `docker-compose.yml:41` | **Open** |
| S6 | **No security scanning** in pre-commit or CI — no `bandit`, `pip-audit`, `gitleaks`, `semgrep` despite framework executing LLM-generated shell commands | `.pre-commit-config.yaml` | **Open** |

### Already Fixed (from prior work)
- `open_app` shell injection → now uses `create_subprocess_exec` with arg lists ✅
- API key fails closed in production ✅
- API key uses `secrets.compare_digest` (timing-safe) ✅
- Webhook SSRF validation blocks localhost/private IPs ✅
- Sandbox hardened with `--network none`, `--read-only`, `--user nobody` ✅
- Rollback steps gated through `safety_gate.is_safe_action()` ✅
- `.env` is in `.gitignore` and not tracked ✅
- No `shell=True`, no `os.system`, no `eval/exec` usage ✅
- No bare `except:` blocks ✅

---

## 2. Architecture & Code Quality

### Critical (runtime correctness)

| # | Issue | File:Line |
|---|-------|-----------|
| A1 | **`images` param silently dropped in `OllamaClient.chat`** — builds `kwargs` but never adds `images`; vision only works because `verifier.py` embeds images inside the message dict. Cloud models via LiteLLM would silently lose vision. | `core/llm_client.py:114-122` |
| A2 | **Voice input blocks the event loop** — `voice_input.listen()` is synchronous (mic capture + Google SR, multi-second) called directly in async `input_loop` | `main.py:417` |
| A3 | **Mid-stream LLM fallback concatenates partial output** — if primary stream fails after yielding chunks, fallback starts from scratch → caller gets garbled `[partial-primary] + [fallback-from-scratch]` | `core/llm_client.py:352-376` |
| A4 | **`stream_chat` has no circuit breaker, no timeout, no retry** — inconsistent with `chat()` which has all three; a hung stream wedges the consumer forever | `core/llm_client.py:160-180, 290-310` |

### High

| # | Issue | File:Line |
|---|-------|-----------|
| A5 | **`event_bus` unguarded in `plan_and_execute`** — `execute_cached_plan` guards with `if self.event_bus:` (3 sites), but `plan_and_execute` publishes unguarded at 4 sites → `AttributeError` if bus is None | `core/plan_execution_engine.py:185,194,332,343` |
| A6 | **`asyncio.gather` without `return_exceptions=True`** — one failed step cancels all siblings and propagates, abandoning the batch | `core/plan_execution_engine.py:150,160` |
| A7 | **Heavy synchronous OCR/CV in async path** — `ui_parser.extract_all_text()`, `screen_cap.capture_fullscreen()`, `mss.mss()` all run inline without `asyncio.to_thread` (0.5–2s blocking) | `core/step_runner.py:285`, `vision/verifier.py:56,130` |
| A8 | **Shared LLM client closed 4× on shutdown** — all 4 agents share one `MultiLLMClient`; `orchestrator.shutdown()` calls `agent.llm.close()` on each → 4× close on same object | `core/orchestrator.py:88-94` |
| A9 | **Fire-and-forget tasks with lost exceptions** — `asyncio.create_task()` never stored, no done-callback, no exception handler | `api.py:212,239`, `main.py:431` |
| A10 | **`LiteLLMClient.stream_chat` may double-await** — `await litellm.acompletion(stream=True)` may raise `TypeError` (async generator can't be awaited) | `core/llm_client.py:299` |
| A11 | **`MemoryStore.close` signature mismatch** — Protocol declares `async def close`, `ChromaStore` implements sync `def close`, orchestrator calls without `await` | `core/protocols.py:71`, `memory/chroma_store.py:186`, `core/orchestrator.py:106` |
| A12 | **Broad `except Exception` in critic** — swallows `LLMTimeoutError`, `CircuitBreakerOpenError`, `CancelledError` as soft "plan rejected" → planner gets unrelated regeneration instead of real error | `core/critic.py:75-77` |

### Medium

| # | Issue | File:Line |
|---|-------|-----------|
| A13 | **`Any` abuse defeats Protocol abstraction** — `protocols.py` types `llm: Any` on every sub-protocol instead of `LLMClient`; `policies.py` types `memory`, `skill_library`, `router` as `Any` | `core/protocols.py:15,21,29,37,45` |
| A14 | **Duplicated retry/timeout logic** — `OllamaClient.chat` and `LiteLLMClient.chat` have near-identical 30-line retry blocks; extract shared helper | `core/llm_client.py:123-157, 244-280` |
| A15 | **`.env.example` env names don't match Config fields** — `CLI_TIMEOUT` should be `CLI_TIMEOUT_SECONDS`, `LLM_TIMEOUT` should be `LLM_TIMEOUT_SECONDS`, `CLI_MAX_OUTPUT` should be `CLI_MAX_OUTPUT_CHARS` → pydantic-settings silently ignores them | `.env.example:9-11` |
| A16 | **Conflicting default models across config sources** — `config.py`, `settings.json`, `.env.example` disagree on model defaults; `settings.json` wins silently | Multiple files |
| A17 | **`Config.save()` persists only 13 of 20+ fields** — env-set values for omitted fields silently revert to defaults on next cold start | `core/config.py:133-153` |
| A18 | **Dead code: `EventBus.publish_async`** never called (17 call sites use sync `publish()`) | `core/events.py:81-91` |
| A19 | **Dead code: `VisionVerificationError`** defined but never raised | `core/exceptions.py:17` |
| A20 | **`.agents/` scratch tree** — 27 subdirs, ~100 files of agent handoffs + 4 duplicated test harnesses; gitignored but cluttering | `.agents/` |
| A21 | **`CircuitBreakerOpenError` doesn't inherit `AgentFrameworkError`** — inconsistent with framework's error hierarchy | `core/circuit_breaker.py:101` |

---

## 3. Tests & Dependencies

### Critical

| # | Issue | Impact |
|---|-------|--------|
| D1 | **`rich` and `numpy` not in `requirements.txt`** — Dockerfile installs from `requirements.txt`; container will `ImportError` on first `setup_logger()` call | Container won't start |
| D2 | **`requirements.txt` and `pyproject.toml` list different dependency sets** — 8 packages in one but not the other; Makefile and Dockerfile paper over with ad-hoc `pip install` | Unreproducible builds |
| D3 | **No lock file** — all pins are `>=` lower bounds only; no `requirements.lock`, `uv.lock`, or hashes | Breaking upstream releases silently break builds |

### High

| # | Issue | Impact |
|---|-------|--------|
| D4 | **No CI** — no `.github/workflows/`; all checks (ruff, mypy, pytest) are opt-in pre-commit hooks, bypassable with `--no-verify` | No quality gate on push/PR |
| D5 | **Test coverage at 39.96%** — `plan_execution_engine.py` (350 LoC, 0%), `api.py` endpoints/auth (0%), `orchestrator.py` (0%), all 4 agent classes (0%), `circuit_breaker.py` (0%), `events.py` (0%) | Core logic untested |
| D6 | **Fakes don't match Protocols** — `InMemoryStore` methods are sync but Protocol requires `async`; `FakeLLMClient` missing `stream_chat`; both fakes are never imported by any test (dead code) | Fakes unusable |
| D7 | **`pytest-cov` and `hypothesis` not declared** as dev dependencies | Fresh checkout can't run tests |
| D8 | **Playwright browsers not installed in container** — `BrowserExecutor` unusable | Container can't do browser automation |
| D9 | **`test_safety_gate_property.py` asserts nothing** — ends with `pass` comment "we only strictly care about blocking bad stuff" | False confidence |

### Medium

| # | Issue |
|---|-------|
| D10 | `dev` extras list `flake8`/`black` (unused; project uses ruff) |
| D11 | Unused deps: `websockets`, `pynput`, `psutil`, `textual` — imported nowhere |
| D12 | `mypy` only runs on `core/ memory/ vision/ api.py` — `plugins/`, `tools/`, `main.py`, `tests/` not type-checked |
| D13 | `benchmarks/test_deterministic.py` is a placeholder (`assert True`) |
| D14 | Tests import `pytesseract`/`cv2`/`numpy` at module top level — collection fails without heavy native deps; should use `pytest.importorskip` |

---

## 4. Priority Action Plan

### P0 — Fix now (breaks runtime/security)
1. Add `rich`, `numpy` to `requirements.txt` (D1)
2. Add `.dockerignore` excluding `.env`, `venv/`, `.git/`, caches, `jobs.db` (S1)
3. Add `USER nonroot` to Dockerfile + docker-compose (S2)
4. Fix healthcheck: install `curl` or use `python -c "urllib..."` (S4)
5. Mount `settings.json` in compose volumes (S5)
6. Wire `images` param in `OllamaClient.chat` or remove it (A1)
7. Wrap `voice_input.listen()` in `asyncio.to_thread` (A2)
8. Fix mid-stream fallback: only retry before first yield (A3)

### P1 — Fix soon (correctness/maintainability)
9. Add timeout/retry/circuit-breaker to `stream_chat` (A4)
10. Guard all `event_bus` access in `plan_execution_engine` (A5)
11. Add `return_exceptions=True` to `asyncio.gather` calls (A6)
12. Wrap OCR/CV work in `asyncio.to_thread` (A7)
13. Close shared LLM client once in shutdown (A8)
14. Store + callback fire-and-forget tasks (A9)
15. Reconcile `requirements.txt` vs `pyproject.toml` (D2)
16. Add `pytest-cov`, `hypothesis` to dev deps (D7)
17. Fix `.env.example` env var names (A15)
18. Remove hardcoded default API key from compose (S3)

### P2 — Improve (quality gates)
19. Add `.github/workflows/` CI with lint + type + test + security scan (D4)
20. Add tests for `plan_execution_engine`, `api.py` endpoints, `circuit_breaker`, `events`, agent classes (D5)
21. Fix fakes to match Protocols; actually use them in tests (D6)
22. Replace `Any` typing with proper Protocols (A13)
23. Extract shared retry/timeout helper (A14)
24. Delete `.agents/` scratch tree (A20)
25. Add lock file / pin upper bounds (D3)

---

## Summary

The architecture is sound (clean DI, Protocol-based, async-first), and the prior security fixes hold up. But there are **4 runtime-breaking bugs** (images dropped, voice blocking, stream fallback garbling, stream_chat no timeout), **3 container-breaking issues** (missing `rich`/`numpy`, broken healthcheck, no `.dockerignore`), and **no CI**. Test coverage at 40% means the core orchestration logic is essentially untested.