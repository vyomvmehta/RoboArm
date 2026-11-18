"use client";
import { PointerEvent, useRef } from "react";
import { ArmData, Pose, chain } from "@/lib/arm";

const ORANGE = "#FF6A1A";
const CYAN = "#22D3EE";

interface Props {
  arm: ArmData;
  pose: Pose;
  active: number | null; // joint index highlighted, or null
  showFourBar: boolean;
  target: { r: number; z: number } | null; // IK target crosshair
  targetOk: boolean;
  onTarget?: (r: number, z: number) => void;
}

/**
 * Side-view schematic of the arm, drawn in millimetres straight from config/arm.yaml.
 * It is a diagram, not a render: the CAD assembly is not in the repo yet.
 */
export default function Schematic({ arm, pose, active, showFourBar, target, targetOk, onTarget }: Props) {
  const svg = useRef<SVGSVGElement | null>(null);
  const dragging = useRef(false);
  const c = chain(arm, pose);
  const Y = (z: number) => -z; // z up -> SVG y down
  const { l1, l2, l3 } = arm.links;
  const ws = arm.workspace;
  const [sr, sz] = c.shoulder;

  const toMm = (e: PointerEvent) => {
    const pt = svg.current!.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(svg.current!.getScreenCTM()!.inverse());
    return { r: p.x, z: -p.y };
  };
  const drag = (e: PointerEvent) => {
    if (!onTarget) return;
    const { r, z } = toMm(e);
    onTarget(Math.round(r), Math.round(z));
  };

  const link = (a: [number, number], b: [number, number], w: number, key: string) => (
    <g>
      <line x1={a[0]} y1={Y(a[1])} x2={b[0]} y2={Y(b[1])} stroke="rgba(255,255,255,0.28)" strokeWidth={w + 2} strokeLinecap="round" />
      <line x1={a[0]} y1={Y(a[1])} x2={b[0]} y2={Y(b[1])} stroke="#161C24" strokeWidth={w} strokeLinecap="round" />
      <line x1={a[0]} y1={Y(a[1])} x2={b[0]} y2={Y(b[1])} stroke="rgba(255,255,255,0.22)" strokeWidth="0.6" strokeDasharray="5 3" />
    </g>
  );

  const joint = (p: [number, number], idx: number, r: number) => {
    const on = active === idx;
    return (
      <g>
        {on && (
          <circle cx={p[0]} cy={Y(p[1])} r={r + 4} fill="none" stroke={ORANGE} strokeWidth="1">
            <animate attributeName="r" values={`${r + 3};${r + 12};${r + 3}`} dur="1.8s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.9;0;0.9" dur="1.8s" repeatCount="indefinite" />
          </circle>
        )}
        <circle cx={p[0]} cy={Y(p[1])} r={r} fill="#0B0D10" stroke={on ? ORANGE : "rgba(243,244,246,0.75)"} strokeWidth={on ? 2 : 1.2} />
        <circle cx={p[0]} cy={Y(p[1])} r="1.6" fill={on ? ORANGE : "#F3F4F6"} />
      </g>
    );
  };

  // Angle arc for the active planar joint: from the reference direction to the link direction.
  const arc = (centre: [number, number], fromDeg: number, toDeg: number, r: number) => {
    const pt = (d: number) => [centre[0] + r * Math.cos((d * Math.PI) / 180), Y(centre[1] + r * Math.sin((d * Math.PI) / 180))];
    const [x0, y0] = pt(fromDeg);
    const [x1, y1] = pt(toDeg);
    const sweep = toDeg > fromDeg ? 0 : 1;
    const large = Math.abs(toDeg - fromDeg) > 180 ? 1 : 0;
    const ref = pt(fromDeg).map((v, i) => (i === 0 ? centre[0] + (v - centre[0]) * 1.5 : Y(centre[1]) + (v - Y(centre[1])) * 1.5));
    return (
      <g>
        <line x1={centre[0]} y1={Y(centre[1])} x2={ref[0]} y2={ref[1]} stroke={ORANGE} strokeOpacity="0.5" strokeWidth="0.8" strokeDasharray="3 3" />
        <path d={`M ${x0} ${y0} A ${r} ${r} 0 ${large} ${sweep} ${x1} ${y1}`} fill="none" stroke={ORANGE} strokeWidth="1.2" />
      </g>
    );
  };

  // Gripper: palm behind the grasp point, two jaws either side of it.
  const phi = (c.pitch * Math.PI) / 180;
  const ux = Math.cos(phi);
  const uz = Math.sin(phi);
  const nx = -uz;
  const nz = ux;
  const palm: [number, number] = [c.tip[0] - ux * 26, c.tip[1] - uz * 26];
  const half = pose.grip / 2;
  const jaw = (s: 1 | -1) => {
    const a: [number, number] = [palm[0] + nx * half * s, palm[1] + nz * half * s];
    const b: [number, number] = [c.tip[0] + ux * 8 + nx * (half - 3) * s, c.tip[1] + uz * 8 + nz * (half - 3) * s];
    return <line x1={a[0]} y1={Y(a[1])} x2={b[0]} y2={Y(b[1])} stroke={active === 4 ? ORANGE : "#F3F4F6"} strokeWidth="3" strokeLinecap="round" />;
  };

  // Four-bar: the elbow servo sits at the shoulder; a rod parallel to the upper arm
  // sets the forearm's absolute angle (calibration.yaml, four_bar_window).
  const a12 = ((pose.t1 + pose.t2) * Math.PI) / 180;
  const crank = 24;
  const fb0: [number, number] = [sr - crank * Math.cos(a12), sz - crank * Math.sin(a12)];
  const fb1: [number, number] = [c.elbow[0] - crank * Math.cos(a12), c.elbow[1] - crank * Math.sin(a12)];

  const yawR = 30;
  const yawC: [number, number] = [262, -262];
  const yaw = (pose.t0 * Math.PI) / 180;
  const [yLo, yHi] = arm.joints[0].limits!;

  const grid: number[] = [];
  for (let v = -50; v <= 300; v += 50) grid.push(v);

  return (
    <svg
      ref={svg}
      viewBox="-80 -310 400 340"
      className={`h-full w-full select-none ${onTarget ? "cursor-crosshair touch-none" : ""}`}
      role="img"
      aria-label="Side-view schematic of the RoboArm showing base, shoulder, elbow, wrist and gripper"
      onPointerDown={(e) => {
        if (!onTarget) return;
        dragging.current = true;
        e.currentTarget.setPointerCapture(e.pointerId);
        drag(e);
      }}
      onPointerMove={(e) => dragging.current && drag(e)}
      onPointerUp={() => (dragging.current = false)}
      onPointerCancel={() => (dragging.current = false)}
    >
      {/* blueprint grid, 50 mm */}
      <g stroke="rgba(255,255,255,0.05)" strokeWidth="0.6">
        {grid.map((v) => (
          <line key={`v${v}`} x1={v} y1={-310} x2={v} y2={30} />
        ))}
        {grid.map((v) => (
          <line key={`h${v}`} x1={-80} y1={Y(v)} x2={320} y2={Y(v)} />
        ))}
      </g>
      <g className="font-mono" fontSize="6.5" fill="rgba(139,148,163,0.8)">
        {[100, 200, 300].map((v) => (
          <text key={v} x={v + 2} y={12}>
            {v} mm
          </text>
        ))}
        {[100, 200].map((v) => (
          <text key={v} x={-78} y={Y(v) - 2}>
            z {v}
          </text>
        ))}
      </g>

      {/* pick zone from arm.yaml workspace, and the fully stretched reach */}
      <rect x={ws.rMin} y={Y(Math.min(ws.zMax, 60))} width={ws.rMax - ws.rMin} height={Math.min(ws.zMax, 60) - ws.zMin} fill="rgba(34,211,238,0.05)" stroke={CYAN} strokeOpacity="0.35" strokeWidth="0.7" strokeDasharray="4 3" />
      <text x={ws.rMin + 3} y={Y(Math.min(ws.zMax, 60)) - 3} className="font-mono" fontSize="6.5" fill={CYAN} fillOpacity="0.8">
        PICK ZONE r {ws.rMin}-{ws.rMax}
      </text>
      <path
        d={`M ${sr + (l1 + l2 + l3)} ${Y(sz)} A ${l1 + l2 + l3} ${l1 + l2 + l3} 0 0 0 ${sr} ${Y(sz + l1 + l2 + l3)}`}
        fill="none"
        stroke="rgba(255,255,255,0.14)"
        strokeWidth="0.7"
        strokeDasharray="2 5"
      />

      {/* table */}
      <line x1={-80} y1={0} x2={320} y2={0} stroke="rgba(243,244,246,0.5)" strokeWidth="1" />
      <g stroke="rgba(255,255,255,0.12)" strokeWidth="0.6">
        {Array.from({ length: 34 }, (_, i) => (
          <line key={i} x1={-80 + i * 12} y1={0} x2={-86 + i * 12} y2={8} />
        ))}
      </g>

      {/* base enclosure, turntable, shoulder bracket */}
      <rect x={-55} y={Y(46)} width={110} height={46} fill="#11161C" stroke={active === 0 ? ORANGE : "rgba(243,244,246,0.5)"} strokeWidth="1" />
      <rect x={-38} y={Y(56)} width={76} height={10} fill="#161C24" stroke={active === 0 ? ORANGE : "rgba(243,244,246,0.5)"} strokeWidth="1" />
      <path d={`M -14 ${Y(56)} L ${sr - 12} ${Y(sz)} L ${sr + 12} ${Y(sz)} L 30 ${Y(56)} Z`} fill="#161C24" stroke="rgba(243,244,246,0.4)" strokeWidth="1" />
      <line x1={0} y1={Y(-6)} x2={0} y2={Y(66)} stroke={active === 0 ? ORANGE : "rgba(255,255,255,0.3)"} strokeWidth="0.7" strokeDasharray="6 2 1 2" />
      <text x={-50} y={Y(20)} className="font-mono" fontSize="6" fill="rgba(139,148,163,0.9)">
        NANO + PCA9685
      </text>

      {showFourBar && (
        <g>
          <line x1={sr} y1={Y(sz)} x2={fb0[0]} y2={Y(fb0[1])} stroke={CYAN} strokeWidth="2" strokeLinecap="round" />
          <line x1={fb0[0]} y1={Y(fb0[1])} x2={fb1[0]} y2={Y(fb1[1])} stroke={CYAN} strokeWidth="1.4" />
          <line x1={c.elbow[0]} y1={Y(c.elbow[1])} x2={fb1[0]} y2={Y(fb1[1])} stroke={CYAN} strokeWidth="2" strokeLinecap="round" />
          <circle cx={fb0[0]} cy={Y(fb0[1])} r="2" fill={CYAN} />
          <circle cx={fb1[0]} cy={Y(fb1[1])} r="2" fill={CYAN} />
        </g>
      )}

      {link(c.shoulder, c.elbow, 15, "l1")}
      {link(c.elbow, c.wrist, 12, "l2")}
      {link(c.wrist, palm, 8, "l3")}
      <line x1={palm[0] - nx * (half + 2)} y1={Y(palm[1] - nz * (half + 2))} x2={palm[0] + nx * (half + 2)} y2={Y(palm[1] + nz * (half + 2))} stroke="#F3F4F6" strokeWidth="3" strokeLinecap="round" />
      {jaw(1)}
      {jaw(-1)}

      {active === 1 && arc(c.shoulder, 0, pose.t1, 26)}
      {active === 2 && arc(c.elbow, pose.t1, pose.t1 + pose.t2, 24)}
      {active === 3 && arc(c.wrist, pose.t1 + pose.t2, c.pitch, 20)}

      {joint(c.shoulder, 1, 9)}
      {joint(c.elbow, 2, 8)}
      {joint(c.wrist, 3, 6)}

      {/* grasp point */}
      <circle cx={c.tip[0]} cy={Y(c.tip[1])} r="2" fill={CYAN} />

      {target && (
        <g stroke={targetOk ? CYAN : "#F87171"} strokeWidth="1" fill="none">
          <circle cx={target.r} cy={Y(target.z)} r="7" />
          <line x1={target.r - 12} y1={Y(target.z)} x2={target.r + 12} y2={Y(target.z)} />
          <line x1={target.r} y1={Y(target.z) - 12} x2={target.r} y2={Y(target.z) + 12} />
        </g>
      )}

      {/* top-view yaw dial for J0 */}
      <g>
        <circle cx={yawC[0]} cy={yawC[1]} r={yawR} fill="rgba(11,13,16,0.7)" stroke="rgba(255,255,255,0.14)" strokeWidth="0.8" />
        <path
          d={`M ${yawC[0] + yawR * Math.cos((yLo * Math.PI) / 180)} ${yawC[1] - yawR * Math.sin((yLo * Math.PI) / 180)} A ${yawR} ${yawR} 0 0 0 ${yawC[0] + yawR * Math.cos((yHi * Math.PI) / 180)} ${yawC[1] - yawR * Math.sin((yHi * Math.PI) / 180)}`}
          fill="none"
          stroke={active === 0 ? ORANGE : "rgba(243,244,246,0.5)"}
          strokeWidth="1.4"
        />
        <line x1={yawC[0]} y1={yawC[1]} x2={yawC[0] + (yawR - 4) * Math.cos(yaw)} y2={yawC[1] - (yawR - 4) * Math.sin(yaw)} stroke={active === 0 ? ORANGE : "#F3F4F6"} strokeWidth="2" strokeLinecap="round" />
        <circle cx={yawC[0]} cy={yawC[1]} r="2.5" fill={active === 0 ? ORANGE : "#F3F4F6"} />
        <text x={yawC[0] - yawR} y={yawC[1] + yawR + 10} className="font-mono" fontSize="6.5" fill="rgba(139,148,163,0.9)">
          TOP VIEW · J0 YAW
        </text>
      </g>
    </svg>
  );
}
