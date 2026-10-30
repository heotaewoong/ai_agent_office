import assert from 'node:assert/strict';
import test from 'node:test';
import {officeRoute,officeHref} from '../lib/navigation.ts';
import {newsSegment,filterNews,newsEmptyState} from '../lib/news.ts';
test('shared URLs restore views and exact job IDs',()=>{
 assert.deepEqual(officeRoute('/scripts/job_abc'),{view:'studio',jobId:'job_abc'});
 assert.equal(officeHref('studio','job/a?b'),'/scripts/job%2Fa%3Fb');
 for(const view of ['home','news','plans','studio','delivery','world','settings','activity','architecture'] as const)assert.equal(officeRoute(officeHref(view)).view,view);
 assert.equal(officeRoute('/unknown').view,'home');
});
test('segments use explicit metadata, retain unknown rows and ignore article order',()=>{
 const rows=[{id:'a',segment:'exam'},{id:'b',segment:'ai'},{id:'c',title:'AI 시험'}];
 assert.equal(newsSegment('exam'),'exam');assert.equal(newsSegment('bad'),'all');
 assert.deepEqual(filterNews(rows,'exam').map(x=>x.id),['a']);
 assert.deepEqual(filterNews(rows,'ai').map(x=>x.id),['b']);
 assert.equal(filterNews(rows,'all').length,3);
});
test('empty collection, collection failure, missing sources and filtered zero differ',()=>{
 assert.equal(newsEmptyState('exam',0,0,false,false).kind,'sources');
 assert.equal(newsEmptyState('all',0,0,false,false).kind,'first');
 assert.equal(newsEmptyState('all',0,2,true,true).kind,'failure');
 assert.equal(newsEmptyState('ai',0,2,true,false).kind,'empty');
 assert.equal(newsEmptyState('exam',4,1,true,false).kind,'filtered');
});
