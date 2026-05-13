"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import VoiceStudio from "@/components/VoiceStudio";
import { PHRASES } from "@/lib/phrases";

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
    <main className="voice-lab-page">
      <VoiceStudio initialText={initialText} />
    </main>
  );
}
