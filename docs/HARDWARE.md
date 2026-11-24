# Hardware checklist (the shop run)

Created 2026-11-24 by Claude for Vyom. Tick items off as they're bought, like
[CHECKLIST.md](CHECKLIST.md). Every size is read out of the CAD, not guessed: the base from
`SolidWorks Parts/Base/grap_base_pivot.py`, the arm from `tools/cad/build_arm.py`,
`build_arm_encased.py`, `build_arm_human.py`, the gripper from `tools/cad/build_gripper.py`.
§7 lists the three things this checklist does **not** settle.

**Where to buy.** The EMS Material Store catalogue is behind UW sign-in at `ems.uwaterloo.ca`,
so the stock below is what we need, not what they're confirmed to have. **Watcard or UW account
number only — no cash, debit or credit.** EMS is **E3-2121**, Mon–Fri 8:45–4:15. ESMS is in
**E5**. RidgidWare (EngSoc, **PSE 1419**) also sells nuts, bolts and screws — that's where the
M3 was borrowed from on Nov 13, and it's likely the better bet for small fasteners.

## 1. Do these three before leaving

- [ ] **Open the servo bags.** 3 MG996R + 2 MG90S came as complete servos, so four tab screws
      and a horn centre screw each should already be in there. That's roughly 12 screws —
      it cancels most of §2 and the two self-tapping servo-tab lines in §3.
- [ ] **Count the 608 bearings already in hand** before buying six in §5. At least one went
      into the Nov 20 press-fit test.
- [ ] **Decide the wheel axle** (see the box in §5). It changes what you buy.

## 2. M2 — self-tapping, and **no M2 nuts anywhere**

Every M2 in the build threads straight into printed plastic, so no M2 nuts and no M2 washers are
needed at all. Pan head or cheese head — countersunk will not seat in any of these.

- [ ] **20 × M2 × 8 self-tapping** — 10 needed: wrist MG90S into the Forearm (2), Wrist Bracket
      onto the wrist horn (2), gripper MG90S into the body (2), Pinion onto the gripper horn (2),
      rack hold-downs (2)
- [ ] **10 × M2 × 10 self-tapping** — 6 needed: Fingers + Thumb onto the rack stems (4),
      Gripper Cover onto its two posts (2)

The spares aren't padding: these are the screws most likely to strip a printed pilot on the
second attempt.

## 3. M3 — self-tapping into printed pilots

- [ ] **10 × M3 × 6** — 8 needed: servo bridge feet into the box floor (4), base MG996R tab
      holes into the bridge (4)
- [ ] **10 × M3 × 8** — 8 needed: four wheel forks into the box floor, 2 screws each
- [ ] **8 × M3 × 10** — 5 needed: Upper Arm onto the shoulder horn (2), Crank onto the elbow
      horn (2), planet gear onto the turntable horn (1 — only the inner hole lands, see §7)
- [ ] **6 × M3 × 16** — 4 needed: lid down into the box wall corners

> **The bridge feet must be 6 mm, not 8.** The box floor is 5 thick and the pilot is 4.5 deep,
> so an 8 would jack the foot off the floor or burst out through the bottom of the box.

## 4. M3 — machine screws and nuts

- [ ] **6 × M3 × 12** — 4 needed: 2 shoulder MG996R into the Shoulder Bracket towers, 2 per
      servo, into the nut pockets on the towers' outer faces
- [ ] **6 × M3 × 30** — 4 needed: Shoulder Caps, through cap + tower + servo tab, 2 per servo,
      nut in the cap's boss. *The long ones — easy to forget.*
- [ ] **12 × M3 × 16** — 10 needed: lid to Shoulder Bracket on the 40 × 60 pattern (4), both
      skins into their heat-set inserts (4), four-bar rod pins (2)
