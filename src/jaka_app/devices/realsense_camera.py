from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

import cv2
import numpy as np

logger = logging.getLogger(__name__)

LIST_DEVICES_HINT = "Run: python scripts/list_realsense_devices.py"


@dataclass
class FrameSample:
    timestamp: float
    image: np.ndarray


class RealSenseCamera:
    """Single Intel RealSense color stream with background capture."""

    def __init__(
        self,
        name: str,
        serial_number: str,
        *,
        capture_fps: int = 30,
        output_width: int = 224,
        output_height: int = 224,
        pipeline_width: int = 640,
        pipeline_height: int = 480,
        buffer_size: int = 30,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.name = name
        self.serial_number = serial_number.strip()
        if not self.serial_number:
            raise ValueError(
                "Camera %r serial_number is empty. %s" % (name, LIST_DEVICES_HINT)
            )

        self._capture_fps = capture_fps
        self._output_width = output_width
        self._output_height = output_height
        self._pipeline_width = pipeline_width
        self._pipeline_height = pipeline_height
        self._buffer_size = buffer_size
        self._log_fn = log_fn

        self._epoch: float = 0.0
        self._running = False
        self._thread: threading.Thread | None = None
        self._buffer: deque[FrameSample] = deque(maxlen=buffer_size)
        self._buffer_lock = threading.Lock()
        self._last_frame: np.ndarray | None = None
        self._pipeline: Any = None

    def start(self, epoch: float) -> None:
        if self._running:
            return

        import pyrealsense2 as rs

        self._epoch = epoch
        config = rs.config()
        config.enable_device(self.serial_number)
        config.enable_stream(
            rs.stream.color,
            self._pipeline_width,
            self._pipeline_height,
            rs.format.bgr8,
            self._capture_fps,
        )

        pipeline = rs.pipeline()
        try:
            pipeline.start(config)
        except Exception as e:
            raise RuntimeError(
                "Failed to open RealSense %r (serial=%s): %s. %s"
                % (self.name, self.serial_number, e, LIST_DEVICES_HINT)
            ) from e

        self._pipeline = pipeline
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

        msg = "RealSense %s connected: serial=%s" % (self.name, self.serial_number)
        if self._log_fn:
            self._log_fn(msg)
        else:
            logger.info(msg)

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

        if self._pipeline is not None:
            try:
                self._pipeline.stop()
            except Exception as e:
                logger.warning("RealSense %s pipeline stop: %s", self.name, e)
            self._pipeline = None

        with self._buffer_lock:
            self._buffer.clear()
            self._last_frame = None

    def _capture_loop(self) -> None:
        while self._running:
            try:
                if self._pipeline is None:
                    break
                frames = self._pipeline.wait_for_frames(timeout_ms=1000)
                color_frame = frames.get_color_frame()
                if not color_frame:
                    continue

                bgr = np.asanyarray(color_frame.get_data())
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                rgb = cv2.resize(
                    rgb,
                    (self._output_width, self._output_height),
                    interpolation=cv2.INTER_AREA,
                )
                ts = time.perf_counter() - self._epoch
                sample = FrameSample(timestamp=ts, image=rgb)

                with self._buffer_lock:
                    self._buffer.append(sample)
                    self._last_frame = rgb
            except Exception as e:
                if self._running:
                    logger.warning("RealSense %s capture error: %s", self.name, e)
                time.sleep(0.01)

    def get_frame_near(
        self,
        tick_ts: float,
        *,
        sync_max_delta_s: float,
        on_sync_warning: Callable[[str], None] | None = None,
    ) -> np.ndarray:
        with self._buffer_lock:
            if not self._buffer:
                if self._last_frame is not None:
                    return self._last_frame.copy()
                return np.zeros(
                    (self._output_height, self._output_width, 3), dtype=np.uint8
                )

            best = min(self._buffer, key=lambda s: abs(s.timestamp - tick_ts))
            delta = abs(best.timestamp - tick_ts)
            frame = best.image

            if delta > sync_max_delta_s:
                msg = (
                    "Camera %s sync delta %.0fms > %.0fms, reusing closest frame"
                    % (self.name, delta * 1000, sync_max_delta_s * 1000)
                )
                if on_sync_warning:
                    on_sync_warning(msg)
                else:
                    logger.warning(msg)
                if self._last_frame is not None:
                    frame = self._last_frame

            self._last_frame = frame.copy()
            return frame.copy()


class ZeroFillCamera:
    """Placeholder when a camera stream is disabled."""

    def __init__(self, name: str, width: int, height: int, log_fn: Callable[[str], None] | None = None) -> None:
        self.name = name
        self._width = width
        self._height = height
        self._log_fn = log_fn
        self._enabled = False

    def start(self, epoch: float) -> None:
        self._enabled = False
        msg = "Camera %s disabled, using zero-filled images" % self.name
        if self._log_fn:
            self._log_fn(msg)
        else:
            logger.warning(msg)

    def stop(self) -> None:
        pass

    def get_frame_near(
        self,
        tick_ts: float,
        *,
        sync_max_delta_s: float,
        on_sync_warning: Callable[[str], None] | None = None,
    ) -> np.ndarray:
        return np.zeros((self._height, self._width, 3), dtype=np.uint8)


class RealSenseCameraPair:
    """box_image + wrist_image capture for episode recording."""

    def __init__(self, camera_cfg: dict[str, Any], *, log_fn: Callable[[str], None] | None = None) -> None:
        self._log_fn = log_fn
        width = int(camera_cfg.get("width", 224))
        height = int(camera_cfg.get("height", 224))
        capture_fps = int(camera_cfg.get("capture_fps", 30))
        pipeline_w = int(camera_cfg.get("pipeline_width", 640))
        pipeline_h = int(camera_cfg.get("pipeline_height", 480))

        self.box = self._make_camera(
            "box_image",
            camera_cfg.get("box_image") or {},
            width=width,
            height=height,
            capture_fps=capture_fps,
            pipeline_width=pipeline_w,
            pipeline_height=pipeline_h,
        )
        self.wrist = self._make_camera(
            "wrist_image",
            camera_cfg.get("wrist_image") or {},
            width=width,
            height=height,
            capture_fps=capture_fps,
            pipeline_width=pipeline_w,
            pipeline_height=pipeline_h,
        )

    def _make_camera(
        self,
        name: str,
        stream_cfg: dict[str, Any],
        *,
        width: int,
        height: int,
        capture_fps: int,
        pipeline_width: int,
        pipeline_height: int,
    ) -> RealSenseCamera | ZeroFillCamera:
        enabled = bool(stream_cfg.get("enabled", True))
        serial = str(stream_cfg.get("serial_number", "") or "").strip()
        if enabled and serial:
            return RealSenseCamera(
                name,
                serial,
                capture_fps=capture_fps,
                output_width=width,
                output_height=height,
                pipeline_width=pipeline_width,
                pipeline_height=pipeline_height,
                log_fn=self._log_fn,
            )
        return ZeroFillCamera(name, width, height, log_fn=self._log_fn)

    def start(self, epoch: float) -> None:
        self.box.start(epoch)
        self.wrist.start(epoch)

    def stop(self) -> None:
        self.box.stop()
        self.wrist.stop()
