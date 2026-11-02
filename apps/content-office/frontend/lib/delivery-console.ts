import type {Channel, Job} from './types.ts';
import {sourceChannelMismatch, youtubePreflight} from './delivery-readiness.ts';
export type DeliveryMode='office'|'private'|'draft';
export const platformChoices=['youtube','instagram','tiktok','linkedin','threads','tistory','naver_blog'] as const;
export const platformNames:Record<string,string>={youtube:'YouTube',instagram:'Instagram',tiktok:'TikTok',linkedin:'LinkedIn',threads:'Threads',tistory:'티스토리',naver_blog:'네이버 블로그'};
const textFiles:Record<string,string>={linkedin_personal:'linkedin-personal.txt',threads_main:'threads-main.txt',tistory_main:'tistory.md',naver_blog_main:'naver.txt'};
export function choiceReadiness(job:Job, channel:Channel|undefined, mode:DeliveryMode, blockedReason?:string):{ok:boolean;reason:string}{
 if(mode==='office')return {ok:true,reason:'EC2 오피스 보관 · 외부 플랫폼에는 전송하지 않습니다.'};
 if(!channel)return {ok:false,reason:'등록된 대상 계정이 없습니다. 제작 설정에서 본인 계정을 확인하세요.'};
 if(mode==='private')return channel.platform==='youtube'?youtubePreflight(job,channel,blockedReason):{ok:false,reason:'이 플랫폼의 비공개 영상 업로드는 지원하지 않습니다.'};
 if(!['linkedin','threads','tistory','naver_blog'].includes(channel.platform))return {ok:false,reason:channel.platform==='instagram'?'Instagram 영상 임시저장은 현재 연결 경로에서 검증되지 않았습니다. 오피스 보관을 사용하세요.':'이 플랫폼의 임시저장 실행기는 연결되지 않았습니다.'};
 if(blockedReason)return {ok:false,reason:blockedReason};
 if(!job.source_hash||job.source_approval?.decision!=='approved'||job.source_approval.version!==job.source_hash)return {ok:false,reason:'현재 원고 승인①이 필요합니다.'};
 if(job.manifest?.source_hash!==job.source_hash||!job.manifest?.hash)return {ok:false,reason:'현재 원고에 연결된 정식 제작물이 필요합니다.'};
 if(job.release_approval?.decision!=='approved'||job.release_approval.version!==job.manifest.hash)return {ok:false,reason:'현재 파일의 출고 승인②가 필요합니다.'};
 const mismatch=sourceChannelMismatch(job,channel);if(mismatch)return {ok:false,reason:mismatch};
 if(!channel.public_url||!channel.publication_enabled)return {ok:false,reason:'이 계정의 주소·전송 허용을 제작 설정에서 확인하세요.'};
 if(!job.release_approval.outputs?.includes('blog'))return {ok:false,reason:'블로그·소셜 원고를 출고 승인②에 포함해 주세요.'};
 if(!job.manifest.files?.some(f=>f.name===textFiles[channel.key]&&f.outputs?.includes('blog')))return {ok:false,reason:'이 계정에 전달할 승인된 원고 파일이 없습니다.'};
 return {ok:true,reason:'요청 가능 · PC 실행기가 계정·파일·현재 작업시간을 다시 검사합니다. 실제 저장 완료는 영수증으로 확인합니다.'};
}

export type HostStatus={online:boolean;last_seen:string|null};
/** One plain line about the owner PC runner. Deliveries only move while it polls; 'pending' is not progress. */
export function hostStatusLine(host:HostStatus|undefined, now=Date.now()):string{
 if(!host)return '';
 if(host.online)return 'PC 실행기 연결됨 · 전달 요청을 바로 가져갑니다.';
 if(!host.last_seen)return 'PC 실행기가 한 번도 접속하지 않았어요. 허태웅 님 PC에서 Chrome 확장과 Windows 실행기를 켜야 플랫폼에 올라갑니다.';
 const minutes=Math.max(1,Math.round((now-Date.parse(host.last_seen))/60_000));
 const ago=minutes>=120?`${Math.round(minutes/60)}시간 전`:`${minutes}분 전`;
 return `PC 실행기가 꺼져 있어요 · 마지막 접속 ${ago}. 켜기 전에는 전달 요청이 '대기'에 머물고 어디에도 올라가지 않습니다.`;
}

/** Existing connectors accept these formats; this does not enable an external connector. */
export function destinationFormat(platform:string):{mode:DeliveryMode;label:string;note:string}{
 if(platform==='youtube')return {mode:'private',label:'영상 · YouTube 비공개',note:'출고 승인②에 포함된 영상과 제목·설명을 사용합니다. 표지 자동 전송은 별도 지원하지 않습니다.'};
 if(platform==='instagram')return {mode:'office',label:'영상·카드·캡션 · 오피스 준비',note:'Instagram 외부 임시저장은 미연결입니다. 플랫폼에 저장된 것으로 표시하지 않습니다.'};
 if(['linkedin','threads','tistory','naver_blog'].includes(platform))return {mode:'draft',label:'글 · 플랫폼 임시저장',note:'이 계정용 승인 원고를 사용합니다. 영상·카드 첨부 전송은 아직 연결되지 않았습니다.'};
 return {mode:'office',label:'오피스 보관',note:'이 플랫폼의 외부 전달 실행기는 연결되지 않았습니다.'};
}
