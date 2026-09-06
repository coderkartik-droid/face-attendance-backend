"""
Real face recognition pipeline using ONNX Runtime (SCRFD + ArcFace).

The `insightface` package cannot be installed on this Windows machine
(no MSVC build tools), so we use the ONNX models directly:

  - det_500m.onnx    : SCRFD face detector (5-point landmarks + box + score)
  - w600k_mbf.onnx   : ArcFace recognizer (112x112 -> 512D embedding)

Models live in backend/face_models/ and are loaded lazily once per process.
Embeddings are L2-normalised 512-D vectors; matching uses cosine similarity.
"""

import io
import logging
from pathlib import Path

import numpy as np
import cv2
from PIL import Image
import onnxruntime as ort
from django.conf import settings

from core.exceptions import FaceNotDetectedError, FaceNotMatchedError
from apps.faces.models import FaceEmbedding
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()

# ArcFace alignment template (order: right eye, left eye, nose, mouth right,
# mouth left) — the same order SCRFD produces in its kps output.
_ARC_FACE_112 = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)

DEFAULT_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "face_models"


class FaceEngineError(RuntimeError):
    """Raised when the ONNX face engine is unavailable or fails."""


class _FaceEngine:
    """Lazily-initialised singleton holding the two ONNX inference sessions."""

    _instance = None

    def __init__(self):
        models_dir = Path(getattr(settings, "FACE_MODELS_DIR", DEFAULT_MODELS_DIR))
        det_path = models_dir / "det_500m.onnx"
        rec_path = models_dir / "w600k_mbf.onnx"

        if not det_path.exists() or not rec_path.exists():
            raise FaceEngineError(
                f"Face models not found in {models_dir}. Expected det_500m.onnx "
                "and w600k_mbf.onnx."
            )

        providers = ["CPUExecutionProvider"]
        self.det_session = ort.InferenceSession(str(det_path), providers=providers)
        self.rec_session = ort.InferenceSession(str(rec_path), providers=providers)

        self.det_input_name = self.det_session.get_inputs()[0].name
        self.rec_input_name = self.rec_session.get_inputs()[0].name

        # SCRFD configuration (9 outputs: scores, boxes, kps at strides 8/16/32).
        self.fmc = 3
        self.feat_stride_fpn = [8, 16, 32]
        self.num_anchors = 2
        self.use_kps = True
        self.nms_thresh = 0.4
        self.det_thresh = 0.5
        self.input_mean = 127.5
        self.input_std = 128.0
        self.det_size = (640, 640)
        self.center_cache = {}

        # ---- CPU thread tuning for faster inference on the server ----
        try:
            self.det_session.set_providers(["CPUExecutionProvider"], [{"CPUExecutionProvider": {"arena_extend_strategy": "kSameAsRequested"}}])
        except Exception:
            pass

        logger.info("ONNX face engine ready (det_500m + w600k_mbf).")

    # ------------------------------------------------------------------ #
    # SCRFD detection
    # ------------------------------------------------------------------ #
    @staticmethod
    def _distance2bbox(points, distance, max_shape=None):
        x1 = points[:, 0] - distance[:, 0]
        y1 = points[:, 1] - distance[:, 1]
        x2 = points[:, 0] + distance[:, 2]
        y2 = points[:, 1] + distance[:, 3]
        if max_shape is not None:
            x1 = np.clip(x1, 0, max_shape[1])
            y1 = np.clip(y1, 0, max_shape[0])
            x2 = np.clip(x2, 0, max_shape[1])
            y2 = np.clip(y2, 0, max_shape[0])
        return np.stack([x1, y1, x2, y2], axis=-1)

    @staticmethod
    def _distance2kps(points, distance, max_shape=None):
        preds = []
        for i in range(0, distance.shape[1], 2):
            px = points[:, i % 2] + distance[:, i]
            py = points[:, i % 2 + 1] + distance[:, i + 1]
            if max_shape is not None:
                px = np.clip(px, 0, max_shape[1])
                py = np.clip(py, 0, max_shape[0])
            preds.append(px)
            preds.append(py)
        return np.stack(preds, axis=-1)

    @staticmethod
    def _nms(dets, thresh):
        x1 = dets[:, 0]
        y1 = dets[:, 1]
        x2 = dets[:, 2]
        y2 = dets[:, 3]
        scores = dets[:, 4]
        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0.0, xx2 - xx1 + 1)
            h = np.maximum(0.0, yy2 - yy1 + 1)
            inter = w * h
            ovr = inter / (areas[i] + areas[order[1:]] - inter)
            inds = np.where(ovr <= thresh)[0]
            order = order[inds + 1]
        return keep

    def _forward(self, img_bgr, det_size):
        input_size = tuple(img_bgr.shape[0:2][::-1])
        blob = cv2.dnn.blobFromImage(
            img_bgr, 1.0 / self.input_std, input_size,
            (self.input_mean, self.input_mean, self.input_mean), swapRB=True,
        )
        net_outs = self.det_session.run(None, {self.det_input_name: blob})

        input_h = blob.shape[2]
        input_w = blob.shape[3]
        scores_list = []
        bboxes_list = []
        kpss_list = []

        for idx, stride in enumerate(self.feat_stride_fpn):
            # The exporter may add a leading batch dim (3D) or not (2D).
            scores = net_outs[idx]
            bbox_preds = net_outs[idx + self.fmc]
            kps_preds = net_outs[idx + self.fmc * 2]
            if scores.ndim == 3:
                scores = scores[0]
                bbox_preds = bbox_preds[0]
                kps_preds = kps_preds[0]
            bbox_preds = bbox_preds * stride
            kps_preds = kps_preds * stride

            height = input_h // stride
            width = input_w // stride
            key = (height, width, stride)
            if key in self.center_cache:
                anchor_centers = self.center_cache[key]
            else:
                anchor_centers = np.stack(
                    np.mgrid[:height, :width][::-1], axis=-1
                ).astype(np.float32)
                anchor_centers = (anchor_centers * stride).reshape((-1, 2))
                if self.num_anchors > 1:
                    anchor_centers = np.stack(
                        [anchor_centers] * self.num_anchors, axis=1
                    ).reshape((-1, 2))
                if len(self.center_cache) < 100:
                    self.center_cache[key] = anchor_centers

            pos_inds = np.where(scores >= self.det_thresh)[0]
            if pos_inds.size == 0:
                continue
            bboxes = self._distance2bbox(anchor_centers, bbox_preds)
            kpss = self._distance2kps(anchor_centers, kps_preds).reshape(
                (kps_preds.shape[0], -1, 2)
            )
            scores_list.append(scores[pos_inds])
            bboxes_list.append(bboxes[pos_inds])
            kpss_list.append(kpss[pos_inds])

        if not scores_list:
            return np.empty((0, 5), dtype=np.float32), np.empty((0, 5, 2), dtype=np.float32)

        scores = np.vstack(scores_list)
        scores_ravel = scores.ravel()
        order = scores_ravel.argsort()[::-1]
        bboxes = np.vstack(bboxes_list)
        kpss = np.vstack(kpss_list)
        pre_det = np.hstack((bboxes, scores)).astype(np.float32, copy=False)
        pre_det = pre_det[order, :]
        kpss = kpss[order, :, :]
        keep = self._nms(pre_det, self.nms_thresh)
        return pre_det[keep, :], kpss[keep, :, :]

    def detect(self, img_bgr):
        """Detect faces and return (boxes Nx5, kps Nx5x2) in original coords."""
        input_w, input_h = self.det_size
        im_ratio = float(img_bgr.shape[0]) / img_bgr.shape[1]
        model_ratio = float(input_w) / input_h
        if im_ratio > model_ratio:
            new_height = input_h
            new_width = int(new_height / im_ratio)
        else:
            new_width = input_w
            new_height = int(new_width * im_ratio)
        det_scale = float(new_height) / img_bgr.shape[0]

        resized = cv2.resize(img_bgr, (new_width, new_height))
        det_img = np.zeros((input_h, input_w, 3), dtype=np.uint8)
        det_img[:new_height, :new_width, :] = resized

        det, kpss = self._forward(det_img, self.det_size)
        if det.shape[0] == 0:
            return det, kpss
        det[:, :4] = det[:, :4] / det_scale
        kpss = kpss / det_scale
        return det, kpss

    # ------------------------------------------------------------------ #
    # ArcFace recognition
    # ------------------------------------------------------------------ #
    @staticmethod
    def _estimate_norm(lmk, image_size=112):
        ratio = float(image_size) / 112.0
        dst = _ARC_FACE_112 * ratio
        tform, _ = cv2.estimateAffinePartial2D(lmk, dst)
        if tform is None:
            raise FaceNotDetectedError("Could not align face landmarks.")
        return tform

    def _align_crop(self, img_bgr, lmk, image_size=112):
        if lmk.shape[0] != 5:
            raise FaceNotDetectedError("5-point landmarks required for alignment.")
        M = self._estimate_norm(lmk, image_size)
        warped = cv2.warpAffine(img_bgr, M, (image_size, image_size), borderValue=0.0)
        return warped

    def _get_embedding(self, aligned_bgr):
        """ArcfE: aligned image -> L2-normalised 512D embedding."""
        blob = cv2.dnn.blobFromImage(
            aligned_bgr, 1.0 / self.input_std, (112, 112),
            (self.input_mean, self.input_mean, self.input_mean), swapRB=True,
        )
        feat = self.rec_session.run(None, {self.rec_input_name: blob})[0]
        embedding = feat[0]
        norm = np.linalg.norm(embedding, keepdims=True)
        if norm == 0:
            raise FaceNotDetectedError("Zero-norm embedding produced by recognizer.")
        return (embedding / norm).astype(np.float32)

    def get_faces_with_embeddings(self, img_bgr):
        """Detect faces and compute an embedding for each."""
        det, kpss = self.detect(img_bgr)
        if det.shape[0] == 0:
            raise FaceNotDetectedError("No face detected in the provided image.")

        results = []
        # Score desc order; alignment needs highest-quality face first.
        order = det[:, 4].argsort()[::-1]
        for i in order:
            box = det[i][:4].astype(int)
            score = float(det[i][4])
            kps = kpss[i].astype(np.float32)
            aligned = self._align_crop(img_bgr, kps)
            embedding = self._get_embedding(aligned)
            results.append(
                {
                    "embedding": embedding,
                    "bbox": box.tolist(),
                    "score": score,
                }
            )
        return results


