import math
from types import SimpleNamespace
import unittest

from gesto.gestures import GestureConfig, GestureDetector, State, hand_sample


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.detector = GestureDetector()
        self.now = -30
        self.events = []

    def sample(self, x, y=0.5, *, delta=30, hand="Right"):
        self.now += delta
        point = None if x is None else (x, y)
        event = self.detector.update(self.now, point, hand)
        if event is not None:
            self.events.append(event)
        return event

    def steady(self, x=0.5, frames=16):
        for _ in range(frames):
            self.sample(x)

    def swipe(self, start=0.5, end=0.1, *, frames=15, y_end=0.5, delta=30):
        for i in range(1, frames + 1):
            fraction = i / frames
            self.sample(start + (end - start) * fraction,
                        0.5 + (y_end - 0.5) * fraction, delta=delta)

    def test_left_swipe_advances_once(self):
        self.steady()
        self.assertEqual(self.detector.state, State.READY)
        self.swipe()
        self.assertEqual([event.action for event in self.events], ["next"])
        self.assertGreaterEqual(self.events[0].duration_ms, 150)

    def test_right_swipe_goes_back_once(self):
        self.steady()
        self.swipe(end=0.9)
        self.assertEqual([event.action for event in self.events], ["previous"])

    def test_return_and_held_hand_do_not_repeat_action(self):
        self.steady()
        self.swipe()
        self.swipe(start=0.1, end=0.5)
        self.steady(frames=60)
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.detector.state, State.READY)

    def test_another_gesture_after_cooldown_and_stability(self):
        self.steady()
        self.swipe()
        self.steady(x=0.1, frames=60)
        self.swipe(start=0.1, end=0.5)
        self.assertEqual([event.action for event in self.events], ["next", "previous"])

    def test_noise_and_stationary_hand_emit_nothing(self):
        for index in range(200):
            self.sample(0.5 + 0.009 * math.sin(index), 0.5 + 0.005 * math.cos(index))
        self.assertEqual(self.events, [])

    def test_vertical_and_diagonal_movements_emit_nothing(self):
        for end_x in (0.5, 0.9):
            with self.subTest(end_x=end_x):
                self.setUp()
                self.steady()
                self.swipe(end=end_x, y_end=0.9)
                self.steady(x=end_x)
                self.assertEqual(self.events, [])

    def test_slow_movement_expires(self):
        self.steady()
        self.swipe(frames=80)
        self.assertEqual(self.events, [])

    def test_instantaneous_jump_and_hold_emit_nothing(self):
        self.steady()
        self.sample(0.05)
        self.steady(x=0.05, frames=50)
        self.assertEqual(self.events, [])

    def test_loss_of_hand_requires_stability_before_new_gesture(self):
        self.steady()
        self.swipe(end=0.4, frames=5)
        self.sample(None, delta=150)
        self.assertEqual(self.detector.state, State.NO_HAND)
        self.swipe(start=0.4, end=0.1)
        self.assertEqual(self.events, [])

    def test_short_dropout_preserves_continuous_swipe(self):
        self.steady()
        self.swipe(end=0.35, frames=7)
        self.sample(None)
        self.assertEqual(self.detector.state, State.OCCLUDED)
        self.sample(0.30)
        self.swipe(start=0.30, end=0.10, frames=8)
        self.assertEqual([event.action for event in self.events], ["next"])

    def test_brief_loss_never_emits_action_on_its_own(self):
        self.steady()
        self.swipe(end=0.35, frames=7)
        for _ in range(3):
            self.assertIsNone(self.sample(None))
        self.assertEqual(self.events, [])

    def test_distant_reappearance_does_not_join_hands(self):
        self.steady()
        self.swipe(end=0.40, frames=5)
        self.sample(None)
        self.sample(0.10)
        self.steady(x=0.1)
        self.assertEqual(self.events, [])

    def test_dropout_does_not_count_toward_initial_stability(self):
        self.sample(0.5)
        self.sample(0.5, delta=240)
        self.sample(None)
        self.sample(0.5)
        self.assertEqual(self.detector.state, State.STABILIZING)

    def test_timeout_records_displacement_for_diagnosis(self):
        self.steady()
        reasons = []
        for index in range(1, 61):
            self.sample(0.5 - 0.15 * index / 60)
            reasons.append(self.detector.reason)
        self.assertTrue(any("Barrido vencido" in reason and "dx=" in reason for reason in reasons))

    def test_configured_threshold_accepts_shorter_slower_swipe(self):
        self.detector = GestureDetector(GestureConfig(distance=0.16, max_duration_ms=1000))
        self.steady()
        self.swipe(end=0.25, frames=50)
        self.assertEqual([event.action for event in self.events], ["next"])
        self.assertGreater(self.events[0].duration_ms, 700)

    def test_changed_hand_discards_trajectory(self):
        self.steady()
        self.swipe(end=0.4, frames=5)
        for index in range(1, 11):
            self.sample(0.4 - 0.03 * index, hand="Left")
        self.assertEqual(self.events, [])

    def test_single_frame_handedness_flip_preserves_swipe(self):
        self.steady()
        for index in range(1, 16):
            self.sample(0.5 - 0.4 * index / 15, hand="Left" if index == 5 else "Right")
        self.assertEqual([event.action for event in self.events], ["next"])

    def test_alternating_handedness_does_not_reset_continuous_same_hand(self):
        self.steady()
        for index in range(1, 16):
            self.sample(0.5 - 0.4 * index / 15, hand="Left" if index % 2 else "Right")
        self.assertEqual([event.action for event in self.events], ["next"])

    def test_distant_changed_hand_is_rejected_immediately(self):
        self.steady()
        self.sample(0.1, hand="Left")
        self.assertEqual(self.detector.state, State.STABILIZING)
        self.assertIn("Cambio de mano confirmado", self.detector.reason)
        self.assertEqual(self.events, [])

    def test_profile_recovers_a_150_ms_dropout_near_last_position(self):
        self.detector = GestureDetector(GestureConfig(dropout_ms=180))
        self.steady()
        self.swipe(end=0.35, frames=7)
        self.sample(None, delta=70)
        self.sample(0.32, delta=80)
        self.swipe(start=0.32, end=0.1, frames=7)
        self.assertEqual([event.action for event in self.events], ["next"])

    def test_new_hand_after_loss_cannot_emit_old_trajectory(self):
        self.steady()
        self.swipe(end=0.4, frames=5)
        self.sample(None)
        for index in range(1, 12):
            self.sample(0.4 - 0.025 * index, hand="Left")
        self.assertEqual(self.events, [])

    def test_sampling_gap_discards_trajectory(self):
        self.steady()
        self.swipe(end=0.4, frames=5)
        self.sample(0.2, delta=500)
        self.steady(x=0.2)
        self.assertEqual(self.events, [])

    def test_irregular_sampling_still_recognizes_swipe(self):
        self.steady()
        elapsed = 0
        for step in (17, 54, 22, 41, 66, 19, 55, 38, 61, 40, 37):
            elapsed += step
            self.sample(0.5 - 0.4 * elapsed / 450, delta=step)
        self.assertEqual([event.action for event in self.events], ["next"])

    def test_pause_and_resume_discard_old_motion(self):
        self.steady()
        self.detector.set_paused(True)
        self.swipe()
        self.assertEqual(self.detector.state, State.PAUSED)
        self.detector.set_paused(False)
        self.swipe(start=0.1, end=0.5)
        self.assertEqual(self.events, [])
        self.steady()
        self.swipe()
        self.assertEqual([event.action for event in self.events], ["next"])

    def test_nonincreasing_timestamp_is_rejected(self):
        self.sample(0.5)
        with self.assertRaisesRegex(ValueError, "timestamps"):
            self.detector.update(self.now, (0.5, 0.5))

    def test_invalid_coordinates_discard_hand(self):
        self.steady()
        self.sample(float("nan"))
        self.assertEqual(self.detector.state, State.NO_HAND)
        self.assertEqual(self.events, [])


