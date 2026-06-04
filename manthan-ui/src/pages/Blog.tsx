/**
 * Blog index. One post for now; the layout is designed to take more
 * without rework - each post is a hero card with cover, date, title,
 * dek, and a one-line role. New posts: prepend to POSTS, generate a
 * page component, add to the route table in AppRouter.tsx.
 */

import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { useEffect } from "react";
import { Logo } from "@/components/Logo";

interface Post {
  slug: string;
  title: string;
  dek: string;
  cover: string;
  coverAlt: string;
  author: string;
  date: string;
  readMinutes: number;
  tags: string[];
}

const POSTS: Post[] = [
  {
    slug: "tokens-are-the-new-salary",
    title: "Tokens are the new salary.",
    dek: "Uber burned its 2026 AI budget in four months. The next hundred AI-native service companies will hit the same wall. Here is the bet we made on Coral that we think survives it.",
    cover: "/blog/01-cover-many-to-one.webp",
    coverAlt:
      "Editorial illustration: vendor-shaped translucent ribbons collapsing through a coral-shaped lens into one clean amber line",
    author: "Hitakshi",
    date: "June 4, 2026",
    readMinutes: 11,
    tags: ["AI-native services", "Coral", "engineering"],
  },
];

export default function Blog() {
  useEffect(() => {
    const prev = document.title;
    document.title = "Blog · Manthan";
    return () => {
      document.title = prev;
    };
  }, []);

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: "#000", color: "oklch(0.95 0.004 75)" }}
    >
      <nav className="relative z-30 px-6 md:px-12 lg:px-20 py-5 flex items-center justify-between">
        <Link
          to="/"
          className="flex items-center gap-2.5 hover:opacity-90 transition-opacity"
        >
          <Logo size={26} showWordmark={false} className="text-white" />
          <span className="text-lg font-semibold tracking-tight text-white">
            Manthan
          </span>
        </Link>
        <Link to="/login">
          <button
            className="rounded-lg text-sm font-semibold px-4 py-2 hover:opacity-90 transition-opacity"
            style={{ background: "#fff", color: "#000" }}
          >
            Sign in
          </button>
        </Link>
      </nav>

      <main className="flex-1 w-full px-6 md:px-12 lg:px-20 pt-12 md:pt-20 pb-24 md:pb-32">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.25, 1, 0.5, 1] }}
          className="max-w-5xl mx-auto"
        >
          {/* Header */}
          <div
            style={{
              fontFamily: "Geist Mono, ui-monospace, monospace",
              fontSize: 11,
              color: "oklch(0.55 0.006 75)",
              letterSpacing: "0.20em",
              textTransform: "uppercase",
              marginBottom: 16,
            }}
          >
            Captain's Log
          </div>

          <h1
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              fontSize: "clamp(40px, 5vw, 64px)",
              lineHeight: 1.04,
              color: "oklch(0.98 0.003 75)",
              letterSpacing: "-0.018em",
              fontWeight: 400,
              maxWidth: "20ch",
            }}
          >
            What we shipped, why, and how we'd do it again.
          </h1>

          <p
            style={{
              fontFamily: "Spectral, serif",
              fontSize: "clamp(18px, 1.9vw, 21px)",
              lineHeight: 1.5,
              color: "oklch(0.72 0.006 75)",
              marginTop: 22,
              maxWidth: "62ch",
              letterSpacing: "-0.004em",
            }}
          >
            Engineering write-ups from the people building Manthan. Long
            enough to be useful, short enough to read on a phone, written
            so a finance lead and an SRE could both get something out of
            them.
          </p>

          <div
            style={{
              marginTop: 48,
              height: 1,
              background: "rgba(255,255,255,0.10)",
            }}
          />

          {/* Posts */}
          <div
            style={{
              marginTop: 48,
              display: "grid",
              gridTemplateColumns: "1fr",
              gap: 56,
            }}
          >
            {POSTS.map((p) => (
              <PostCard key={p.slug} post={p} />
            ))}
          </div>

          {POSTS.length === 1 && (
            <p
              style={{
                marginTop: 80,
                fontFamily: "Spectral, serif",
                fontStyle: "italic",
                fontSize: 16,
                color: "oklch(0.55 0.006 75)",
                textAlign: "center",
              }}
            >
              More to come. We are mostly heads down shipping right now.
            </p>
          )}
        </motion.div>
      </main>

      <footer
        className="px-6 md:px-12 lg:px-20 py-10 border-t flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
        style={{ borderColor: "rgba(255,255,255,0.08)" }}
      >
        <div className="flex items-center gap-2.5">
          <Logo size={20} showWordmark={false} className="text-white" />
          <span
            className="font-mono"
            style={{ fontSize: 12, color: "oklch(0.55 0.006 75)" }}
          >
            © {new Date().getFullYear()} Manthan. All rights reserved.
          </span>
        </div>
        <div className="flex items-center gap-5 text-sm">
          {[
            { label: "Privacy", to: "/privacy" },
            { label: "Terms", to: "/terms" },
            { label: "DPA", to: "/dpa" },
            { label: "Contact", to: "/contact" },
          ].map((l) => (
            <Link
              key={l.to}
              to={l.to}
              style={{ color: "oklch(0.65 0.006 75)" }}
            >
              {l.label}
            </Link>
          ))}
        </div>
      </footer>
    </div>
  );
}

function PostCard({ post }: { post: Post }) {
  return (
    <Link
      to={`/blog/${post.slug}`}
      style={{
        textDecoration: "none",
        color: "inherit",
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 1fr)",
        gap: 36,
        alignItems: "stretch",
      }}
      className="group blog-post-card"
    >
      <div
        style={{
          position: "relative",
          aspectRatio: "16 / 9",
          borderRadius: 8,
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        <img
          src={post.cover}
          alt={post.coverAlt}
          loading="lazy"
          decoding="async"
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: "block",
            transition: "transform 0.5s ease",
          }}
          className="group-hover:scale-[1.02]"
        />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div
          style={{
            fontFamily: "Geist Mono, ui-monospace, monospace",
            fontSize: 11,
            color: "oklch(0.55 0.006 75)",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
          }}
        >
          <span>{post.date}</span>
          <span style={{ opacity: 0.4 }}>·</span>
          <span>{post.readMinutes} min read</span>
        </div>

        <h2
          style={{
            fontFamily: "Spectral, serif",
            fontStyle: "italic",
            fontSize: "clamp(30px, 3.4vw, 44px)",
            lineHeight: 1.05,
            color: "oklch(0.98 0.003 75)",
            letterSpacing: "-0.014em",
            fontWeight: 400,
            marginTop: 4,
          }}
        >
          {post.title}
        </h2>

        <p
          style={{
            fontFamily: "Spectral, serif",
            fontSize: 17,
            lineHeight: 1.55,
            color: "oklch(0.76 0.006 75)",
            marginTop: 6,
            letterSpacing: "-0.003em",
          }}
        >
          {post.dek}
        </p>

        <div
          style={{
            marginTop: "auto",
            paddingTop: 20,
            display: "flex",
            alignItems: "center",
            gap: 14,
            fontFamily: "Geist Mono, ui-monospace, monospace",
            fontSize: 11,
            color: "oklch(0.55 0.006 75)",
            letterSpacing: "0.12em",
          }}
        >
          <span>{post.author}</span>
          <span style={{ opacity: 0.4 }}>·</span>
          <span
            style={{
              color: "#C97B2A",
              textTransform: "uppercase",
              letterSpacing: "0.18em",
            }}
            className="group-hover:underline"
          >
            Read →
          </span>
        </div>
      </div>
    </Link>
  );
}
