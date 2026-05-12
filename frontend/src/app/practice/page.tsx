"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { Accent, AssessmentResult, PhonemeResult, Scores } from "@/lib/types";
import { PHRASES, CATEGORY_LABELS } from "@/lib/phrases";
import { createRecorder, type Recorder } from "@/lib/recorder";
import {
  scoreRecording,
  playNativeAudio,
  prefetchNativeAudio,
  prewarmPhrase,
  isMockMode,
} from "@/lib/api";
import { useCountUp } from "@/lib/useCountUp";
import { appendSession, getProfile, setProfile, subscribeStorage } from "@/lib/store";
import { tap, confirm, release } from "@/lib/sounds";
import PhonemeTimeline from "@/components/PhonemeTimeline";
import ScoreBars from "@/components/ScoreBars";
import PitchContourOverlay from "@/components/PitchContourOverlay";
import PhonemeABDiff from "@/components/PhonemeABDiff";

const ACCENT_LABELS: Record<Accent, string> = {
  GA: "General American",
  RP: "Received Pronunciation",
};

const MAX_TEXT = 180;
const MIN_TEXT = 3;

type CapturePhase = "idle" | "recording" | "processing";
type SessionMode = "phrases" | "free";

function sanitiseText(text: string): string {
  return text.replace(/[^\x20-\x7E]/g, "").slice(0, MAX_TEXT);
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
    "stress-timing": "stress and timing",
    "flap-t": "flap T",
    "consonant-cluster": "consonant clusters",
    "intonation-rise": "rising intonation",
    "falling-intonation": "falling intonation",
    "emphatic-stress": "emphatic stress",
    "polite-intonation": "polite intonation",
    "narrative-pace": "pace and rhythm",
  };
  return map[focus] ?? focus.replace(/-/g, " ");
}

function weakestPhoneme(phonemes: PhonemeResult[]): PhonemeResult | null {
  if (phonemes.length === 0) return null;
  const errors = phonemes.filter((p) => !p.correct);
  const pool = errors.length ? errors : phonemes;
  return pool.reduce((worst, p) => (p.gop < worst.gop ? p : worst), pool[0]);
}

function lowestDimension(scores: Scores): [keyof Scores, number] {
  return (Object.entries(scores) as Array<[keyof Scores, number]>).sort((a, b) => a[1] - b[1])[0];
}

function dimensionLabel(key: keyof Scores): string {
  return {
    phoneme_accuracy: "sound placement",
    intonation: "pitch movement",
    stress_rhythm: "stress rhythm",
    vowel_quality: "vowel shape",
  }[key];
}

function resultSentence(result: AssessmentResult, weak: PhonemeResult | null): string {
  const [key, value] = lowestDimension(result.scores);
  if (weak && key !== "intonation" && key !== "stress_rhythm") {
    const heard = weak.substitution ? ` It sounded closer to ${weak.substitution.split("→")[0]}.` : "";
    return `Start with /${weak.expected}/.${heard}`;
  }
  return `Start with ${dimensionLabel(key)}. It is the lowest signal at ${Math.round(value)}%.`;
}

