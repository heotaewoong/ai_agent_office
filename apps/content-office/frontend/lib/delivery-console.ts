import type {Channel, Job} from './types.ts';
import {sourceChannelMismatch, youtubePreflight} from './delivery-readiness.ts';
export type DeliveryMode='office'|'private'|'draft';
export const platformChoices=['youtube','instagram','tiktok','linkedin','threads','tistory','naver'] as const;
export const platformNames:Record<string,string>={youtube:'YouTube',instagram:'Instagram',tiktok:'TikTok',linkedin:'LinkedIn',threads:'Threads',tistory:'티스토리',naver:'네이버 블로그'};
const textFiles:Record<string,string>={linkedin_personal:'linkedin-personal.txt',threads_main:'threads-main.txt',tistory_main:'tistory.md',naver_blog_main:'naver.txt'};
export function choiceReadiness(job:Job, channel:Channel|undefined, mode:DeliveryMode, blockedReason?:string):{ok:boolean;reason:string}{
 if(mode==='office')return {ok:true,reason:'EC2 오피스 보관 · 외부 플랫폼에는 전송하지 않습니다.'};
 if(!channel)return {ok:false,reason:'등록된 대상 계정이 없습니다. 제작 설정에서 본인 계정을 확인하세요.'};
 if(mode==='private')return channel.platform==='youtube'?youtubePreflight(job,channel,blockedReason):{ok:false,reason:'이 플랫폼의 비공개 영상 업로드는 지원하지 않습니다.'};
 if(!['linkedin','threads','tistory','naver'].includes(channel.platform))return {ok:false,reason:channel.platform==='instagram'?'Instagram 영상 임시저장은 현재 연결 경로에서 검증되지 않았습니다. 오피스 보관을 사용하세요.':'이 플랫폼의 임시저장 실행기는 연결되지 않았습니다.'};
 if(!job.source_hash||job.source_approval?.decision!=='approved'||job.source_approval.version!==job.source_hash)return {ok:false,reason:'현재 원고 승인①이 필요합니다.'};
 if(job.manifest?.source_hash!==job.source_hash||!job.manifest?.hash)return {ok:false,reason:'현재 원고에 연결된 정식 제작물이 필요합니다.'};
 if(job.release_approval?.decision!=='approved'||job.release_approval.version!==job.manifest.hash)return {ok:false,reason:'현재 파일의 출고 승인②가 필요합니다.'};
 const mismatch=sourceChannelMismatch(job,channel);if(mismatch)return {ok:false,reason:mismatch};
 if(!channel.public_url||!channel.publication_enabled)return {ok:false,reason:'이 계정의 주소·전송 허용을 제작 설정에서 확인하세요.'};
 if(!job.release_approval.outputs?.includes('blog'))return {ok:false,reason:'블로그·소셜 원고를 출고 승인②에 포함해 주세요.'};
 if(!job.manifest.files?.some(f=>f.name===textFiles[channel.key]&&f.outputs?.includes('blog')))return {ok:false,reason:'이 계정에 전달할 승인된 원고 파일이 없습니다.'};
 return {ok:true,reason:'요청 가능 · PC 실행기가 계정·파일·현재 작업시간을 다시 검사합니다. 실제 저장 완료는 영수증으로 확인합니다.'};
}
