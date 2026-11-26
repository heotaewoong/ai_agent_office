import type { NoeriMood } from "../lib/noeri";

const C = { body: "#cfeedd", shade: "#a9dcc1", line: "#2f5e4a", groove: "#8fc4a8", cheek: "#f6b9a6", eye: "#223c31", spark: "#ff8a3d", mouth: "#c45a4a", drop: "#8cc8f0" };
const LOBES: [number, number, number][] = [[100, 112, 70], [62, 70, 34], [100, 56, 38], [138, 70, 34], [40, 106, 32], [160, 106, 32], [60, 146, 30], [140, 146, 30]];

function star(cx: number, cy: number, r: number) {
  return Array.from({ length: 10 }, (_, i) => {
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    const radius = i % 2 === 0 ? r : r * 0.45;
    return `${(cx + radius * Math.cos(angle)).toFixed(1)},${(cy + radius * Math.sin(angle)).toFixed(1)}`;
  }).join(" ");
}

function Eyes({ mood }: { mood: NoeriMood }) {
  if (mood === "happy" || mood === "proud") return <g fill="none" stroke={C.eye} strokeWidth={5} strokeLinecap="round"><path d="M67 116 Q78 101 89 116" /><path d="M111 116 Q122 101 133 116" /></g>;
  if (mood === "tired") return <g stroke={C.eye} strokeWidth={5} strokeLinecap="round" fill="none"><path d="M68 114 H88" /><path d="M112 114 H132" /><path d="M70 117 Q78 123 86 117" strokeWidth={3} /><path d="M114 117 Q122 123 130 117" strokeWidth={3} /></g>;
  if (mood === "calm") return <g fill={C.eye}><circle cx={78} cy={114} r={5} /><circle cx={122} cy={114} r={5} /></g>;
  const big = mood === "surprised" ? 12 : 10;
  const dx = mood === "thinking" ? 4 : 0;
  const dy = mood === "thinking" ? -4 : 0;
  return <g>
    {[78, 122].map((x) => <g key={x}>
      <circle cx={x} cy={112} r={big} fill="#ffffff" stroke={C.eye} strokeWidth={3} />
      <circle cx={x + dx} cy={112 + dy} r={6} fill={C.eye} />
      <circle cx={x + dx + 1} cy={112 + dy - 2} r={2} fill="#ffffff" />
    </g>)}
    {mood === "curious" && <path d="M110 97 Q122 88 134 97" fill="none" stroke={C.eye} strokeWidth={3} strokeLinecap="round" />}
  </g>;
}

function Mouth({ mood }: { mood: NoeriMood }) {
  switch (mood) {
    case "happy":
    case "proud":
      return <path d="M86 129 Q100 153 114 129 Z" fill={C.mouth} stroke={C.eye} strokeWidth={3} strokeLinejoin="round" />;
    case "surprised":
      return <ellipse cx={100} cy={142} rx={7} ry={9} fill={C.mouth} stroke={C.eye} strokeWidth={3} />;
    case "curious":
      return <circle cx={104} cy={140} r={5} fill="none" stroke={C.eye} strokeWidth={3} />;
    case "thinking":
      return <path d="M92 141 L110 139" stroke={C.eye} strokeWidth={4} strokeLinecap="round" />;
    case "tired":
      return <path d="M88 142 L94 138 L100 142 L106 138 L112 142" fill="none" stroke={C.eye} strokeWidth={3} strokeLinejoin="round" />;
    default:
      return <path d="M88 136 Q100 148 112 136" fill="none" stroke={C.eye} strokeWidth={4} strokeLinecap="round" />;
  }
}

function Extras({ mood }: { mood: NoeriMood }) {
  return <g>
    <polygon points={star(152, 18, 15)} fill={C.spark} />
    {mood === "thinking" && <g fill={C.line} className="noeri-dots"><circle cx={170} cy={44} r={4} /><circle cx={180} cy={32} r={5} /><circle cx={192} cy={18} r={6} /></g>}
    {mood === "tired" && <path d="M162 64 L154 80 A8 8 0 1 0 170 80 Z" fill={C.drop} />}
    {mood === "proud" && <g fill={C.spark}><polygon points={star(24, 40, 9)} /><polygon points={star(182, 62, 8)} /><polygon points={star(14, 150, 7)} /></g>}
    {mood === "surprised" && <g stroke={C.line} strokeWidth={4} strokeLinecap="round"><path d="M12 34 L24 54" /><path d="M184 34 L172 54" /></g>}
  </g>;
}

/** HeoBrain 캐릭터 '뇌리'. 장식이 아니라 상태 표시라서, label이 있으면 화면 읽기 프로그램에도 그 상태를 읽어 준다. */
export function Noeri({ mood = "happy", size = 72, label, className }: { mood?: NoeriMood; size?: number; label?: string; className?: string }) {
  const armY = mood === "proud" || mood === "surprised" ? 104 : 128;
  return (
    <svg viewBox="-6 -6 212 212" width={size} height={size} className={["noeri", `noeri-${mood}`, className].filter(Boolean).join(" ")}
      role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} focusable="false">
      {[78, 122].map((x) => <ellipse key={x} cx={x} cy={182} rx={20} ry={12} fill={C.line} />)}
      {[78, 122].map((x) => <ellipse key={`f${x}`} cx={x} cy={182} rx={17} ry={9} fill={C.shade} />)}
      {[22, 178].map((x) => <circle key={x} cx={x} cy={armY} r={20} fill={C.line} />)}
      {[22, 178].map((x) => <circle key={`a${x}`} cx={x} cy={armY} r={15} fill={C.shade} />)}
      {LOBES.map(([x, y, r]) => <circle key={`o${x}-${y}`} cx={x} cy={y} r={r + 5} fill={C.line} />)}
      {LOBES.map(([x, y, r]) => <circle key={`b${x}-${y}`} cx={x} cy={y} r={r} fill={C.body} />)}
      <g fill="none" stroke={C.groove} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
        <path d="M100 30 L94 44 L104 58 L96 72 L102 86" />
        <path d="M58 64 Q67 54 78 62" /><path d="M122 62 Q133 54 142 64" /><path d="M34 108 Q38 96 50 96" /><path d="M150 96 Q162 96 166 108" />
      </g>
      <ellipse cx={62} cy={134} rx={13} ry={8} fill={C.cheek} />
      <ellipse cx={138} cy={134} rx={13} ry={8} fill={C.cheek} />
      <Eyes mood={mood} />
      <Mouth mood={mood} />
      <Extras mood={mood} />
    </svg>
  );
}
