"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { FindingsTable } from "@/components/findings-table";
import { getRun, reportUrl, type Run } from "@/lib/api";

export default function RunPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.id) return;
    let cancelled = false;
    async function load() {
      try {
        let current = await getRun(params.id);
        if (!cancelled) setRun(current);
        while (!cancelled && (current.status === "queued" || current.status === "running")) {
          await new Promise((resolve) => setTimeout(resolve, 1500));
          current = await getRun(params.id);
          if (!cancelled) setRun(current);
        }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Không tải được run.");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  return (
    <AppShell>
      <section className="hero">
        <p className="eyebrow">Run evidence</p>
        <h1>{run ? run.id : "Đang tải run…"}</h1>
        <p>{run?.claim_level ?? "Run fixture nằm trong bộ nhớ process; LLM run được worker ghi Redis."}</p>
      </section>
      {error && <p className="notice">{error}</p>}
      {run && <section className="panel">
        <p>
          <strong>Status:</strong> {run.status} · <strong>Mode:</strong> {run.mode} ·
          <strong> Target:</strong> {run.target} · <strong>Attacker:</strong> {run.attacker} ·
          <strong> Split:</strong> {run.split} · <strong>Egress:</strong> {run.egress_host ?? "none"} ({run.metrics.external_requests})
        </p>
        {run.error && <p className="notice" role="alert">{run.error}</p>}
        <div style={{ display: "flex", gap: "0.75rem", margin: "0.9rem 0" }}>
          <a className="primary" href={reportUrl(run.id, "csv")}>Tải CSV</a>
          <a className="primary" href={reportUrl(run.id, "xlsx")}>Tải Excel</a>
          <Link href="/" className="primary">Chạy mới</Link>
        </div>
        <FindingsTable findings={run.findings} />
      </section>}
    </AppShell>
  );
}
