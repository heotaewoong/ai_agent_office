import './guards.js';
export const TARGETS = Object.freeze({
 youtube_main_ko:{platform:'youtube'},youtube_english:{platform:'youtube'},
 threads_main:{platform:'threads',url:'https://www.threads.com/'},
 linkedin_personal:{platform:'linkedin',url:'https://www.linkedin.com/feed/'},
 tistory_main:{platform:'tistory',url:'https://onethingflow.tistory.com/manage/newpost/'},
 naver_blog_main:{platform:'naver',url:'https://blog.naver.com/oneflowwhy/postwrite'},
 instagram_main:{platform:'instagram',url:'https://business.facebook.com/'},
 instagram_english:{platform:'instagram',url:'https://business.facebook.com/'},
});
export function validateItem(row, now=Date.now()) {
 const target=TARGETS[row?.channel_key];
 if(!target || !/^od_[0-9a-f]{24}$/.test(row.id) || !/^[0-9a-f]{64}$/.test(row.content_hash) || !row.account_id || typeof row.text!=='string' || row.text.length>150000) throw Error('초안 대상·본문 검증 실패');
 if(!Number.isFinite(Date.parse(row.authorized_end)) || Date.parse(row.authorized_end)<=now) throw Error('작업 시간이 종료됐습니다');
 if(row.visibility!==(target.platform==='youtube'?'private':'draft') || row.publish_at || row.public_publish) throw Error('공개·예약 발행은 차단했습니다');
 return target;
}
export const safeButton=globalThis.HeoBrainDraftGuards.safeButton;
export function proof(row,state,externalId,reason='') {
 const expected=row.visibility==='private'?'platform_private':'platform_draft';
 if(![expected,'blocked','unknown'].includes(state))throw Error('공개 결과는 기록할 수 없습니다');
 return {state,claim_id:row.claim_id,content_hash:row.content_hash,account_id:row.account_id,external_id:externalId,reason};
}
