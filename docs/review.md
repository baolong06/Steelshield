# Review: Steelshield Agent Control Plane — vòng 5

**Verdict: APPROVED**

**Root cause: NONE**

**Loop: 5**

## Phạm vi review

Đối chiếu `docs/plan.md` Revision 4 (single-worker exclusivity) với `docs/report.md` vòng 4 và chạy lại kiểm chứng local. Không in, log hay commit credential.

## Kết quả kiểm chứng thực tế (vòng này)

- `python -m compileall -q backend/app backend/tests` → PASS.
- `python dataset/scripts/validate_dataset.py` → **VALIDATION PASSED** (600 cases / 300 families; splits 360/120/120).
- `python -m pytest dataset/tests/test_benchmark.py backend/tests -q` → **28 passed in 2.41s** (4 benchmark + 19 backend cũ + 5 Rev4).
- `python -m ruff check backend/app backend/tests` → **All checks passed**.
- `python -m ruff format --check backend/app backend/tests` → **30 files already formatted**.
- `docker compose config --quiet` → **PASS** (không lỗi).
- `npm --prefix frontend run build` → PASS; Next.js 16.3.5, 6 routes.
- `git diff --check` → PASS; chỉ có cảnh báo Git LF/CRLF trên `README.md`, không có whitespace error.
- `git check-ignore -v backend/.env` → `.gitignore:16:*.env backend/.env`; `git ls-files --error-unmatch backend/.env` → không track.
- Two-process integration test (với `STEELSHIELD_REDIS_TEST_URL=redis://127.0.0.1:6379/15` + Compose Redis) → **PASS**; worker thứ hai exit code 1 và log lock conflict.

## Đối chiếu plan Revision 4

| Tiêu chí | Kết luận | Bằng chứng |
|---|---|---|
| Gateway HTTPS, host/path không khóa | Đạt | Settings giữ validate HTTPS + hostname; regression test pass. |
| Client không gửi URL target | Đạt | `RunRequest(extra="forbid")`; test `endpoint` → 422. |
| Live egress opt-in | Đạt | `STEELSHIELD_LIVE_LLM=1` ở `run_service` và `ResponsesClient._post`. |
| Không follow redirect | Đạt | `httpx.Client(follow_redirects=False)`. |
| Sandbox in-process | Đạt | `ToolSandbox` chỉ set state local. |
| Oracle là authority | Đạt | `campaign.run_llm_cases` gọi `evaluate_oracle`. |
| Redis bắt buộc cho LLM mode | Đạt | Queue 503 khi Redis down; fixture không cần Redis. |
| Secret không commit | Đạt | `.env` ignored, không tracked. |
| Dataset integrity | Đạt | Hash khớp manifest. |
| **Single-worker exclusivity (Rev4)** | **Đạt** | `SET NX EX` chỉ một token owner; holder renew qua CAS Lua; CAS release; instance thứ hai exit code 1 với log "lock conflict"; full suite 28 passed (two-process skip khi không có `STEELSHIELD_REDIS_TEST_URL`); integration test với Redis thật PASS. |

## Điểm thay đổi so với vòng 4 (implement Rev4)

- `backend/app/adapters/queue.py`: thêm token lock bằng `SET NX EX`, renew bằng Lua compare-and-expire, release bằng Lua compare-and-delete (đúng contract owner token, không khóa mù khiến instance khác không thể renew).
- `backend/app/worker.py`: acquire lock **trước** `recover_inflight()` và vòng `blpop`; second instance log conflict + exit 1; heartbeat gia hạn TTL trong campaign; clean shutdown release theo token. Quan trọng: `recover_inflight()` chỉ chạy sau khi lock đã giữ → tránh hai instance cùng reclaim job cũ.
- `backend/app/core/settings.py`, `backend/.env.example`: `STEELSHIELD_WORKER_LOCK_TTL_SEC` mặc định 60; validate >= 1.
- `backend/tests/test_agent.py`: test owner token/CAS release, renewal, TTL expiry, `worker.main()` fail-fast; two-process integration test (skip khi thiếu `STEELSHIELD_REDIS_TEST_URL`).
- `backend/pyproject.toml`: `fakeredis[lua]` để test được CAS Lua scripts.
- `docker-compose.yml`, `README.md`: nêu worker không được scale; recovery sau crash = chờ TTL hết hạn.

## Vấn đề đã đóng (không mở lại)

1. Tool continuation Responses (`function_call` + `function_call_output`, cùng `call_id`, không dùng `previous_response_id` khi `store=false`).
2. Hạch toán `external_requests` khi gateway lỗi / `agent_timeout`.
3. Exact-host allowlist `modelapi.vn` — đã bỏ theo Revision 2.
4. Ràng buộc path phải kết thúc `/v1` — đã bỏ theo Revision 3.
5. Single-worker race: hai instance chạy `recover_inflight()` + `blpop` đồng thời — Rev4 giải bằng owner-token Redis lock.

## Vấn đề phải sửa

Không có issue DEV.

## Ghi chú kỹ thuật (không phải issue bắt buộc)

- Two-process test vẫn có thể skip khi thiếu `STEELSHIELD_REDIS_TEST_URL`. Full suite 28 passed trong CI không Redis là đúng — production stack cần Compose Redis. Đã chạy integration test với Redis thật trong vòng này.
- `docker-compose.yml` không nên chạy `worker` ở scale > 1. Operator tự ý thay đổi sẽ vi phạm invariant Rev4.
- Heartbeat renewal Lua script chỉ gia hạn khi token khớp → nếu lock hết hạn và instance khác đã acquire, worker hiện tại không thể "đòi lại" lock; nó sẽ log mất lock và thoát vòng lặp.

## Credential audit (root cause: NONE)

Credential được cung cấp qua biến môi trường trong `backend/.env`, file này bị Git ignore và không được in vào log, báo cáo hoặc source code. Mã nguồn chỉ đọc tên biến `STEELSHIELD_LLM_API_KEY`; không lưu giá trị credential trong repository.

## Kết luận

Triển khai Revision 4 đúng và đã được kiểm chứng local + integration test với Redis thật. Toàn bộ acceptance criteria của plan Revision 4 pass. Tất cả issue DEV đã đóng. Credential không có dấu hiệu bị lộ.

Review **APPROVED**.
