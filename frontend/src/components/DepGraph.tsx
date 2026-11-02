import type { Action } from "../types";

/** Layered dependency graph: prerequisites (left) -> actions (right). Edge color = satisfied or not. */
export function DepGraph({ actions, onSelect }: { actions: Action[]; onSelect?: (key: string) => void }) {
  const withDeps = actions.filter((a) => a.prerequisites.length);
  if (!withDeps.length) return <div className="muted small" style={{ padding: 16 }}>No dependencies were found between actions.</div>;
  const prereqNodes: { id: string; label: string; ok: boolean; kind: string }[] = [];
  const seen = new Map<string, number>();
  withDeps.forEach((a) => a.prerequisites.forEach((p) => {
    const id = `${p.kind}:${p.ref}`;
    if (!seen.has(id)) { seen.set(id, prereqNodes.length); prereqNodes.push({ id, label: p.label, ok: p.ok, kind: p.kind }); }
  }));
  const rowH = 54, W = 860, leftX = 20, nodeW = 290, rightX = W - nodeW - 20;
  const H = Math.max(prereqNodes.length, withDeps.length) * rowH + 30;
  const ly = (i: number) => 20 + i * rowH + (H - 30 - prereqNodes.length * rowH) / 2;
  const ry = (i: number) => 20 + i * rowH + (H - 30 - withDeps.length * rowH) / 2;
  const tone = (ok: boolean) => (ok ? "#2dd4bf" : "#f0616d");
  const trunc = (s: string, n = 38) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  return (
    <div className="graph-wrap">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Dependency graph">
        {withDeps.map((a, i) => a.prerequisites.map((p) => {
          const j = seen.get(`${p.kind}:${p.ref}`)!;
          const x1 = leftX + nodeW, y1 = ly(j) + 19, x2 = rightX, y2 = ry(i) + 19;
          return <path key={a.key + p.ref} d={`M${x1},${y1} C${x1 + 120},${y1} ${x2 - 120},${y2} ${x2},${y2}`} fill="none"
            stroke={tone(p.ok)} strokeOpacity={0.65} strokeWidth={1.8} strokeDasharray={p.ok ? "" : "5 4"} />;
        }))}
        {prereqNodes.map((n, j) => (
          <g key={n.id} transform={`translate(${leftX},${ly(j)})`}>
            <rect width={nodeW} height={38} rx={9} fill="#141925" stroke={tone(n.ok)} strokeOpacity={0.6} />
            <circle cx={16} cy={19} r={4.5} fill={tone(n.ok)} />
            <text x={30} y={16} fill="#e8ebf2" fontSize={12} fontWeight={600}>{trunc(n.label)}</text>
            <text x={30} y={30} fill="#7f889c" fontSize={10}>{n.kind}{n.ok ? " · satisfied" : " · not satisfied"}</text>
          </g>
        ))}
        {withDeps.map((a, i) => (
          <g key={a.key} transform={`translate(${rightX},${ry(i)})`} style={{ cursor: onSelect ? "pointer" : "default" }} onClick={() => onSelect?.(a.key)}>
            <rect width={nodeW} height={38} rx={9} fill="#171c28" stroke={a.readiness === "ready" ? "#2dd4bf" : a.readiness === "blocked" ? "#f0616d" : "#f5b544"} strokeOpacity={0.7} />
            <text x={14} y={16} fill="#e8ebf2" fontSize={12} fontWeight={650}>{trunc(a.title)}</text>
            <text x={14} y={30} fill="#7f889c" fontSize={10}>action · {a.readiness.replace("_", " ")}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}
