import test from 'node:test';
import assert from 'node:assert/strict';
import {validateItem,safeButton,proof} from './policy.mjs';
const row={id:'od_'+'a'.repeat(24),content_hash:'b'.repeat(64),channel_key:'linkedin_personal',account_id:'in/owner',text:'승인한 본문',visibility:'draft',authorized_end:'2099-01-01T00:00:00Z',claim_id:'claim_'+'c'.repeat(16)};
test('공개·예약·임의 플랫폼 요청은 전송 전에 거절',()=>{
 for(const patch of [{visibility:'public'},{publish_at:'2099-01-01'},{channel_key:'slack_internal'},{authorized_end:'2000-01-01'}])assert.throws(()=>validateItem({...row,...patch}));
 assert.equal(validateItem(row).platform,'linkedin');
});
test('공개/예약/삭제 버튼을 초안 버튼으로 선택하지 않음',()=>{
 for(const label of ['게시','발행','등록','Post','Share','Schedule','Publish','Delete','Save and publish','예약','Save changes and post']) assert.equal(safeButton(label),false,label);
 for(const label of ['임시저장','Save as draft','Close']) assert.equal(safeButton(label),true);
});
test('증빙은 같은 초안·계정·본문·처리 키에만 연결',()=>{
 assert.throws(()=>proof(row,'published','public-id'));
 assert.deepEqual(proof(row,'platform_draft','draft-local'),{state:'platform_draft',claim_id:row.claim_id,content_hash:row.content_hash,account_id:row.account_id,external_id:'draft-local',reason:''});
});
test('본인 메뉴의 프로필 링크만 계정 ID 증거로 인정',()=>{
 const match=globalThis.HeoBrainDraftGuards.linkedInProfile;
 assert.equal(match('https://www.linkedin.com/in/taewoong-heo-323b34366/','in/taewoong-heo-323b34366','View Taewoong Heo’s profile'),true);
 assert.equal(match('https://evil.example/in/taewoong-heo-323b34366/','in/taewoong-heo-323b34366','View profile'),false);
 assert.equal(match('/in/other/','in/taewoong-heo-323b34366','View other profile'),false);
 assert.equal(match('/in/taewoong-heo-323b34366/','in/taewoong-heo-323b34366','기사 본문에 등장한 프로필'),false);
 assert.equal(match('/in/taewoong-heo-323b34366/','in/taewoong-heo-323b34366','허태웅님의 프로필 보기'),true);
 assert.equal(safeButton('글 올리기'),true);
});