class LandmarkMappingTests(unittest.TestCase):
    def result(self, x):
        return SimpleNamespace(
            hand_landmarks=[[SimpleNamespace(x=x, y=0.4) for _ in range(21)]],
            handedness=[[SimpleNamespace(category_name="Right")]],
        )

    def test_direction_is_consistent_with_and_without_mirror(self):
        mirrored, identity = hand_sample(self.result(0.2), mirror=True)
        unmirrored, _ = hand_sample(self.result(0.8), mirror=False)
        self.assertAlmostEqual(mirrored[0], unmirrored[0])
        self.assertEqual(identity, "Right")

    def test_no_hand_produces_missing_sample(self):
        result = SimpleNamespace(hand_landmarks=[], handedness=[])
        self.assertEqual(hand_sample(result, mirror=True), (None, None))

    def test_center_uses_palm_landmarks(self):
        result = self.result(0.4)
        result.hand_landmarks[0][8].x = 0.9  # La punta del índice no mueve el centro.
        center, _ = hand_sample(result, mirror=True)
        self.assertAlmostEqual(center[0], 0.4)


class ConfigTests(unittest.TestCase):
    def test_invalid_thresholds_are_rejected(self):
        for options in ({"distance": 0.01}, {"stable_ms": 0}, {"cooldown_ms": -1},
                        {"distance": float("nan")}, {"smoothing_ms": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                GestureConfig(**options)


if __name__ == "__main__":
    unittest.main()
