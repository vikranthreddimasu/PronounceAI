"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Accent } from "@/lib/types";
import {
  chooseEnrollmentPrompts,
  precomposeVoice,
  refreshVoiceSession,
  speakInVoice,
  type EnrollmentPrompt,
  type VoiceRenderMode,
  type WordTiming,
} from "@/lib/voiceProfile";
import { useVoiceSession } from "@/lib/useVoiceSession";
import { getProfile, setProfile } from "@/lib/store";
import { tap, confirm, release } from "@/lib/sounds";
import EnrollmentModal from "@/components/EnrollmentModal";
import SpokenText from "@/components/SpokenText";

const ACCENT_LABELS: Record<Accent, string> = {
  GA: "American",
  RP: "British",
};

const ACCENT_DESCRIPTIONS: Record<Accent, string> = {
  GA: "General American",
  RP: "Received Pronunciation",
};

const RENDER_MODE_LABELS: Record<VoiceRenderMode, string> = {
  target_accent: "Keep chosen accent",
  natural: "Sound like my recording",
};

const MAX_LEN = 400;
const MIN_LEN = 2;
const HISTORY_KEY = "pronounceai.studio.history.v1";
const MAX_HISTORY = 6;

type ClipState = "idle" | "loading" | "ready" | "error";
type HistoryEntry = { text: string; accent: Accent; renderMode?: VoiceRenderMode };

type Props = {
  initialText?: string;
  compact?: boolean;
};

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

