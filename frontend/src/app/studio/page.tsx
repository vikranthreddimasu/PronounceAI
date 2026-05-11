"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import VoiceStudio from "@/components/VoiceStudio";
import { PHRASES } from "@/lib/phrases";

const QUICK_PROMPTS: { label: string; text: string }[] = [
  {
    label: "Daily",
    text: "Could you pass me the salt, please? Actually, never mind, I'll get it myself.",
  },
  {
    label: "News read",
    text: "The Prime Minister addressed Parliament this morning, calling for calm amid rising tensions abroad.",
  },
  {
    label: "Coffee order",
    text: "I'll have a large flat white with oat milk, and a slice of the lemon drizzle cake, thanks.",
  },
  {
    label: "Phone reply",
    text: "Hello, this is Alex speaking. Sorry, I'm not available right now. Please leave a message after the tone.",
  },
  {
    label: "Pangram",
    text: "The quick brown fox jumps over the lazy dog by the river.",
  },
];

export default function StudioPage() {
  return (
    <Suspense fallback={null}>
      <StudioInner />
    </Suspense>
  );
}

function StudioInner() {
  const searchParams = useSearchParams();
  const [initialText, setInitialText] = useState("");

  // Honour deep-links from /practice and /library
  useEffect(() => {
    const phraseId = searchParams.get("phrase");
    const text = searchParams.get("text");
    if (text) {
      setInitialText(text);
      return;
    }
    if (phraseId) {
      const phrase = PHRASES.find((p) => p.id === phraseId);
      if (phrase) setInitialText(phrase.text);
    }
  }, [searchParams]);

  return (
    <main className="mx-auto" style={{ maxWidth: 760, padding: "32px 20px 80px" }}>
      <header style={{ marginBottom: 24 }}>
        <p
          className="font-mono"
          style={{
            fontSize: 11,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--ink-4)",
            marginBottom: 6,
          }}
        >
          Studio
        </p>
        <h1
          className="font-display"
          style={{
            fontSize: 36,
            fontWeight: 700,
            color: "var(--ink)",
            letterSpacing: "-0.02em",
          }}
        >
          Hear yourself, in any accent.
        </h1>
      </header>

      <VoiceStudio initialText={initialText} />

      {/* Quick prompts — drop-ins for whatever you want to test */}
      <section style={{ marginTop: 28 }}>
        <p
          className="font-mono"
          style={{
            fontSize: 10,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--ink-4)",
            marginBottom: 10,
          }}
        >
          Quick prompts
        </p>
        <div className="flex flex-wrap" style={{ gap: 8 }}>
          {QUICK_PROMPTS.map((q) => (
            <button
              key={q.label}
              className="btn-paper press"
              onClick={() => setInitialText(q.text)}
              style={{ fontSize: 12 }}
              title={q.text}
            >
              {q.label}
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
