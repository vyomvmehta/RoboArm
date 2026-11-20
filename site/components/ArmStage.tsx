"use client";

// The home page's opening: the arm on a true-scale mat (1 small square = 10 mm), driven by
// the same maths the real arm runs. The two numbers in the headline are the target; so is
// the yellow marker, which can be dragged. Below it: what the laptop would compute and send.

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { type Angles, type ArmConfig, fk, frame, pulses, pulsesInRange, solve, stepToward } from "@/lib/kinematics";
import styles from "./ArmStage.module.css";

// Stage window in arm coordinates (mm): x out from the base axis, z up from the table.
const X0 = -130, X1 = 330, Z0 = -24, Z1 = 356;
// Rounded to 0.01 mm: the server and the browser compute trig to slightly different last digits,
// and unrounded coordinates make React's hydration check fail.
const q = (v: number) => Math.round(v * 100) / 100;
const sx = (x: number) => q(x - X0);
const sy = (z: number) => q(Z1 - z);
const W = X1 - X0, H = Z1 - Z0;

// Each number field is as wide as what is typed in it (the condensed digits run wider than "0").
const fit = (text: string) => ({ width: `${Math.max(2, text.length) * 0.5 + 0.12}em` });

const deg = (v: number) =>`${v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}°`;
const same = (a: Angles, b: Angles) => a.theta1 === b.theta1 && a.theta2 === b.theta2 && a.theta3 === b.theta3;

function start(arm: ArmConfig) {
  const s = solve(arm, arm.home.r, arm.home.z);
  if (!s.ok) throw new Error(`home pose is not reachable: ${s.why}`);
  return s.angles;
}

function Capsule({ a, b, w }: { a: { x: number; z: number }; b: { x: number; z: number }; w: number }) {
  return (
    <>
      <line x1={sx(a.x)} y1={sy(a.z)} x2={sx(b.x)} y2={sy(b.z)} className={styles.edge} strokeWidth={w + 2.6} />
      <line x1={sx(a.x)} y1={sy(a.z)} x2={sx(b.x)} y2={sy(b.z)} className={styles.pla} strokeWidth={w} />
    </>
  );
}

