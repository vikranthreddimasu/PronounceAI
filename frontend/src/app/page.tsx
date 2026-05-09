"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { PHRASES } from "@/lib/phrases";
import { isMock, scoreRecording } from "@/lib/api";
import { createRecorder, speakReference, type Recorder } from "@/lib/recorder";
import type { Difficulty, Phrase, ScoreResponse } from "@/lib/types";
import { Brand } from "@/components/Brand";
import { DifficultyTabs } from "@/components/DifficultyTabs";
import { PhraseStage } from "@/components/PhraseStage";
import { RecordButton, type RecorderState } from "@/components/RecordButton";
import { ResultCard } from "@/components/ResultCard";
import { PhraseNav } from "@/components/PhraseNav";

type Filter = Difficulty | "all";

export default function Home() {
  const [filter, setFilter] = useState<Filter>("all");
  const [phraseId, setPhraseId] = useState<string>(PHRASES[0].id);
  const [state, setState] = useState<RecorderState>("idle");
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [userBlobUrl, setUserBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPlayingNative, setPlayingNative] = useState(false);
  const [isPlayingUser, setPlayingUser] = useState(false);

  const recorderRef = useRef<Recorder | null>(null);
  const userAudioRef = useRef<HTMLAudioElement | null>(null);

  const visiblePhrases = useMemo<Phrase[]>(
    () => (filter === "all" ? PHRASES : PHRASES.filter((p) => p.difficulty === filter)),
    [filter],
  );

  const phraseIndex = Math.max(
    0,
    visiblePhrases.findIndex((p) => p.id === phraseId),
  );
  const phrase = visiblePhrases[phraseIndex] ?? visiblePhrases[0];

  function handleFilterChange(next: Filter) {
    setFilter(next);
    const nextVisible =
      next === "all" ? PHRASES : PHRASES.filter((p) => p.difficulty === next);
    if (!nextVisible.find((p) => p.id === phraseId)) {
      setPhraseId(nextVisible[0]?.id ?? PHRASES[0].id);
      reset();
    }
  }

  useEffect(() => {
    return () => {
      recorderRef.current?.dispose();
      if (userBlobUrl) URL.revokeObjectURL(userBlobUrl);
      window.speechSynthesis?.cancel?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function reset() {
    setResult(null);
    setError(null);
    if (userBlobUrl) {
      URL.revokeObjectURL(userBlobUrl);
      setUserBlobUrl(null);
    }
    if (userAudioRef.current) {
      userAudioRef.current.pause();
      userAudioRef.current = null;
    }
    setPlayingUser(false);
  }

  async function handleToggle() {
    setError(null);
    if (state === "idle") {
      try {
        if (!recorderRef.current) recorderRef.current = await createRecorder();
        await recorderRef.current.start();
        setState("recording");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Microphone unavailable.");
        setState("idle");
      }
      return;
    }
    if (state === "recording") {
      setState("processing");
      try {
        const blob = await recorderRef.current!.stop();
        if (userBlobUrl) URL.revokeObjectURL(userBlobUrl);
        setUserBlobUrl(URL.createObjectURL(blob));
        const res = await scoreRecording(blob, phrase);
        setResult(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Scoring failed. Try again.");
      } finally {
        setState("idle");
      }
    }
  }

  function changePhrase(delta: number) {
    const next =
      (phraseIndex + delta + visiblePhrases.length) % visiblePhrases.length;
    setPhraseId(visiblePhrases[next].id);
    reset();
  }

  function shuffle() {
    if (visiblePhrases.length <= 1) return;
    let next = phraseIndex;
    while (next === phraseIndex) {
      next = Math.floor(Math.random() * visiblePhrases.length);
    }
    setPhraseId(visiblePhrases[next].id);
    reset();
  }

  function playUser() {
    if (!userBlobUrl) return;
    if (userAudioRef.current) {
      userAudioRef.current.pause();
      userAudioRef.current = null;
      setPlayingUser(false);
      return;
    }
    const a = new Audio(userBlobUrl);
    userAudioRef.current = a;
    setPlayingUser(true);
    a.onended = () => {
      userAudioRef.current = null;
      setPlayingUser(false);
    };
    a.onerror = () => {
      userAudioRef.current = null;
      setPlayingUser(false);
    };
    a.play().catch(() => {
      userAudioRef.current = null;
      setPlayingUser(false);
    });
  }

  async function playReference() {
    if (isPlayingNative) {
      window.speechSynthesis?.cancel?.();
      setPlayingNative(false);
      return;
    }
    setPlayingNative(true);
    await speakReference(phrase.text);
    setPlayingNative(false);
  }

  function getLevel() {
    return recorderRef.current?.getLevel() ?? 0;
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col px-5 pb-10 pt-6 sm:px-6 sm:pt-9">
      <header className="rise rise-1 flex items-center justify-between">
        <Brand />
        <ModeBadge />
      </header>

      <div className="rise rise-2 mt-7 flex justify-center sm:mt-9">
        <DifficultyTabs value={filter} onChange={handleFilterChange} />
      </div>

      <section className="rise rise-3 mt-9 sm:mt-11">
        <PhraseStage
          phrase={phrase}
          index={phraseIndex}
          total={visiblePhrases.length}
          onPlayNative={playReference}
          isPlayingNative={isPlayingNative}
        />
      </section>

      <section className="rise rise-4 mt-12 sm:mt-14">
        <RecordButton state={state} onToggle={handleToggle} getLevel={getLevel} />
      </section>

      {error ? (
        <div
          role="alert"
          className="result-enter mt-7 rounded-xl border border-warn/40 bg-warn/[0.07] px-4 py-3 text-[13px] text-warn"
        >
          {error}
        </div>
      ) : null}

      {result ? (
        <section className="mt-9">
          <ResultCard
            result={result}
            canPlayUser={!!userBlobUrl}
            onRetry={reset}
            onPlayUser={playUser}
            onPlayReference={playReference}
            isPlayingNative={isPlayingNative}
            isPlayingUser={isPlayingUser}
          />
        </section>
      ) : null}

      <div className="rise rise-5 mt-10">
        <PhraseNav
          onPrev={() => changePhrase(-1)}
          onNext={() => changePhrase(1)}
          onShuffle={shuffle}
        />
      </div>

      <footer className="mt-auto pt-10 text-center text-[11px] text-ink-4">
        v1 · pronunciation that tells you why
      </footer>
    </main>
  );
}

function ModeBadge() {
  return (
    <span
      title={isMock ? "Running with mock scores" : "Connected to backend"}
      className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/60 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-3"
    >
      <span
        aria-hidden
        className={[
          "block h-1.5 w-1.5 rounded-full",
          isMock ? "bg-ink-3" : "bg-jade",
        ].join(" ")}
      />
      {isMock ? "Demo" : "Live"}
    </span>
  );
}
