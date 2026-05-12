"use client";

import { useEffect, useState } from "react";
import {
  getVoiceSessionSnapshot,
  refreshVoiceSession,
  subscribeVoiceSession,
  type VoiceSessionState,
} from "@/lib/voiceProfile";

export function useVoiceSession(): VoiceSessionState {
  const [session, setSession] = useState<VoiceSessionState>(() => getVoiceSessionSnapshot());

  useEffect(() => {
    let mounted = true;
    const ac = new AbortController();

    const sync = () => {
      refreshVoiceSession({ force: true, signal: ac.signal }).catch(() => {});
    };
    const unsubscribe = subscribeVoiceSession((next) => {
      if (mounted) setSession(next);
    });

    sync();
    const syncVisible = () => {
      if (!document.hidden) sync();
    };

    window.addEventListener("focus", sync);
    document.addEventListener("visibilitychange", syncVisible);

    return () => {
      mounted = false;
      ac.abort();
      unsubscribe();
      window.removeEventListener("focus", sync);
      document.removeEventListener("visibilitychange", syncVisible);
    };
  }, []);

  return session;
}
