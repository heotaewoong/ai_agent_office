import React from 'react';
import {AbsoluteFill, Composition, OffthreadVideo, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import cues from './cues.json';

const CaptionPilot = () => {
  const frame = useCurrentFrame();
  const time = frame / 24;
  const cue = cues.find(c => time >= c.start && time < c.end);
  const age = cue ? (time - cue.start) * 24 : 0;
  const remaining = cue ? (cue.end - time) * 24 : 0;
  const alpha = cue ? Math.min(1, age / 4, remaining / 3) : 0;
  const rise = 14 * (1 - Math.min(1, age / 6)) ** 2;
  return <AbsoluteFill style={{background: '#070e19', fontFamily: 'Noto Sans CJK KR, Arial, sans-serif'}}>
    <OffthreadVideo src={staticFile('baseline.mp4')} trimBefore={192} trimAfter={384} muted />
    <div style={{position: 'absolute', left: 90, right: 150, top: 1270, color: '#8ed7e9', fontSize: 25, letterSpacing: 3,
      opacity: Math.min(1, frame / 8)}}>01 / CONTENT TEAM</div>
    <div style={{position: 'absolute', left: 90, right: 150, top: 1325, height: 2, background: '#1c3746'}}>
      <div style={{width: `${100 * frame / 191}%`, height: 2, background: '#8ed7e9'}} />
    </div>
    {cue && <div style={{position: 'absolute', left: 85, right: 155, top: 1375, textAlign: 'center',
      opacity: alpha, transform: `translateY(${rise}px)`, wordBreak: 'keep-all'}}>
      <div style={{fontSize: 47, fontWeight: 650, lineHeight: 1.35, color: '#f4f8fc'}}>{cue.ko}</div>
      <div style={{fontSize: 35, lineHeight: 1.4, marginTop: 22, color: '#e8c690'}}>{cue.en}</div>
    </div>}
  </AbsoluteFill>;
};
const Root = () => <Composition id="CaptionPilot" component={CaptionPilot} width={1080} height={1920}
  durationInFrames={192} fps={24} />;
registerRoot(Root);
