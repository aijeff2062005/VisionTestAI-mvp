from pathlib import Path

import librosa
import numpy as np
import onnxruntime as ort
import torch
import torchaudio.compliance.kaldi as kaldi

ROOT = Path(__file__).resolve().parent


def _ort_providers():
    """Prefer CUDA on Jetson; TensorRT is optional (engine build OOMs Orin Nano + YOLO).

    Set SLOAN_ORT_TRT=1 to try TensorRT first.
    """
    import os
    try:
        available = set(ort.get_available_providers())
    except Exception:
        return ["CPUExecutionProvider"]
    use_trt = os.environ.get("SLOAN_ORT_TRT", "").strip() in ("1", "true", "yes")
    ordered = []
    if use_trt:
        ordered.append("TensorrtExecutionProvider")
    ordered.extend(["CUDAExecutionProvider", "CPUExecutionProvider"])
    providers = [p for p in ordered if p in available]
    return providers or ["CPUExecutionProvider"]


CHECKPOINT = ROOT / "checkpoint"

HEAD_FILES = {
    "sloan": {
        "classifier": "classifier_sloan.onnx",
        "labels": "labels_sloan.txt",
        "temperature": "temperature_sloan.txt",
    },
    "three_labels": {
        "classifier": "classifier_3labels.onnx",
        "labels": "labels_3labels.txt",
        "temperature": "temperature_3labels.txt",
    },
}

THREE_LABEL_GROUPS = {
    "DUNG": "TRUE",
    "CHINH_XAC": "TRUE",
    "PHAI": "TRUE",
    "SAI": "FALSE",
    "KHONG_PHAI": "FALSE",
    "KHONG_DUNG": "FALSE",
    "KHONG": "FALSE",
}
# X and BO_QUA are still present in the frozen ONNX heads.  Their positions in
# the label files must not be deleted (that would shift the output indices), so
# inference masks them before ranking/normalising.  The effective heads are:
# Sloan = 10 optotypes; confirmation = TRUE/FALSE only.
SLOAN_EXCLUDED_LABELS = frozenset({"X"})
CONFIRM_EXCLUDED_LABELS = frozenset({"BO_QUA"})
GROUP_ORDER = ("TRUE", "FALSE")


def make_fbank(audio, sample_rate):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sample_rate != 16000:
        audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)
    if audio.size < 400:
        audio = np.pad(audio, (0, 400 - audio.size))
    return kaldi.fbank(
        torch.from_numpy(audio).unsqueeze(0), sample_frequency=16000,
        num_mel_bins=80, frame_length=25.0, frame_shift=10.0,
        high_freq=-400.0, dither=0.0, energy_floor=0.0, use_energy=False,
    )


class Encoder:
    def __init__(self):
        self.session = ort.InferenceSession(
            str(CHECKPOINT / "encoder.int8.onnx"),
            providers=_ort_providers(),
        )
        print(f"Sloan STT encoder providers: {self.session.get_providers()}")

    def __call__(self, fbank):
        feeds = {}
        for item in self.session.get_inputs():
            name = item.name.lower()
            if "lens" in name or "length" in name:
                feeds[item.name] = np.asarray([fbank.shape[0]], dtype=np.int64)
            elif len(item.shape) == 3 and item.shape[-1] == 80:
                feeds[item.name] = fbank.numpy()[None].astype(np.float32)
            elif len(item.shape) == 2 and item.shape[-1] == 80:
                feeds[item.name] = fbank.numpy().astype(np.float32)
            else:
                shape = [1 if isinstance(x, str) or x is None else x for x in item.shape]
                dtype = np.int64 if "int" in item.type else np.float32
                feeds[item.name] = np.zeros(shape, dtype=dtype)
        outputs = self.session.run(None, feeds)
        arrays = [x for x in outputs if isinstance(x, np.ndarray) and x.ndim >= 3]
        if not arrays:
            raise RuntimeError("Encoder output is not a sequence embedding")
        # One utterance is encoded at a time; pool its temporal dimension.
        return arrays[0][0].mean(axis=0).astype(np.float32)


class ClassifierHead:
    def __init__(self, name):
        config = HEAD_FILES[name]
        self.name = name
        self.labels = [
            line.strip() for line in (CHECKPOINT / config["labels"]).read_text(
                encoding="utf-8"
            ).splitlines() if line.strip()
        ]
        self.temperature = max(
            float((CHECKPOINT / config["temperature"]).read_text().strip()), .05
        )
        self.session = ort.InferenceSession(
            str(CHECKPOINT / config["classifier"]),
            providers=_ort_providers(),
        )
        print(f"Sloan STT classifier[{self.name}] providers: {self.session.get_providers()}")

    def probabilities(self, embedding):
        logits = self.session.run(
            ["logits"], {"embedding": embedding[None].astype(np.float32)}
        )[0][0]
        logits = logits / self.temperature
        probabilities = np.exp(logits - logits.max())
        return probabilities / probabilities.sum()


