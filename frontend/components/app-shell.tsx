import Link from "next/link";
import type { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="site-header">
        <Link className="brand" href="/">Steel<span>shield</span></Link>
        <nav aria-label="Điều hướng chính">
          <Link href="/">Tổng quan</Link>
          <Link href="/policies">Policies</Link>
          <Link href="/datasets">Dataset</Link>
          <Link href="/reports">Reports</Link>
        </nav>
        <div className="egress-badge"><i /> Fixture: offline · LLM: server-configured gateway</div>
      </header>
      <main>{children}</main>
    </>
  );
}
