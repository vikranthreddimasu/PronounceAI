"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AppState, AssessmentResult, Accent } from "@/lib/types";
import { PHRASES } from "@/lib/phrases";
import { createRecorder, type Recorder } from "@/lib/recorder";
import { scoreRecording, playNativeAudio, isMockMode } from "@/lib/api";
import RecordButton from "@/components/RecordButton";
import PhonemeTimeline from "@/components/PhonemeTimeline";
import ScoreBars from "@/components/ScoreBars";
import FeedbackPanel from "@/components/FeedbackPanel";

const ACCENT_LABELS: Record<Accent, string> = {
  GA: "General American",
  RP: "RP British",
};

function focusLabel(focus: string): string {
  if (focus.includes("-vs-")) {
    const [a, b] = focus.split("-vs-");
    return `/${a}/ vs /${b}/`;
  }
  const map: Record<string, string> = {
    "weak-forms": "weak forms",
    "full-prosody": "full prosody",
    "connected-speech": "connected speech",
    "stress-timing": "stress & timing",
    "flap-t": "flap T",
    "consonant-cluster": "consonant clusters",
    "intonation-rise": "rising intonation",
    "falling-intonation": "falling intonation",
    "emphatic-stress": "emphatic stress",
    "polite-intonation": "polite intonation",
    "narrative-pace": "pace & rhythm",
  };
  return map[focus] ?? focus.replace(/-/g, " ");
}

function verdictLabel(score: number): string {
  if (score >= 90) return "Native-level";
  if (score >= 80) return "Strong";
  if (score >= 70) return "Getting there";
  if (score >= 55) return "Building";
  return "Keep going";
}

