"""V1 control server (step 1: skeleton).

Run from the repo root:   py -m arm.web.server
Then open:                http://localhost:8000

Two jobs:
  1. GET /      -> send the control page (index.html) once.
  2. WS  /ws    -> a long-lived two-way pipe. The browser sends joint angles in
                   degrees; later steps turn them into pulses and send them to the Nano.
"""
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from arm.calibration import load_calibration
from arm.comms.link import FakeLink
from arm.config import JOINTS, load_arm

HERE = Path(__file__).parent
cfg = load_arm()  # fails at startup (not mid-run) if arm.yaml is broken
calibration = load_calibration(cfg)
link = FakeLink()  # step 5 swaps this for the real serial port
app = FastAPI()


@app.get("/")
def index():
    return FileResponse(HERE / "index.html")


@app.get("/config")
def config():
    """Slider ranges and start values, read from config/arm.yaml so the page hard-codes nothing."""
    joints = cfg.raw["joints"]
    park = cfg.raw["poses"]["park"]
    sliders = [
        {"name": name, "min": joints[name]["limits"][0], "max": joints[name]["limits"][1],
         "start": park[theta]}
        for name, theta in zip(JOINTS, ("theta0", "theta1", "theta2", "theta3"))
    ]
    g = cfg.raw["gripper"]
    sliders.append({"name": "j4_gripper_mm", "min": g["closed_mm"], "max": g["open_mm"],
                    "start": g["open_mm"]})
    return {"sliders": sliders}


@app.websocket("/ws")
async def ws(socket: WebSocket):
    await socket.accept()
    print("browser connected")
    try:
        while True:
            msg = json.loads(await socket.receive_text())
            if msg.get("type") == "joints":
                deg = msg["deg"]
                try:
                    pulses = calibration.to_pulses(deg)       # step 3 (Vyom's function)
                except ValueError as e:
                    # The "clear no": send NOTHING to the arm, tell the page why.
                    await socket.send_text(json.dumps({"type": "error", "msg": str(e)}))
                    continue
                line = link.send("C", *pulses)                 # step 4: protocol frame
                await socket.send_text(json.dumps(
                    {"type": "sent", "deg": deg, "us": pulses, "line": line.strip()}))
    except WebSocketDisconnect:
        # Step 5: this is where we will tell the Nano to hold still (dead-man rule).
        print("browser disconnected")


if __name__ == "__main__":
    # 0.0.0.0 = reachable from your phone on the same Wi-Fi, not just this laptop.
    uvicorn.run(app, host="0.0.0.0", port=8000)
