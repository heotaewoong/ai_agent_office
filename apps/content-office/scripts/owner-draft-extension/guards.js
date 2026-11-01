// Shared by the actual content-script click path and the policy regression tests.
globalThis.HeoBrainDraftGuards=Object.freeze({
 safeButton(label){return /^(임시저장|임시 저장|저장|초안으로 저장|Save|Save draft|Save as draft|닫기|Close|Cancel|취소|글쓰기|게시물 작성|Start a post|만들기|Create|초안|Drafts|내 메뉴|나|Me)$/i.test(label.trim());},
 linkedInProfile(href,account,label){try{const u=new URL(href,'https://www.linkedin.com');return u.protocol==='https:' && u.hostname==='www.linkedin.com' && u.pathname.replace(/\/$/,'')==='/'+account.replace(/\/$/,'') && /^(View .+profile|프로필 보기)$/i.test(label.trim());}catch{return false;}}
});
