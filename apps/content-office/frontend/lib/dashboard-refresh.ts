type DashboardRefreshTicket = {
  controller: AbortController;
  timer: ReturnType<typeof setTimeout>;
};

/** 목록 조회만 직렬화한다. 강제 갱신·화면 복귀는 예전 응답을 무효화한다. */
export function createDashboardRefreshGuard() {
  let active = false;
  let visible = true;
  let pending: DashboardRefreshTicket | null = null;

  function invalidate() {
    const previous = pending;
    pending = null;
    if (previous) {
      clearTimeout(previous.timer);
      previous.controller.abort(new Error("이전 목록 조회를 무효화했습니다."));
    }
  }

  return {
    activate(isVisible: boolean) {
      invalidate();
      active = true;
      visible = isVisible;
    },
    deactivate() {
      active = false;
      invalidate();
    },
    setVisible(isVisible: boolean) {
      visible = isVisible;
      if (!visible) invalidate();
    },
    begin(force = false): DashboardRefreshTicket | null {
      if (!active || !visible || (pending && !force)) return null;
      if (force) invalidate();
      const controller = new AbortController();
      pending = {
        controller,
        timer: setTimeout(() => controller.abort(new Error("목록 조회 시간이 초과되었습니다. 연결을 확인해 주세요.")), 30_000),
      };
      return pending;
    },
    isCurrent(ticket: DashboardRefreshTicket) {
      return active && visible && pending === ticket;
    },
    async wait<T>(ticket: DashboardRefreshTicket, response: Promise<T>): Promise<T> {
      const { signal } = ticket.controller;
      let onAbort: () => void;
      try {
        return await new Promise<T>((resolve, reject) => {
          onAbort = () => reject(signal.reason);
          if (signal.aborted) onAbort();
          else signal.addEventListener("abort", onAbort, { once: true });
          // 취소 이후 도착한 실제 요청의 거절도 소비해 미처리 Promise를 남기지 않는다.
          response.then(resolve, reject);
        });
      } finally {
        clearTimeout(ticket.timer);
        signal.removeEventListener("abort", onAbort!);
      }
    },
    settle(ticket: DashboardRefreshTicket) {
      if (!active || !visible || pending !== ticket) return false;
      clearTimeout(ticket.timer);
      pending = null;
      return true;
    },
  };
}
