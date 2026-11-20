"""V1 control server.

Run from the repo root:
    py -m arm.web.server              real Nano on the port in config/comms.yaml
    py -m arm.web.server --port COM5  real Nano on another port
    py -m arm.web.server --fake       no hardware: a simulated Nano (arm/comms/link.py FakeNano)
Then open http://localhost:8000 (or http://<laptop IP>:8000 on a phone on the same hotspot).

The browser only ever sends WISHES (arm, disarm, slider values). The Controller
(arm/control.py) decides what actually reaches the Nano: safe arming order, heartbeat,
dead-man rule, rejection of out-of-range targets.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from arm.calibration import load_calibration
from arm.comms.link import Link, open_link
from arm.config import JOINTS, load_arm
from arm.control import Controller
from arm.demo import PoseStore, move_and_wait, run_sequence
from arm.targets import point_to_joints

HERE = Path(__file__).parent
COMMS = yaml.safe_load((HERE.parents[1] / "config" / "comms.yaml").read_text(encoding="utf-8"))


def create_app(link: Link, poses_path: Path | None = None) -> FastAPI:
    cfg = load_arm()                      # fails at startup (not mid-run) if arm.yaml is broken
    controller = Controller(link, load_calibration(cfg), COMMS["heartbeat_hz"])
    app = FastAPI()
    app.state.controller = controller
    owner = {"socket": None}              # only ONE browser may drive the arm at a time
    store = PoseStore(poses_path) if poses_path else PoseStore()
    # Demo state: the running sequence (one at a time) and which step it is on.
    demo = {"task": None, "stop": asyncio.Event(), "step": None}

    def demo_status() -> dict:
        return {"poses": store.names(), "sequence_step": demo["step"],
                "sequence_running": demo["task"] is not None and not demo["task"].done()}

    async def stop_sequence() -> None:
        """Any manual input or a disarm interrupts a running sequence first (operator wins)."""
        t = demo["task"]
        if t is not None and not t.done():
            demo["stop"].set()
            await t
        demo["task"], demo["step"] = None, None

    @app.get("/")
    def index():
        return FileResponse(HERE / "index.html")

    @app.get("/config")
    def config():
        """Slider ranges and start values from config/arm.yaml, so the page hard-codes nothing."""
        joints = cfg.raw["joints"]
        park = controller.park_values()
        sliders = [{"name": n, "min": joints[n]["limits"][0], "max": joints[n]["limits"][1],
                    "start": park[i]} for i, n in enumerate(JOINTS)]
        g = cfg.raw["gripper"]
        sliders.append({"name": "j4_gripper_mm", "min": g["closed_mm"], "max": g["open_mm"],
                        "start": park[4]})
        h = cfg.raw["poses"]["home"]
        return {"sliders": sliders, "links": cfg.raw["links"], "workspace": cfg.workspace,
                "home": h, "base_limits": joints["j0_base"]["limits"]}

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        if owner["socket"] is not None:
            await socket.send_text(json.dumps({"type": "busy"}))
            await socket.close()
            return
        owner["socket"] = socket
        send = lambda obj: socket.send_text(json.dumps(obj))

        async def push_status():          # tell the page what the Nano says, 5x a second
            while True:
                await send({"type": "status", **controller.status(), **demo_status()})
                await asyncio.sleep(0.2)

        pusher = asyncio.create_task(push_status())
        try:
            while True:
                msg = json.loads(await socket.receive_text())
                kind = msg.get("type")
                if kind in ("arm", "disarm", "joints", "point", "gripper", "home", "goto_pose",
                            "run_sequence", "stop_sequence"):
                    await stop_sequence()
                if kind == "arm":
                    why = await controller.arm()
                    if why:
                        await send({"type": "error", "msg": why})
                    else:                 # sliders jump back to park: that's what is being sent
                        await send({"type": "pose", "values": controller.target_values})
                elif kind == "disarm":
                    await controller.disarm()
                elif kind == "joints":
                    why = controller.set_target(msg["deg"])
                    if why:
                        await send({"type": "error", "msg": "NOT SENT: " + why})
                elif kind in ("gripper", "home", "goto_pose"):
                    # One-press demo moves. Each builds a full 5-value pose and goes through the
                    # same set_target (limits, base clearance, ramp) as everything else.
                    goal = controller.goal_values or controller.park_values()
                    try:
                        if kind == "gripper":
                            g = cfg.raw["gripper"]
                            values = goal[:4] + [g["open_mm"] if msg.get("open") else g["closed_mm"]]
                        elif kind == "home":   # replaces the firmware H: IK runs here, ramp does the rest
                            h = cfg.raw["poses"]["home"]
                            values = point_to_joints(cfg, h["x"], h["y"], h["z"], h["pitch"]) + [goal[4]]
                        else:
                            values = store.get(str(msg.get("name")))
                    except (ValueError, KeyError) as e:
                        await send({"type": "error", "msg": f"NOT SENT: {e}"})
                        continue
                    why = controller.set_target(values)
                    if why:
                        await send({"type": "error", "msg": "NOT SENT: " + why})
                    else:
                        await send({"type": "pose", "values": values, "point": True})
                elif kind == "save_pose":       # store where the arm is being SENT now (not the goal)
                    if controller.target_values is None:
                        await send({"type": "error", "msg": "arm first: nothing to save yet"})
                        continue
                    try:
                        store.save(str(msg.get("name", "")), controller.target_values)
                        await send({"type": "info", "msg": f"saved pose {msg['name'].strip()!r}"})
                    except ValueError as e:
                        await send({"type": "error", "msg": str(e)})
                elif kind == "delete_pose":
                    store.delete(str(msg.get("name")))
                elif kind == "run_sequence":
                    names = msg.get("names") or store.names()
                    try:
                        steps = [(n, store.get(n)) for n in names]
                    except KeyError as e:
                        await send({"type": "error", "msg": str(e)})
                        continue
                    demo["stop"] = asyncio.Event()

                    async def on_step(i, name):
                        demo["step"] = f"{i}/{len(steps)}: {name}"

                    async def run():
                        why = await run_sequence(controller, steps, stop=demo["stop"], on_step=on_step)
                        demo["step"] = None
                        if why and why.endswith("stopped"):
                            reply = {"type": "info", "msg": "sequence stopped"}
                        elif why:
                            reply = {"type": "error", "msg": "SEQUENCE STOPPED at " + why}
                        else:
                            reply = {"type": "info", "msg": f"sequence done ({len(steps)} poses)"}
                        try:
                            await send(reply)
                        except Exception:        # the browser may have gone; the run is over anyway
                            pass
                    demo["task"] = asyncio.create_task(run())
                elif kind == "stop_sequence":
                    pass                         # already stopped above
                elif kind == "point":          # point-and-go: IK on the laptop, then ramp
                    try:
                        joints = point_to_joints(cfg, float(msg["x"]), float(msg["y"]),
                                                 float(msg["z"]), float(msg["pitch"]))
                    except (ValueError, KeyError, TypeError) as e:
                        await send({"type": "error", "msg": f"NOT SENT: {e}"})
                        continue
                    goal = controller.goal_values or controller.park_values()
                    values = joints + [goal[4]]   # keep the gripper as it is
                    why = controller.set_target(values)
                    if why:
                        await send({"type": "error", "msg": "NOT SENT: " + why})
                    else:                     # sliders show where the arm is heading
                        await send({"type": "pose", "values": values, "point": True})
        except WebSocketDisconnect:
            pass
        finally:
            # Dead-man rule: the person controlling the arm is gone, so the arm stops.
            pusher.cancel()
            await stop_sequence()
            if controller.armed:
                await controller.disarm()
                print("browser disconnected while armed -> disarmed")
            owner["socket"] = None

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=COMMS["port"], help="serial port, e.g. COM14")
    ap.add_argument("--fake", action="store_true", help="simulated Nano, no hardware")
    args = ap.parse_args()

    print("opening", "simulated Nano" if args.fake else args.port, "...")
    link = open_link(args.port, COMMS["baud"], COMMS["banner_timeout_s"], args.fake)
    print(f"Nano ready: firmware {link.firmware}, state {link.state}")
    try:
        # 0.0.0.0 = reachable from your phone on the same network, not just this laptop.
        uvicorn.run(create_app(link), host="0.0.0.0", port=8000)
    finally:
        if link.connected:
            link.send("D")                # never leave the arm armed when the server stops
        link.close()


if __name__ == "__main__":
    main()
