from __future__ import annotations

import importlib.util
import logging
import threading
import time
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from jaka_app.robot_controller import COORD_JOINT, JogStreamer, JakaRobotController

if TYPE_CHECKING:
    from jaka_app.context import ApplicationContext

logger = logging.getLogger(__name__)


class RobotWorker(QObject):
    """Runs blocking jkrc calls off the GUI thread."""

    log_line = pyqtSignal(str)
    status_ready = pyqtSignal(dict)
    production_ready = pyqtSignal(dict)
    connect_result = pyqtSignal(bool, str)
    teach_list_changed = pyqtSignal()
    flow_finished = pyqtSignal(bool, str)

    def __init__(self, ctx: ApplicationContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._jog: JogStreamer | None = None
        self._auto_thread: threading.Thread | None = None
        self._auto_stop = threading.Event()

    @pyqtSlot()
    def slot_refresh_status(self) -> None:
        r = self._ctx.robot
        if r:
            self.status_ready.emit(asdict(r.snapshot_status()))
        else:
            self.status_ready.emit({})
        self.production_ready.emit(self._ctx.get_production_snapshot())

    @pyqtSlot("PyQt_PyObject")
    def slot_connect(self, bundle: Any) -> None:
        if not isinstance(bundle, dict):
            self.connect_result.emit(False, "internal: bad connect bundle")
            return
        ip = str(bundle.get("ip", ""))
        do_power = bool(bundle.get("power_on", False))
        do_enable = bool(bundle.get("enable", False))
        try:
            ctrl = JakaRobotController(ip)
            ctrl.connect(power_on=do_power, enable=do_enable)
            self._ctx.robot = ctrl
            self._ctx.config.setdefault("robot", {})
            self._ctx.config["robot"]["ip"] = ip
            self.log_line.emit("Connected to robot.")
            self.connect_result.emit(True, "ok")
        except Exception as e:
            logger.exception("connect")
            self._ctx.robot = None
            self.connect_result.emit(False, str(e))

    @pyqtSlot()
    def slot_disconnect(self) -> None:
        self._stop_jog()
        r = self._ctx.robot
        if r:
            try:
                r.disable_robot()
            except Exception:
                pass
            try:
                r.disconnect()
            except Exception:
                pass
        self._ctx.robot = None
        self.log_line.emit("Disconnected.")
        self.connect_result.emit(False, "disconnected")

    @pyqtSlot()
    def slot_power_on(self) -> None:
        r = self._ctx.robot
        if not r:
            return
        r.power_on()
        self.log_line.emit("power_on sent")

    @pyqtSlot()
    def slot_enable(self) -> None:
        r = self._ctx.robot
        if not r:
            return
        r.enable_robot()
        self.log_line.emit("enable_robot sent")

    @pyqtSlot()
    def slot_disable(self) -> None:
        r = self._ctx.robot
        if not r:
            return
        r.disable_robot()
        self.log_line.emit("disable_robot sent")

    @pyqtSlot(bool)
    def slot_drag(self, enable: bool) -> None:
        r = self._ctx.robot
        if not r:
            return
        r.drag_mode_enable(enable)
        self.log_line.emit("drag_mode %s" % enable)

    @pyqtSlot(int, float, float)
    def slot_jog_start(self, joint_index: int, velocity: float, direction: float) -> None:
        self._stop_jog()
        r = self._ctx.robot
        if not r:
            return
        self._jog = JogStreamer(r, joint_index, COORD_JOINT, velocity, direction)
        self._jog.start()
        self.log_line.emit("jog start j=%s v=%s d=%s" % (joint_index, velocity, direction))

    @pyqtSlot()
    def slot_jog_stop(self) -> None:
        self._stop_jog()
        self.log_line.emit("jog stop")

    def _stop_jog(self) -> None:
        if self._jog:
            self._jog.stop()
            self._jog = None

    @pyqtSlot("PyQt_PyObject")
    def slot_record_teach(self, bundle: Any) -> None:
        if not isinstance(bundle, dict):
            return
        name = str(bundle.get("name", "")).strip()
        r = self._ctx.robot
        if not r or not name:
            return
        from jaka_app.teach_points import capture_current_pose

        j, t = capture_current_pose(r)
        self._ctx.teach.add_point(name, j, tcp=t)
        self._ctx.teach.save(self._ctx.teach_points_path)
        self.teach_list_changed.emit()
        self.log_line.emit("Recorded teach point %r" % name)

    @pyqtSlot(str)
    def slot_delete_teach(self, name: str) -> None:
        n = str(name)
        self._ctx.teach.delete(n)
        self._ctx.teach.save(self._ctx.teach_points_path)
        self.teach_list_changed.emit()
        self.log_line.emit("Deleted teach point %r" % n)

    @pyqtSlot(str)
    def slot_run_flow(self, path: str) -> None:
        self._ctx.cancel_event.clear()
        try:
            main_fn = self._load_callable(path, "main")
            main_fn()
            self.flow_finished.emit(True, "done")
        except Exception as e:
            logger.exception("flow")
            self.flow_finished.emit(False, str(e))

    def _load_callable(self, path: str, func_name: str):
        spec = importlib.util.spec_from_file_location("user_main_flow", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load flow spec")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, func_name, None)
        if fn is None:
            raise RuntimeError(f"flow module has no {func_name}()")
        return fn

    @pyqtSlot("PyQt_PyObject")
    def slot_run_flow_function(self, bundle: Any) -> None:
        if not isinstance(bundle, dict):
            return
        path = str(bundle.get("path", "")).strip()
        func = str(bundle.get("function", "main")).strip() or "main"
        self._ctx.cancel_event.clear()
        try:
            fn = self._load_callable(path, func)
            fn()
            self.flow_finished.emit(True, f"manual function {func} done")
        except Exception as e:
            logger.exception("manual flow function")
            self.flow_finished.emit(False, str(e))

    @pyqtSlot("PyQt_PyObject")
    def slot_auto_start(self, bundle: Any) -> None:
        if not isinstance(bundle, dict):
            return
        if self._auto_thread and self._auto_thread.is_alive():
            self.log_line.emit("auto is already running")
            return
        path = str(bundle.get("path", "")).strip()
        interval_s = float(bundle.get("interval_s", 0.0))
        self._ctx.cancel_event.clear()
        self._auto_stop.clear()

        def loop() -> None:
            self._ctx.set_run_state("AUTO_RUNNING")
            self.log_line.emit("auto loop started")
            while not self._auto_stop.is_set():
                try:
                    main_fn = self._load_callable(path, "main")
                    main_fn()
                    self.flow_finished.emit(True, "auto cycle done")
                except Exception as e:
                    logger.exception("auto flow")
                    self.flow_finished.emit(False, str(e))
                    break
                if self._auto_stop.is_set():
                    break
                if interval_s > 0:
                    time.sleep(interval_s)
            self._ctx.set_run_state("IDLE")
            self.log_line.emit("auto loop stopped")

        self._auto_thread = threading.Thread(target=loop, daemon=True)
        self._auto_thread.start()

    @pyqtSlot()
    def slot_auto_stop(self) -> None:
        self._auto_stop.set()
        self._ctx.cancel_event.set()
        self.log_line.emit("auto stop requested")

    @pyqtSlot()
    def slot_cancel_flow(self) -> None:
        self._ctx.cancel_event.set()
        self._auto_stop.set()
        self.log_line.emit("cancel requested")

    @pyqtSlot("PyQt_PyObject")
    def slot_move_named(self, bundle: Any) -> None:
        if not isinstance(bundle, dict):
            return
        from jaka_app.teach_points import move_to_named

        name = str(bundle.get("name", ""))
        strategy = str(bundle.get("strategy", "joint"))
        if strategy not in ("joint", "linear"):
            strategy = "joint"
        req_idle = bool(bundle.get("require_program_idle", True))
        move_to_named(
            self._ctx,
            name,
            strategy=strategy,  # type: ignore[arg-type]
            require_program_idle=req_idle,
        )

    @pyqtSlot(str)
    def slot_program_load(self, name: str) -> None:
        r = self._ctx.robot
        if not r:
            return
        r.program_load(name)
        self.log_line.emit("program_load %r" % name)

    @pyqtSlot()
    def slot_program_run(self) -> None:
        r = self._ctx.robot
        if not r:
            return
        r.program_run()
        self.log_line.emit("program_run")

    @pyqtSlot()
    def slot_program_abort(self) -> None:
        r = self._ctx.robot
        if not r:
            return
        r.program_abort()
        self.log_line.emit("program_abort")

    @pyqtSlot()
    def slot_collision_recover(self) -> None:
        r = self._ctx.robot
        if not r:
            return
        r.collision_recover()
        self.log_line.emit("collision_recover")
