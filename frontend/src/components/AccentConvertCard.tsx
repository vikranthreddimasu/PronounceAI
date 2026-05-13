"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Accent } from "@/lib/types";
import { cloneAccent, speakInVoice, type VoiceProfile } from "@/lib/voiceProfile";
import { isAbortError } from "@/lib/abortError";

type Props = {
  userAudio: Blob | null;
  accent: Accent;
  /** Profile loaded from /api/voice/<id>. Null when no enrollment. */
  voiceProfile: VoiceProfile | null;
  /** Known target phrase; lets us skip ASR and hit the speculative voice cache. */
  overrideText?: string;
  /** Triggered when the user wants to (re-)enroll. */
  onOpenEnrollment: () => void;
};

const ACCENT_NAME: Record<Accent, string> = {
  GA: "American",
  RP: "British RP",
};

export default function AccentConvertCard({
  userAudio,
  accent,
  voiceProfile,
  overrideText,
  onOpenEnrollment,
}: Props) {
  const [state, setState] = useState<"idle" | "converting" | "ready" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [convertedUrl, setConvertedUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mountedRef = useRef(true);
  const convertAbortRef = useRef<AbortController | null>(null);
  const convertedUrlRef = useRef<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      convertAbortRef.current?.abort();
      convertAbortRef.current = null;
      if (convertedUrlRef.current) URL.revokeObjectURL(convertedUrlRef.current);
    };
  }, []);

  // Reset whenever inputs change.
  useEffect(() => {
    convertAbortRef.current?.abort();
    convertAbortRef.current = null;
    setState("idle");
    setErrorMsg(null);
    if (convertedUrl) {
      URL.revokeObjectURL(convertedUrl);
      convertedUrlRef.current = null;
      setConvertedUrl(null);
    }
    setIsPlaying(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userAudio, accent, voiceProfile?.user_id]);

  useEffect(() => {
    convertedUrlRef.current = convertedUrl;
  }, [convertedUrl]);

  const handleConvert = useCallback(async () => {
    if (!userAudio || state === "converting") return;
    if (!voiceProfile) {
      onOpenEnrollment();
      return;
    }
    convertAbortRef.current?.abort();
    const ac = new AbortController();
    convertAbortRef.current = ac;
    setState("converting");
    setErrorMsg(null);
    try {
      let blob: Blob;
      if (overrideText?.trim()) {
        blob = (
          await speakInVoice(
            voiceProfile.user_id,
            overrideText,
            accent,
            voiceProfile.revision,
            "target_accent",
            ac.signal
          )
        ).audio;
      } else {
        blob = await cloneAccent(userAudio, accent, voiceProfile.user_id, { signal: ac.signal });
      }
      if (!mountedRef.current || ac.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      if (convertedUrlRef.current && convertedUrlRef.current !== url) {
        URL.revokeObjectURL(convertedUrlRef.current);
      }
      convertedUrlRef.current = url;
      setConvertedUrl(url);
      setState("ready");
      if (!audioRef.current) audioRef.current = new Audio();
      audioRef.current.src = url;
      audioRef.current.onended = () => setIsPlaying(false);
      audioRef.current.onerror = () => setIsPlaying(false);
      setIsPlaying(true);
      audioRef.current.play().catch(() => setIsPlaying(false));
    } catch (e) {
      if (!mountedRef.current || isAbortError(e)) {
        if (mountedRef.current) setState("idle");
        return;
      }
      setErrorMsg((e as Error).message ?? "Could not convert");
      setState("error");
    } finally {
      if (convertAbortRef.current === ac) convertAbortRef.current = null;
    }
  }, [userAudio, accent, voiceProfile, overrideText, state, onOpenEnrollment]);

  const handleReplay = useCallback(() => {
    if (!convertedUrl) return;
    if (!audioRef.current) audioRef.current = new Audio();
    audioRef.current.src = convertedUrl;
    audioRef.current.currentTime = 0;
    audioRef.current.onended = () => setIsPlaying(false);
    audioRef.current.onerror = () => setIsPlaying(false);
    setIsPlaying(true);
    audioRef.current.play().catch(() => setIsPlaying(false));
  }, [convertedUrl]);

  if (!userAudio) return null;

  const isConverting = state === "converting";
  const isReady = state === "ready";
  const subTitle = voiceProfile
    ? "Your timbre with the target accent locked in."
    : "Set up your voice to hear this phrase in your own timbre.";

  return (
    <div
      className="rounded-2xl fade-pop"
      style={{
        padding: 18,
        background: "var(--surface)",
        border: "1px solid var(--line)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {isConverting && (
        <div
          className="shimmer-bar"
          aria-hidden
          style={{ position: "absolute", inset: 0, opacity: 0.35, pointerEvents: "none" }}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between" style={{ marginBottom: 10, position: "relative" }}>
        <div>
          <div
            className="text-xs uppercase tracking-wider"
            style={{ color: "var(--ink-3)", letterSpacing: "0.08em" }}
          >
            Accent conversion · {ACCENT_NAME[accent]}
          </div>
          <div className="text-sm font-semibold" style={{ color: "var(--ink)", marginTop: 2 }}>
            {voiceProfile ? "Your voice" : "Set up your voice"}
          </div>
        </div>

        {isReady ? (
          <button
            className="press rounded-full text-xs font-semibold"
            style={{
              padding: "9px 16px",
              background: isPlaying ? "var(--surface-2)" : "var(--accent)",
              color: isPlaying ? "var(--ink-2)" : "var(--bg)",
              border: isPlaying ? "1px solid var(--line)" : "none",
              transition: "background-color 180ms var(--ease-out), color 180ms var(--ease-out), border-color 180ms var(--ease-out)",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
            onClick={handleReplay}
          >
            <span
              aria-hidden
              style={{
                width: 0,
                height: 0,
                borderLeft: `7px solid ${isPlaying ? "var(--ink-2)" : "var(--bg)"}`,
                borderTop: "5px solid transparent",
                borderBottom: "5px solid transparent",
                display: "inline-block",
              }}
            />
            {isPlaying ? "Playing" : "Replay"}
          </button>
        ) : (
          <button
            className="press rounded-full text-xs font-semibold"
            style={{
              padding: "9px 16px",
              background: isConverting
                ? "var(--surface-2)"
                : "linear-gradient(160deg, var(--accent-soft), var(--accent))",
              color: isConverting ? "var(--ink-3)" : "var(--bg)",
              border: isConverting ? "1px solid var(--line)" : "none",
              opacity: isConverting ? 0.85 : 1,
              transition: "background-color 180ms var(--ease-out), color 180ms var(--ease-out), opacity 180ms var(--ease-out), border-color 180ms var(--ease-out)",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
            disabled={isConverting}
            onClick={handleConvert}
          >
            {isConverting && (
              <span
                aria-hidden
                className="spin"
                style={{
                  width: 10,
                  height: 10,
                  border: "1.5px solid var(--ink-3)",
                  borderTopColor: "transparent",
                  borderRadius: "50%",
                  display: "inline-block",
                }}
              />
            )}
            {isConverting ? "Converting" : voiceProfile ? "Convert" : "Set up voice"}
          </button>
        )}
      </div>

      <p
        className="text-xs leading-snug"
        style={{ color: state === "error" ? "var(--rose)" : "var(--ink-3)", position: "relative", minHeight: 16 }}
      >
        {state === "error"
          ? errorMsg
          : isConverting
          ? "Locking the target accent to your voice..."
          : isReady
          ? "Compare it with your original above."
          : subTitle}
      </p>

      {!voiceProfile && (
        <button
          className="press hover-accent"
          onClick={onOpenEnrollment}
          style={{
            marginTop: 10,
            width: "100%",
            padding: "9px 0",
            borderRadius: 10,
            background: "transparent",
            border: "1px dashed var(--line-2, var(--line))",
            color: "var(--ink-3)",
            fontSize: 12,
            fontWeight: 500,
            transition: "background-color 180ms var(--ease-out), color 180ms var(--ease-out), border-color 180ms var(--ease-out)",
          }}
        >
          Record a short voice sample to enable accent conversion
        </button>
      )}
    </div>
  );
}