// `arm` is read from config/*.yaml at build time by the page (lib/armConfig.ts).
export function ArmStage({ arm }: { arm: ArmConfig }) {
  const g = arm.geometry, workspace = arm.workspace, heartbeatHz = arm.heartbeatHz;
  const [r, setR] = useState<number>(Math.round(arm.home.r));
  const [z, setZ] = useState<number>(Math.round(arm.home.z));
  const [rText, setRText] = useState(String(Math.round(arm.home.r)));
  const [zText, setZText] = useState(String(Math.round(arm.home.z)));
  const [goal, setGoal] = useState<Angles>(() => start(arm));
  const [cur, setCur] = useState<Angles>(() => start(arm));
  const [seq, setSeq] = useState(1);
  const [why, setWhy] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragging = useRef(false);
  const dragged = useRef(false); // a drag just ended: ignore the click the browser sends after it
  const ids = useId();

  // A new target: solve it. If it is refused, the arm keeps its previous goal, like the real one.
  const aim = useCallback((nr: number, nz: number) => {
    setR(nr);
    setZ(nz);
    const s = solve(arm, nr, nz);
    if (!s.ok) return setWhy(s.why);
    if (!pulsesInRange(arm, pulses(arm, s.angles))) return setWhy("a servo pulse would be outside its calibrated range");
    setWhy(null);
    setGoal(s.angles);
  }, [arm]);

  // The laptop's heartbeat: 30 times a second, step the pose being sent toward the goal.
  useEffect(() => {
    if (same(cur, goal)) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setCur(goal);
      setSeq((n) => n + 1);
      return;
    }
    const t = setTimeout(() => {
      setCur((c) => stepToward(arm, c, goal));
      setSeq((n) => n + 1);
    }, 1000 / heartbeatHz);
    return () => clearTimeout(t);
  }, [cur, goal, arm, heartbeatHz]);

  const fromPointer = (e: { clientX: number; clientY: number }) => {
    const svg = svgRef.current;
    const m = svg?.getScreenCTM();
    if (!svg || !m) return;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    const nr = Math.round(Math.max(X0 + 10, Math.min(X1 - 10, p.x + X0)));
    const nz = Math.round(Math.max(0, Math.min(Z1 - 10, Z1 - p.y)));
    setRText(String(nr));
    setZText(String(nz));
    aim(nr, nz);
  };

  const typed = (text: string, which: "r" | "z") => {
    (which === "r" ? setRText : setZText)(text);
    const v = Number(text);
    if (text.trim() === "" || !Number.isFinite(v)) return;
    aim(which === "r" ? v : r, which === "z" ? v : z);
  };

  const pose = fk(arm, cur);
  const ghost = fk(arm, goal);
  const moving = !same(cur, goal);
  const p = pulses(arm, cur);
  // Base drawn from the config: the shoulder axis sits 50 mm above the lid (shoulder bracket, D18).
  const lid = Math.max(20, g.shoulderHeight - 50);
  const dir = { x: Math.cos(pose.phi), z: Math.sin(pose.phi) }; // along the hand
  const nrm = { x: -dir.z, z: dir.x }; // across it
  const along = (o: { x: number; z: number }, d: number, side = 0) => ({ x: o.x + dir.x * d + nrm.x * side, z: o.z + dir.z * d + nrm.z * side });
  const palm = along(pose.W, 39);

  const status = why
    ? `Not sent: ${why}. The arm stays where it was.`
    : moving
      ? "Moving. Every joint is paced to arrive at the same moment."
      : "Holding this pose.";

  return (
    <section className={styles.stage} aria-labelledby={`${ids}-h`}>
      <div className={styles.inner}>
        <h1 id={`${ids}-h`} className={styles.headline}>
          Put the gripper{" "}
          <span className={styles.field}>
            <input id={`${ids}-r`} aria-label="Millimetres out from the base" type="number" inputMode="numeric" value={rText} style={fit(rText)} onChange={(e) => typed(e.target.value, "r")} />
          </span>{" "}
          mm out and{" "}
          <span className={styles.field}>
            <input id={`${ids}-z`} aria-label="Millimetres up from the table" type="number" inputMode="numeric" value={zText} style={fit(zText)} onChange={(e) => typed(e.target.value, "z")} />
          </span>{" "}
          mm up.
        </h1>

        <div className={styles.drawing}>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className={styles.svg}
            role="img"
            aria-label="Side view of the arm on a 10 millimetre grid. The yellow marker is the target; type new numbers in the headline or drag the marker."
            onClick={(e) => {
              if (dragged.current) return void (dragged.current = false);
              fromPointer(e);
            }}
          >
            <defs>
              <pattern id={`${ids}-g10`} width="10" height="10" patternUnits="userSpaceOnUse" x={sx(0)} y={sy(0)}>
                <path d="M10 0 H0 V10" className={styles.grid10} />
              </pattern>
              <pattern id={`${ids}-g50`} width="50" height="50" patternUnits="userSpaceOnUse" x={sx(0)} y={sy(0)}>
                <path d="M50 0 H0 V50" className={styles.grid50} />
              </pattern>
            </defs>
            {/* the mat runs past the drawing and under the headline */}
            <rect x="-3000" y="-3000" width="6000" height={3000 + sy(0)} fill={`url(#${ids}-g10)`} />
            <rect x="-3000" y="-3000" width="6000" height={3000 + sy(0)} fill={`url(#${ids}-g50)`} />

            {/* the box of targets the arm accepts */}
            <rect
              x={sx(workspace.rMin)}
              y={sy(workspace.zMax)}
              width={workspace.rMax - workspace.rMin}
              height={workspace.zMax - workspace.zMin}
              className={styles.workspace}
            />
            <text x={sx(workspace.rMax)} y={sy(workspace.zMax) - 6} textAnchor="end" className={styles.note}>
              targets accepted in here
            </text>

            {/* table and its scale */}
            <line x1={0} y1={sy(0)} x2={W} y2={sy(0)} className={styles.table} />
            {[0, 50, 100, 150, 200, 250].map((x) => (
              <text key={x} x={sx(x)} y={sy(0) + 15} textAnchor="middle" className={styles.scale}>
                {x}
              </text>
            ))}
            {[100, 200, 300].map((zz) => (
              <text key={zz} x={sx(X1) - 4} y={sy(zz) + 4} textAnchor="end" className={styles.scale}>
                {zz}
              </text>
            ))}
            <text x={sx(X1) - 4} y={sy(0) + 15} textAnchor="end" className={styles.scale}>
              mm
            </text>

            {/* base: plate, casters, enclosure, lid, shoulder bracket */}
            <g className={styles.body}>
              <rect x={sx(-100)} y={sy(6)} width="200" height="6" />
              <rect x={sx(-78)} y={sy(10.5)} width="14" height="4.5" />
              <rect x={sx(64)} y={sy(10.5)} width="14" height="4.5" />
              <rect x={sx(-85)} y={sy(lid)} width="170" height={q(lid - 10.5)} />
              <path d={`M${sx(g.shoulderOffset - 22)} ${sy(lid)} V${sy(g.shoulderHeight)} a22 22 0 0 1 44 0 V${sy(lid)} Z`} />
            </g>

            {/* where it is heading, when that is not where it is */}
            {moving && (
              <polyline
                points={[ghost.S, ghost.E, ghost.W, ghost.T].map((q) => `${sx(q.x)},${sy(q.z)}`).join(" ")}
                className={styles.ghost}
              />
            )}

            {/* four-bar: crank, rod, lever */}
            <g className={styles.rod}>
              <line x1={sx(pose.S.x)} y1={sy(pose.S.z)} x2={sx(pose.C.x)} y2={sy(pose.C.z)} />
              <line x1={sx(pose.C.x)} y1={sy(pose.C.z)} x2={sx(pose.L.x)} y2={sy(pose.L.z)} />
              <line x1={sx(pose.E.x)} y1={sy(pose.E.z)} x2={sx(pose.L.x)} y2={sy(pose.L.z)} />
            </g>

            {/* links and hand, printed in black */}
            <Capsule a={pose.S} b={pose.E} w={17} />
            <Capsule a={pose.E} b={pose.W} w={14} />
            <Capsule a={pose.W} b={palm} w={11} />
            <Capsule a={along(pose.W, 39, -20)} b={along(pose.W, 39, 20)} w={7} />
            <Capsule a={along(pose.W, 39, -20)} b={along(pose.W, 104, -20)} w={5} />
            <Capsule a={along(pose.W, 39, 20)} b={along(pose.W, 104, 20)} w={5} />

            <g className={styles.pin}>
              <circle cx={sx(pose.C.x)} cy={sy(pose.C.z)} r="2.6" />
              <circle cx={sx(pose.L.x)} cy={sy(pose.L.z)} r="2.6" />
              <circle cx={sx(pose.S.x)} cy={sy(pose.S.z)} r="5" />
              <circle cx={sx(pose.E.x)} cy={sy(pose.E.z)} r="4" />
              <circle cx={sx(pose.W.x)} cy={sy(pose.W.z)} r="3.4" />
            </g>

            {/* the target: the same yellow as the numbers in the headline */}
            <g
              className={styles.target}
              data-refused={why !== null}
              transform={`translate(${sx(r)} ${sy(z)})`}
              onPointerDown={(e) => {
                dragging.current = true;
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
              onPointerMove={(e) => {
                if (!dragging.current) return;
                dragged.current = true;
                fromPointer(e);
              }}
              onPointerUp={(e) => {
                e.currentTarget.releasePointerCapture(e.pointerId);
                dragging.current = false;
              }}
              onPointerCancel={() => (dragging.current = false)}
            >
              <circle r="26" className={styles.hit} />
              <circle r="8" className={styles.ring} />
              <path d="M-15 0 H-4 M4 0 H15 M0 -15 V-4 M0 4 V15" className={styles.cross} />
            </g>
          </svg>
        </div>

        <div className={styles.readout}>
          <p className={styles.status} data-refused={why !== null} role="status">
            {status}
          </p>

          <div className="table-wrap">
            <table className={styles.table5}>
              <caption className="visually-hidden">What the laptop works out for this target</caption>
              <thead>
                <tr>
                  <th scope="col">Joint</th>
                  <th scope="col">Angle</th>
                  <th scope="col">Pulse, µs</th>
                </tr>
              </thead>
              <tbody className="num">
                {[
                  ["Base", "0.0°"],
                  ["Shoulder", deg(cur.theta1)],
                  ["Elbow", deg(cur.theta2)],
                  ["Wrist", deg(cur.theta3)],
                  ["Gripper", "open"],
                ].map(([name, angle], i) => (
                  <tr key={name}>
                    <th scope="row">{name}</th>
                    <td>{angle}</td>
                    <td>{p[i]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className={styles.sent}>
            <span>Sent to the Arduino</span>
            <code>{frame(seq, p)}</code>
          </p>

          <p className={styles.explain}>
            This is the arm&apos;s own maths running in your browser: inverse kinematics, then calibration, then the line of text
            the laptop sends {heartbeatHz} times a second, checksum included. The grid is to scale, 10 mm a square. The real arm
            is still being assembled.
          </p>
        </div>
      </div>
    </section>
  );
}
