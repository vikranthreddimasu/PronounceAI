"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { AppState, AssessmentResult, Accent, Scores } from "@/lib/types";
import { PHRASES, CATEGORY_LABELS } from "@/lib/phrases";
import { createRecorder, type Recorder } from "@/lib/recorder";
import { scoreRecording, playNativeAudio, isMockMode } from "@/lib/api";
import { useCountUp } from "@/lib/useCountUp";
import { appendSession, getProfile, setProfile, subscribeStorage } from "@/lib/store";
import { tap, confirm, release } from "@/lib/sounds";
import RecordButton from "@/components/RecordButton";
import PhonemeTimeline from "@/components/PhonemeTimeline";
import ScoreBars from "@/components/ScoreBars";
import PitchContourOverlay from "@/components/PitchContourOverlay";
import PhonemeABDiff from "@/components/PhonemeABDiff";
import AccentConvertCard from "@/components/AccentConvertCard";
import EnrollmentModal from "@/components/EnrollmentModal";
import Tabs, { type TabItem } from "@/components/Tabs";
import VoiceStudio from "@/components/VoiceStudio";
import SpokenText from "@/components/SpokenText";
import {
  fetchVoiceProfile,
  getOrCreateVoiceId,
  speakInVoice,
  type VoiceProfile,
  type WordTiming,
} from "@/lib/voiceProfile";

const ACCENT_LABELS: Record<Accent, string> = {
  GA: "General American",
  RP: "Received Pronunciation",
};

type Mode = "phrases" | "free";
type ResultTab = "overview" | "phonemes" | "prosody" | "accent";

const MIN_FREE_LEN = 3;
const MAX_FREE_LEN = 200;

function sanitiseFree(text: string): string {
  return text.replace(/[^\x20-\x7E]/g, "").slice(0, MAX_FREE_LEN);
}

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

function pickInitialTab(scores: Scores): ResultTab {
  const entries: { key: keyof Scores; tab: ResultTab; v: number }[] = [
    { key: "phoneme_accuracy", tab: "phonemes", v: scores.phoneme_accuracy },
    { key: "intonation", tab: "prosody", v: scores.intonation },
    { key: "stress_rhythm", tab: "prosody", v: scores.stress_rhythm },
    { key: "vowel_quality", tab: "phonemes", v: scores.vowel_quality },
  ];
  entries.sort((a, b) => a.v - b.v);
  return entries[0].tab;
}

export default function PracticePage() {
  return (
    <Suspense fallback={null}>
      <PracticeInner />
    </Suspense>
  );
}

