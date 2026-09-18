---
name: steelshield-blue-team
description: Use when defending Steelshield, reviewing prompt injection or jailbreak findings, hardening egress/sandbox/worker lock, triaging oracle leaks (canary, cross-tenant, outbound send), writing IR playbooks, or mapping POL-01..10 to OWASP LLM / MITRE ATT&CK.
---

# Steelshield Blue Team

Defense here is **synthetic policy evaluation**, not live chatbot pentest and not a generic SOC.

**Authority:** `evaluate_oracle()` is pass/fail. LLM never changes a verdict. Timeout, gateway error, and not-run are FAIL.

## When to Use

Oracle leak, canary, `external_send`, `cross_tenant_read`, injection/jailbreak, encoded exfil, secret leak, egress, worker lock, `.env`, sandbox tools, extra `RunRequest` fields, IR/playbook/OWASP/MITRE for this product.

**Not this skill:** client-supplied chatbot URL; real email/DB/HTTP tools; LLM-as-judge as ground truth.

## Hard invariants

Do not weaken these:

| Control | Where | Rule |
|---|---|---|
| No client target URL | `RunRequest(extra="forbid")` | `endpoint` → 422 |
| HTTPS gateway | `assert_allowed_gateway` | `follow_redirects=False` |
| Live LLM opt-in | `STEELSHIELD_LIVE_LLM=1` | Default off |
| Tools are mocks | `tool_sandbox.py` | No network |
| Oracle authority | `oracles.py` | LLM never overrides |
| One worker | `SET NX EX` before recover | Do not scale `worker` |
| Secrets | gitignored `.env` | Never print or commit keys |

## Finding triage

Fill this outcome before patching:

1. Identify — run, policy, case, oracle, target.
2. Data — canary, PII, tenant record, tool payload.
3. Path — model text vs `send_email` / `export_data` / `lookup_record` / `refund`.
4. Destination — configured `egress_host` vs undeclared vs sandbox `outbox_new`.
5. Classify — Benign (vulnerable twin expected) / Suspicious / Malicious (hardened or LLM leaked) / Inconclusive (timeout, missing dataset).
6. Act — expected fixture leak: document. Unexpected: failing test then fix. Secret in git or unexpected live host: stop, redact, do not push.

See [references/playbooks.md](references/playbooks.md). Policy map: [references/defense-map.md](references/defense-map.md).

## Hardening before merge

Client still cannot send a URL. New HTTP is HTTPS, no redirects, counted in `external_requests`. New tools stay in-process and set oracle flags. Worker acquires lock **before** `recover_inflight()`. Tests cover leak, base64 leak, 422 extra fields, live-LLM gate, lock conflict. No secret in the diff.

## Common mistakes

| Excuse | Reality |
|---|---|
| "Hit the real chatbot" | Product forbids client URLs. Use synthetic cases. |
| "Let the LLM judge" | Oracle is authority. |
| "Scale workers" | Two recover loops steal jobs. |
| "Log the API key" | Name the env var, never the value. |
| "Need EDR/firewall logs" | Evidence is run record, oracle, tool events, egress metrics. |

## Sources (not vendored)

- https://github.com/wtalaat78/Blue-Team-Skills
- https://github.com/paulveillard/cybersecurity-blue-team
- https://github.com/secwexen/security-playbooks
