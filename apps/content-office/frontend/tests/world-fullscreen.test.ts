import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('fallback fullscreen Escape exits once and cannot also close the iframe team panel', () => {
 const source=readFileSync(new URL('../app/world-view.tsx',import.meta.url),'utf8');
 const start=source.indexOf('const escape = '),end=source.indexOf('\n    };',start);
 const callback=source.slice(start+'const escape = '.length,end+6).replace('event: KeyboardEvent','event');
 let closed=0,prevented=0,stopped=0;
 const escape=Function('document','closeScreen','return '+callback)({fullscreenElement:null},()=>closed++);
 escape({key:'Escape',preventDefault(){prevented++;},stopPropagation(){stopped++;}});
 assert.deepEqual({closed,prevented,stopped},{closed:1,prevented:1,stopped:1});
 escape({key:'a',preventDefault(){throw Error('unrelated key');}});
 assert.equal(closed,1);
});
