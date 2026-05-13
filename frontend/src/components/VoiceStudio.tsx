"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Accent } from "@/lib/types";
import {
  VOICE_EMOTION_CHOICES,
  chooseEnrollmentPrompts,
  deleteVoiceProfile,
  precomposeVoice,
  refreshVoiceSession,
  speakInVoice,
  type EnrollmentPrompt,
  type VoiceEmotion,
  type VoiceEmotionChoice,
  type VoiceRenderMode,
  type WordTiming,
} from "@/lib/voiceProfile";
import { useVoiceSession } from "@/lib/useVoiceSession";
import { getProfile, setProfile } from "@/lib/store";
import { tap, confirm, release } from "@/lib/sounds";
import { isAbortError } from "@/lib/abortError";
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

const EMOTION_LABELS: Record<VoiceEmotion, string> = {
  neutral: "Neutral",
  happy: "Happy",
  sad: "Sad",
  angry: "Angry",
  excited: "Excited",
  calm: "Calm",
  whisper: "Whisper",
};

const EMOTION_CHOICE_LABELS: Record<VoiceEmotionChoice, string> = {
  auto: "Auto (detect from text)",
  ...EMOTION_LABELS,
};

const MAX_LEN = 400;
const MIN_LEN = 2;
const HISTORY_KEY = "pronounceai.studio.history.v1";
const MAX_HISTORY = 6;

type ClipState = "idle" | "loading" | "ready" | "error";
type HistoryEntry = {
  text: string;
  accent: Accent;
  renderMode?: VoiceRenderMode;
  emotion?: VoiceEmotionChoice;
};

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
  const [emotion, setEmotion] = useState<VoiceEmotionChoice>("auto");
  const [detectedEmotion, setDetectedEmotion] = useState<VoiceEmotion | null>(null);
  const [state, setState] = useState<ClipState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [words, setWords] = useState<WordTiming[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [enrollPrompts, setEnrollPrompts] = useState<EnrollmentPrompt[] | undefined>(undefined);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mountedRef = useRef(true);
  const speakAbortRef = useRef<AbortController | null>(null);
  const deleteAbortRef = useRef<AbortController | null>(null);
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
      precomposeVoice(profile.user_id, trimmedText, accent, profile.revision, renderMode, emotion);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [accent, emotion, profile, renderMode, trimmedText]);

  useEffect(() => () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
  }, [audioUrl]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      speakAbortRef.current?.abort();
      speakAbortRef.current = null;
      deleteAbortRef.current?.abort();
      deleteAbortRef.current = null;
      try {
        audioRef.current?.pause();
      } catch {}
    };
  }, []);

  const canRender = voiceSession.status === "ready" && profile !== null && trimmedText.length >= MIN_LEN;
  const voiceReady = voiceSession.status === "ready" && profile !== null;

  const clearClip = useCallback(() => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(null);
    setWords([]);
    setIsPlaying(false);
    setState("idle");
    setDetectedEmotion(null);
  }, [audioUrl]);

  const openEnrollment = useCallback(() => {
    tap();
    setEnrollPrompts(chooseEnrollmentPrompts(profile));
    setEnrollOpen(true);
  }, [profile]);

  const resetVoiceProfile = useCallback(async () => {
    if (!profile?.user_id || resetting) return;
    tap();
    setResetting(true);
    deleteAbortRef.current?.abort();
    const ac = new AbortController();
    deleteAbortRef.current = ac;
    try {
      clearClip();
      await deleteVoiceProfile(profile.user_id, { signal: ac.signal });
      if (!mountedRef.current || ac.signal.aborted) return;
      setConfirmReset(false);
    } catch (err) {
      if (!mountedRef.current || isAbortError(err)) {
        return;
      }
      setErrorMsg((err as Error).message ?? "Could not delete voice profile.");
    } finally {
      if (deleteAbortRef.current === ac) deleteAbortRef.current = null;
      setResetting(false);
    }
  }, [clearClip, profile?.user_id, resetting]);

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

  const onEmotionChange = useCallback((next: VoiceEmotionChoice) => {
    tap();
    setEmotion(next);
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
    speakAbortRef.current?.abort();
    try {
      audioRef.current?.pause();
    } catch {}
    const ac = new AbortController();
    speakAbortRef.current = ac;
    try {
      const clip = await speakInVoice(
        profile.user_id,
        trimmedText,
        accent,
        profile.revision,
        renderMode,
        ac.signal,
        emotion
      );
      if (!mountedRef.current || ac.signal.aborted) return;
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      const url = URL.createObjectURL(clip.audio);
      setAudioUrl(url);
      setWords(clip.words);
      setDetectedEmotion(clip.emotionSource === "auto" ? clip.emotion : null);
      setState("ready");
      confirm();

      if (!audioRef.current) audioRef.current = new Audio();
      audioRef.current.src = url;
      audioRef.current.onended = () => setIsPlaying(false);
      audioRef.current.onerror = () => setIsPlaying(false);
      setIsPlaying(true);
      audioRef.current.play().catch(() => setIsPlaying(false));

      const entry: HistoryEntry = { text: trimmedText, accent, renderMode, emotion };
      const next = [
        entry,
        ...history.filter(
          (h) =>
            !(
              h.text === entry.text &&
              h.accent === entry.accent &&
              (h.renderMode ?? "target_accent") === entry.renderMode &&
              (h.emotion ?? "neutral") === entry.emotion
            )
        ),
      ].slice(0, MAX_HISTORY);
      setHistory(next);
      writeHistory(next);
    } catch (e) {
      if (!mountedRef.current || isAbortError(e)) {
        if (mountedRef.current) setState("idle");
        return;
      }
      setErrorMsg((e as Error).message ?? "Voice rendering failed.");
      setState("error");
    } finally {
      if (speakAbortRef.current === ac) speakAbortRef.current = null;
    }
  }, [accent, audioUrl, emotion, history, openEnrollment, profile, renderMode, state, trimmedText]);

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
    setEmotion(h.emotion ?? "auto");
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
          <ProfileActions
            status={voiceSession.status}
            ready={voiceReady}
            takes={profile?.takes.length ?? 0}
            onPrimary={voiceSession.status === "error" ? () => refreshVoiceSession({ force: true }) : openEnrollment}
            confirmReset={confirmReset}
            resetting={resetting}
            onAskReset={() => { tap(); setConfirmReset(true); }}
            onConfirmReset={resetVoiceProfile}
            onCancelReset={() => setConfirmReset(false)}
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
            <ProfileActions
              status={voiceSession.status}
              ready={voiceReady}
              takes={profile?.takes.length ?? 0}
              onPrimary={voiceSession.status === "error" ? () => refreshVoiceSession({ force: true }) : openEnrollment}
              confirmReset={confirmReset}
              resetting={resetting}
              onAskReset={() => { tap(); setConfirmReset(true); }}
              onConfirmReset={resetVoiceProfile}
              onCancelReset={() => setConfirmReset(false)}
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
            <label className="voice-lab-emotion-label" htmlFor="voice-lab-emotion">
              Emotion
            </label>
            <select
              id="voice-lab-emotion"
              className="voice-lab-emotion-select press"
              value={emotion}
              onChange={(e) => onEmotionChange(e.target.value as VoiceEmotionChoice)}
            >
              {VOICE_EMOTION_CHOICES.map((e) => (
                <option key={e} value={e}>
                  {EMOTION_CHOICE_LABELS[e]}
                </option>
              ))}
            </select>
            {emotion === "auto" && detectedEmotion && (
              <p className="voice-lab-emotion-detected" aria-live="polite">
                Detected: <strong>{EMOTION_LABELS[detectedEmotion]}</strong>
              </p>
            )}
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
                  key={`${h.text}-${h.accent}-${h.renderMode ?? "target_accent"}-${h.emotion ?? "neutral"}-${i}`}
                  className="press"
                  onClick={() => onHistoryClick(h)}
                  type="button"
                >
                  <span>
                    {ACCENT_LABELS[h.accent]}
                    {h.emotion && h.emotion !== "neutral"
                      ? ` · ${EMOTION_CHOICE_LABELS[h.emotion]}`
                      : ""}
                  </span>
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