function PracticeInner() {
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<Mode>("phrases");
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [freeText, setFreeText] = useState("");
  const [accent, setAccent] = useState<Accent>("GA");
  const [appState, setAppState] = useState<AppState>({ phase: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [isPlayingNative, setIsPlayingNative] = useState(false);
  const [userAudioUrl, setUserAudioUrl] = useState<string | null>(null);
  const [userAudioBlob, setUserAudioBlob] = useState<Blob | null>(null);
  const [voiceProfile, setVoiceProfile] = useState<VoiceProfile | null>(null);
  const [enrollmentOpen, setEnrollmentOpen] = useState(false);
  const [resultTab, setResultTab] = useState<ResultTab>("overview");
  const [hearInVoiceState, setHearInVoiceState] = useState<"idle" | "loading" | "playing">("idle");
  const [hearInVoiceWords, setHearInVoiceWords] = useState<WordTiming[]>([]);
  const recorderRef = useRef<Recorder | null>(null);
  const userAudioRef = useRef<HTMLAudioElement | null>(null);
  const hearInVoiceRef = useRef<HTMLAudioElement | null>(null);
  const hearInVoiceUrlRef = useRef<string | null>(null);

  // Sync accent with stored profile on mount.
  useEffect(() => {
    const p = getProfile();
    setAccent(p.targetAccent);
    return subscribeStorage(() => setAccent(getProfile().targetAccent));
  }, []);

  // Honour ?phrase=ID from Library deep links.
  useEffect(() => {
    const id = searchParams.get("phrase");
    if (!id) return;
    const idx = PHRASES.findIndex((p) => p.id === id);
    if (idx >= 0) {
      setMode("phrases");
      setPhraseIdx(idx);
    }
  }, [searchParams]);

  const activeText = mode === "free" ? freeText.trim() : PHRASES[phraseIdx].text;
  const activePhrase = mode === "phrases" ? PHRASES[phraseIdx] : null;
  const activeFocus = mode === "free" ? null : PHRASES[phraseIdx].focus;
  const canRecord = mode === "free" ? activeText.length >= MIN_FREE_LEN : true;

  const result = appState.phase === "result" ? appState.result : null;
  const isRecording = appState.phase === "recording";
  const isProcessing = appState.phase === "processing";

  useEffect(() => {
    return () => {
      recorderRef.current?.dispose();
      if (userAudioUrl) URL.revokeObjectURL(userAudioUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const id = getOrCreateVoiceId();
    if (!id) return;
    fetchVoiceProfile(id)
      .then((p) => setVoiceProfile(p))
      .catch(() => setVoiceProfile(null));
  }, []);

  useEffect(() => {
    setAppState({ phase: "idle" });
    setError(null);
    if (userAudioUrl) {
      URL.revokeObjectURL(userAudioUrl);
      setUserAudioUrl(null);
    }
    setUserAudioBlob(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phraseIdx, accent, mode]);

  const getLevel = useCallback(() => recorderRef.current?.getLevel() ?? null, []);

  async function handleRecord() {
    setError(null);
    setAppState({ phase: "recording" });
    tap();
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
    release();
    try {
      const blob = await recorderRef.current.stop();
      if (userAudioUrl) URL.revokeObjectURL(userAudioUrl);
      const url = URL.createObjectURL(blob);
      setUserAudioUrl(url);
      setUserAudioBlob(blob);
      const res: AssessmentResult = await scoreRecording(blob, activeText, accent);
      setAppState({ phase: "result", result: res });
      setResultTab(pickInitialTab(res.scores));
      appendSession(res, { phrase: activeText, mode, accent });
      confirm();
    } catch (e) {
      setError((e as Error).message ?? "Something went wrong. Try again.");
      setAppState({ phase: "idle" });
    }
  }

  async function handlePlayNative() {
    if (isPlayingNative || !activeText) return;
    setIsPlayingNative(true);
    tap();
    await playNativeAudio(activeText, accent);
    setIsPlayingNative(false);
  }

  async function handleHearInVoice() {
    if (!voiceProfile || !activeText || hearInVoiceState !== "idle") return;
    tap();
    setHearInVoiceState("loading");
    setHearInVoiceWords([]);
    try {
      const id = getOrCreateVoiceId();
      const clip = await speakInVoice(id, activeText, accent);
      if (hearInVoiceUrlRef.current) URL.revokeObjectURL(hearInVoiceUrlRef.current);
      const url = URL.createObjectURL(clip.audio);
      hearInVoiceUrlRef.current = url;
      setHearInVoiceWords(clip.words);
      if (!hearInVoiceRef.current) hearInVoiceRef.current = new Audio();
      const a = hearInVoiceRef.current;
      a.src = url;
      a.currentTime = 0;
      a.onended = () => setHearInVoiceState("idle");
      a.onerror = () => setHearInVoiceState("idle");
      setHearInVoiceState("playing");
      a.play().catch(() => setHearInVoiceState("idle"));
      confirm();
    } catch (e) {
      setError((e as Error).message ?? "Voice synthesis failed.");
      setHearInVoiceState("idle");
    }
  }

  const playNativeFromPanel = useCallback(
    () => playNativeAudio(activeText, accent),
    [activeText, accent]
  );

  const playUserRecording = useCallback((): Promise<void> => {
    if (!userAudioUrl) return Promise.resolve();
    return new Promise((resolve) => {
      if (!userAudioRef.current) userAudioRef.current = new Audio();
      const a = userAudioRef.current;
      a.src = userAudioUrl;
      a.currentTime = 0;
      a.onended = () => resolve();
      a.onerror = () => resolve();
      a.play().catch(() => resolve());
    });
  }, [userAudioUrl]);

  const onAccentChange = useCallback((a: Accent) => {
    tap();
    setAccent(a);
    setProfile({ targetAccent: a });
  }, []);

  const tabs: TabItem<ResultTab>[] = useMemo(
    () => [
      { id: "overview", label: "Overview" },
      { id: "phonemes", label: "Phonemes", count: result?.phonemes.filter((p) => !p.correct).length },
      { id: "prosody", label: "Prosody" },
      { id: "accent", label: "Accent" },
    ],
    [result]
  );

  return (
    <main
      className="mx-auto"
      style={{ maxWidth: 1180, padding: "32px 20px 80px" }}
    >
      <div
        className="grid"
        style={{
          gridTemplateColumns: "minmax(0, 1fr)",
          gap: 32,
        }}
      >
        {/* ── Header row ── */}
        <header className="flex flex-wrap items-end justify-between" style={{ gap: 16 }}>
          <div>
            <p
              className="font-mono"
              style={{
                fontSize: 11,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "var(--ink-4)",
              }}
            >
              {mode === "free" ? "Free speak" : activePhrase ? CATEGORY_LABELS[activePhrase.category] : ""}
              {activeFocus && (
                <span style={{ marginLeft: 10, color: "var(--accent)" }}>
                  · {focusLabel(activeFocus)}
                </span>
              )}
            </p>
            <h1
              className="font-display"
              style={{
                fontSize: 28,
                fontWeight: 700,
                color: "var(--ink)",
                marginTop: 6,
                letterSpacing: "-0.02em",
              }}
            >
              {mode === "phrases"
                ? `Phrase ${phraseIdx + 1} of ${PHRASES.length}`
                : "Say anything"}
            </h1>
          </div>

          <div className="flex items-center" style={{ gap: 10 }}>
            {/* Mode toggle */}
            <div className="tab-bar" role="tablist" aria-label="Practice mode">
              {(["phrases", "free"] as Mode[]).map((m) => (
                <button
                  key={m}
                  className="tab-btn press"
                  data-active={mode === m}
                  onClick={() => {
                    if (mode === m) return;
                    tap();
                    setMode(m);
                  }}
                >
                  {m === "phrases" ? "Phrases" : "Free"}
                </button>
              ))}
            </div>

            {/* Accent toggle */}
            <div className="tab-bar" role="tablist" aria-label="Target accent">
              {(["GA", "RP"] as Accent[]).map((a) => (
                <button
                  key={a}
                  className="tab-btn press"
                  data-active={accent === a}
                  onClick={() => onAccentChange(a)}
                  title={ACCENT_LABELS[a]}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>
        </header>

        {/* Phrase progress (phrases mode only) */}
        {mode === "phrases" && (
          <div className="dim-track" style={{ height: 4 }}>
            <div
              className="dim-fill"
              style={{
                ["--pct" as string]: `${((phraseIdx + 1) / PHRASES.length) * 100}%`,
                ["--tone" as string]: "var(--accent)",
                ["--delay" as string]: "0ms",
              } as React.CSSProperties}
            />
          </div>
        )}

        {/* ── Phrase card ── */}
        <section
          className="card-paper"
          style={{ padding: "40px 32px", textAlign: "center" }}
        >
          {mode === "phrases" ? (
            <p
              key={phraseIdx}
              className="font-display phrase-mount"
              style={{
                fontSize: result ? 24 : 34,
                fontWeight: 600,
                color: "var(--ink)",
                lineHeight: 1.2,
                margin: "0 auto",
                maxWidth: 720,
                transition: "font-size 400ms var(--ease-paper)",
              }}
            >
              {activeText}
            </p>
          ) : (
            <textarea
              value={freeText}
              onChange={(e) => setFreeText(sanitiseFree(e.target.value))}
              disabled={isRecording || isProcessing}
              placeholder="Type any English sentence you want to practice…"
              rows={result ? 2 : 3}
              className="font-display phrase-mount"
              style={{
                fontSize: result ? 22 : 28,
                fontWeight: 600,
                color: "var(--ink)",
                lineHeight: 1.3,
                width: "100%",
                maxWidth: 720,
                background: "transparent",
                border: "none",
                outline: "none",
                resize: "none",
                textAlign: "center",
                padding: "8px 4px",
                margin: "0 auto",
                display: "block",
                transition: "font-size 400ms var(--ease-paper)",
              }}
              maxLength={MAX_FREE_LEN}
            />
          )}

          <div className="flex flex-wrap items-center justify-center" style={{ gap: 10, marginTop: 20 }}>
            <button
              className="btn-paper btn-ghost press"
              onClick={handlePlayNative}
              disabled={isPlayingNative || isRecording || isProcessing || !activeText}
              style={{ fontSize: 12, color: isPlayingNative ? "var(--accent)" : "var(--ink-3)" }}
            >
              <span aria-hidden style={{ fontSize: 10 }}>{isPlayingNative ? "♪" : "▶"}</span>
              {isPlayingNative ? "Playing…" : `Native ${accent}`}
              {isMockMode() && <span style={{ fontSize: 10, opacity: 0.5, marginLeft: 4 }}>browser</span>}
            </button>
            {voiceProfile && (
              <button
                className="btn-paper btn-ghost press"
                onClick={handleHearInVoice}
                disabled={hearInVoiceState !== "idle" || isRecording || isProcessing || !activeText}
                style={{
                  fontSize: 12,
                  color: hearInVoiceState === "playing" ? "var(--accent)" : "var(--ink-3)",
                }}
              >
                <span aria-hidden style={{ fontSize: 10 }}>
                  {hearInVoiceState === "playing" ? "♪" : hearInVoiceState === "loading" ? "…" : "▶"}
                </span>
                {hearInVoiceState === "playing"
                  ? "Your voice…"
                  : hearInVoiceState === "loading"
                  ? "Synthesising…"
                  : `Your voice · ${accent}`}
              </button>
            )}
            <Link
              href={`/studio?text=${encodeURIComponent(activeText)}`}
              onClick={() => tap()}
              className="btn-paper btn-ghost press"
              style={{ fontSize: 12, color: "var(--ink-4)", textDecoration: "none" }}
            >
              Open in Studio →
            </Link>
          </div>

          {/* Live word highlight when your-voice plays */}
          {hearInVoiceWords.length > 0 && hearInVoiceState !== "idle" && (
            <div
              className="card-paper-inset fade-pop"
              style={{ padding: "14px 18px", marginTop: 16, maxWidth: 640, width: "100%" }}
            >
              <p
                className="font-mono"
                style={{
                  fontSize: 10,
                  letterSpacing: "0.14em",
                  textTransform: "uppercase",
                  color: "var(--accent)",
                  marginBottom: 8,
                }}
              >
                Your voice · {accent}
              </p>
              <SpokenText
                words={hearInVoiceWords}
                audio={hearInVoiceRef.current}
                playing={hearInVoiceState === "playing"}
                size="md"
              />
            </div>
          )}
        </section>

        {/* ── Record zone ── */}
        <section className="flex flex-col items-center" style={{ gap: 14 }}>
          {!result && !isRecording && !isProcessing && mode === "free" && !canRecord && (
            <p
              className="rise"
              style={{ fontSize: 12, color: "var(--ink-4)" }}
            >
              {MIN_FREE_LEN}+ characters
            </p>
          )}
          {isProcessing && (
            <p style={{ fontSize: 13, color: "var(--ink-3)", fontStyle: "italic" }}>Analysing…</p>
          )}

          <RecordButton
            state={isRecording ? "recording" : isProcessing ? "processing" : "idle"}
            onRecord={canRecord ? handleRecord : () => {}}
            onStop={handleStop}
            getLevel={getLevel}
          />

          {error && (
            <p
              className="rounded-xl"
              style={{
                fontSize: 12,
                maxWidth: 360,
                background: "rgba(184, 82, 63, 0.08)",
                color: "var(--rose)",
                border: "1px solid rgba(184, 82, 63, 0.20)",
                padding: "10px 14px",
                textAlign: "center",
              }}
            >
              {error}
            </p>
          )}
        </section>

        {/* ── Result ── */}
        {result && (
          <section className="result-enter flex flex-col" style={{ gap: 24 }}>
            <div className="flex items-center justify-center">
              <Tabs items={tabs} active={resultTab} onChange={setResultTab} ariaLabel="Result view" />
            </div>

            <div
              className="card-paper"
              style={{ padding: "28px 28px 24px", minHeight: 320 }}
            >
              {resultTab === "overview" && (
                <div className="grid" style={{ gap: 28, gridTemplateColumns: "minmax(0, 1fr)" }}>
                  <ScoreHero overall={result.overall} verdict={verdictLabel(result.overall)} />
                  <ScoreBars scores={result.scores} overall={result.overall} />
                </div>
              )}

              {resultTab === "phonemes" && (
                <div className="flex flex-col" style={{ gap: 24 }}>
                  <PhonemeTimeline phonemes={result.phonemes} />
                  <PhonemeABDiff
                    phonemes={result.phonemes}
                    onPlayNative={playNativeFromPanel}
                    onPlayUser={playUserRecording}
                    hasUserAudio={!!userAudioUrl}
                  />
                </div>
              )}

              {resultTab === "prosody" && (
                <div className="flex flex-col" style={{ gap: 20 }}>
                  {result.pitch_contour ? (
                    <PitchContourOverlay
                      contour={result.pitch_contour}
                      onPlayNative={playNativeFromPanel}
                      onPlayUser={playUserRecording}
                      hasUserAudio={!!userAudioUrl}
                    />
                  ) : (
                    <p style={{ color: "var(--ink-3)", fontSize: 13 }}>
                      Pitch contour unavailable for this recording.
                    </p>
                  )}
                </div>
              )}

              {resultTab === "accent" && (
                <AccentConvertCard
                  userAudio={userAudioBlob}
                  accent={accent}
                  voiceProfile={voiceProfile}
                  onOpenEnrollment={() => setEnrollmentOpen(true)}
                />
              )}
            </div>

            <div className="flex flex-wrap" style={{ gap: 12, justifyContent: "center" }}>
              <button
                className="btn-paper press"
                onClick={() => {
                  tap();
                  setAppState({ phase: "idle" });
                  setError(null);
                }}
              >
                Try again
              </button>
              <button
                className="btn-paper btn-primary press"
                onClick={() => {
                  tap();
                  if (mode === "free") {
                    setFreeText("");
                    setAppState({ phase: "idle" });
                    setError(null);
                  } else {
                    setPhraseIdx((i) => (i + 1) % PHRASES.length);
                  }
                }}
              >
                {mode === "free" ? "Clear" : "Next phrase →"}
              </button>
            </div>
          </section>
        )}
      </div>

      <EnrollmentModal
        open={enrollmentOpen}
        onClose={() => setEnrollmentOpen(false)}
        onEnrolled={(profile) => setVoiceProfile(profile)}
      />
    </main>
  );
}

function ScoreHero({ overall, verdict }: { overall: number; verdict: string }) {
  const color =
    overall >= 80 ? "var(--jade)" : overall >= 65 ? "var(--accent)" : "var(--rose)";
  const animated = useCountUp(overall, 1100);
  const pct = animated / 100;
  const R = 42;
  const C = 2 * Math.PI * R;
  const dashOffset = C * (1 - pct);

  return (
    <div className="flex items-center" style={{ gap: 28 }}>
      <div
        style={{
          width: 108,
          height: 108,
          flexShrink: 0,
          position: "relative",
        }}
      >
        <svg width="108" height="108" viewBox="0 0 108 108" style={{ position: "absolute", inset: 0 }}>
          <circle cx="54" cy="54" r={R} fill={color} opacity="0.10" />
          <circle cx="54" cy="54" r={R} fill="none" stroke="var(--line)" strokeWidth={2.5} opacity="0.7" />
          <circle
            cx="54"
            cy="54"
            r={R}
            fill="none"
            stroke={color}
            strokeWidth={3.5}
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={dashOffset}
            transform="rotate(-90 54 54)"
          />
        </svg>
        <div
          className="absolute inset-0 flex flex-col items-center justify-center"
          style={{ pointerEvents: "none" }}
        >
          <span
            className="font-display"
            style={{
              fontSize: 36,
              fontWeight: 700,
              color,
              fontVariantNumeric: "tabular-nums",
              lineHeight: 1,
            }}
          >
            {Math.round(animated)}
          </span>
          <span
            className="font-mono"
            style={{
              fontSize: 9,
              fontWeight: 600,
              letterSpacing: "0.1em",
              color,
              textTransform: "uppercase",
              opacity: 0.7,
              marginTop: 4,
            }}
          >
            / 100
          </span>
        </div>
      </div>

      <div>
        <p
          className="font-display"
          style={{ fontSize: 28, fontWeight: 700, color: "var(--ink)", lineHeight: 1.1 }}
        >
          {verdict}
        </p>
      </div>
    </div>
  );
}