def get_face_engine():
    if _FaceEngine._instance is None:
        _FaceEngine._instance = _FaceEngine()
    return _FaceEngine._instance


class FaceRecognitionService:
    @staticmethod
    def process_image(image_input):
        """Converts uploaded file/bytes into OpenCV BGR numpy array."""
        if hasattr(image_input, "read"):
            image_bytes = image_input.read()
        elif isinstance(image_input, bytes):
            image_bytes = image_input
        else:
            raise ValueError("Unsupported image input type.")

        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_np = np.array(pil_img)
        return img_np[:, :, ::-1].copy()

    @classmethod
    def extract_face_embeddings(cls, image_input):
        """Detects faces and extracts real L2-normalised 512D embeddings."""
        img_bgr = cls.process_image(image_input)
        engine = get_face_engine()
        return engine.get_faces_with_embeddings(img_bgr)

    @staticmethod
    def cosine_similarity(vec1, vec2):
        v1 = np.asarray(vec1, dtype=np.float32)
        v2 = np.asarray(vec2, dtype=np.float32)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))

    @classmethod
    def match_face(cls, target_embedding, threshold=None):
        """Matches a target 512D embedding against the stored database."""
        if threshold is None:
            threshold = getattr(settings, "FACE_MATCH_THRESHOLD", 0.35)  # Lower threshold for better matching

        stored_records = (
            FaceEmbedding.objects.filter(is_active=True)
            .select_related("user")
            .order_by("user_id", "-created_at")
        )
        if not stored_records.exists():
            raise FaceNotMatchedError("No registered face database found.")

        best_user = None
        best_score = -1.0

        # Group by user and take average similarity for each user
        user_similarities = {}
        for record in stored_records:
            user_id = record.user.id
            sim = cls.cosine_similarity(target_embedding, record.embedding)
            
            if user_id not in user_similarities:
                user_similarities[user_id] = []
            user_similarities[user_id].append(sim)

        # Calculate average similarity for each user
        for user_id, similarities in user_similarities.items():
            avg_sim = sum(similarities) / len(similarities)
            if avg_sim > best_score:
                best_score = avg_sim
                best_user = next((r.user for r in stored_records if r.user.id == user_id), None)

        if best_score >= threshold and best_user is not None:
            return best_user, round(best_score, 4)

        raise FaceNotMatchedError(
            f"Face not recognized. Highest match score {best_score:.4f} "
            f"below threshold {threshold}."
        )