function ProfileActions({
  status,
  ready,
  takes,
  onPrimary,
  confirmReset,
  resetting,
  onAskReset,
  onConfirmReset,
  onCancelReset,
}: {
  status: string;
  ready: boolean;
  takes: number;
  onPrimary: () => void;
  confirmReset: boolean;
  resetting: boolean;
  onAskReset: () => void;
  onConfirmReset: () => void;
  onCancelReset: () => void;
}) {
  const label = status === "loading"
    ? "Checking voice"
    : ready
      ? "Add another take"
      : status === "error"
        ? "Retry voice"
        : "Record voice";
  return (
    <div style={{ display: "grid", gap: 8, justifyItems: "stretch" }}>
      <button
        className="voice-profile-button press"
        onClick={onPrimary}
        disabled={status === "loading" || resetting}
        type="button"
      >
        <span>{label}</span>
        <small>{ready ? `${takes} take${takes === 1 ? "" : "s"} saved` : "Local voice profile"}</small>
      </button>
      {ready && !confirmReset && (
        <button
          type="button"
          onClick={onAskReset}
          disabled={resetting}
          style={{
            border: 0,
            background: "transparent",
            color: "var(--ink-4)",
            cursor: "pointer",
            padding: "4px 4px",
            fontFamily: "var(--type-sans)",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            textAlign: "left",
          }}
        >
          Delete and re-record
        </button>
      )}
      {ready && confirmReset && (
        <div style={{ display: "grid", gap: 6 }}>
          <p
            style={{
              color: "var(--ink-3)",
              fontFamily: "var(--type-mono)",
              fontSize: 11,
              letterSpacing: "0.04em",
              lineHeight: 1.5,
            }}
          >
            Wipe all takes and start a fresh profile?
          </p>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              type="button"
              onClick={onConfirmReset}
              disabled={resetting}
              style={{
                flex: 1,
                minHeight: 34,
                border: "1px solid var(--accent)",
                background: "var(--accent)",
                color: "var(--paper)",
                fontFamily: "var(--type-sans)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                cursor: resetting ? "wait" : "pointer",
              }}
            >
              {resetting ? "Deleting" : "Yes, delete"}
            </button>
            <button
              type="button"
              onClick={onCancelReset}
              disabled={resetting}
              style={{
                flex: 1,
                minHeight: 34,
                border: "1px solid var(--rule)",
                background: "transparent",
                color: "var(--ink)",
                fontFamily: "var(--type-sans)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function PlayStateIcon({ active }: { active: boolean }) {
  if (active) {
    return <span aria-hidden className="stop-icon" />;
  }
  return <span aria-hidden className="play-icon" />;
}