- [ ] **4 × M3 × 20** — 2 needed: gripper onto the Wrist Bracket plate, captive nuts in the deck
- [ ] **16 × plain M3 nuts** — 14 needed: 4 tower + 4 cap + 4 lid-to-bracket + 2 gripper
- [ ] **4 × M3 nylock nuts** — 2 needed: the four-bar rod pins. Snug, then back off about a
      quarter turn so the rod still swivels (D19).

Only if the electronics tray gets printed later:

- [ ] **4 × M3 × 50** — replaces the 4 × M3 × 16 lid screws, because the bolt then runs
      lid → tray → box corner. Not yet: Plate 10 is still waiting on the board hole patterns.

## 5. M8 and the bearings

- [ ] **2 × M8 × 25 hex bolt** — 1 needed: turntable pivot, head captive under the base plate
- [ ] **2 × M8 × 30 bolt** — 1 needed: elbow, clamping only the 608's inner race
- [ ] **4 × M8 nuts** — 2 needed (pivot, elbow)
- [ ] **4 × M8 washers** — 1 needed (elbow)
- [ ] **5 × 8 mm plain dowel pin, 19 mm** — 4 needed: the wheel-fork axles. Read the box below
      first; M8 × 20 bolts are the fallback.
- [ ] **6 × 608ZZ bearing** (22 × 8 × 7) — 4 wheels + 1 pivot + 1 elbow, minus whatever §1 found

> **The wheel axles are not in the CAD.** `fork_part()` bores 8.2 mm through both rails and the
> assembly puts a bare 608 ring there with nothing through it — no axle part in the STEP, no
> bolt. The bore is also blind 1.5 mm short of the outer face, so a nut cannot go on. As drawn it
> takes a **19 mm plain 8 mm pin** pushed in from the inside, or an M8 × 20 bolt with its head
> against the inner rail and nothing retaining the far end. Buy the dowels: an M8 thread turning
> inside a 608's inner race is point contact on the race. This wants a decision before the forks
> go in.

## 6. Everything else

- [ ] **4 × M3 brass heat-set inserts** for 4.0 × 4.0 holes — 2 in the Upper Arm, 2 in the
      Forearm, holding the two skins. Usually sold in packs; a soldering iron with a plain
      conical tip sets them.
- [ ] **An M3 tap** — or confirm in §1 that the servo screws fit. The aluminium horn holes are
      3.0 mm (D15), which is a thread-forming size, not a clearance size.
- [ ] *Optional:* **4 × M4 × 20 + 4 M4 nuts + 8 M4 washers** — the base plate has four 4.5 mm
      holes on a 184 mm circle for bolting it to a board or the bench. Wood screws do instead.
- [ ] *Cable route only (D20):* **a hollow M8 bolt, 4.5–5 mm bore.** Specialty item, unlikely to
      be on a campus shelf. The plain M8 × 30 is the fallback and changes nothing mechanically.

No thread locker is needed anywhere — the nylock and the printed pilots do that job.

## 7. What this checklist does not settle

- [ ] **Measure the horn blade thickness and the horn hole diameter** — two caliper readings.
      The planet gear's pocket is 2.0, deliberately at or under every plausible blade, and its
      tap holes are 2.4, right for M3 and drillable up if they turn out to be M4.
- [ ] **Decide whether to grow the planet gear's top plate to about radius 27.** It stops at
      23.75 and the outer horn screw sits at 25.0, so one of the two screws has nothing under
      it. Fixing it is a reprint of one small part.
- [ ] **Re-check Siddharth's 12 floor pilot positions** — they may be 2 mm out, because
      `SERVO_SHAFT_OFFSET` went 10.0 → 8.0 and carried the servo bridge with it.

## Printed-hole sizes this list assumes

D15, re-measured Nov 20: M3 clearance 3.45 · M3 nut pocket 5.6 AF × 4.2 deep · M3 self-tapping
pilot 2.5 · M2 clearance 2.4 · M2 self-tapping pilot 1.8 (1.6 at the two servo horns) ·
heat-set insert hole 4.0 × 4.0 deep.
