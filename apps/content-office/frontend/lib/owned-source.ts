export type OwnedSourceForm = { title: string; body: string; url: string; owned: boolean; preset: string; experienceFirst: boolean };
export type OwnedSourceInput = { title: string; body: string; source_url: string; owner_confirmed: boolean; brief_preset?: string; experience_first?: true };

/** 내 글로 만들기 요청. '내 경험 중심'은 켰을 때만 보내서 기존 요청과 같은 모양을 유지합니다. */
export function ownedSourceInput(form: OwnedSourceForm): OwnedSourceInput {
  const input: OwnedSourceInput = { title: form.title, body: form.body, source_url: form.url, owner_confirmed: form.owned, brief_preset: form.preset };
  if (form.experienceFirst) input.experience_first = true;
  return input;
}
