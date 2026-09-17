"use client";

import { useState } from "react";
import { createRun, type Attacker, type Dataset, type Policy, type Run, type RunMode, type RunTarget } from "@/lib/api";

export function RunWizard({ policies, datasets, onComplete }: {
  policies: Policy[];
  datasets: Dataset;
  onComplete: (run: Run) => void;
}) {
  const [split, setSplit] = useState("train");
  const [policyId, setPolicyId] = useState("POL-06");
  const [mode, setMode] = useState<RunMode>("fixture");
  const [target, setTarget] = useState<RunTarget>("hardened");
  const [attacker, setAttacker] = useState<Attacker>("replay");
  const [limit, setLimit] = useState("20");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function selectMode(next: RunMode) {
    setMode(next);
    setTarget(next === "fixture" ? "hardened" : "llm_hardened");
    setAttacker("replay");
    setLimit(next === "fixture" ? "20" : "4");
  }

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const run = await createRun({
        split,
        policy_ids: policyId ? [policyId] : [],
        limit: Number(limit) || undefined,
        target,
        mode,
        attacker,
      });
      onComplete(run);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể tạo run.");
    } finally {
      setBusy(false);
    }
  }

  const llm = mode === "llm";
  return (
    <section className="panel" aria-label="Tạo synthetic run">
      <p className="eyebrow">Run wizard</p>
      <h2>{llm ? "Chạy chiến dịch agent synthetic" : "Chạy mô phỏng fixture local"}</h2>
      <p>
        {llm
          ? "Attacker/target LLM chỉ dùng sandbox synthetic; egress đi qua HTTPS gateway do server cấu hình. Không có URL target từ client."
          : "Target là twin fixture hardened/vulnerable, không phải chatbot hay endpoint thật; egress luôn bằng 0."}
      </p>
      <div className="form-grid" style={{ marginTop: "1rem" }}>
        <label>Chế độ
          <select value={mode} onChange={(event) => selectMode(event.target.value as RunMode)}>
            <option value="fixture">fixture — local, egress 0</option>
            <option value="llm">LLM agent — Redis worker, declared egress</option>
          </select>
        </label>
        <label>Split
          <select value={split} onChange={(event) => setSplit(event.target.value)}>
            {datasets.splits.map((item) => <option value={item.id} key={item.id}>{item.id} · {item.case_count} cases</option>)}
          </select>
        </label>
        <label>Policy
          <select value={policyId} onChange={(event) => setPolicyId(event.target.value)}>
            {policies.map((policy) => <option value={policy.id} key={policy.id}>{policy.id} · {policy.name}</option>)}
          </select>
        </label>
        <label>Target {llm ? "agent" : "fixture"}
          <select value={target} onChange={(event) => setTarget(event.target.value as RunTarget)}>
            {llm ? <>
              <option value="llm_hardened">llm_hardened — enforce policy</option>
              <option value="llm_vulnerable">llm_vulnerable — deliberate sandbox contrast</option>
            </> : <>
              <option value="hardened">hardened — should block attacks</option>
              <option value="vulnerable">vulnerable — deliberate leak simulation</option>
            </>}
          </select>
        </label>
        {llm && <label>Attacker
          <select value={attacker} onChange={(event) => setAttacker(event.target.value as Attacker)}>
            <option value="replay">replay — benchmark user turns</option>
            <option value="llm">llm — generate one synthetic turn</option>
          </select>
        </label>}
        <label>Case limit
          <input type="number" min="1" max="300" value={limit} onChange={(event) => setLimit(event.target.value)} />
        </label>
        <button className="primary" type="button" disabled={busy} onClick={submit}>
          {busy ? "Đang tạo…" : llm ? "Xếp hàng LLM campaign" : "Chạy fixture"}
        </button>
      </div>
      {llm && <p className="notice" style={{ marginTop: "1rem" }}>LLM run tốn phí gateway và cần Redis worker. Timeout, exception hoặc not-run được ghi là fail; oracle tất định quyết định verdict.</p>}
      {split === "evaluation_candidate" && <p className="notice" style={{ marginTop: "1rem" }}>Cảnh báo: đây là split tạo trong repo, không phải secret holdout.</p>}
      {error && <p role="alert" style={{ color: "#ffb4c8", marginBottom: 0 }}>{error}</p>}
    </section>
  );
}
