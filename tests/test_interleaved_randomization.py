"""Run with: python -m unittest discover -s tests -v (no camera required)."""

import csv
import itertools
import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import Mock, patch

from config.settings import ExperimentConfig
from core.enums import Shape
from core.experiment_engine import ExperimentEngine
from core.interleaved_randomization import generate_interleaved_sequence
from core.session_queue import QueueItem
from data.event_logger import EventLogger


class RandomizationTests(unittest.TestCase):
    def test_counts_and_run_limit(self):
        for shape_count, cycles, shape_reps in (
            (1, 1, 1), (1, 2, 1), (2, 1, 1), (2, 3, 1),
            (2, 5, 1), (2, 10, 1), (2, 3, 2), (3, 4, 1), (4, 3, 1),
        ):
            names = [f"shape_{i}" for i in range(shape_count)] * shape_reps
            expected = Counter({name: cycles * shape_reps for name in names})
            for seed in range(30):
                with self.subTest(names=names, cycles=cycles, seed=seed):
                    sequence = generate_interleaved_sequence(names, cycles, seed)
                    self.assertEqual(Counter(sequence), expected)
                    self.assertTrue(all(
                        len(list(group)) <= 2
                        for _, group in itertools.groupby(sequence)
                    ))

    def test_seed_replay_leaves_global_rng_untouched(self):
        global_state = random.getstate()
        first = generate_interleaved_sequence(["circle", "triangle"], 5, 123456)
        self.assertEqual(random.getstate(), global_state)
        self.assertEqual(
            first,
            generate_interleaved_sequence(["circle", "triangle"], 5, 123456),
        )

    def test_all_valid_small_orders_are_reachable(self):
        # Enumerate the entire valid space independently, including both
        # starting classes and valid orders containing repeated neighbours.
        valid = {
            order for order in itertools.permutations("AAABBB")
            if all(len(list(group)) <= 2 for _, group in itertools.groupby(order))
        }
        sampled = {
            tuple(generate_interleaved_sequence(["A", "B"], 3, seed))
            for seed in range(500)
        }
        self.assertEqual(len(valid), 14)
        self.assertEqual(sampled, valid)

    def test_rejects_complete_proposals_without_repairs(self):
        proposals = iter([list("AAABBB"), list("ABBAAB")])
        rng = Mock()

        def shuffle(candidate):
            candidate[:] = next(proposals)

        rng.shuffle.side_effect = shuffle
        with patch("core.interleaved_randomization.random.Random", return_value=rng):
            sequence = generate_interleaved_sequence(["A", "B"], 3, 12)
        self.assertEqual(sequence, list("ABBAAB"))
        self.assertEqual(rng.shuffle.call_count, 2)

    def test_impossible_counts_fail_immediately(self):
        for names, cycles in ((["A"], 3), (["A"] * 5 + ["B"], 1)):
            with self.subTest(names=names, cycles=cycles):
                with self.assertRaisesRegex(ValueError, "cannot avoid"):
                    generate_interleaved_sequence(names, cycles, 1)

    def test_bounded_search_does_not_return_a_fallback(self):
        rng = Mock()

        def shuffle(candidate):
            candidate[:] = list("AAABBB")

        rng.shuffle.side_effect = shuffle
        with patch("core.interleaved_randomization.random.Random", return_value=rng):
            with self.assertRaisesRegex(RuntimeError, "3 attempts.*seed=12"):
                generate_interleaved_sequence(["A", "B"], 3, 12, max_attempts=3)
        self.assertEqual(rng.shuffle.call_count, 3)

    def test_search_can_be_aborted(self):
        with self.assertRaises(InterruptedError):
            generate_interleaved_sequence(
                ["A", "B"], 3, 12, should_abort=lambda: True,
            )

    def test_invalid_inputs(self):
        for names, cycles in (([], 1), (["A", "B"], 0), (["A", "B"], -1)):
            with self.subTest(names=names, cycles=cycles):
                with self.assertRaises(ValueError):
                    generate_interleaved_sequence(names, cycles, 1)
        with self.assertRaises(ValueError):
            generate_interleaved_sequence(["A", "B"], 3, 1, max_attempts=0)


class EngineRandomizationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.event_path = Path(temporary.name) / "event_log.csv"
        self.config = ExperimentConfig(
            shapes=["circle", "triangle"], interleaving_mode=True,
        )
        self.engine = ExperimentEngine(self.config, Mock())
        self.engine.event_logger = EventLogger(self.event_path)
        self.addCleanup(self.engine.event_logger.close)
        self.engine.excel_logger = Mock()
        self.engine._protocol = Mock()
        self.engine._protocol.run_interleaved.return_value = True
        self.worker = Mock()

    def test_each_repetition_gets_a_seed_logged_in_csv_and_excel(self):
        with patch("core.experiment_engine.secrets.randbits", side_effect=[123, 456]) as seeds:
            for rep in (1, 2):
                item = QueueItem("Participant", rep, [Shape.CIRCLE, Shape.TRIANGLE])
                self.assertTrue(self.engine._run_interleaved_item(self.worker, item, False))
        self.assertEqual(seeds.call_count, 2)
        self.engine.event_logger.close()
        with self.event_path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        metadata = [
            (row, json.loads(row["detail"])) for row in rows
            if row["event_type"] == "INTERLEAVED_RANDOMIZATION"
        ]
        orders = [row["detail"] for row in rows if row["event_type"] == "INTERLEAVED_SEQUENCE"]
        self.assertEqual([data["seed"] for _, data in metadata], [123, 456])
        self.assertEqual([row["rep"] for row, _ in metadata], ["1", "2"])
        for index, (_, data) in enumerate(metadata):
            sequence = generate_interleaved_sequence(
                data["shape_names"], data["cycles_per_shape"], data["seed"],
            )
            self.assertEqual(orders[index], ",".join(sequence))
            passed = self.engine._protocol.run_interleaved.call_args_list[index].kwargs
            self.assertEqual(passed["cycle_sequence"], sequence)
            self.assertEqual(data["max_consecutive"], 2)
            notes = self.engine.excel_logger.log_trial.call_args_list[index * 2].kwargs["notes"]
            self.assertIn(str(data["seed"]), notes)
            self.assertIn(",".join(sequence), notes)

    def test_pause_resume_reuses_seed_and_order(self):
        item = QueueItem("Participant", 1, [Shape.CIRCLE, Shape.TRIANGLE])

        def interrupt_first_cycle(**kwargs):
            self.engine._protocol.last_completed_cycle = 1
            self.engine.pause()
            return False

        calls = iter([interrupt_first_cycle, lambda **kwargs: True])
        self.engine._protocol.run_interleaved.side_effect = lambda **kwargs: next(calls)(**kwargs)
        with patch("core.experiment_engine.secrets.randbits", return_value=789) as seeds:
            with patch.object(self.engine, "_check_pause", side_effect=lambda w: self.engine.resume()):
                self.assertTrue(self.engine._run_interleaved_item(self.worker, item, True))
        seeds.assert_called_once_with(64)
        first, resumed = self.engine._protocol.run_interleaved.call_args_list
        self.assertEqual(first.kwargs["cycle_sequence"], resumed.kwargs["cycle_sequence"])
        self.assertEqual(resumed.kwargs["start_from_cycle"], 2)

    def test_single_shape_validation_only_applies_in_interleaving_mode(self):
        self.config.shapes = ["circle"]
        self.assertTrue(any("two consecutive" in error for error in self.config.validate()))
        self.config.timing.imagination_cycles = 2
        self.assertEqual(self.config.validate(), [])
        self.config.interleaving_mode = False
        self.config.timing.imagination_cycles = 3
        self.assertEqual(self.config.validate(), [])

    def test_abort_during_generation_does_not_start_the_protocol(self):
        self.engine._abort_flag.set()
        item = QueueItem("Participant", 1, [Shape.CIRCLE, Shape.TRIANGLE])
        self.assertFalse(self.engine._run_interleaved_item(self.worker, item, False))
        self.engine._protocol.run_interleaved.assert_not_called()

    def test_pause_during_generation_is_honored_before_recording(self):
        item = QueueItem("Participant", 1, [Shape.CIRCLE, Shape.TRIANGLE])

        def generate_and_pause(*args, **kwargs):
            sequence = generate_interleaved_sequence(*args, **kwargs)
            self.engine.pause()
            return sequence

        def wait_and_resume(worker):
            self.assertFalse(self.engine._pause_event.is_set())
            self.engine._protocol.run_interleaved.assert_not_called()
            self.engine.resume()

        with patch("core.experiment_engine.generate_interleaved_sequence", side_effect=generate_and_pause):
            with patch.object(self.engine, "_check_pause", side_effect=wait_and_resume) as wait:
                self.assertTrue(self.engine._run_interleaved_item(self.worker, item, False))
        wait.assert_called_once_with(self.worker)


if __name__ == "__main__":
    unittest.main()
