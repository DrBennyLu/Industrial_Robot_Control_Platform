from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jaka_app.exceptions import JakaApiError, JakaNotInstalledError

logger = logging.getLogger(__name__)

_JAKA_SDK_DIR = Path(__file__).resolve().parent
if str(_JAKA_SDK_DIR) not in sys.path:
    sys.path.insert(0, str(_JAKA_SDK_DIR))
if sys.platform == "win32":
    try:
        os.add_dll_directory(str(_JAKA_SDK_DIR))
    except (AttributeError, OSError):
        pass


try:
    import src.jaka_app.jkrc as _jkrc

    _JKRC = _jkrc
except ImportError:  # pragma: no cover - dev machine without vendor SDK
    _JKRC = None

# Official SDK constants (see JAKA Python SDK doc)
ABS = getattr(_JKRC, "ABS", 0) if _JKRC else 0
INCR = getattr(_JKRC, "INCR", 1) if _JKRC else 1
COORD_BASE = getattr(_JKRC, "COORD_BASE", 0) if _JKRC else 0
COORD_JOINT = getattr(_JKRC, "COORD_JOINT", 1) if _JKRC else 1
COORD_TOOL = getattr(_JKRC, "COORD_TOOL", 2) if _JKRC else 2


def _require_jkrc() -> Any:
    if _JKRC is None:
        raise JakaNotInstalledError(
            "jkrc is not installed. Install vendor JAKA Python SDK and jakaAPI.dll per README."
        )
    return _JKRC


def _check(ret: Any, method: str) -> None:
    if ret is None:
        raise JakaApiError(f"{method}: no return value", None, method)
    if isinstance(ret, tuple) and len(ret) > 0 and ret[0] != 0:
        raise JakaApiError(f"{method} failed with ret={ret[0]}", int(ret[0]), method)


@dataclass
class RobotStatusSnapshot:
    """Subset of fields for HMI; indices follow get_robot_status() order in V3 doc."""

    errcode: int | None = None
    inpos: int | None = None
    powered_on: int | None = None
    enabled: int | None = None
    rapidrate: float | None = None
    protective_stop: int | None = None
    drag_status: int | None = None
    on_soft_limit: int | None = None
    emergency_stop: int | None = None
    is_socket_connect: int | None = None
    cart_position: Any | None = None
    joint_position: Any | None = None
    din: Any | None = None
    dout: Any | None = None
    estoped: int | None = None
    power_on_state: int | None = None
    servo_enabled: int | None = None
    program_state: int | None = None
    logic_line: int | None = None
    motion_line: Any | None = None
    loaded_file: str | None = None
    raw_robot_status_len: int | None = None


