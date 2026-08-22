export type LoginLoadingSessionSnapshot = {
  sessionId: number;
  tipId: string | null;
  revealComplete: boolean;
  exitAccepted: boolean;
};

export function createLoginLoadingSessionController() {
  let nextSessionId = 0;
  let snapshot: LoginLoadingSessionSnapshot = {
    sessionId: 0,
    tipId: null,
    revealComplete: false,
    exitAccepted: false,
  };

  return {
    begin() {
      nextSessionId += 1;
      snapshot = {
        sessionId: nextSessionId,
        tipId: null,
        revealComplete: false,
        exitAccepted: false,
      };
      return nextSessionId;
    },
    getSnapshot() {
      return { ...snapshot };
    },
    isCurrent(sessionId: number) {
      return snapshot.sessionId === sessionId;
    },
    activateTip(sessionId: number, tipId: string) {
      if (!snapshot.sessionId || snapshot.sessionId !== sessionId) return false;
      snapshot = { ...snapshot, tipId, revealComplete: false, exitAccepted: false };
      return true;
    },
    isTipActive(sessionId: number, tipId: string) {
      return snapshot.sessionId === sessionId && snapshot.tipId === tipId;
    },
    markRevealComplete(sessionId: number, tipId: string) {
      if (!snapshot.sessionId || snapshot.sessionId !== sessionId || snapshot.tipId !== tipId) return false;
      snapshot = { ...snapshot, revealComplete: true };
      return true;
    },
    isRevealComplete(sessionId: number, tipId: string) {
      return snapshot.sessionId === sessionId && snapshot.tipId === tipId && snapshot.revealComplete;
    },
    acceptExit(sessionId: number, tipId: string) {
      if (
        snapshot.sessionId !== sessionId ||
        snapshot.tipId !== tipId ||
        !snapshot.revealComplete ||
        snapshot.exitAccepted
      ) {
        return false;
      }
      snapshot = { ...snapshot, exitAccepted: true };
      return true;
    },
  };
}

export type LoginLoadingSessionController = ReturnType<typeof createLoginLoadingSessionController>;
