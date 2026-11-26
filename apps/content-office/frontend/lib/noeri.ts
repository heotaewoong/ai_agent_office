// HeoBrain 캐릭터 '뇌리'의 표정과, 화면에서 뇌리가 무엇을 알려 주는지 정한다.
// 표정은 서버가 준 사실(작업 시간, 작업자 기록, 검사 결과)로만 고른다. 없는 진행 상황을 꾸며 보이지 않는다.
// 그림은 app/noeri.tsx, 같은 비율의 PNG는 backend/office/mascot.py가 그린다.

export type NoeriMood = "happy" | "curious" | "thinking" | "tired" | "proud" | "surprised" | "calm";

export const NOERI_MOODS: readonly NoeriMood[] = ["happy", "curious", "thinking", "tired", "proud", "surprised", "calm"];

export const NOERI_LABELS: Record<NoeriMood, string> = {
  happy: "신남",
  curious: "궁금",
  thinking: "생각 중",
  tired: "지침",
  proud: "뿌듯",
  surprised: "놀람",
  calm: "차분",
};

export type NoeriStatus = { mood: NoeriMood; label: string; detail: string };

/** 파이프라인 화면 맨 위의 뇌리. 배포 검사 실패가 있으면 그것부터, 다음은 작업 시간과 작업자 기록 순서로 본다. */
export function noeriStatus(input: { windowOpen: boolean; worker?: string | null; failedTests?: boolean }): NoeriStatus {
  if (input.failedTests) return { mood: "surprised", label: "확인이 필요해요", detail: "배포 때 검사 실패가 기록돼 있어요. 아래 실행판 기록부터 보세요." };
  if (input.windowOpen && input.worker === "online") return { mood: "thinking", label: "일하는 중", detail: "작업 시간이 열려 있고 작업자가 줄 선 일을 받고 있어요." };
  if (input.windowOpen) return { mood: "curious", label: "작업 시간 열림", detail: "작업자 기록이 없어요. 줄 선 일이 있으면 작업자가 켜졌는지 보세요." };
  return { mood: "calm", label: "쉬는 중", detail: "작업 시간이 닫혀 있어요. 아침 수집만 정한 시각에 혼자 열고 닫아요." };
}

/** 그림 기억 이야기 패널의 뇌리 표정. */
export function storyMood(story: { checks: { passed: boolean } } | null, pending: boolean): NoeriMood {
  if (pending) return "thinking";
  if (!story) return "happy";
  return story.checks.passed ? "proud" : "tired";
}
