import Head from "next/head";
import Link from "next/link";
import Nav from "../components/Nav";

export default function NotFound() {
  return (
    <>
      <Head>
        <title>Not found — Live Portfolio Simulator</title>
      </Head>
      <Nav />
      <main id="main-content" className="container" style={{ textAlign: "center", paddingTop: 96 }}>
        <div className="eyebrow">404</div>
        <h1 className="page-title" style={{ fontSize: 30, margin: "8px 0 10px" }}>
          This page isn&apos;t in the universe.
        </h1>
        <p className="lede" style={{ margin: "0 auto 24px" }}>
          Nothing lives at this address. Head back to the portfolio or search the full equity universe.
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
          <Link href="/" className="btn active">
            My Portfolio
          </Link>
          <Link href="/explore" className="btn">
            Explore
          </Link>
        </div>
      </main>
    </>
  );
}