export default function VoiceStudio({ initialText = "", compact = false }: Props) {
  const [text, setText] = useState(initialText);
  const [accent, setAccent] = useState<Accent>("GA");
  const [renderMode, setRenderMode] = useState<VoiceRenderMode>("target_accent");
  const [state, setState] = useState<ClipState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [words, setWords] = useState<WordTiming[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [enrollPrompts, setEnrollPrompts] = useState<EnrollmentPrompt[] | undefined>(undefined);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const voiceSession = useVoiceSession();
  const profile = voiceSession.profile;
  const trimmedText = text.trim();

  useEffect(() => {
    setAccent(getProfile().targetAccent);
    setHistory(readHistory());
  }, []);

  useEffect(() => {
    if (initialText) setText(initialText);
  }, [initialText]);

  useEffect(() => {
    if (!profile || trimmedText.length < MIN_LEN) return;
    const timer = window.setTimeout(() => {
      precomposeVoice(profile.user_id, trimmedText, accent, profile.revision, renderMode);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [accent, profile, renderMode, trimmedText]);

  useEffect(() => () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
  }, [audioUrl]);

  const canRender = voiceSession.status === "ready" && profile !== null && trimmedText.length >= MIN_LEN;
  const voiceReady = voiceSession.status === "ready" && profile !== null;

  const clearClip = useCallback(() => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(null);
    setWords([]);
    setIsPlaying(false);
    setState("idle");
  }, [audioUrl]);

  const openEnrollment = useCallback(() => {
    tap();
    setEnrollPrompts(chooseEnrollmentPrompts(profile));
    setEnrollOpen(true);
  }, [profile]);

  const onAccentChange = useCallback((a: Accent) => {
    tap();
    setAccent(a);
    setProfile({ targetAccent: a });
    clearClip();
  }, [clearClip]);

  const onRenderModeChange = useCallback((mode: VoiceRenderMode) => {
    tap();
    setRenderMode(mode);
    clearClip();
  }, [clearClip]);

  const onTextChange = useCallback((value: string) => {
    setText(value.slice(0, MAX_LEN));
    if (state !== "idle") clearClip();
  }, [clearClip, state]);

  const onSpeak = useCallback(async () => {
    if (state === "loading" || trimmedText.length < MIN_LEN) return;
    if (!profile) {
      openEnrollment();
      return;
    }
    tap();
    setState("loading");
    setErrorMsg(null);
    try {
      const clip = await speakInVoice(profile.user_id, trimmedText, accent, profile.revision, renderMode);
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

      const entry: HistoryEntry = { text: trimmedText, accent, renderMode };
      const next = [
        entry,
        ...history.filter(
          (h) => !(h.text === entry.text && h.accent === entry.accent && (h.renderMode ?? "target_accent") === entry.renderMode)
        ),
      ].slice(0, MAX_HISTORY);
      setHistory(next);
      writeHistory(next);
    } catch (e) {
      setErrorMsg((e as Error).message ?? "Voice rendering failed.");
      setState("error");
    }
  }, [accent, audioUrl, history, openEnrollment, profile, renderMode, state, trimmedText]);

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
    setRenderMode(h.renderMode ?? "target_accent");
    clearClip();
  }, [clearClip]);

  const onClearHistory = useCallback(() => {
    tap();
    setHistory([]);
    writeHistory([]);
  }, []);

  const primaryLabel = (() => {
    if (state === "loading") return "Generating voice";
    if (voiceSession.status === "loading") return "Checking voice";
    if (voiceSession.status === "error") return "Voice unavailable";
    if (!profile) return "Record voice first";
    if (state === "ready") return "Generate again";
    return "Generate voice";
  })();

  return (
    <section className={compact ? "voice-lab voice-lab-compact" : "voice-lab"}>
      {!compact && (
        <header className="voice-lab-hero">
          <div>
            <p className="eyebrow">Voice Lab</p>
            <h1>Hear your voice in any accent.</h1>
            <p>
              Choose an accent, write any English text, and render it locally with your saved voice profile.
            </p>
          </div>
          <ProfileButton
            status={voiceSession.status}
            ready={voiceReady}
            takes={profile?.takes.length ?? 0}
            onClick={voiceSession.status === "error" ? () => refreshVoiceSession({ force: true }) : openEnrollment}
          />
        </header>
      )}

      <div className="voice-lab-panel">
        <div className="voice-lab-topline">
          <div>
            <label className="voice-lab-label" htmlFor="voice-lab-text">
              Text
            </label>
            <p>{voiceReady ? "Your voice profile is ready." : "Record your voice once before generating audio."}</p>
          </div>
          {compact && (
            <ProfileButton
              status={voiceSession.status}
              ready={voiceReady}
              takes={profile?.takes.length ?? 0}
              onClick={voiceSession.status === "error" ? () => refreshVoiceSession({ force: true }) : openEnrollment}
            />
          )}
        </div>

        <textarea
          id="voice-lab-text"
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          placeholder="Write what you want your voice to say..."
          rows={3}
          className="voice-lab-input"
          maxLength={MAX_LEN}
        />

        <div className="voice-lab-controls" aria-label="Voice lab controls">
          <div className="accent-choice" role="radiogroup" aria-label="Accent">
            {(["GA", "RP"] as Accent[]).map((a) => (
              <button
                key={a}
                className="press"
                data-active={accent === a}
                onClick={() => onAccentChange(a)}
                title={ACCENT_DESCRIPTIONS[a]}
                type="button"
              >
                <span>{ACCENT_LABELS[a]}</span>
                <small>{ACCENT_DESCRIPTIONS[a]}</small>
              </button>
            ))}
          </div>

          <details className="voice-lab-advanced">
            <summary>Advanced</summary>
            <div className="tab-bar" role="tablist" aria-label="Voice render mode">
              {(["target_accent", "natural"] as VoiceRenderMode[]).map((mode) => (
                <button
                  key={mode}
                  className="tab-btn press"
                  data-active={renderMode === mode}
                  onClick={() => onRenderModeChange(mode)}
                  type="button"
                >
                  {RENDER_MODE_LABELS[mode]}
                </button>
              ))}
            </div>
          </details>
        </div>

        <div className="voice-lab-action-row">
          <span>
            {text.length}/{MAX_LEN} · {ACCENT_DESCRIPTIONS[accent]}
          </span>
          {state === "ready" && audioUrl ? (
            <div className="voice-lab-actions">
              <button className="btn-paper btn-primary press" onClick={isPlaying ? onStop : onReplay}>
                <PlayStateIcon active={isPlaying} />
                {isPlaying ? "Stop" : "Play"}
              </button>
              <button className="btn-paper press" onClick={onSpeak} disabled={!canRender}>
                Generate again
              </button>
            </div>
          ) : (
            <button
              className="btn-paper btn-primary press"
              onClick={onSpeak}
              disabled={state === "loading" || voiceSession.status === "loading" || voiceSession.status === "error" || trimmedText.length < MIN_LEN}
            >
              {state === "loading" && <span className="mini-spinner" aria-hidden />}
              {primaryLabel}
            </button>
          )}
        </div>

        {state === "error" && errorMsg && (
          <p className="voice-lab-error" role="alert">
            {errorMsg}
          </p>
        )}

        {(state === "ready" || isPlaying) && words.length > 0 && (
          <div className="voice-lab-transcript">
            <p>{isPlaying ? "Speaking" : "Last render"}</p>
            <SpokenText words={words} audio={audioRef.current} playing={isPlaying} size="md" />
          </div>
        )}

        {history.length > 0 && (
          <details className="voice-history">
            <summary>Recent clips</summary>
            <div>
              {history.map((h, i) => (
                <button
                  key={`${h.text}-${h.accent}-${h.renderMode ?? "target_accent"}-${i}`}
                  className="press"
                  onClick={() => onHistoryClick(h)}
                  type="button"
                >
                  <span>{ACCENT_LABELS[h.accent]}</span>
                  <strong>{h.text}</strong>
                </button>
              ))}
            </div>
            <button className="voice-history-clear press" onClick={onClearHistory} type="button">
              Clear recent clips
            </button>
          </details>
        )}
      </div>

      <EnrollmentModal
        open={enrollOpen}
        prompts={enrollPrompts}
        onClose={() => setEnrollOpen(false)}
        onEnrolled={() => {}}
      />
    </section>
  );
}

function ProfileButton({
  status,
  ready,
  takes,
  onClick,
}: {
  status: string;
  ready: boolean;
  takes: number;
  onClick: () => void;
}) {
  const label = status === "loading" ? "Checking voice" : ready ? "Update voice" : status === "error" ? "Retry voice" : "Record voice";
  return (
    <button
      className="voice-profile-button press"
      onClick={onClick}
      disabled={status === "loading"}
      type="button"
    >
      <span>{label}</span>
      <small>{ready ? `${takes} take${takes === 1 ? "" : "s"} saved` : "Local voice profile"}</small>
    </button>
  );
}

function PlayStateIcon({ active }: { active: boolean }) {
  if (active) {
    return <span aria-hidden className="stop-icon" />;
  }
  return <span aria-hidden className="play-icon" />;
}
