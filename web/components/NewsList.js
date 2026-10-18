const SOURCE_LABELS = {
  yahoo: "Yahoo",
  google_news: "Google News",
  sec_edgar: "SEC EDGAR",
};

// Sentiment is never color-alone (dataviz guidance: status needs a label,
// not just a hue) -- the word "positive"/"negative"/"neutral" carries the
// meaning, color is secondary reinforcement using the same up/down tokens
// already used for price changes elsewhere in this app.
function SentimentTag({ label }) {
  if (!label) return null;
  const cls = label === "positive" ? "up" : label === "negative" ? "down" : "";
  return (
    <span className={cls} style={{ fontSize: 10.5, fontWeight: 650, textTransform: "uppercase", letterSpacing: "0.02em" }}>
      {label}
    </span>
  );
}

export default function NewsList({ items, emptyLabel = "No recent headlines." }) {
  if (!items || items.length === 0) {
    return <p style={{ fontSize: 13, color: "var(--muted)" }}>{emptyLabel}</p>;
  }
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {items.map((item, i) => (
        <li key={item.link} style={{ padding: "12px 0", borderTop: i === 0 ? "none" : "1px solid var(--grid)" }}>
          <a
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 13.5, fontWeight: 600, textDecoration: "none" }}
          >
            {item.title}
          </a>
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 4 }}>
            <span style={{ fontSize: 11, color: "var(--muted)" }}>
              {SOURCE_LABELS[item.source] || item.source}
              {item.published_at ? ` · ${item.published_at}` : ""}
            </span>
            <SentimentTag label={item.sentiment_label} />
          </div>
        </li>
      ))}
    </ul>
  );
}
