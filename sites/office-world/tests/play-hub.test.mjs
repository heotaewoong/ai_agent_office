import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {installPlayHub} from '../play-hub.js';
const source=await readFile(new URL('../app.js',import.meta.url),'utf8');
const hubSource=await readFile(new URL('../play-hub.js',import.meta.url),'utf8');

test('an incomplete game UI stays untouched rather than hiding existing controls',()=>{
  assert.equal(installPlayHub({querySelector:()=>null},()=>undefined),null);
});

test('failed boarding keeps its message visible; successful boarding focuses the world',()=>{
  const start=hubSource.indexOf("  doc.addEventListener('click', event => {");
  const end=hubSource.indexOf('\n  });',start);
  const body=hubSource.slice(hubSource.indexOf('{',start)+1,end);
  for(const speed of [0,24]){
    const calls=[],canvas={focus:options=>{assert.equal(options.preventScroll,true);calls.push('focus-world');}};
    const onClick=Function('opened','office','setOpen','doc','return event=>{'+body+'}')(true,
      ()=>({space:{view:'walk'},controls:{vehicleSpeed:speed}}),value=>calls.push(value),{getElementById:()=>canvas});
    onClick({target:{closest:()=>({matches:()=>false})}});
    assert.deepEqual(calls,speed?[false,'focus-world']:[]);
    if(speed)assert.equal(canvas.tabIndex,0);
  }
});

test('opening the play drawer blocks movement and still releases previously held keys',()=>{
  const start=source.indexOf('    onKey('),end=source.indexOf('\n    },',start);
  const space={playHubOpen:true,view:'walk'};
  const handler=Function('space','return ({'+source.slice(start,end+6)+'}).onKey')(space);
  const controls={keys:new Set(['w'])};
  handler.call(controls,{key:'w'},false);
  assert.equal(controls.keys.size,0,'keyup must release a key even with the drawer open');
  for(const key of ['w','a','s','d','m','e','r','Escape'])handler.call(controls,{key},true);
  assert.equal(controls.keys.size,0,'no movement or world action is queued behind the drawer');
});

function toolbarFixture(nestedAttention) {
  function element(tagName='DIV') {
    return {tagName,children:[],parentNode:null,dataset:{},attributes:{},listeners:{},
      classList:{add(){},toggle(){}},focus(){},setAttribute(key,value){this.attributes[key]=value;},
      getAttribute(key){return this.attributes[key];},
      addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);},
      append(...nodes){for(const child of nodes){child.parentNode=this;this.children.push(child);}},
      insertBefore(child,anchor){
        const index=this.children.indexOf(anchor);
        if(anchor&&index<0)throw new Error('NotFoundError: reference is not a direct child');
        child.parentNode=this;this.children.splice(anchor?index:this.children.length,0,child);
      },
      closest(selector){
        if(selector==='.topbar')return this===topbar?this:this.parentNode?.closest(selector);
        if(selector==='button,summary')return ['BUTTON','SUMMARY'].includes(this.tagName)?this:null;
        if(selector==='#btn-play-hub')return this.id==='btn-play-hub'?this:null;
        return null;
      },
      querySelector(selector){return local[selector]??null;},
    };
  }
  const local={'.play-hub-tabs':element(),'.play-hub-close':element('BUTTON')};
  const body=element(),topbar=element(),toolbar=element(),tools=element('DETAILS'),secondary=element();
  const attention=element('BUTTON'),overview=element('BUTTON'),walk=element('BUTTON');
  body.append(topbar);topbar.append(toolbar,overview,walk);toolbar.append(tools);tools.append(secondary);
  (nestedAttention?secondary:toolbar).append(attention);
  const games={'.free-drive':element('DETAILS'),'#explore':element('DETAILS'),'.city-activities':element(),'.alien-game':element()};
  const doc={body,createElement:tag=>element(tag.toUpperCase()),addEventListener(){},
    querySelector:selector=>selector==='.world-actions'?toolbar:games[selector],
    getElementById:id=>({'world-tools':tools,'btn-attention':attention}[id]),};
  return {doc,toolbar,topbar,overview,walk,games};
}

test('play entry installs when attention is nested in the secondary tools',()=>{
  const f=toolbarFixture(true),hub=installPlayHub(f.doc,()=>undefined);
  assert.equal(hub.trigger.parentNode,f.toolbar);
  assert.equal(hub.hub.parentNode,f.doc.body);
  for(const game of Object.values(f.games))assert.equal(game.parentNode.parentNode,hub.hub);
});

test('view buttons outside the action group close play and release its input lock',()=>{
  const f=toolbarFixture(false),space={},controls={keys:new Set(['w']),dragging:true};
  const hub=installPlayHub(f.doc,()=>({space,controls}));
  for(const button of [f.overview,f.walk]){
    hub.open();assert.equal(space.playHubOpen,true);
    for(const listener of f.topbar.listeners.click??[])listener({target:button});
    assert.equal(hub.hub.hidden,true);assert.equal(space.playHubOpen,false);
    assert.equal(controls.keys.size,0);assert.equal(controls.dragging,false);
  }
});
