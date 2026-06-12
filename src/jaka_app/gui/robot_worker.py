from __future__ import annotations

import importlib.util
import logging
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
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
    connect_result = pyqtSignal(bool, str)
    gripper_connect_result = pyqtSignal(bool, str)
    teach_list_changed = pyqtSignal()
    flow_finished = pyqtSignal(bool, str)

    def __init__(self, ctx: ApplicationContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._jog: JogStreamer | None = None
        self._auto_thread: threading.Thread | None = None
        self._auto_stop = threading.Event()
        self._ctx.log_sink = self.log_line.emit

    @pyqtSlot()
    def slot_refresh_status(self) -> None:
        r = self._ctx.robot
        if r:
            self.status_ready.emit(asdict(r.snapshot_status()))
        else:
            self.status_ready.emit({})

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

    def _run_flow_once_record_cycle(self, path: str, func_name: str = "main") -> None:
        """Execute flow once; wall-clock time → append_cycle_record (OK/NG)."""
        import inspect

        t0 = time.perf_counter()
        try:
            fn = self._load_callable(path, func_name)
            # 检查函数签名，如果接受 ctx 参数则传递
            sig = inspect.signature(fn)
            if "ctx" in sig.parameters:
                fn(ctx=self._ctx)
            else:
                fn()
        except Exception as e:
            elapsed = time.perf_counter() - t0
            self._ctx.append_cycle_record(False, elapsed, str(e))
            raise
        elapsed = time.perf_counter() - t0
        self._ctx.append_cycle_record(True, elapsed)

    @pyqtSlot(str)
    def slot_run_flow(self, path: str) -> None:
        self._ctx.cancel_event.clear()
        self._ctx.set_run_state("MAIN_FLOW")
        try:
            self._init_flow_session()
            self._run_flow_once_record_cycle(path, "main")
            self._ctx.set_run_state("IDLE")
            self.flow_finished.emit(True, "done")
        except Exception as e:
            logger.exception("flow")
            self._ctx.set_run_state("FAULT")
            self.flow_finished.emit(False, str(e))
        finally:
            self._teardown_flow_session()

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
        self._ctx.set_run_state("MANUAL_FLOW")
        try:
            fn = self._load_callable(path, func)
            fn()
            self._ctx.set_run_state("IDLE")
            self.flow_finished.emit(True, f"manual function {func} done")
        except Exception as e:
            logger.exception("manual flow function")
            self._ctx.set_run_state("FAULT")
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
            # 无限循环：init 一次后反复调用 main()，间隔 interval_s，直到停止
            self._ctx.set_run_state("AUTO_RUNNING")
            self.log_line.emit("auto loop started")
            try:
                self._init_flow_session()
                while not self._auto_stop.is_set():
                    try:
                        self._run_flow_once_record_cycle(path, "main")
                        self.flow_finished.emit(True, "auto cycle done")
                    except Exception as e:
                        logger.exception("auto flow")
                        self.flow_finished.emit(False, str(e))
                        break
                    if self._auto_stop.is_set():
                        break
                    if interval_s > 0:
                        time.sleep(interval_s)
            finally:
                self._teardown_flow_session()
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

    def _ensure_flows_import_path(self) -> Path:
        project_root = Path(__file__).resolve().parents[3]
        flows_dir = project_root / "flows"
        src_dir = project_root / "src"
        for p in (flows_dir, src_dir):
            s = str(p)
            if s not in sys.path:
                sys.path.insert(0, s)
        return flows_dir

    def _init_flow_session(self) -> None:
        if self._ctx.flow_session_ready:
            self._teardown_flow_session()
        self._ensure_flows_import_path()
        import init_flow

        self.log_line.emit("Flow session init starting...")
        init_flow.init_session(self._ctx, cancel_event=self._ctx.cancel_event)
        self.log_line.emit("Flow session init done.")

    def _teardown_flow_session(self) -> None:
        if not (
            self._ctx.flow_session_ready
            or self._ctx.robot
            or self._ctx.gripper
            or self._ctx.force_sensor
        ):
            return
        self._ensure_flows_import_path()
        import init_flow

        init_flow.teardown_session(self._ctx)

    @pyqtSlot(str)
    def slot_gripper_connect(self, port: str) -> None:
        port = str(port).strip()
        if not port:
            self.gripper_connect_result.emit(False, "串口不能为空")
            return
        g = self._ctx.gripper
        if g is not None and g.is_connected:
            try:
                g.disconnect()
            except Exception:
                pass
            self._ctx.gripper = None
        try:
            self._ensure_flows_import_path()
            import robot_flow

            self._ctx.gripper = robot_flow.connect_gripper(port)
            self._ctx.config.setdefault("gripper", {})
            self._ctx.config["gripper"]["port"] = port
            self.log_line.emit("Gripper connected on %r." % port)
            self.gripper_connect_result.emit(True, "ok")
        except Exception as e:
            logger.exception("gripper connect")
            self._ctx.gripper = None
            self.gripper_connect_result.emit(False, str(e))

    @pyqtSlot()
    def slot_gripper_disconnect(self) -> None:
        g = self._ctx.gripper
        if g:
            try:
                g.disconnect()
            except Exception:
                pass
        self._ctx.gripper = None
        self.log_line.emit("Gripper disconnected.")
        self.gripper_connect_result.emit(False, "disconnected")

    @pyqtSlot()
    def slot_gripper_open(self) -> None:
        g = self._ctx.gripper
        if not g or not g.is_initialized:
            self.log_line.emit("Gripper not connected or not initialized.")
            return
        if not g.open():
            self.log_line.emit("Gripper open failed.")
            return
        self.log_line.emit("Gripper open sent.")

    @pyqtSlot()
    def slot_gripper_close(self) -> None:
        g = self._ctx.gripper
        if not g or not g.is_initialized:
            self.log_line.emit("Gripper not connected or not initialized.")
            return
        if not g.close():
            self.log_line.emit("Gripper close failed.")
            return
        self.log_line.emit("Gripper close sent.")

    @pyqtSlot()
    def slot_run_home_flow(self) -> None:
        self._ctx.cancel_event.clear()
        self._ctx.set_run_state("HOME_FLOW")
        try:
            flows_dir = self._ensure_flows_import_path()
            home_path = flows_dir / "home_flow.py"
            fn = self._load_callable(str(home_path), "main")
            fn()
            self._ctx.set_run_state("IDLE")
            self.flow_finished.emit(True, "home done")
        except Exception as e:
            logger.exception("home flow")
            self._ctx.set_run_state("FAULT")
            self.flow_finished.emit(False, str(e))
