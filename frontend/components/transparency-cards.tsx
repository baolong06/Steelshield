export function TransparencyCards() {
  return (
    <section className="transparency-grid" aria-label="Thông tin minh bạch">
      <article className="panel transparency-card">
        <p className="eyebrow">Vì sao tin được</p>
        <h2>Oracle quyết định, không phải LLM judge</h2>
        <p>Canary và synthetic state là tiêu chí pass/fail tất định. LLM chỉ đóng vai attacker/target trong LLM mode, không đổi verdict.</p>
      </article>
      <article className="panel transparency-card">
        <p className="eyebrow">Dữ liệu đi đâu</p>
        <h2>Fixture local hoặc gateway do server cấu hình</h2>
        <p>Fixture không có HTTP outbound. LLM mode gọi HTTPS gateway do operator cấu hình ở server; email, ticket, export và refund là tool mock in-process.</p>
      </article>
      <article className="panel transparency-card warning-card">
        <p className="eyebrow">Giới hạn bằng chứng</p>
        <h2>Generated, chưa review</h2>
        <p>Split evaluation_candidate là dữ liệu tạo trong repo, không phải secret holdout và không dùng làm bằng chứng dự thi.</p>
      </article>
    </section>
  );
}