class Recognizer:
    def __init__(self, top_k=3, enabled_heads=("sloan", "three_labels")):
        self.encoder = Encoder()
        self.top_k = top_k
        self.heads = {}
        for name in enabled_heads:
            if name not in HEAD_FILES:
                raise ValueError(f"Unknown head: {name}")
            self.heads[name] = ClassifierHead(name)

    @staticmethod
    def _requested_heads(head):
        if head == "both":
            return ("sloan", "three_labels")
        if head in HEAD_FILES:
            return (head,)
        raise ValueError("head must be: sloan, three_labels, or both")

    def _predict_sloan(
        self,
        probabilities,
        classifier,
        min_confidence,
        min_margin,
        class_confidence_thresholds=None,
    ):
        active = [
            i for i, label in enumerate(classifier.labels)
            if label not in SLOAN_EXCLUDED_LABELS
        ]
        active_probabilities = np.asarray(
            [probabilities[i] for i in active], dtype=np.float64
        )
        # Keep the original softmax mass.  Renormalising after removing X would
        # turn an X-dominant/out-of-domain utterance into a confident optotype.
        order = np.argsort(active_probabilities)[::-1]
        top = [
            {
                "label": classifier.labels[active[i]],
                "confidence": float(active_probabilities[i]),
            }
            for i in order[:self.top_k]
        ]
        margin = top[0]["confidence"] - top[1]["confidence"] if len(top) > 1 else top[0]["confidence"]
        class_thresholds = class_confidence_thresholds or {}
        acceptance_threshold = float(
            class_thresholds.get(top[0]["label"], min_confidence)
        )
        reliable = top[0]["confidence"] >= acceptance_threshold and margin >= min_margin
        return {
            "raw": top[0]["label"],
            "prediction": top[0]["label"] if reliable else "[UNK]",
            "confidence": top[0]["confidence"], "margin": margin,
            "reliable": reliable,
            "acceptance_threshold": acceptance_threshold,
            "topk": top,
        }

    def _predict_three_labels(
        self,
        probabilities,
        classifier,
        min_confidence,
        min_margin,
        confirm_dung_priority_threshold=None,
    ):
        active = [
            i for i, label in enumerate(classifier.labels)
            if label not in CONFIRM_EXCLUDED_LABELS
        ]
        active_probabilities = np.asarray(
            [probabilities[i] for i in active], dtype=np.float64
        )
        # Preserve excluded BO_QUA probability as rejection mass.  Otherwise a
        # BO_QUA-dominant clip would be forced into TRUE/FALSE after masking.
        fine_order = np.argsort(active_probabilities)[::-1]
        fine_top = [
            {
                "label": classifier.labels[active[i]],
                "confidence": float(active_probabilities[i]),
            }
            for i in fine_order[:self.top_k]
        ]
        grouped = {group: 0.0 for group in GROUP_ORDER}
        dung_confidence = 0.0
        for i, probability in zip(active, active_probabilities):
            label = classifier.labels[i]
            if label == "DUNG":
                dung_confidence = float(probability)
            group = THREE_LABEL_GROUPS[label]
            grouped[group] = max(grouped[group], float(probability))
        group_top = sorted(grouped.items(), key=lambda item: item[1], reverse=True)
        margin = group_top[0][1] - group_top[1][1]
        dung_threshold = (
            float(confirm_dung_priority_threshold)
            if confirm_dung_priority_threshold is not None
            else None
        )
        dung_wins = dung_threshold is not None and dung_confidence >= dung_threshold
        if dung_wins:
            prediction = "TRUE"
            confidence = dung_confidence
            detail = "DUNG"
            reliable = True
            acceptance_threshold = dung_threshold
        else:
            prediction = group_top[0][0]
            confidence = group_top[0][1]
            detail = fine_top[0]["label"]
            reliable = confidence >= min_confidence and margin >= min_margin
            acceptance_threshold = float(min_confidence)
        return {
            "raw": group_top[0][0],
            "prediction": prediction if reliable else "[UNK]",
            "confidence": confidence, "margin": margin,
            "reliable": reliable,
            "detail": detail,
            "detail_confidence": confidence if dung_wins else fine_top[0]["confidence"],
            "acceptance_threshold": acceptance_threshold,
            "dung_priority": dung_wins,
            "groups": [{"label": label, "confidence": confidence} for label, confidence in group_top],
            "topk": fine_top,
        }

    def predict(
        self,
        audio,
        sample_rate,
        min_confidence=.55,
        min_margin=.05,
        head="sloan",
        class_confidence_thresholds=None,
        confirm_dung_priority_threshold=None,
    ):
        requested = self._requested_heads(head)
        missing = [name for name in requested if name not in self.heads]
        if missing:
            raise RuntimeError(f"Heads not loaded: {', '.join(missing)}")

        # The shared encoder is executed exactly once, even when both heads run.
        embedding = self.encoder(make_fbank(audio, sample_rate))
        results = {}
        for name in requested:
            classifier = self.heads[name]
            probabilities = classifier.probabilities(embedding)
            if name == "sloan":
                results[name] = self._predict_sloan(
                    probabilities,
                    classifier,
                    min_confidence,
                    min_margin,
                    class_confidence_thresholds,
                )
            else:
                results[name] = self._predict_three_labels(
                    probabilities,
                    classifier,
                    min_confidence,
                    min_margin,
                    confirm_dung_priority_threshold,
                )
        return results[requested[0]] if len(requested) == 1 else results