function stateCopy(phase: CapturePhase, hasResult: boolean): { label: string; title: string; copy: string } {
  if (phase === "recording") {
    return {
      label: "Listening",
      title: "Recording your take",
      copy: "Finish the sentence, then stop. The notebook will score the same line.",
    };
  }
  if (phase === "processing") {
    return {
      label: "Analyzing",
      title: "Reading the acoustics",
      copy: "Aligning phonemes, pitch, rhythm, and transcript into one correction.",
    };
  }
  if (hasResult) {
    return {
      label: "Reviewed",
      title: "One correction is ready",
      copy: "Try the same line again, or open the acoustic notes if you want the full trace.",
    };
  }
  return {
    label: "Ready",
    title: "Work on this line",
    copy: "Hear the target if useful, then record one natural take.",
  };
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
  const initialPhrase = PHRASES[0];
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [selectedPhraseId, setSelectedPhraseId] = useState<string | null>(initialPhrase.id);
  const [text, setText] = useState(initialPhrase.text);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sourceQuery, setSourceQuery] = useState("");
  const [accent, setAccent] = useState<Accent>("GA");
  const [phase, setPhase] = useState<CapturePhase>("idle");
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPlayingTarget, setIsPlayingTarget] = useState(false);
  const [userAudioUrl, setUserAudioUrl] = useState<string | null>(null);

  const recorderRef = useRef<Recorder | null>(null);
  const userAudioRef = useRef<HTMLAudioElement | null>(null);
  const userAudioUrlRef = useRef<string | null>(null);

  const cleanText = text.trim();
  const selectedPhrase = selectedPhraseId ? PHRASES.find((p) => p.id === selectedPhraseId) ?? null : null;
  const mode: SessionMode = selectedPhrase && selectedPhrase.text === cleanText ? "phrases" : "free";
  const canRecord = cleanText.length >= MIN_TEXT;
  const weak = useMemo(() => (result ? weakestPhoneme(result.phonemes) : null), [result]);
  const lowest = useMemo(() => (result ? lowestDimension(result.scores) : null), [result]);
  const sessionState = stateCopy(phase, !!result);
  const progressPct = ((phraseIdx + 1) / PHRASES.length) * 100;

  const clearRecording = useCallback(() => {
    if (userAudioUrlRef.current) {
      URL.revokeObjectURL(userAudioUrlRef.current);
      userAudioUrlRef.current = null;
    }
    setUserAudioUrl(null);
  }, []);

  useEffect(() => {
    const profile = getProfile();
    setAccent(profile.targetAccent);
    return subscribeStorage(() => setAccent(getProfile().targetAccent));
  }, []);

  useEffect(() => {
    const current = window.setTimeout(() => {
      prewarmPhrase(cleanText, accent);
      prefetchNativeAudio(cleanText, accent);
    }, mode === "phrases" ? 80 : 420);
    const next = PHRASES[(phraseIdx + 1) % PHRASES.length];
    const nextTimer = next ? window.setTimeout(() => {
      prewarmPhrase(next.text, accent);
      prefetchNativeAudio(next.text, accent);
    }, 900) : null;
    return () => {
      window.clearTimeout(current);
      if (nextTimer !== null) window.clearTimeout(nextTimer);
    };
  }, [accent, cleanText, mode, phraseIdx]);

  useEffect(() => {
    const id = searchParams.get("phrase");
    if (!id) return;
    const idx = PHRASES.findIndex((p) => p.id === id);
    if (idx >= 0) {
      const phrase = PHRASES[idx];
      setPhraseIdx(idx);
      setSelectedPhraseId(phrase.id);
      setText(phrase.text);
      setResult(null);
      setSourceOpen(false);
      clearRecording();
    }
  }, [searchParams, clearRecording]);

  useEffect(() => {
    return () => {
      recorderRef.current?.dispose();
      if (userAudioUrlRef.current) URL.revokeObjectURL(userAudioUrlRef.current);
    };
  }, []);

  const sourceList = useMemo(() => {
    const q = sourceQuery.trim().toLowerCase();
    if (q) {
      return PHRASES.filter(
        (phrase) =>
          phrase.text.toLowerCase().includes(q) ||
          phrase.focus.toLowerCase().includes(q) ||
          CATEGORY_LABELS[phrase.category].toLowerCase().includes(q)
      ).slice(0, 10);
    }
    return Array.from({ length: 8 }, (_, offset) => PHRASES[(phraseIdx + offset) % PHRASES.length]);
  }, [phraseIdx, sourceQuery]);

  const applyPhrase = useCallback(
    (id: string) => {
      const idx = PHRASES.findIndex((p) => p.id === id);
      if (idx < 0) return;
      const phrase = PHRASES[idx];
      tap();
      setPhraseIdx(idx);
      setSelectedPhraseId(phrase.id);
      setText(phrase.text);
      setResult(null);
      setError(null);
      setSourceOpen(false);
      clearRecording();
    },
    [clearRecording]
  );

  const nextPhrase = useCallback(() => {
    const next = PHRASES[(phraseIdx + 1) % PHRASES.length];
    applyPhrase(next.id);
  }, [applyPhrase, phraseIdx]);

  const handleTextChange = useCallback(
    (value: string) => {
      setText(sanitiseText(value));
      setSelectedPhraseId(null);
      setResult(null);
      setError(null);
      clearRecording();
    },
    [clearRecording]
  );

  const toggleAccent = useCallback(() => {
    const next = accent === "GA" ? "RP" : "GA";
    tap();
    setAccent(next);
    setProfile({ targetAccent: next });
    setResult(null);
    clearRecording();
  }, [accent, clearRecording]);

  async function handlePlayTarget() {
    if (isPlayingTarget || !cleanText) return;
    tap();
    setIsPlayingTarget(true);
    await playNativeAudio(cleanText, accent);
    setIsPlayingTarget(false);
  }

  async function handleRecord() {
    if (!canRecord) {
      setError(`Write at least ${MIN_TEXT} characters before recording.`);
      return;
    }
    tap();
    setError(null);
    setResult(null);
    clearRecording();
    setPhase("recording");
    try {
      if (!recorderRef.current) recorderRef.current = await createRecorder();
      await recorderRef.current.start();
    } catch (e) {
      setError((e as Error).message ?? "Could not access the microphone.");
      setPhase("idle");
    }
  }

  async function handleStop() {
    if (!recorderRef.current) return;
    release();
    setPhase("processing");
    try {
      const blob = await recorderRef.current.stop();
      const url = URL.createObjectURL(blob);
      userAudioUrlRef.current = url;
      setUserAudioUrl(url);
      const profile = getProfile();
      const assessment = await scoreRecording(blob, cleanText, accent, profile.l1 ?? "unknown");
      setResult(assessment);
      appendSession(assessment, { phrase: cleanText, mode, accent });
      setPhase("idle");
      confirm();
    } catch (e) {
      setError((e as Error).message ?? "Scoring failed. Try one more recording.");
      setPhase("idle");
    }
  }

  async function handlePrimaryCapture() {
    if (phase === "recording") {
      await handleStop();
      return;
    }
    if (phase !== "processing") {
      await handleRecord();
    }
  }

  const playTargetFromPanel = useCallback(() => playNativeAudio(cleanText, accent), [accent, cleanText]);

  const playUserRecording = useCallback((): Promise<void> => {
    if (!userAudioUrl) return Promise.resolve();
    return new Promise((resolve) => {
      if (!userAudioRef.current) userAudioRef.current = new Audio();
      const audio = userAudioRef.current;
      audio.src = userAudioUrl;
      audio.currentTime = 0;
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
      audio.play().catch(() => resolve());
    });
  }, [userAudioUrl]);

  return (
    <main className="notebook-session">
      <section className="session-notebook" aria-label="Practice session">
        <header className="workspace-bar">
          <div>
            <p className="eyebrow">Practice</p>
            <h1>{sessionState.label}</h1>
          </div>
          <div className="workspace-status">
            <span>{isMockMode() ? "Demo scorer" : "Live scorer"}</span>
            <button className="status-button press" onClick={toggleAccent} disabled={phase !== "idle"}>
              {ACCENT_LABELS[accent]}
            </button>
          </div>
        </header>

        <div className="notebook-thread">
          <article className="coach-message">
            <span className="coach-avatar" aria-hidden>
              AI
            </span>
            <div>
              <p className="eyebrow">Coach</p>
              <h2>{sessionState.title}</h2>
              <p>{sessionState.copy}</p>
            </div>
          </article>

          <article className="line-note">
            <header className="line-note-header">
              <div>
                <p className="eyebrow">Current line</p>
                <span>
                  {selectedPhrase
                    ? `${CATEGORY_LABELS[selectedPhrase.category]} · ${focusLabel(selectedPhrase.focus)}`
                    : `${cleanText.length}/${MAX_TEXT} characters`}
                </span>
              </div>
              <button
                className="notebook-link press"
                onClick={() => setSourceOpen((open) => !open)}
                disabled={phase !== "idle"}
                aria-expanded={sourceOpen}
              >
                {sourceOpen ? "Done" : "Change"}
              </button>
            </header>

            <textarea
              value={text}
              onChange={(e) => handleTextChange(e.target.value)}
              disabled={phase !== "idle"}
              className="notebook-line"
              rows={2}
              aria-label="Practice line"
              placeholder="Write a short English line."
            />

            {selectedPhrase && (
              <div className="notebook-progress" aria-hidden>
                <span style={{ width: `${progressPct}%` }} />
              </div>
            )}

            <footer className="line-note-footer">
              <span>{mode === "free" ? "Custom line" : `Line ${phraseIdx + 1} of ${PHRASES.length}`}</span>
              <span>{ACCENT_LABELS[accent]}</span>
            </footer>

            {sourceOpen && (
              <div className="notebook-source" aria-label="Phrase source">
                <input
                  value={sourceQuery}
                  onChange={(e) => setSourceQuery(e.target.value)}
                  className="notebook-source-search"
                  placeholder="Search sound or phrase"
                  aria-label="Search phrases"
                />
                <div>
                  {sourceList.map((phrase) => (
                    <button
                      key={phrase.id}
                      className="notebook-source-row press"
                      onClick={() => applyPhrase(phrase.id)}
                      aria-current={phrase.id === selectedPhraseId ? "true" : undefined}
                    >
                      <span>{phrase.text}</span>
                      <small>{focusLabel(phrase.focus)}</small>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </article>

          {error && (
            <p className="session-error" role="alert">
              {error}
            </p>
          )}

          {result && (
            <Review
              result={result}
              weak={weak}
              lowest={lowest}
              accent={accent}
              userAudioUrl={userAudioUrl}
              onPlayTarget={playTargetFromPanel}
              onPlayUser={playUserRecording}
              onTryAgain={() => {
                tap();
                setResult(null);
                clearRecording();
              }}
              onNextLine={nextPhrase}
            />
          )}
        </div>

        <footer className="capture-composer" data-state={phase}>
          <div className="composer-state">
            <span className="state-dot" aria-hidden />
            <div>
              <strong>{sessionState.label}</strong>
              <p>{phase === "idle" && result ? "Record again when you are ready." : sessionState.copy}</p>
            </div>
          </div>
          <div className="composer-actions">
            <button
              className="composer-secondary press"
              onClick={handlePlayTarget}
              disabled={!cleanText || isPlayingTarget || phase !== "idle"}
            >
              {isPlayingTarget ? "Playing" : "Hear target"}
            </button>
            {result && (
              <button className="composer-secondary press" onClick={nextPhrase} disabled={phase !== "idle"}>
                Next line
              </button>
            )}
            <button
              className="primary-capture press"
              onClick={handlePrimaryCapture}
              disabled={phase === "processing" || !canRecord}
            >
              {phase === "processing" ? (
                <Spinner />
              ) : phase === "recording" ? (
                <StopIcon />
              ) : (
                <MicIcon />
              )}
              <span>
                {phase === "recording"
                  ? "Stop and score"
                  : phase === "processing"
                  ? "Analyzing"
                  : result
                  ? "Record again"
                  : "Record take"}
              </span>
            </button>
          </div>
        </footer>
      </section>

    </main>
  );
}

function Review({
  result,
  weak,
  lowest,
  accent,
  userAudioUrl,
  onPlayTarget,
  onPlayUser,
  onTryAgain,
  onNextLine,
}: {
  result: AssessmentResult;
  weak: PhonemeResult | null;
  lowest: [keyof Scores, number] | null;
  accent: Accent;
  userAudioUrl: string | null;
  onPlayTarget: () => Promise<void>;
  onPlayUser: () => Promise<void> | void;
  onTryAgain: () => void;
  onNextLine: () => void;
}) {
  const animated = useCountUp(result.overall, 700);
  const [lowestKey, lowestValue] = lowest ?? ["phoneme_accuracy", result.scores.phoneme_accuracy];

  return (
    <section className="review-message" aria-label="Session review">
      <article className="coach-message result-message">
        <span className="coach-avatar" aria-hidden>
          {Math.round(animated)}
        </span>
        <div>
          <p className="eyebrow">Coach response</p>
          <h2>{resultSentence(result, weak)}</h2>
          <p>
            Lowest signal: {dimensionLabel(lowestKey)} at {Math.round(lowestValue)}%.
            {weak ? ` Focus on /${weak.expected}/ before chasing the total score.` : ""}
          </p>
          {result.feedback.length > 0 && (
            <ul
              aria-label="Coaching tips"
              style={{
                display: "grid",
                gap: 8,
                marginTop: 14,
                marginBottom: 4,
                padding: 0,
                listStyle: "none",
              }}
            >
              {result.feedback.slice(0, 3).map((tip, index) => (
                <li
                  key={`${tip.text}-${index}`}
                  style={{
                    padding: "10px 12px",
                    borderRadius: 8,
                    background: "var(--paper-2)",
                    border: "1px solid var(--line)",
                    color: "var(--ink-2)",
                    fontSize: 13,
                    lineHeight: 1.45,
                  }}
                >
                  {tip.text}
                </li>
              ))}
            </ul>
          )}
          <div className="review-actions">
            <button className="btn-paper btn-primary press" onClick={onTryAgain}>
              Try same line
            </button>
            <button className="btn-paper press" onClick={onNextLine}>
              Next line
            </button>
            {userAudioUrl && (
              <button className="btn-paper press" onClick={() => onPlayUser()}>
                Play your take
              </button>
            )}
          </div>
        </div>
      </article>

      <details className="analysis-fold">
        <summary>
          <span>Open acoustic notes</span>
          <small>scores, phonemes, pitch</small>
        </summary>
        <div className="analysis-grid">
          <aside>
            <ScoreBars scores={result.scores} overall={result.overall} />
            <SessionData result={result} accent={accent} />
          </aside>
          <div className="analysis-main">
            <PhonemeTimeline phonemes={result.phonemes} />
            <PhonemeABDiff
              phonemes={result.phonemes}
              onPlayNative={onPlayTarget}
              onPlayUser={onPlayUser}
              hasUserAudio={!!userAudioUrl}
            />
            {result.pitch_contour && (
              <PitchContourOverlay
                contour={result.pitch_contour}
                onPlayNative={onPlayTarget}
                onPlayUser={onPlayUser}
                hasUserAudio={!!userAudioUrl}
              />
            )}
          </div>
        </div>
      </details>
    </section>
  );
}

function SessionData({ result, accent }: { result: AssessmentResult; accent: Accent }) {
  const wer = typeof result.wer === "number" ? `${Math.round(result.wer * 100)}%` : "not reported";
  const elapsed = result.debug?.elapsed_ms ? `${result.debug.elapsed_ms}ms` : isMockMode() ? "demo" : "live";
  return (
    <dl className="session-data">
      <div>
        <dt>Target</dt>
        <dd>{ACCENT_LABELS[accent]}</dd>
      </div>
      <div>
        <dt>Phonemes</dt>
        <dd>{result.phonemes.length}</dd>
      </div>
      <div>
        <dt>WER</dt>
        <dd>{wer}</dd>
      </div>
      <div>
        <dt>Latency</dt>
        <dd>{elapsed}</dd>
      </div>
      {result.transcript?.text && (
        <div>
          <dt>Transcript</dt>
          <dd>{result.transcript.text}</dd>
        </div>
      )}
    </dl>
  );
}

function MicIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <path d="M12 19v3" />
      <path d="M8 22h8" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <rect x="5" y="5" width="14" height="14" rx="3" />
    </svg>
  );
}

function Spinner() {
  return (
    <span
      className="spin"
      aria-hidden
      style={{
        width: 16,
        height: 16,
        borderRadius: "50%",
        border: "2px solid currentColor",
        borderTopColor: "transparent",
      }}
    />
  );
}
