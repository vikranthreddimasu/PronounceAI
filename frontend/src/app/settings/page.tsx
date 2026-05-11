"use client";

import { useEffect, useState } from "react";
import {
  getProfile,
  setProfile,
  resetAll,
  subscribeStorage,
  type UserProfile,
  type Theme,
} from "@/lib/store";
import { isSoundsEnabled, setSoundsEnabled, tap, confirm } from "@/lib/sounds";
import {
  fetchVoiceProfile,
  getOrCreateVoiceId,
  deleteVoiceProfile,
  deleteVoiceTake,
  ENROLLMENT_PROMPTS,
  type EnrollmentPrompt,
  type VoiceProfile,
} from "@/lib/voiceProfile";
import EnrollmentModal from "@/components/EnrollmentModal";
import type { Accent } from "@/lib/types";

const L1_OPTIONS = [
  "Japanese", "Mandarin", "Spanish", "German", "French",
  "Korean", "Hindi", "Arabic", "Portuguese", "Russian",
  "Italian", "Vietnamese", "Tagalog", "Polish", "Turkish",
  "Other",
];

const ACCENT_OPTIONS: { id: Accent; label: string; desc: string }[] = [
  { id: "GA", label: "General American", desc: "Neutral US English." },
  { id: "RP", label: "Received Pronunciation", desc: "BBC British." },
];

