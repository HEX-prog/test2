import math
import time
from typing import List, Dict, Optional, Tuple


class Track:
    """Lightweight track used by ByteTrackLite.

    This is a simplified, dependency-free tracker that mimics the essential
    behavior we need from ByteTrack: consistent IDs across frames based on IoU
    matching and short-term memory (TTL).
    """

    def __init__(self, track_id: int, bbox: Tuple[float, float, float, float],
                 score: float, ttl: int) -> None:
        self.id = track_id
        self.bbox = bbox  # (x1, y1, x2, y2)
        self.score = score
        self.ttl = ttl
        self.last_update = time.time()

    def update(self, bbox: Tuple[float, float, float, float], score: float, ttl: int) -> None:
        self.bbox = bbox
        self.score = score
        self.ttl = ttl
        self.last_update = time.time()


def iou(boxA: Tuple[float, float, float, float], boxB: Tuple[float, float, float, float]) -> float:
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    inter_w = max(0.0, xB - xA)
    inter_h = max(0.0, yB - yA)
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    areaA = max(0.0, (boxA[2] - boxA[0])) * max(0.0, (boxA[3] - boxA[1]))
    areaB = max(0.0, (boxB[2] - boxB[0])) * max(0.0, (boxB[3] - boxB[1]))
    union = areaA + areaB - inter
    if union <= 0:
        return 0.0
    return inter / union


class ByteTrackLite:
    """A minimal tracker that assigns stable IDs using IoU matching.

    Notes:
        - This is intentionally simple and self-contained to avoid heavy
          dependencies. It serves the purpose of assigning IDs to detections
          so the aimbot can keep tracking a chosen target.
    """

    def __init__(self, iou_threshold: float = 0.5, max_ttl: int = 8) -> None:
        self.iou_threshold = iou_threshold
        self.max_ttl = max_ttl
        self.tracks: List[Track] = []
        self.next_id = 1

    def update(self, detections: List[Dict]) -> List[Dict]:
        """Update tracker with current detections.

        Args:
            detections: List of dict with keys: x1,y1,x2,y2,conf(optional)

        Returns:
            detections with an added 'track_id' field when matched/assigned.
        """
        assigned = set()
        # Try to match each detection with an existing track by highest IoU
        for det in detections:
            bbox = (float(det['x1']), float(det['y1']), float(det['x2']), float(det['y2']))
            score = float(det.get('conf', 1.0))
            best_iou = 0.0
            best_track: Optional[Track] = None
            for tr in self.tracks:
                cur_iou = iou(tr.bbox, bbox)
                if cur_iou > best_iou:
                    best_iou = cur_iou
                    best_track = tr
            if best_track is not None and best_iou >= self.iou_threshold:
                best_track.update(bbox, score, self.max_ttl)
                det['track_id'] = best_track.id
                assigned.add(best_track.id)
            else:
                # Create new track
                new_tr = Track(self.next_id, bbox, score, self.max_ttl)
                self.tracks.append(new_tr)
                det['track_id'] = new_tr.id
                assigned.add(new_tr.id)
                self.next_id += 1

        # Decrease TTL and remove stale tracks
        alive_tracks: List[Track] = []
        for tr in self.tracks:
            if tr.id in assigned:
                alive_tracks.append(tr)
            else:
                tr.ttl -= 1
                if tr.ttl > 0:
                    alive_tracks.append(tr)
        self.tracks = alive_tracks

        return detections


class NCAFController:
    """Nonlinear Close-Aim with Focus (NCAF) controller.

    Implements the behavior illustrated by the diagram:
      - Near radius: distance within which speed is tapered by exponent alpha
      - Snap radius: inner radius with an extra boost factor
      - Speed curve exponent alpha (alpha > 0)
      - Optional max step limiting

    It also maintains a light ByteTrack-based tracker to provide stable IDs.
    """

    def __init__(self) -> None:
        self.tracker = ByteTrackLite(iou_threshold=0.5, max_ttl=8)
        self.last_target_id: Optional[int] = None

    def set_tracker_params(self, iou_threshold: float, max_ttl: int) -> None:
        self.tracker.iou_threshold = iou_threshold
        self.tracker.max_ttl = max_ttl

    def update_tracking(self, detections: List[Dict]) -> None:
        """Update tracker state with raw detection dicts."""
        if not detections:
            return
        self.tracker.update(detections)
        # Prefer to keep last target id if still present
        if self.last_target_id is not None:
            if any(d.get('track_id') == self.last_target_id for d in detections):
                return
        # Otherwise pick the highest confidence one
        best = max(detections, key=lambda d: float(d.get('conf', 0.0)))
        self.last_target_id = best.get('track_id', None)

    def choose_target_center(self, candidates: List[Dict], crosshair_x: float, crosshair_y: float) -> Optional[Tuple[float, float]]:
        """Choose a target center using track IDs to stabilize selection."""
        if not candidates:
            return None
        # Prefer same track id
        if self.last_target_id is not None:
            for d in candidates:
                if d.get('track_id') == self.last_target_id:
                    cx = 0.5 * (d['x1'] + d['x2'])
                    cy = 0.5 * (d['y1'] + d['y2'])
                    return cx, cy
        # Otherwise nearest to crosshair
        def dist2(d):
            cx = 0.5 * (d['x1'] + d['x2'])
            cy = 0.5 * (d['y1'] + d['y2'])
            return (cx - crosshair_x) ** 2 + (cy - crosshair_y) ** 2
        d_best = min(candidates, key=dist2)
        cx = 0.5 * (d_best['x1'] + d_best['x2'])
        cy = 0.5 * (d_best['y1'] + d_best['y2'])
        self.last_target_id = d_best.get('track_id', None)
        return cx, cy

    def compute_ncaf_delta(self,
                            dx: float,
                            dy: float,
                            near_radius: float,
                            snap_radius: float,
                            alpha: float,
                            snap_boost: float,
                            max_step: float) -> Tuple[float, float]:
        """Apply NCAF speed curve to the raw delta (dx, dy)."""
        distance = math.hypot(dx, dy)
        if distance <= 1e-6:
            return 0.0, 0.0

        # Base speed factor decreases as we get closer using exponent alpha
        if distance <= near_radius and near_radius > 0:
            factor = (distance / max(1e-6, near_radius)) ** max(0.0, alpha)
        else:
            factor = 1.0

        # Snap boost inside snap radius
        if distance <= snap_radius:
            factor *= max(1.0e-3, snap_boost)

        new_dx = dx * factor
        new_dy = dy * factor

        # Limit per-step movement
        step = math.hypot(new_dx, new_dy)
        if max_step > 0 and step > max_step:
            scale = max_step / step
            new_dx *= scale
            new_dy *= scale
        return new_dx, new_dy


_ncaf_singleton: Optional[NCAFController] = None


def get_ncaf_controller() -> NCAFController:
    """Factory returning a shared NCAFController instance."""
    global _ncaf_singleton
    if _ncaf_singleton is None:
        _ncaf_singleton = NCAFController()
    return _ncaf_singleton


