from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import h5py
import numpy as np

from jaka_app.devices.realsense_camera import RealSenseCameraPair
from jaka_app.utils.logging_utils import add_log

if TYPE_CHECKING:
    from DHGripper.DHController import GripperController
    from jaka_app.robot_controller import JakaRobotController

logger = logging.getLogger(__name__)

NUM_JOINTS = 6
NUM_EEF = 6


def _parse_data_collection_config(cfg: dict[str, Any]) -> dict[str, Any]:
    dc = cfg.get("data_collection") or {}
    cameras = dc.get("cameras") or {}
    metadata = dc.get("metadata") or {}
    return {
        "enabled": bool(dc.get("enabled", True)),
        "sample_hz": float(dc.get("sample_hz", 15)),
        "output_dir": str(dc.get("output_dir", "data/episodes")),
        "sync_max_delta_ms": float(dc.get("sync_max_delta_ms", 50)),
        "metadata": {
            "run_type": str(metadata.get("run_type", "auto_run")),
            "control_type": str(metadata.get("control_type", "joint")),
        },
        "cameras": cameras,
        "camera_height": int(cameras.get("height", 224)),
        "camera_width": int(cameras.get("width", 224)),
        "camera_channels": int(cameras.get("channels", 3)),
    }


class EpisodeRecorder:
    """Background episode sampler; writes HDF5 on successful stop(save=True)."""

    def __init__(
        self,
        robot: JakaRobotController,
        gripper: GripperController,
        cfg: dict[str, Any],
        *,
        cancel_event: threading.Event | None = None,
        ctx: Any = None,
    ) -> None:
        self._robot = robot
        self._gripper = gripper
        self._cfg = _parse_data_collection_config(cfg)
        self._cancel_event = cancel_event
        self._ctx = ctx

        self._lock = threading.Lock()
        self._task = ""
        self._subtask = ""

        self._running = False
        self._thread: threading.Thread | None = None
        self._start_perf: float = 0.0
        self._cameras: RealSenseCameraPair | None = None

        self._timestamps: list[float] = []
        self._subtasks: list[str] = []
        self._joint_positions: list[list[float]] = []
        self._eef_positions: list[list[float]] = []
        self._gripper_states: list[float] = []
        self._box_images: list[np.ndarray] = []
        self._wrist_images: list[np.ndarray] = []

    @property
    def enabled(self) -> bool:
        return self._cfg["enabled"]

    @property
    def task(self) -> str:
        with self._lock:
            return self._task

    @task.setter
    def task(self, value: str) -> None:
        with self._lock:
            self._task = str(value)

    @property
    def subtask(self) -> str:
        with self._lock:
            return self._subtask

    @subtask.setter
    def subtask(self, value: str) -> None:
        with self._lock:
            self._subtask = str(value)

    def _log(self, msg: str) -> None:
        add_log(msg, ctx=self._ctx)

    def _sync_warning(self, msg: str) -> None:
        add_log(msg, ctx=self._ctx)

    def start(self) -> None:
        if not self.enabled:
            return
        if self._running:
            return

        self._clear_buffers()

        self._start_perf = time.perf_counter()
        self._cameras = RealSenseCameraPair(
            self._cfg["cameras"],
            log_fn=self._log,
        )
        self._cameras.start(self._start_perf)

        self._running = True
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

        add_log(
            "Data collection started: task=%r, subtask=%r, rate=%sHz"
            % (self.task, self.subtask, int(self._cfg["sample_hz"])),
            ctx=self._ctx,
        )

    def stop(self, *, save: bool) -> str | None:
        if not self.enabled:
            return None

        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

        if self._cameras is not None:
            self._cameras.stop()
            self._cameras = None

        frame_count = len(self._timestamps)
        duration_s = self._timestamps[-1] if self._timestamps else 0.0

        if not save:
            self._clear_buffers()
            add_log("Data collection discarded: cycle cancelled or failed", ctx=self._ctx)
            return None

        if frame_count == 0:
            add_log("Data collection discarded: no frames captured", ctx=self._ctx)
            return None

        path = self._write_hdf5(duration_s)
        add_log(
            "Data collection saved: %s, frames=%s, duration=%.1fs"
            % (path.name, frame_count, duration_s),
            ctx=self._ctx,
        )
        self._clear_buffers()
        return str(path)

    def _clear_buffers(self) -> None:
        self._timestamps.clear()
        self._subtasks.clear()
        self._joint_positions.clear()
        self._eef_positions.clear()
        self._gripper_states.clear()
        self._box_images.clear()
        self._wrist_images.clear()

    def _sample_loop(self) -> None:
        interval = 1.0 / self._cfg["sample_hz"]
        sync_max_delta_s = self._cfg["sync_max_delta_ms"] / 1000.0
        next_tick = time.perf_counter()
        cameras = self._cameras

        while self._running:
            if self._cancel_event and self._cancel_event.is_set():
                break

            now = time.perf_counter()
            if now < next_tick:
                time.sleep(min(0.001, next_tick - now))
                continue
            next_tick += interval
            if now - next_tick > interval:
                next_tick = now + interval

            try:
                joints = self._robot.get_actual_joint_position()
                if len(joints) != NUM_JOINTS:
                    logger.warning(
                        "Unexpected joint count %s (expected %s), skipping frame",
                        len(joints),
                        NUM_JOINTS,
                    )
                    continue

                eef = self._robot.get_actual_tcp_position()
                if len(eef) != NUM_EEF:
                    logger.warning(
                        "Unexpected eef count %s (expected %s), skipping frame",
                        len(eef),
                        NUM_EEF,
                    )
                    continue

                gripper_open = self._gripper.commanded_is_open
                gripper_val = 1.0 if gripper_open else 0.0

                with self._lock:
                    subtask = self._subtask

                ts = time.perf_counter() - self._start_perf

                box_img = np.zeros(
                    (self._cfg["camera_height"], self._cfg["camera_width"], self._cfg["camera_channels"]),
                    dtype=np.uint8,
                )
                wrist_img = box_img.copy()
                if cameras is not None:
                    box_img = cameras.box.get_frame_near(
                        ts,
                        sync_max_delta_s=sync_max_delta_s,
                        on_sync_warning=self._sync_warning,
                    )
                    wrist_img = cameras.wrist.get_frame_near(
                        ts,
                        sync_max_delta_s=sync_max_delta_s,
                        on_sync_warning=self._sync_warning,
                    )

                self._timestamps.append(ts)
                self._subtasks.append(subtask)
                self._joint_positions.append(joints)
                self._eef_positions.append(eef)
                self._gripper_states.append(gripper_val)
                self._box_images.append(box_img)
                self._wrist_images.append(wrist_img)
            except Exception as e:
                logger.warning("Data collection sample failed: %s", e)

    def _write_hdf5(self, duration_s: float) -> Path:
        out_dir = Path(self._cfg["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"episode_{stamp}.hdf5"

        n = len(self._timestamps)
        h = self._cfg["camera_height"]
        w = self._cfg["camera_width"]
        c = self._cfg["camera_channels"]

        str_dtype = h5py.string_dtype(encoding="utf-8")
        timestamps = np.asarray(self._timestamps, dtype=np.float64)
        subtasks = np.asarray(self._subtasks, dtype=str_dtype)
        joint_state = np.asarray(self._joint_positions, dtype=np.float64).reshape(n, NUM_JOINTS)
        eef_state = np.asarray(self._eef_positions, dtype=np.float64).reshape(n, NUM_EEF)
        gripper_state = np.asarray(self._gripper_states, dtype=np.float32)

        if self._box_images:
            box_stack = np.stack(self._box_images, axis=0)
            wrist_stack = np.stack(self._wrist_images, axis=0)
        else:
            box_stack = np.zeros((n, h, w, c), dtype=np.uint8)
            wrist_stack = box_stack.copy()

        with h5py.File(path, "w") as f:
            f.attrs["task"] = self.task
            f.attrs["sample_rate_hz"] = self._cfg["sample_hz"]
            f.attrs["created_at"] = datetime.now().isoformat(timespec="seconds")
            f.attrs["duration_s"] = float(duration_s)

            meta_grp = f.create_group("metadata")
            for key, value in self._cfg["metadata"].items():
                meta_grp.attrs[key] = value

            f.create_dataset("timestamps", data=timestamps, compression="gzip")
            f.create_dataset("subtask", data=subtasks, compression="gzip")

            obs_grp = f.create_group("observation")
            images_grp = obs_grp.create_group("images")
            images_grp.create_dataset(
                "box_image",
                data=box_stack,
                compression="gzip",
                compression_opts=4,
            )
            images_grp.create_dataset(
                "wrist_image",
                data=wrist_stack,
                compression="gzip",
                compression_opts=4,
            )

            state_grp = obs_grp.create_group("state")
            state_grp.create_dataset("joint_state", data=joint_state, compression="gzip")
            state_grp.create_dataset("eef_state", data=eef_state, compression="gzip")
            state_grp.create_dataset("gripper_state", data=gripper_state, compression="gzip")

        return path
