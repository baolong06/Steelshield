"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { getPolicies, type Policy } from "@/lib/api";

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getPolicies().then((response) => setPolicies(response.items)).catch((cause) => setError(cause instanceof Error ? cause.message : "Không tải được policies."));
  }, []);

  return (
    <AppShell>
      <section className="hero"><p className="eyebrow">Policy catalog</p><h1>10 policy tiếng Việt được compile local.</h1><p>Mỗi policy liên kết với deterministic canary hoặc state oracle. Không dùng LLM judge làm ground truth.</p></section>
      {error && <p className="notice">{error}</p>}
      <section className="grid-3">
        {policies.map((policy) => (
          <article className="panel" key={policy.id}>
            <p className="eyebrow">{policy.id} · {policy.oracle_type}</p>
            <h2>{policy.name}</h2>
            <p>{policy.statement_vi}</p>
            <p style={{ marginTop: "0.75rem", fontSize: "0.84rem" }}><strong>Ví dụ cấm:</strong> {policy.forbidden_examples[0]}</p>
          </article>
        ))}
      </section>
    </AppShell>
  );
}
