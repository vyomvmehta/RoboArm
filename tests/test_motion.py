"""Spec for arm/motion.py step_toward (the laptop ramp). These fail until Vyom writes it."""
from arm.motion import step_toward

STEP = [1.5, 1.5, 1.5, 3.0, 0.7]  # 45/45/45/90 deg/s and ~20 mm/s at 30 Hz


def test_a_big_request_moves_at_most_one_step_per_joint():
    new = step_toward([0, 0, 0, 0, 30], [90, -60, 40, -90, 40], STEP)
    for old, n, s in zip([0, 0, 0, 0, 30], new, STEP):
        assert abs(n - old) <= s + 1e-9


def test_it_moves_toward_the_goal_in_both_directions():
    new = step_toward([0, 0, 0, 0, 30], [90, -60, 40, -90, 26], STEP)
    assert new[0] > 0 and new[1] < 0 and new[2] > 0 and new[3] < 0 and new[4] < 30


def test_never_overshoots_and_lands_exactly_on_the_goal():
    new = step_toward([10, 10, 10, 10, 30], [10.5, 9.2, 10, 11, 30.3], STEP)
    assert new == [10.5, 9.2, 10, 11, 30.3]


def test_repeated_ticks_reach_the_goal_and_stay_there():
    pose, goal = [0, 90, -130, -40, 40], [20, 30, -80, -40, 26]
    for _ in range(200):
        pose = step_toward(pose, goal, STEP)
    assert pose == goal
    assert step_toward(pose, goal, STEP) == goal


def test_all_joints_arrive_on_the_same_tick():
    # Vyom's choice (Nov 15): base has 60 deg to go, elbow only 10 -> they still finish together.
    pose, goal = [0, 0, 0, 0, 30], [60, 0, 10, 0, 30]
    arrived = {}
    for tick in range(1, 100):
        pose = step_toward(pose, goal, STEP)
        for i in (0, 2):
            if pose[i] == goal[i]:
                arrived.setdefault(i, tick)
    assert arrived[0] == arrived[2] == 40          # 60 deg at 1.5 deg/tick = 40 ticks


def test_current_is_not_modified():
    current = [0, 0, 0, 0, 30]
    step_toward(current, [90, 90, 90, 90, 40], STEP)
    assert current == [0, 0, 0, 0, 30]


def test_a_zero_speed_freezes_that_joint_instead_of_crashing():
    # PR #11 review (Ishaan): a 0 in arm.yaml used to raise ZeroDivisionError.
    new = step_toward([0, 0, 0, 0, 30], [10, 5, 0, 0, 30], [0, 1, 1, 1, 1])
    assert new[0] == 0                 # frozen joint stays put
    assert new[1] == 1                 # the others still move at their limit


def test_all_joints_frozen_returns_current():
    assert step_toward([1, 2, 3, 4, 30], [9, 9, 9, 9, 40], [0] * 5) == [1, 2, 3, 4, 30]
