import React, {useLayoutEffect, useRef} from 'react';
import {AbsoluteFill, Composition, registerRoot, useCurrentFrame, delayRender, continueRender, cancelRender} from 'remotion';
import cues from './cues.json';
import {captionBoundsFromOffsets} from './caption_layout.cjs';

const sections = [
  [0, '00 / EMERGENCY BROADCAST'], [8, '01 / CONTENT TEAM'],
  [32, '02 / STOCK AGENTS'], [44, '03 / DEVELOPMENT TEAM'],
  [56, '04 / OBSIDIAN TEAM'], [68, '05 / THE MISSION'],
  [80, '06 / FLEET MOBILIZATION'], [114, '07 / ONE CONNECTED AI OFFICE'],
] as const;
const CaptionPanel = () => {
  const frame = useCurrentFrame();
  const time = frame / 24;
  const index = cues.findIndex(c => time >= c.start && time < c.end);
  const cue = cues[index];
  const block = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const section = [...sections].reverse().find(s => time >= s[0])!;
  const age = cue ? (time - cue.start) * 24 : 0;
  const remaining = cue ? (cue.end - time) * 24 : 0;
  const alpha = cue ? Math.min(1, age / 3, remaining / 2) : 0;
  const rise = 12 * (1 - Math.min(1, age / 5)) ** 2;
  useLayoutEffect(() => {
    if (!cue) return;
    const handle = delayRender('caption geometry after composition sizing');
    let cancelled = false;
    let released = false;
    const release = () => {if (!released) {continueRender(handle); released = true;}};
    const nextPaint = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    (async () => {
      await document.fonts.ready;
      for (let attempt = 0; attempt < 120; attempt++) {
        await nextPaint();
        if (cancelled) return;
        if (block.current && block.current.offsetWidth >= 800 && panel.current?.offsetWidth === 1080) {
          const r = captionBoundsFromOffsets(block.current, rise);
          console.log('__CAPTION_LAYOUT__' + JSON.stringify({cue:index+1,frame,
            left:r.left,right:r.right,top:r.top,bottom:r.bottom,height:r.height,en:cue.en,ko:cue.ko}));
          release();
          return;
        }
      }
      throw Error('Composition width was not ready for caption measurement');
    })().catch(error => {release(); cancelRender(error);});
    return () => {cancelled = true; release();};
  }, [frame, index]);
  return <AbsoluteFill ref={panel} style={{background: '#070e19', fontFamily: 'Noto Sans CJK KR, Arial, sans-serif'}}>
    <div style={{position:'absolute',left:90,right:150,top:50,color:'#8ed7e9',fontSize:25,letterSpacing:2.2}}>{section[1]}</div>
    <div style={{position:'absolute',left:90,right:150,top:105,height:2,background:'#1c3746'}}>
      <div style={{width:`${100 * frame / 3551}%`,height:2,background:'#8ed7e9'}} />
    </div>
    {cue && <div ref={block} style={{position:'absolute',left:85,right:155,top:155,textAlign:'center',
      opacity:alpha,transform:`translateY(${rise}px)`,wordBreak:'keep-all',overflowWrap:'break-word'}}>
      <div style={{fontSize:44,fontWeight:650,lineHeight:1.3,color:'#f4f8fc'}}>{cue.ko}</div>
      <div style={{fontSize:34,lineHeight:1.35,marginTop:18,color:'#e8c690'}}>{cue.en}</div>
    </div>}
  </AbsoluteFill>;
};
const Root = () => <Composition id="CaptionPanel" component={CaptionPanel} width={1080} height={660}
  durationInFrames={3552} fps={24} />;
registerRoot(Root);
