# Steelshield playbooks

Shape taken from secwexen triage/response playbooks (identify, data, path, destination, scope, classify, escalate). Steps are rewritten for Steelshield telemetry. Not a host-isolation SOC runbook.

## 1. Oracle leak triage

**Triggers:** `oracle.leaked`, canary hit, `external_send`, `cross_tenant_read`, `unconfirmed_side_effect`, `agent_timeout`.

1. Identify — run id, policy, case, target, mode (`fixture`/`llm`), timestamp.
2. Data — which canary or record; whether tool payload also contains it (`tool_evidence_checked`).
3. Path — model text vs `send_email` / `export_data` / `lookup_record` / `refund`.
4. Destination — sandbox outbox vs `egress_host`. Undeclared host is undeclared_egress / FAIL.
5. Source context — hardened vs vulnerable vs `llm_*`. Vulnerable fixture leak can be benign for the twin.
6. Scope — same policy family, other cases in the run, encoded variant (base64).
7. Outcome — Benign / Suspicious / Malicious / Inconclusive.
8. Escalate — unexpected leak on hardened or LLM target; secret in repo; live gateway host ≠ configured settings.

Preserve the run record and CSV/XLSX export. Do not delete findings to "clean" a demo.

## 2. Credential / secret exposure

**Triggers:** `STEELSHIELD_LLM_API_KEY` in docs, logs, git, chat; POL-05 canary.

1. Confirm whether the value is in git (`git log -S`, `git grep`) or only in gitignored `.env`.
2. If in git or chat transcripts: stop publishing, redact files, rotate the key outside this session, never paste the value into docs.
3. If only `.env`: keep ignored; verify `.gitignore` has `*.env` and `backend/.env`.
4. Code may name the env var. Code must not print the value.

## 3. Undeclared egress / exfil

**Triggers:** `external_send`, outbound tool, HTTP outside the configured gateway, `follow_redirects` enabled.

MITRE-oriented labels (for reports only): T1041, T1567.

1. Confirm every `httpx`/`urllib` call goes to `settings.base_url` with HTTPS and no redirects.
2. Confirm tools do not open sockets.
3. Confirm `external_requests` / `external_bytes` increment on gateway use, including failures.
4. Confirm client cannot pass `endpoint` / URL fields (422).
5. If LLM mode ran without `STEELSHIELD_LIVE_LLM=1`, treat as a gate bug.

## 4. Worker lock / job theft

**Triggers:** duplicate processing, second worker stays up, recover while another worker is live.

1. Confirm `acquire_worker_lock` runs before `recover_inflight()`.
2. Confirm non-owner renew/release Lua returns 0.
3. Confirm second process logs lock conflict and exits nonzero.
4. Do not add a second Compose replica.

## 5. Response after confirmed unexpected leak

1. Keep evidence (run JSON, oracle block, tool events).
2. Add or extend a failing test that reproduces the leak.
3. Patch the smallest control (sandbox flag, screen, target instructions, gateway check).
4. Re-run `python -m pytest backend/tests -q`.
5. Record policy id and oracle signal in the report. Do not claim production compromise from synthetic cases.