export default function SettingsPage() {
  const [profile, setLocal] = useState<UserProfile>(getProfile());
  const [sounds, setSounds] = useState(true);
  const [voiceProfile, setVoice] = useState<VoiceProfile | null>(null);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [enrollPrompts, setEnrollPrompts] = useState<EnrollmentPrompt[] | undefined>(undefined);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    setLocal(getProfile());
    setSounds(isSoundsEnabled());
    const id = getOrCreateVoiceId();
    if (id) {
      fetchVoiceProfile(id).then(setVoice).catch(() => setVoice(null));
    }
    return subscribeStorage(() => setLocal(getProfile()));
  }, []);

  const update = (patch: Partial<UserProfile>) => {
    tap();
    setLocal(setProfile(patch));
    if (patch.theme) applyTheme(patch.theme);
  };

  const toggleSounds = () => {
    const next = !sounds;
    setSounds(next);
    setSoundsEnabled(next);
    if (next) tap();
  };

  return (
    <main className="mx-auto" style={{ maxWidth: 760, padding: "32px 20px 80px" }}>
      <header style={{ marginBottom: 28 }}>
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
          Settings
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
          Tune the app to you.
        </h1>
      </header>

      {/* Target accent */}
      <Group title="Target accent" hint="The accent your sessions are scored against.">
        <div className="flex flex-col" style={{ gap: 10 }}>
          {ACCENT_OPTIONS.map((a) => (
            <button
              key={a.id}
              className="press"
              onClick={() => update({ targetAccent: a.id })}
              style={{
                padding: "14px 18px",
                borderRadius: 12,
                border: `1px solid ${profile.targetAccent === a.id ? "var(--accent)" : "var(--line)"}`,
                background: profile.targetAccent === a.id ? "var(--accent-faint)" : "var(--paper)",
                textAlign: "left",
                display: "flex",
                alignItems: "center",
                gap: 12,
                cursor: "pointer",
              }}
            >
              <span
                aria-hidden
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  border: `2px solid ${profile.targetAccent === a.id ? "var(--accent)" : "var(--line-2)"}`,
                  background:
                    profile.targetAccent === a.id
                      ? "radial-gradient(circle, var(--accent) 0%, var(--accent) 40%, transparent 45%)"
                      : "transparent",
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1 }}>
                <p
                  className="font-display"
                  style={{ fontSize: 16, fontWeight: 600, color: "var(--ink)", letterSpacing: "-0.01em" }}
                >
                  {a.label}
                </p>
                <p style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>{a.desc}</p>
              </div>
            </button>
          ))}
        </div>
      </Group>

      {/* Native language */}
      <Group title="Native language" hint="Used to highlight your L1's typical English errors.">
        <select
          value={profile.l1 ?? ""}
          onChange={(e) => update({ l1: e.target.value || null })}
          className="font-mono"
          style={{
            width: "100%",
            padding: "12px 14px",
            borderRadius: 10,
            border: "1px solid var(--line)",
            background: "var(--paper)",
            color: "var(--ink-2)",
            fontSize: 13,
            outline: "none",
            appearance: "none",
          }}
        >
          <option value="">— select —</option>
          {L1_OPTIONS.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
      </Group>

      {/* Voice enrollment */}
      <Group
        title="Voice profile"
        hint="Each take strengthens the speaker embedding. CosyVoice uses up to 28s of reference; more variety + length = harder to distinguish from real you."
      >
        {voiceProfile ? (
          <div className="flex flex-col" style={{ gap: 14 }}>
            <div className="flex items-end justify-between" style={{ gap: 12 }}>
              <div>
                <p
                  className="font-display"
                  style={{ fontSize: 22, fontWeight: 700, color: "var(--ink)", letterSpacing: "-0.015em", lineHeight: 1 }}
                >
                  {voiceProfile.bundle_duration_s.toFixed(1)}
                  <span style={{ fontSize: 13, color: "var(--ink-4)", marginLeft: 4, fontWeight: 500 }}>s ref</span>
                </p>
                <p
                  className="font-mono"
                  style={{ fontSize: 11, color: "var(--ink-4)", letterSpacing: 0, marginTop: 4 }}
                >
                  {voiceProfile.takes.length} take{voiceProfile.takes.length === 1 ? "" : "s"} · {voiceProfile.duration_s.toFixed(1)}s raw
                </p>
              </div>
              <QualityBar duration={voiceProfile.bundle_duration_s} />
            </div>

            <div className="flex flex-col" style={{ gap: 6 }}>
              {voiceProfile.takes.map((t, i) => (
                <div
                  key={t.id}
                  className="card-paper-inset"
                  style={{
                    padding: "10px 12px",
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    fontSize: 12,
                  }}
                >
                  <span
                    className="font-mono"
                    style={{ color: "var(--ink-4)", fontSize: 10, width: 24, letterSpacing: 0 }}
                  >
                    #{i + 1}
                  </span>
                  <span
                    style={{
                      flex: 1,
                      minWidth: 0,
                      color: "var(--ink-2)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {t.ref_text}
                  </span>
                  <span className="font-mono" style={{ color: "var(--ink-4)", fontSize: 10, letterSpacing: 0 }}>
                    {t.duration_s.toFixed(1)}s
                  </span>
                  <button
                    className="press"
                    onClick={async () => {
                      tap();
                      const id = getOrCreateVoiceId();
                      try {
                        const next = await deleteVoiceTake(id, t.id);
                        setVoice(next);
                      } catch {
                        /* surface as toast later */
                      }
                    }}
                    title="Delete take"
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: 6,
                      background: "transparent",
                      border: "none",
                      color: "var(--ink-4)",
                      fontSize: 14,
                      cursor: "pointer",
                      lineHeight: 1,
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>

            <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
              <button
                className="btn-paper btn-primary press"
                onClick={() => {
                  tap();
                  // Default: cycle through the next missing prompt(s)
                  const usedTexts = new Set(voiceProfile.takes.map((t) => t.ref_text));
                  const missing = ENROLLMENT_PROMPTS.filter((p) => !usedTexts.has(p.text));
                  setEnrollPrompts(missing.length > 0 ? missing : ENROLLMENT_PROMPTS);
                  setEnrollOpen(true);
                }}
                style={{ fontSize: 12 }}
              >
                + Add take
              </button>
              <button
                className="btn-paper press"
                onClick={async () => {
                  tap();
                  const id = getOrCreateVoiceId();
                  await deleteVoiceProfile(id);
                  setVoice(null);
                }}
                style={{ fontSize: 12, color: "var(--rose)" }}
              >
                Delete profile
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col" style={{ gap: 12 }}>
            <p style={{ fontSize: 13, color: "var(--ink-2)" }}>
              Not enrolled yet. 3 short takes (~30s total).
            </p>
            <button
              className="btn-paper btn-primary press"
              onClick={() => {
                tap();
                setEnrollPrompts(undefined);
                setEnrollOpen(true);
              }}
              style={{ fontSize: 13 }}
            >
              Set up voice profile →
            </button>
          </div>
        )}
      </Group>

      {/* Theme */}
      <Group title="Theme" hint="Light reads best in daytime; dark when the room is dim.">
        <div className="tab-bar" role="tablist" aria-label="Theme">
          {(["light", "dark", "system"] as Theme[]).map((t) => (
            <button
              key={t}
              className="tab-btn press"
              data-active={profile.theme === t}
              onClick={() => update({ theme: t })}
            >
              {t === "system" ? "System" : t === "light" ? "Light" : "Dark"}
            </button>
          ))}
        </div>
      </Group>

      {/* Sounds */}
      <Group title="Sounds" hint="Soft tactile clicks on press, gentle confirm on save.">
        <button
          className="press"
          onClick={toggleSounds}
          style={{
            padding: "12px 16px",
            borderRadius: 12,
            border: "1px solid var(--line)",
            background: sounds ? "var(--accent-faint)" : "var(--paper)",
            color: sounds ? "var(--accent)" : "var(--ink-3)",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 10,
            width: "100%",
            justifyContent: "space-between",
          }}
        >
          <span>{sounds ? "On" : "Off"}</span>
          <span
            aria-hidden
            style={{
              width: 36,
              height: 20,
              borderRadius: 9999,
              background: sounds ? "var(--accent)" : "var(--paper-3)",
              position: "relative",
              transition: "background 220ms var(--ease-paper)",
            }}
          >
            <span
              style={{
                position: "absolute",
                top: 2,
                left: sounds ? 18 : 2,
                width: 16,
                height: 16,
                borderRadius: "50%",
                background: "#fefaf0",
                boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
                transition: "left 220ms var(--ease-paper)",
              }}
            />
          </span>
        </button>
      </Group>

      {/* Danger zone */}
      <Group title="Local data" hint="Everything lives in your browser. Nuke from orbit?">
        {!confirmReset ? (
          <button
            className="btn-paper press"
            onClick={() => {
              tap();
              setConfirmReset(true);
            }}
            style={{ fontSize: 12, color: "var(--rose)" }}
          >
            Reset everything
          </button>
        ) : (
          <div className="flex" style={{ gap: 8 }}>
            <button
              className="btn-paper press"
              onClick={() => setConfirmReset(false)}
              style={{ fontSize: 12 }}
            >
              Cancel
            </button>
            <button
              className="btn-paper press"
              onClick={() => {
                resetAll();
                confirm();
                setLocal(getProfile());
                setConfirmReset(false);
              }}
              style={{
                fontSize: 12,
                background: "var(--rose)",
                color: "#fefaf0",
                borderColor: "var(--rose)",
              }}
            >
              Yes, wipe profile + sessions
            </button>
          </div>
        )}
      </Group>

      <EnrollmentModal
        open={enrollOpen}
        onClose={() => {
          setEnrollOpen(false);
          setEnrollPrompts(undefined);
        }}
        onEnrolled={(p) => setVoice(p)}
        prompts={enrollPrompts}
      />
    </main>
  );
}

function QualityBar({ duration }: { duration: number }) {
  // 0..28s mapped to 0..1; soft-cap visualisation
  const pct = Math.min(1, duration / 28);
  const color =
    pct >= 0.75 ? "var(--jade)" : pct >= 0.4 ? "var(--accent)" : "var(--rose)";
  const label = pct >= 0.75 ? "Strong" : pct >= 0.4 ? "OK" : "Thin";
  return (
    <div style={{ width: 140, textAlign: "right" }}>
      <p
        className="font-mono"
        style={{
          fontSize: 10,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color,
          marginBottom: 4,
        }}
      >
        {label}
      </p>
      <div
        className="dim-track"
        style={{ width: "100%", height: 6 }}
      >
        <div
          className="dim-fill"
          style={
            {
              ["--pct" as string]: `${pct * 100}%`,
              ["--tone" as string]: color,
            } as React.CSSProperties
          }
        />
      </div>
    </div>
  );
}

function Group({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 24 }}>
      <header style={{ marginBottom: 12 }}>
        <p
          className="font-display"
          style={{ fontSize: 18, fontWeight: 700, color: "var(--ink)", letterSpacing: "-0.01em" }}
        >
          {title}
        </p>
        {hint && (
          <p style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 3, lineHeight: 1.5 }}>{hint}</p>
        )}
      </header>
      <div className="card-paper-flat" style={{ padding: 18 }}>{children}</div>
    </section>
  );
}

function applyTheme(t: Theme) {
  const root = document.documentElement;
  const resolved =
    t === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : t;
  root.setAttribute("data-theme", resolved);
}
