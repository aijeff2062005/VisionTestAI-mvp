from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import numpy as np


SLOAN_ROOT = Path(__file__).resolve().parents[1]
if str(SLOAN_ROOT) not in sys.path:
    sys.path.insert(0, str(SLOAN_ROOT))

from runtime import Recognizer  # noqa: E402


class RemovedSkipClassesTest(unittest.TestCase):
    def setUp(self) -> None:
        # Avoid loading ONNX sessions; these tests exercise post-processing only.
        self.recognizer = object.__new__(Recognizer)
        self.recognizer.top_k = 3

    def test_sloan_x_is_never_ranked_or_returned(self) -> None:
        classifier = SimpleNamespace(labels=list("CDHKNORSVZX"))
        probabilities = np.array(
            [0.06, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.85],
            dtype=np.float64,
        )

        result = self.recognizer._predict_sloan(
            probabilities,
            classifier,
            min_confidence=0.30,
            min_margin=0.0,
        )

        self.assertNotEqual(result["raw"], "X")
        self.assertEqual(result["prediction"], "[UNK]")
        self.assertNotIn("X", {row["label"] for row in result["topk"]})

    def test_bo_qua_is_never_ranked_or_grouped(self) -> None:
        labels = [
            "DUNG",
            "CHINH_XAC",
            "PHAI",
            "BO_QUA",
            "SAI",
            "KHONG_PHAI",
            "KHONG_DUNG",
            "KHONG",
        ]
        classifier = SimpleNamespace(labels=labels)
        probabilities = np.array(
            [0.02, 0.01, 0.01, 0.90, 0.02, 0.01, 0.01, 0.02], dtype=np.float64
        )

        result = self.recognizer._predict_three_labels(
            probabilities,
            classifier,
            min_confidence=0.40,
            min_margin=0.0,
        )

        self.assertEqual(result["prediction"], "[UNK]")
        self.assertNotEqual(result["detail"], "BO_QUA")
        self.assertNotIn("BO_QUA", {row["label"] for row in result["topk"]})
        self.assertEqual(
            {row["label"] for row in result["groups"]}, {"TRUE", "FALSE"}
        )

    def test_near_uniform_noise_does_not_bias_to_false(self) -> None:
        labels = [
            "DUNG",
            "CHINH_XAC",
            "PHAI",
            "BO_QUA",
            "SAI",
            "KHONG_PHAI",
            "KHONG_DUNG",
            "KHONG",
        ]
        classifier = SimpleNamespace(labels=labels)
        # Uniform noise across classes: previously sum(FALSE) was ~0.60, triggering false FALSE verdict.
        # With max(), group confidence is max(0.15) = 0.15 < 0.55 -> [UNK].
        probabilities = np.array(
            [0.14, 0.12, 0.12, 0.02, 0.15, 0.15, 0.15, 0.15], dtype=np.float64
        )
        result = self.recognizer._predict_three_labels(
            probabilities,
            classifier,
            min_confidence=0.55,
            min_margin=0.05,
        )
        self.assertEqual(result["prediction"], "[UNK]")
        self.assertFalse(result["reliable"])

    def test_strong_dung_returns_true(self) -> None:
        labels = [
            "DUNG",
            "CHINH_XAC",
            "PHAI",
            "BO_QUA",
            "SAI",
            "KHONG_PHAI",
            "KHONG_DUNG",
            "KHONG",
        ]
        classifier = SimpleNamespace(labels=labels)
        probabilities = np.array(
            [0.85, 0.02, 0.01, 0.01, 0.03, 0.03, 0.02, 0.03], dtype=np.float64
        )
        result = self.recognizer._predict_three_labels(
            probabilities,
            classifier,
            min_confidence=0.55,
            min_margin=0.05,
        )
        self.assertEqual(result["prediction"], "TRUE")
        self.assertTrue(result["reliable"])
        self.assertAlmostEqual(result["confidence"], 0.85)

    def test_strong_sai_returns_false(self) -> None:
        labels = [
            "DUNG",
            "CHINH_XAC",
            "PHAI",
            "BO_QUA",
            "SAI",
            "KHONG_PHAI",
            "KHONG_DUNG",
            "KHONG",
        ]
        classifier = SimpleNamespace(labels=labels)
        probabilities = np.array(
            [0.02, 0.01, 0.01, 0.01, 0.85, 0.04, 0.03, 0.03], dtype=np.float64
        )
        result = self.recognizer._predict_three_labels(
            probabilities,
            classifier,
            min_confidence=0.55,
            min_margin=0.05,
        )
        self.assertEqual(result["prediction"], "FALSE")
        self.assertTrue(result["reliable"])
        self.assertAlmostEqual(result["confidence"], 0.85)

    def test_dung_at_priority_threshold_wins_over_higher_false(self) -> None:
        labels = [
            "DUNG",
            "CHINH_XAC",
            "PHAI",
            "BO_QUA",
            "SAI",
            "KHONG_PHAI",
            "KHONG_DUNG",
            "KHONG",
        ]
        classifier = SimpleNamespace(labels=labels)
        probabilities = np.array(
            [0.41, 0.01, 0.01, 0.01, 0.45, 0.03, 0.04, 0.04], dtype=np.float64
        )

        result = self.recognizer._predict_three_labels(
            probabilities,
            classifier,
            min_confidence=0.55,
            min_margin=0.05,
            confirm_dung_priority_threshold=0.40,
        )

        self.assertEqual(result["prediction"], "TRUE")
        self.assertEqual(result["detail"], "DUNG")
        self.assertTrue(result["reliable"])
        self.assertTrue(result["dung_priority"])
        self.assertAlmostEqual(result["confidence"], 0.41)
        self.assertAlmostEqual(result["acceptance_threshold"], 0.40)

    def test_dung_below_priority_threshold_does_not_override_false(self) -> None:
        labels = [
            "DUNG",
            "CHINH_XAC",
            "PHAI",
            "BO_QUA",
            "SAI",
            "KHONG_PHAI",
            "KHONG_DUNG",
            "KHONG",
        ]
        classifier = SimpleNamespace(labels=labels)
        probabilities = np.array(
            [0.39, 0.01, 0.01, 0.01, 0.50, 0.03, 0.03, 0.02], dtype=np.float64
        )

        result = self.recognizer._predict_three_labels(
            probabilities,
            classifier,
            min_confidence=0.55,
            min_margin=0.05,
            confirm_dung_priority_threshold=0.40,
        )

        self.assertEqual(result["prediction"], "[UNK]")
        self.assertFalse(result["dung_priority"])


if __name__ == "__main__":
    unittest.main()
