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

HERE = Path(__file__).parent
COMMS = yaml.safe_load((HERE.parents[1] / "config" / "comms.yaml").read_text(encoding="utf-8"))


def create_app(link: Link) -> FastAPI:
    cfg = load_arm()                      # fails at startup (not mid-run) if arm.yaml is broken
    controller = Controller(link, load_calibration(cfg), COMMS["heartbeat_hz"])
    app = FastAPI()
    app.state.controller = controller
    owner = {"socket": None}              # only ONE browser may drive the arm at a time

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
        return {"sliders": sliders}

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
                await send({"type": "status", **controller.status()})
                await asyncio.sleep(0.2)

        pusher = asyncio.create_task(push_status())
        try:
            while True:
                msg = json.loads(await socket.receive_text())
                kind = msg.get("type")
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
        except WebSocketDisconnect:
            pass
        finally:
            # Dead-man rule: the person controlling the arm is gone, so the arm stops.
            pusher.cancel()
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
