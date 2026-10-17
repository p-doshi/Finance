import Head from "next/head";
import { Manrope } from "next/font/google";
import "../styles/globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-sans",
});

export default function App({ Component, pageProps }) {
  return (
    <div className={`${manrope.variable} ${manrope.className}`}>
      <Head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <meta
          name="description"
          content="Live-updating portfolio simulator: a real walk-forward backtest extended with a live market-data tail, across equal-weight, risk parity, HRP, min-variance and max-Sharpe strategies."
        />
      </Head>
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <Component {...pageProps} />
    </div>
  );
}
