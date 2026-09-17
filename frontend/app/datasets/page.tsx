"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { getDatasets, type Dataset } from "@/lib/api";

export default function DatasetsPage() {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getDatasets().then(setDataset).catch((cause) => setError(cause instanceof Error ? cause.message : "Không tải được dataset.")); }, []);

  return (
    <AppShell>
      <section className="hero"><p className="eyebrow">Dataset provenance</p><h1>Synthetic dataset v{dataset?.version ?? "…"}</h1><p>Phiên bản, quy mô và trạng thái integrity do server cung cấp.</p></section>
      {error && <p className="notice">{error}</p>}
      {dataset && <>
        <p className="notice">{dataset.notice}</p>
        <section className="grid-3" style={{ marginTop: "1rem" }}>
          {dataset.splits.map((split) => <article className="panel" key={split.id}><p className="eyebrow">{split.id}</p><h2>{split.case_count} cases</h2><p>{split.purpose}</p></article>)}
        </section>
        <section className="panel" style={{ marginTop: "1rem" }}>
          <p className="eyebrow">Hash integrity gate</p><h2>Manifest-locked files</h2>
          <div className="table-scroll"><table><thead><tr><th>Artifact</th><th>SHA-256</th><th>Trạng thái</th></tr></thead><tbody>{Object.entries(dataset.hashes).map(([key, hash]) => <tr key={key}><td>{key}</td><td className="hash">{hash}</td><td>{dataset.integrity[key.replace("_sha256", "_sha256")] ?? "—"}</td></tr>)}</tbody></table></div>
        </section>
      </>}
    </AppShell>
  );
}
