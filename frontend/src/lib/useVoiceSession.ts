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
    const sync = () => {
      refreshVoiceSession({ force: true }).catch(() => {});
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
      unsubscribe();
      window.removeEventListener("focus", sync);
      document.removeEventListener("visibilitychange", syncVisible);
    };
  }, []);

  return session;
}