class JakaRobotController:
    """Thin wrapper over jkrc.RC with return-code checks and a motion lock."""

    def __init__(self, ip: str) -> None:
        _require_jkrc()
        self._ip = ip
        self._rc: Any = None
        self.motion_lock = threading.RLock()

    def _ensure_rc(self) -> Any:
        if self._rc is None:
            raise JakaApiError("Robot is not connected.", -1, "session")
        return self._rc

    @property
    def ip(self) -> str:
        return self._ip

    def connect(self, power_on: bool = False, enable: bool = False) -> None:
        jk = _require_jkrc()
        with self.motion_lock:
            if self._rc is not None:
                return
            self._rc = jk.RC(self._ip)
            try:
                ret = self._rc.login()
                _check(ret, "login")
            except Exception:
                self._rc = None
                raise
            if power_on:
                self.power_on()
            if enable:
                self.enable_robot()

    def disconnect(self) -> None:
        with self.motion_lock:
            if self._rc is None:
                return
            try:
                ret = self._rc.logout()
                if isinstance(ret, tuple) and ret and ret[0] != 0:
                    logger.warning("logout ret=%s", ret[0])
            finally:
                self._rc = None

    def power_on(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().power_on(), "power_on")

    def power_off(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().power_off(), "power_off")

    def enable_robot(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().enable_robot(), "enable_robot")

    def disable_robot(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().disable_robot(), "disable_robot")

    def get_robot_state(self) -> tuple[int, int, int]:
        """Returns (estoped, power_on, servo_enabled) after ret check."""
        with self.motion_lock:
            ret = self._ensure_rc().get_robot_state()
        _check(ret, "get_robot_state")
        return int(ret[1][0]), int(ret[1][1]), int(ret[1][2])

    def get_robot_status_tuple(self) -> tuple[Any, ...]:
        with self.motion_lock:
            ret = self._ensure_rc().get_robot_status()
        _check(ret, "get_robot_status")
        return tuple(ret[1])

    def snapshot_status(self) -> RobotStatusSnapshot:
        snap = RobotStatusSnapshot()
        if self._rc is None:
            return snap
        try:
            st = self.get_robot_status_tuple()
            snap.raw_robot_status_len = len(st)
            # Indices per JAKA V3 Python SDK doc (get_robot_status tuple order).
            if len(st) >= 24:
                snap.errcode = int(st[0])
                snap.inpos = int(st[1])
                snap.powered_on = int(st[2])
                snap.enabled = int(st[3])
                snap.rapidrate = float(st[4]) if st[4] is not None else None
                snap.protective_stop = int(st[5])
                snap.drag_status = int(st[6])
                snap.on_soft_limit = int(st[7])
                snap.dout = st[10]
                snap.din = st[11]
                snap.cart_position = st[18]
                snap.joint_position = st[19]
                snap.is_socket_connect = int(st[22])
                snap.emergency_stop = int(st[23])
        except JakaApiError as e:
            snap.errcode = -1
            logger.debug("snapshot_status robot_status failed: %s", e)
        try:
            e, p, s = self.get_robot_state()
            snap.estoped, snap.power_on_state, snap.servo_enabled = e, p, s
        except JakaApiError:
            pass
        try:
            with self.motion_lock:
                pr = self._ensure_rc().get_program_state()
            _check(pr, "get_program_state")
            snap.program_state = int(pr[1])
        except JakaApiError:
            snap.program_state = None
        try:
            with self.motion_lock:
                pi = self._ensure_rc().get_program_info()
            _check(pi, "get_program_info")
            snap.logic_line = int(pi[1])
            snap.motion_line = pi[2]
            snap.loaded_file = str(pi[3]) if pi[3] is not None else None
        except JakaApiError:
            pass
        return snap

    def get_actual_joint_position(self) -> list[float]:
        with self.motion_lock:
            ret = self._ensure_rc().get_actual_joint_position()
        _check(ret, "get_actual_joint_position")
        return [float(x) for x in ret[1]]

    def get_actual_tcp_position(self) -> list[float]:
        with self.motion_lock:
            ret = self._ensure_rc().get_actual_tcp_position()
        _check(ret, "get_actual_tcp_position")
        return [float(x) for x in ret[1]]

    def joint_move_abs(self, joint_rad: list[float], speed_rad_s: float, blocking: bool = True) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().joint_move(joint_rad, ABS, blocking, speed_rad_s), "joint_move")

    def linear_move_abs(self, tcp_pose: list[float], speed_mm_s: float, blocking: bool = True) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().linear_move(tcp_pose, ABS, blocking, speed_mm_s), "linear_move")

    def jog_once(
        self,
        axis_index: int,
        coord_type: int,
        velocity: float,
        pos_cmd: float,
        move_mode: int = INCR,
    ) -> None:
        """Single jog command; streamer calls periodically (<500ms)."""
        with self.motion_lock:
            ret = self._ensure_rc().jog(axis_index, move_mode, coord_type, velocity, pos_cmd)
            _check(ret, "jog")

    def jog_stop_all(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().jog_stop(-1), "jog_stop")

    def drag_mode_enable(self, enable: bool) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().drag_mode_enable(enable), "drag_mode_enable")

    def is_in_drag_mode(self) -> bool:
        with self.motion_lock:
            ret = self._ensure_rc().is_in_drag_mode()
        _check(ret, "is_in_drag_mode")
        return bool(ret[1])

    def program_load(self, name: str) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().program_load(name), "program_load")

    def program_run(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().program_run(), "program_run")

    def program_pause(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().program_pause(), "program_pause")

    def program_resume(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().program_resume(), "program_resume")

    def program_abort(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().program_abort(), "program_abort")

    def collision_recover(self) -> None:
        with self.motion_lock:
            _check(self._ensure_rc().collision_recover(), "collision_recover")

    def wait_program_done(
        self,
        timeout_s: float = 120.0,
        poll_s: float = 0.2,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Block until cabinet program stops (state 0) or timeout/cancel."""
        deadline = time.time() + timeout_s
        while True:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Program wait cancelled by user.")
            with self.motion_lock:
                ret = self._ensure_rc().get_program_state()
            _check(ret, "get_program_state")
            state = int(ret[1])
            if state == 0:
                return
            if time.time() > deadline:
                raise TimeoutError(f"program did not finish within {timeout_s:.1f}s")
            time.sleep(poll_s)

    def confirm_cabinet_program_started(self, settle_s: float = 0.3, timeout_s: float = 5.0) -> None:
        """After program_run(), wait until program state is running or paused (1 or 2)."""
        time.sleep(settle_s)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            with self.motion_lock:
                ret = self._ensure_rc().get_program_state()
            _check(ret, "get_program_state")
            state = int(ret[1])
            if state in (1, 2):
                return
            time.sleep(0.1)
        raise RuntimeError("作业指令已发，但未进入运行/暂停状态")

    def wait_cabinet_program_complete(
        self,
        timeout_s: float = 1200.0,
        poll_s: float = 0.1,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """
        Poll until cabinet program idle (state 0). During wait, re-check robot safety;
        abort program on fault (same policy as run_remote_job_robust wait phase).
        """
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if cancel_event and cancel_event.is_set():
                try:
                    self.program_abort()
                except Exception:
                    pass
                raise RuntimeError("Program wait cancelled by user.")

            try:
                with self.motion_lock:
                    ret = self._ensure_rc().get_program_state()
                _check(ret, "get_program_state")
                state = int(ret[1])
            except JakaApiError as e:
                try:
                    self.program_abort()
                except Exception:
                    pass
                raise RuntimeError(f"轮询程序状态失败: {e}") from e

            safe, msg = self.is_safe_to_move(auto_enable=False, allow_program_busy=True)
            if not safe and "忙碌" not in msg:
                try:
                    self.program_abort()
                except Exception:
                    pass
                raise RuntimeError(f"作业运行中断: {msg}")

            if state == 0:
                return
            time.sleep(poll_s)

        try:
            self.program_abort()
        except Exception:
            pass
        raise TimeoutError(f"cabinet program did not finish within {timeout_s:.1f}s")

    def run_remote_job(
        self,
        program_name: str,
        wait_done: bool = True,
        timeout_s: float = 120.0,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """
        Convenience wrapper:
        program_load(program_name) -> program_run() -> optional wait done.
        """
        self.program_load(program_name)
        self.program_run()
        if wait_done:
            self.wait_program_done(timeout_s=timeout_s, cancel_event=cancel_event)

    def get_detailed_status(self) -> dict[str, Any] | None:
        """
        获取可读状态字典（用于产线前置检查/日志）。
        """
        if self._rc is None:
            return None
        snap = self.snapshot_status()
        return {
            "errcode": snap.errcode,
            "inpos": snap.inpos,
            "powered_on": snap.powered_on if snap.powered_on is not None else snap.power_on_state,
            "enabled": snap.enabled if snap.enabled is not None else snap.servo_enabled,
            "rapidrate": snap.rapidrate,
            "protective_stop": snap.protective_stop,
            "drag_status": snap.drag_status,
            "emergency_stop": snap.emergency_stop if snap.emergency_stop is not None else snap.estoped,
            "program_state": snap.program_state,
            "is_socket_connect": snap.is_socket_connect,
        }

    def is_safe_to_move(
        self,
        auto_enable: bool = False,
        allow_program_busy: bool = False,
    ) -> tuple[bool, str]:
        """
        核心鲁棒性检查：判断机器人是否满足运动条件。
        """
        try:
            status = self.get_detailed_status()
            if not status:
                return False, "无法获取机器人状态，通信可能中断"

            if status.get("is_socket_connect") == 0:
                return False, "SDK 与控制器通信异常"
            if status.get("emergency_stop") == 1:
                return False, "急停已触发"
            if status.get("protective_stop") == 1:
                return False, "碰撞/保护停止触发"

            errcode = status.get("errcode")
            if errcode not in (None, 0):
                return False, f"机器人报错 errcode={errcode}"

            # 某些控制器版本有 is_error()，可额外检查。
            if hasattr(self._ensure_rc(), "is_error"):
                try:
                    ret = self._ensure_rc().is_error()
                    _check(ret, "is_error")
                    if bool(ret[1]):
                        return False, "机器人报警状态未清除"
                except Exception:
                    logger.debug("is_error() not usable on current controller", exc_info=True)

            if status.get("enabled") == 0:
                if not auto_enable:
                    return False, "机器人未使能"
                logger.warning("机器人未使能，尝试自动使能...")
                self.enable_robot()
                time.sleep(1.0)
                status = self.get_detailed_status() or {}
                if status.get("enabled") == 0:
                    return False, "自动使能失败"

            # SDK 文档: 0停止, 1运行, 2暂停。运行/暂停都视为 busy。
            p_state = status.get("program_state")
            if not allow_program_busy and p_state in (1, 2):
                return False, f"机器人忙碌（程序状态={p_state}）"

            return True, "Ready"
        except Exception as e:
            logger.exception("is_safe_to_move 异常")
            return False, f"安全检查异常: {e}"

    def run_remote_job_robust(
        self,
        program_name: str,
        wait_until_done: bool = True,
        timeout_s: float = 1200.0,
        poll_s: float = 0.5,
        cancel_event: threading.Event | None = None,
        auto_enable: bool = False,
        precheck: bool = True,
    ) -> bool:
        """
        高鲁棒执行：可选前置检查 -> 下发作业 -> 启动确认 -> 运行监控。
        Set precheck=False when the caller already ran pre_action_check (e.g. main flow).
        """
        logger.info("准备执行作业: %s", program_name)

        if precheck:
            safe, msg = self.is_safe_to_move(auto_enable=auto_enable, allow_program_busy=False)
            if not safe:
                logger.error("拒绝执行作业，原因: %s", msg)
                return False

        try:
            self.program_load(program_name)
            self.program_run()
        except Exception as e:
            logger.error("作业启动失败: %s", e)
            return False

        try:
            self.confirm_cabinet_program_started()
        except Exception as e:
            logger.error("作业状态确认失败: %s", e)
            return False

        if not wait_until_done:
            return True

        try:
            self.wait_cabinet_program_complete(
                timeout_s=timeout_s, poll_s=poll_s, cancel_event=cancel_event
            )
        except TimeoutError:
            logger.error("作业 %s 执行超时(%.1fs)", program_name, timeout_s)
            return False
        except RuntimeError as e:
            logger.error("%s", e)
            return False

        logger.info("作业 %s 执行完成", program_name)
        return True


class JogStreamer:
    """Background jog sender; controller requires jog within ~500ms."""

    def __init__(self, controller: JakaRobotController, axis_index: int, coord_type: int, velocity: float, pos_cmd: float):
        self._controller = controller
        self._axis_index = axis_index
        self._coord_type = coord_type
        self._velocity = velocity
        self._pos_cmd = pos_cmd
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.stop()
        self._stop.clear()

        def loop() -> None:
            while not self._stop.wait(0.35):
                try:
                    self._controller.jog_once(
                        self._axis_index,
                        self._coord_type,
                        self._velocity,
                        self._pos_cmd,
                        INCR,
                    )
                except JakaApiError as e:
                    logger.warning("jog stream error: %s", e)
                    break

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._controller.jog_stop_all()
        except JakaApiError:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