export default function Home() {
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [accent, setAccent] = useState<Accent>("GA");
  const [appState, setAppState] = useState<AppState>({ phase: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [isPlayingNative, setIsPlayingNative] = useState(false);
  const recorderRef = useRef<Recorder | null>(null);

  const phrase = PHRASES[phraseIdx];
  const result = appState.phase === "result" ? appState.result : null;
  const isRecording = appState.phase === "recording";
  const isProcessing = appState.phase === "processing";

  useEffect(() => { return () => { recorderRef.current?.dispose(); }; }, []);
  useEffect(() => { setAppState({ phase: "idle" }); setError(null); }, [phraseIdx, accent]);

  const getLevel = useCallback(() => recorderRef.current?.getLevel() ?? null, []);

  async function handleRecord() {
    setError(null);
    setAppState({ phase: "recording" });
    try {
      if (!recorderRef.current) recorderRef.current = await createRecorder();
      await recorderRef.current.start();
    } catch (e) {
      setError((e as Error).message ?? "Couldn't access microphone.");
      setAppState({ phase: "idle" });
    }
  }

  async function handleStop() {
    if (!recorderRef.current) return;
    setAppState({ phase: "processing" });
    try {
      const blob = await recorderRef.current.stop();
      const res: AssessmentResult = await scoreRecording(blob, phrase.text, accent);
      setAppState({ phase: "result", result: res });
    } catch (e) {
      setError((e as Error).message ?? "Something went wrong. Try again.");
      setAppState({ phase: "idle" });
    }
  }

  async function handlePlayNative() {
    if (isPlayingNative) return;
    setIsPlayingNative(true);
    await playNativeAudio(phrase.text, accent);
    setIsPlayingNative(false);
  }

  return (
    <main
      className="mx-auto flex min-h-dvh flex-col"
      style={{ maxWidth: 440, padding: "0 20px" }}
    >
      {/* ── Header ── */}
      <header className="flex items-center justify-between" style={{ height: 60, flexShrink: 0 }}>
        <span
          className="font-display font-bold tracking-tight"
          style={{ fontSize: 17, color: "var(--accent)", letterSpacing: "-0.02em" }}
        >
          PronounceAI
        </span>

        <div className="flex items-center gap-0.5 rounded-lg p-1" style={{ background: "var(--surface)" }}>
          {(["GA", "RP"] as Accent[]).map((a) => (
            <button
              key={a}
              className="press rounded-md text-xs font-semibold"
              style={{
                padding: "5px 12px",
                background: accent === a ? "var(--surface-2)" : "transparent",
                color: accent === a ? "var(--ink)" : "var(--ink-4)",
                border: accent === a ? "1px solid var(--line)" : "1px solid transparent",
              }}
              onClick={() => setAccent(a)}
              title={ACCENT_LABELS[a]}
            >
              {a}
            </button>
          ))}
        </div>
      </header>

      {/* ── Progress bar ── */}
      <div style={{ height: 2, background: "var(--surface-2)", borderRadius: 9999, marginBottom: 2, flexShrink: 0 }}>
        <div
          style={{
            height: "100%",
            width: `${((phraseIdx + 1) / PHRASES.length) * 100}%`,
            background: "var(--accent)",
            borderRadius: 9999,
            transition: "width 600ms var(--ease-out)",
          }}
        />
      </div>

      {/* ── Phrase zone ── */}
      <section
        className="flex flex-col items-center justify-end"
        style={{ flex: "0 0 auto", paddingTop: 32, paddingBottom: 28, gap: 14 }}
      >
        {/* Focus label */}
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--accent)",
            opacity: 0.75,
          }}
        >
          {focusLabel(phrase.focus)}
        </span>

        {/* Phrase */}
        <p
          key={phraseIdx}
          className="font-display phrase-mount text-center"
          style={{
            fontSize: result ? 20 : 26,
            fontWeight: 700,
            color: "var(--ink)",
            lineHeight: 1.25,
            transition: "font-size 400ms var(--ease-out)",
            maxWidth: 340,
          }}
        >
          {phrase.text}
        </p>

        {/* Hear it */}
        <button
          className="press flex items-center gap-2 rounded-full hover-accent"
          style={{
            padding: "6px 14px 6px 10px",
            background: isPlayingNative ? "var(--accent-faint)" : "transparent",
            border: "1px solid var(--line)",
            color: isPlayingNative ? "var(--accent)" : "var(--ink-4)",
            fontSize: 12,
            fontWeight: 500,
            transition: "all 200ms var(--ease-out)",
          }}
          onClick={handlePlayNative}
          disabled={isPlayingNative || isRecording || isProcessing}
        >
          <span style={{ fontSize: 10 }}>{isPlayingNative ? "♪" : "▶"}</span>
          <span>{isPlayingNative ? "Playing…" : `Hear it — ${accent}`}</span>
          {isMockMode() && <span style={{ fontSize: 9, opacity: 0.5 }}>browser</span>}
        </button>
      </section>

      {/* ── Record zone — always in the middle ── */}
      <section
        className="flex flex-col items-center"
        style={{ flexShrink: 0, paddingBottom: 28, gap: 16 }}
      >
        {!result && !isRecording && !isProcessing && (
          <p
            className="rise"
            style={{ fontSize: 13, color: "var(--ink-4)", fontStyle: "italic" }}
          >
            When you&rsquo;re ready.
          </p>
        )}

        {isRecording && (
          <p style={{ fontSize: 12, color: "var(--ink-4)" }}>
            &nbsp;
          </p>
        )}

        {isProcessing && (
          <p
            style={{ fontSize: 13, color: "var(--ink-3)", fontStyle: "italic" }}
          >
            Analyzing&hellip;
          </p>
        )}

        <RecordButton
          state={isRecording ? "recording" : isProcessing ? "processing" : "idle"}
          onRecord={handleRecord}
          onStop={handleStop}
          getLevel={getLevel}
        />

        {error && (
          <p
            className="text-center rounded-xl px-4 py-2.5"
            style={{
              fontSize: 12,
              maxWidth: 280,
              background: "rgba(217,155,138,0.08)",
              color: "var(--rose)",
              border: "1px solid rgba(217,155,138,0.18)",
            }}
          >
            {error}
          </p>
        )}
      </section>

      {/* ── Results ── */}
      {result && (
        <section className="result-enter flex flex-col" style={{ gap: 28, paddingBottom: 48 }}>
          {/* Score hero */}
          <ScoreHero overall={result.overall} />

          {/* Phoneme timeline */}
          <PhonemeTimeline phonemes={result.phonemes} />

          {/* Dimension bars */}
          <ScoreBars scores={result.scores} overall={result.overall} />

          {/* Coaching */}
          <FeedbackPanel tips={result.feedback} />

          {/* Actions */}
          <div className="flex gap-3">
            <button
              className="press hover-lift flex-1 rounded-xl text-sm font-semibold"
              style={{
                padding: "13px 0",
                background: "var(--surface)",
                border: "1px solid var(--line)",
                color: "var(--ink-3)",
              }}
              onClick={() => { setAppState({ phase: "idle" }); setError(null); }}
            >
              Try again
            </button>
            <button
              className="press flex-1 rounded-xl text-sm font-bold"
              style={{
                padding: "13px 0",
                background: "linear-gradient(160deg, var(--accent-soft), var(--accent))",
                color: "var(--bg)",
                boxShadow: "0 4px 20px -4px rgba(232,184,95,0.45)",
              }}
              onClick={() => setPhraseIdx((i) => (i + 1) % PHRASES.length)}
            >
              Next →
            </button>
          </div>
        </section>
      )}
    </main>
  );
}

function ScoreHero({ overall }: { overall: number }) {
  const verdict = verdictLabel(overall);
  const color = overall >= 80 ? "var(--jade)" : overall >= 65 ? "var(--accent)" : "var(--rose)";

  return (
    <div className="result-enter flex items-center gap-5">
      <div
        className="flex flex-col items-center justify-center rounded-2xl"
        style={{
          width: 72, height: 72, flexShrink: 0,
          background: color + "15",
          border: `2px solid ${color}`,
        }}
      >
        <span style={{ fontSize: 26, fontWeight: 800, color, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
          {overall}
        </span>
        <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.06em", color, textTransform: "uppercase", opacity: 0.8, marginTop: 3 }}>
          / 100
        </span>
      </div>

      <div>
        <p style={{ fontSize: 20, fontWeight: 700, color: "var(--ink)", lineHeight: 1.1, marginBottom: 4 }}>
          {verdict}
        </p>
        <p style={{ fontSize: 12, color: "var(--ink-4)", lineHeight: 1.5 }}>
          See below for what to fix.
        </p>
      </div>
    </div>
  );
}
