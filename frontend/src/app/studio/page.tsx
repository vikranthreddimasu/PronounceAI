"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import VoiceStudio from "@/components/VoiceStudio";
import { PHRASES } from "@/lib/phrases";
import { tap } from "@/lib/sounds";

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
    <main className="studio-shell">
      <section className="shelf-header">
        <div>
          <p className="eyebrow">Voice experiment</p>
          <h1>Render a line only when you need another listening angle.</h1>
        </div>
        <Link href="/practice" onClick={() => tap()} className="btn-paper press">
          Back to session
        </Link>
      </section>
      <VoiceStudio initialText={initialText} />
    </main>
  );
}
