"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Accent } from "@/lib/types";
import {
  fetchVoiceProfile,
  getOrCreateVoiceId,
  speakInVoice,
  type VoiceProfile,
  type WordTiming,
} from "@/lib/voiceProfile";
import { getProfile, setProfile } from "@/lib/store";
import { tap, confirm, release } from "@/lib/sounds";
import EnrollmentModal from "@/components/EnrollmentModal";
import SpokenText from "@/components/SpokenText";

const ACCENT_LABELS: Record<Accent, string> = {
  GA: "General American",
  RP: "Received Pronunciation",
};

const MAX_LEN = 400;
const MIN_LEN = 2;
const HISTORY_KEY = "pronounceai.studio.history.v1";
const MAX_HISTORY = 6;

type ClipState = "idle" | "loading" | "ready" | "error";

type HistoryEntry = { text: string; accent: Accent };

function readHistory(): HistoryEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function writeHistory(entries: HistoryEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
  } catch {}
}

type Props = {
  /** Initial text used when arriving from /practice with a phrase loaded. */
  initialText?: string;
  /** Compact = embedded inside another card (no outer card frame). */
  compact?: boolean;
};

export default function VoiceStudio({ initialText = "", compact = false }: Props) {
  const [text, setText] = useState(initialText);
  const [accent, setAccent] = useState<Accent>("GA");
  const [profile, setProfileState] = useState<VoiceProfile | null>(null);
  const [state, setState] = useState<ClipState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [words, setWords] = useState<WordTiming[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    setAccent(getProfile().targetAccent);
    setHistory(readHistory());
    const id = getOrCreateVoiceId();
    if (id) fetchVoiceProfile(id).then(setProfileState).catch(() => setProfileState(null));
  }, []);

  useEffect(() => {
    if (initialText) setText(initialText);
  }, [initialText]);

  useEffect(() => () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
  }, [audioUrl]);

  const canSpeak = profile !== null && text.trim().length >= MIN_LEN;

  const onAccentChange = useCallback((a: Accent) => {
    tap();
    setAccent(a);
    setProfile({ targetAccent: a });
    // accent change invalidates the cached clip
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    setState("idle");
  }, [audioUrl]);

  const onSpeak = useCallback(async () => {
    if (!canSpeak || state === "loading") return;
    tap();
    setState("loading");
    setErrorMsg(null);
    try {
      const id = getOrCreateVoiceId();
      const clip = await speakInVoice(id, text.trim(), accent);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      const url = URL.createObjectURL(clip.audio);
      setAudioUrl(url);
      setWords(clip.words);
      setState("ready");
      confirm();

      if (!audioRef.current) audioRef.current = new Audio();
      audioRef.current.src = url;
      audioRef.current.onended = () => setIsPlaying(false);
      audioRef.current.onerror = () => setIsPlaying(false);
      setIsPlaying(true);
      audioRef.current.play().catch(() => setIsPlaying(false));

      const entry: HistoryEntry = { text: text.trim(), accent };
      const next = [entry, ...history.filter((h) => !(h.text === entry.text && h.accent === entry.accent))].slice(0, MAX_HISTORY);
      setHistory(next);
      writeHistory(next);
    } catch (e) {
      setErrorMsg((e as Error).message ?? "Synthesis failed");
      setState("error");
    }
  }, [accent, audioUrl, canSpeak, history, state, text]);

  const onReplay = useCallback(() => {
    if (!audioUrl) return;
    tap();
    if (!audioRef.current) audioRef.current = new Audio();
    audioRef.current.src = audioUrl;
    audioRef.current.currentTime = 0;
    audioRef.current.onended = () => setIsPlaying(false);
    audioRef.current.onerror = () => setIsPlaying(false);
    setIsPlaying(true);
    audioRef.current.play().catch(() => setIsPlaying(false));
  }, [audioUrl]);

  const onStop = useCallback(() => {
    if (audioRef.current && isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
      release();
    }
  }, [isPlaying]);

  const onHistoryClick = useCallback((h: HistoryEntry) => {
    tap();
    setText(h.text);
    setAccent(h.accent);
    setState("idle");
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
  }, [audioUrl]);

  const onClearHistory = useCallback(() => {
    tap();
    setHistory([]);
    writeHistory([]);
  }, []);

  const Outer = compact ? "div" : "div";
  const outerClass = compact ? "" : "card-paper";
  const outerStyle: React.CSSProperties = compact ? {} : { padding: "24px 24px 22px" };

  // ── No-enrollment empty state ───────────────────────────────────────
  if (profile === null) {
    return (
      <Outer className={outerClass} style={outerStyle}>
        <div style={{ textAlign: compact ? "left" : "center", padding: compact ? 0 : "8px 0" }}>
          <p
            className="font-mono"
            style={{
              fontSize: 11,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--ink-4)",
              marginBottom: 8,
            }}
          >
            Studio · not enrolled
          </p>
          <h3
            className="font-display"
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: "var(--ink)",
              letterSpacing: 0,
              marginBottom: 10,
              lineHeight: 1.2,
            }}
          >
            Lend your voice once, use it forever.
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-3)", lineHeight: 1.55, marginBottom: 18, maxWidth: 460 }}>
            Read one sentence (~10s). After that, any text you type can be spoken in your voice in any target accent. No need to record again.
          </p>
          <button
            className="btn-paper btn-primary press"
            onClick={() => {
              tap();
              setEnrollOpen(true);
            }}
            style={{ fontSize: 13 }}
          >
            Set up voice profile
          </button>
        </div>
        <EnrollmentModal
          open={enrollOpen}
          onClose={() => setEnrollOpen(false)}
          onEnrolled={(p) => setProfileState(p)}
        />
      </Outer>
    );
  }

  // ── Enrolled studio ─────────────────────────────────────────────────
  return (
    <Outer className={outerClass} style={outerStyle}>
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between" style={{ gap: 10, marginBottom: 14 }}>
        <div>
          <p
            className="font-mono"
            style={{
              fontSize: 10,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--ink-4)",
            }}
          >
            Studio · {profile.takes?.length ?? 1} take{(profile.takes?.length ?? 1) === 1 ? "" : "s"} · {profile.bundle_duration_s?.toFixed(1) ?? profile.duration_s.toFixed(1)}s ref
          </p>
          <p
            className="font-display"
            style={{ fontSize: 18, fontWeight: 700, color: "var(--ink)", letterSpacing: 0, marginTop: 2 }}
          >
            Your voice, any accent, any text.
          </p>
        </div>
        <div className="tab-bar" role="tablist" aria-label="Accent">
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

      {/* Text area */}
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value.slice(0, MAX_LEN));
          if (state === "ready") setState("idle");
        }}
        placeholder="Type anything you want to hear in your voice..."
        rows={3}
        className="font-display"
        style={{
          width: "100%",
          padding: "14px 16px",
          borderRadius: 12,
          border: "1px solid var(--line)",
          background: "var(--paper-2)",
          color: "var(--ink)",
          fontSize: 17,
          fontWeight: 500,
          letterSpacing: 0,
          lineHeight: 1.4,
          outline: "none",
          resize: "vertical",
          minHeight: 84,
          boxShadow: "var(--shadow-inset)",
        }}
        maxLength={MAX_LEN}
      />

      {/* Meta row */}
      <div className="flex items-center justify-between" style={{ marginTop: 8, fontSize: 11 }}>
        <span className="font-mono" style={{ color: "var(--ink-4)", letterSpacing: 0 }}>
          {text.length}/{MAX_LEN}
        </span>
        <span className="font-mono" style={{ color: "var(--ink-4)", letterSpacing: 0 }}>
          target: {ACCENT_LABELS[accent]}
        </span>
      </div>

      {/* Live transcript with word-by-word highlight */}
      {(state === "ready" || isPlaying) && words.length > 0 && (
        <div
          className="card-paper-inset"
          style={{ padding: "16px 18px", marginTop: 16 }}
        >
          <p
            className="font-mono"
            style={{
              fontSize: 10,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: isPlaying ? "var(--accent)" : "var(--ink-4)",
              marginBottom: 10,
              transition: "color 200ms var(--ease-out)",
            }}
          >
            {isPlaying ? "Speaking" : "Last clip"}
            <span style={{ marginLeft: 8, opacity: 0.7 }}>{words.length} words</span>
          </p>
          <SpokenText words={words} audio={audioRef.current} playing={isPlaying} size="md" />
        </div>
      )}

      {/* Primary action */}
      <div className="flex" style={{ gap: 10, marginTop: 16 }}>
        {state === "ready" && audioUrl ? (
          <>
            <button
              className="btn-paper btn-primary press"
              onClick={isPlaying ? onStop : onReplay}
              style={{ fontSize: 13, flex: 1 }}
            >
              <PlayStateIcon active={isPlaying} />
              {isPlaying ? "Stop" : "Play"}
            </button>
            <button
              className="btn-paper press"
              onClick={onSpeak}
              disabled={!canSpeak}
              style={{ fontSize: 13 }}
            >
              Re-render
            </button>
          </>
        ) : (
          <button
            className="btn-paper btn-primary press"
            onClick={onSpeak}
            disabled={!canSpeak || state === "loading"}
            style={{ fontSize: 13, flex: 1 }}
          >
            {state === "loading" ? (
              <>
                <span
                  className="spin"
                  aria-hidden
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    border: "1.5px solid rgba(255,250,240,0.4)",
                    borderTopColor: "#fffaf0",
                    display: "inline-block",
                  }}
                />
                Synthesising...
              </>
            ) : (
              <>
                <WaveIcon />
                Speak it
              </>
            )}
          </button>
        )}
      </div>

      {/* Error */}
      {state === "error" && errorMsg && (
        <p
          style={{
            marginTop: 12,
            fontSize: 12,
            background: "rgba(184, 82, 63, 0.08)",
            color: "var(--rose)",
            border: "1px solid rgba(184, 82, 63, 0.18)",
            padding: "8px 12px",
            borderRadius: 10,
          }}
        >
          {errorMsg}
        </p>
      )}

      {/* History */}
      {history.length > 0 && (
        <div style={{ marginTop: 22 }}>
          <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
            <p
              className="font-mono"
              style={{
                fontSize: 10,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "var(--ink-4)",
              }}
            >
              Recent
            </p>
            <button
              className="press"
              onClick={onClearHistory}
              style={{ fontSize: 10, color: "var(--ink-4)", background: "none", border: "none", cursor: "pointer" }}
            >
              clear
            </button>
          </div>
          <div className="flex flex-col" style={{ gap: 6 }}>
            {history.map((h, i) => (
              <button
                key={`${h.text}-${h.accent}-${i}`}
                className="press"
                onClick={() => onHistoryClick(h)}
                style={{
                  padding: "10px 14px",
                  borderRadius: 10,
                  border: "1px solid var(--line)",
                  background: "var(--paper)",
                  color: "var(--ink-2)",
                  textAlign: "left",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  fontSize: 13,
                }}
              >
                <span className="tag tag-accent" style={{ flexShrink: 0 }}>{h.accent}</span>
                <span
                  style={{
                    flex: 1,
                    minWidth: 0,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {h.text}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </Outer>
  );
}

function PlayStateIcon({ active }: { active: boolean }) {
  if (active) {
    return (
      <span
        aria-hidden
        style={{
          width: 10,
          height: 10,
          borderRadius: 2,
          background: "currentColor",
          display: "inline-block",
        }}
      />
    );
  }
  return (
    <span
      aria-hidden
      style={{
        width: 0,
        height: 0,
        borderLeft: "8px solid currentColor",
        borderTop: "5px solid transparent",
        borderBottom: "5px solid transparent",
        display: "inline-block",
      }}
    />
  );
}

function WaveIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden>
      <path d="M2 9c1.2 0 1.2-5 2.4-5s1.2 8 2.4 8S8 6 9.2 6s1.2 4 2.4 4S12.8 7 14 7" />
    </svg>
  );
}
