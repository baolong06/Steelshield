# Plan: Steelshield Agent Control Plane — LLM attacker + LLM target + deterministic oracle

> Revision: 4 — 2026-09-17. Operator-configured HTTPS LLM gateway (any host and path); no exact-host or `/v1` restriction. **Single-worker exclusivity** enforced via Redis lock key; second instance must fail fast.

## 1. Context

MVP fixture evaluator already compiles POL-01..10, scores synthetic twins with canary/state oracles, and exports CSV/Excel. That path is **not** an agent test: the simulator hard-codes results. This revision adds a real agent control plane: LLM attacker, LLM target, in-process tool sandbox, Redis worker, and a server-configured HTTPS LLM gateway.

Oracle tất định vẫn là trọng tài pass/fail. LLM không được đổi verdict. Client không gửi URL chatbot. Tool email/ticket/DB/refund là mock in-process. Gateway host và path không bị khóa; URL phải dùng HTTPS.

## 2. Architecture

```
UI (Next.js)
  POST /api/v1/runs {mode, target, attacker, split, policy, limit}
        │
        ├─ mode=fixture  → runner hiện tại (in-process, egress=0)
        └─ mode=llm      → enqueue Redis job, trả run status=queued
                              │
                         worker (blpop)
                              │
              Attacker (replay | llm) → Target (llm_hardened | llm_vulnerable)
              tools → ToolSandbox (local) → evaluate_oracle() ← authority
```

## 3. In scope

- Keep fixture runner unchanged in behavior.
- `backend/.env` gitignored; `.env.example` committed.
- Responses client uses the operator-configured HTTPS gateway (`STEELSHIELD_LLM_BASE_URL` must be an HTTPS URL). Any host and path are allowed; clients still cannot supply a URL.
- Tool sandbox: lookup_record, send_email, create_ticket, export_data, refund.
- Redis queue + worker + docker-compose (redis, backend, worker, frontend).
- UI mode/target/attacker, poll queued runs, egress badge.
- Timeout / exception / not-run = FAIL.
- Live LLM egress is disabled by default; `STEELSHIELD_LIVE_LLM=1` is required before any gateway request.
- **Single-worker exclusivity (Rev4):** Worker acquires a Redis lock key `steelshield:worker:lock` via `SET key value NX EX <ttl>`. Only one worker instance processes LLM-mode jobs at a time. A second instance attempting `SET NX` fails fast and exits non-zero with a clear log line. Lock is released on clean shutdown (`DEL` only if token matches via Lua `GETSET`/CAS) and expires automatically on TTL if the worker crashes mid-job.

## 4. Out of scope

LangGraph/PyRIT, scan URL bên ngoài, LLM-as-judge làm ground truth, production Docker hardening, R0 human review dataset.

## 5. Implementation steps

1. Settings, .env.example, gitignore, HTTPS URL shape. → verify: accept any HTTPS host/path, reject HTTP
2. LLM client, sandbox, attacker, target, campaign. → verify: mock LLM tests
3. Redis queue + worker + run_service/routes. → verify: fakeredis + 503 without Redis
4. Frontend wizard/poll/copy. → verify: next build
5. docker-compose.yml. → verify: files present
6. Live 1 case behind `STEELSHIELD_LIVE_LLM=1`. → verify: recorded `egress_host` matches configured gateway
7. Write `docs/report.md` with real command output.
8. **Worker lock (Rev4):** Implement `acquire_worker_lock(redis, ttl)` returning `(acquired: bool, token: str)`. Worker entrypoint calls it before `blpop` loop; non-acquired instance logs and exits with code 1. Release uses CAS Lua script comparing token before `DEL`. Add settings `STEELSHIELD_WORKER_LOCK_TTL_SEC` (default 60). → verify: two-process test, second instance exits non-zero.

## 6. Test plan

- `python dataset/scripts/validate_dataset.py`
- `python -m pytest dataset/tests/test_benchmark.py backend/tests -q`
- POST extra field `endpoint` → 422
- POST fixture POL-06 still 201, external_requests=0
- POST mode=llm without Redis → 503
- Mock campaign: timeout/error = failed; canary in tool events = leaked
- **Worker lock (Rev4):** Start two worker processes against the same fakeredis; assert exactly one processes jobs and the other logs the lock-conflict message and exits with code 1. After SIGKILL of the holder, the surviving instance acquires the lock within TTL+epsilon.

## 7. Acceptance criteria

- [ ] Dataset hashes unchanged vs manifest
- [ ] Fixture tests still PASS
- [ ] Gateway URL must be HTTPS; host and path are not restricted
- [ ] Sandbox never makes HTTP
- [ ] Oracle remains pass/fail authority including tool evidence
- [ ] LLM timeout/error/not-run is FAIL
- [ ] Redis required for llm mode; fixture does not need Redis
- [ ] Client cannot supply a target URL
- [ ] No secret committed
- [ ] **Worker lock (Rev4):** Exactly one worker instance holds `steelshield:worker:lock` at any time; second instance exits non-zero with a clear log.

## Plan revisions

- Revision 1: expand from offline evaluator to agent control plane (LLM attacker+target, Redis worker, declared egress).
- Revision 2: remove the exact-host allowlist (`modelapi.vn`). Operator may set any https LLM gateway whose path ends in `/v1`. Client still cannot supply a chatbot URL. Tools remain in-process mocks. Live egress still requires `STEELELSHIELD_LIVE_LLM=1`.
- Revision 3: remove the `/v1` path restriction. Operator may set any HTTPS gateway URL. Client still cannot supply a chatbot URL; live opt-in, no redirects, and local sandbox tools remain unchanged.
- Revision 4: add single-worker exclusivity. Worker acquires Redis lock `steelshield:worker:lock` via `SET NX EX`; second instance exits non-zero. Lock released via CAS Lua on clean shutdown; auto-expires on TTL if worker crashes. Prevents operator from accidentally running two workers and double-processing queued LLM jobs. Credential issue from earlier loop is replaced by code-only path; live verification deferred to operator opt-in.

## Out of scope (not adding)

- Horizontal scaling workers: not in scope. Single-worker is enforced; no sharding, no leader election beyond the Redis lock.
- Lock failover beyond TTL: lock holder death is handled by TTL expiry, not by external watchdog.
- Multi-region or HA Redis: single Redis assumed.
