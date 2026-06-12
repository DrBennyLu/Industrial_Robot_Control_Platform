from __future__ import annotations

import sys
from pathlib import Path
import time

# 同目录子流程、项目 src（DHGripper、jaka_app）
_FLOW_DIR = Path(__file__).resolve().parent
_PROJECT_SRC = _FLOW_DIR.parent / "src"
for _p in (_FLOW_DIR, _PROJECT_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from jaka_app.config_loader import load_application_config
from jaka_app.data_collection import EpisodeRecorder
from jaka_app.robot_controller import JakaRobotController, find_value_by_key
from jaka_app.utils.logging_utils import add_log
from PLCControl.modbus_control import loader_forward

import robot_flow
import slot_flow

_PROJECT_ROOT = _FLOW_DIR.parent
_APPLICATION_YAML = _PROJECT_ROOT / "config" / "application.yaml"
# FIRST_PICK = True
SHEET_NUM = 1   # 对应两种不同钣金物料

# 机器人 IP、夹爪串口见 application.yaml；柜内程序名见 robot_flow
# 料盘全满时的放料等待（秒）；是否循环等待直到出现空位
PLACE_WAIT_INTERVAL_S = 5.0
PLACE_WAIT_UNTIL_EMPTY = True

def load_from_config() -> tuple[str, str, dict]:
    cfg = load_application_config(_APPLICATION_YAML)
    robot = cfg.get("robot") or {}
    gripper = cfg.get("gripper") or {}
    ip = str(robot.get("ip") or "").strip()
    port = str(gripper.get("port") or "").strip()
    if not ip:
        raise ValueError(f"robot.ip is missing or empty in {_APPLICATION_YAML}")
    if not port:
        raise ValueError(f"gripper.port is missing or empty in {_APPLICATION_YAML}")
    return ip, port, cfg


def run_place_phase(arm: JakaRobotController, cfg: dict, SN: int, cancel_event=None, ctx=None) -> int | None:
    """
    放料阶段：有空位则 PROG_LIFT_n；料盘全满则仅 PROG_PICK 并等待。

    返回料槽下标；全满且 PLACE_WAIT_UNTIL_EMPTY=False 时返回 None。
    被取消时抛出 RuntimeError。
    """
    MOVE = True

    while True:
        # 检查取消信号
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("流程被用户取消")

        # occupancy = slot_flow.read_slot_io_fake(cfg)
        occupancy = slot_flow.read_slot_io(cfg)
        if not slot_flow.all_slots_full(occupancy):
            slot_index = slot_flow.find_first_empty_slot(occupancy)
            prog = robot_flow.lift_program_for_slot(slot_index, SN)
            add_log(
                "Place: slot_index=%s occupancy=%s program=%r"
                % (slot_index, occupancy, prog),
                ctx=ctx,
            )
            robot_flow.pre_action_check(arm)
            robot_flow.run_cabinet_program(arm, prog, cancel_event=cancel_event)
            return slot_index

        add_log(
            "All slots full (occupancy=%s): pick-only %r, no lift"
            % (occupancy, robot_flow.PROG_PICK_ONLY),
            ctx=ctx,
        )
        if MOVE:
            robot_flow.pre_action_check(arm)
            if SN == 1:
                robot_flow.run_cabinet_program(arm, robot_flow.PROG_PICK_ONLY, cancel_event=cancel_event)
            else:
                robot_flow.run_cabinet_program(arm, robot_flow.PROG_PICK_ONLY2, cancel_event=cancel_event)
            MOVE = False

        if not PLACE_WAIT_UNTIL_EMPTY:
            return None

        # 分段 sleep，每秒检查一次取消信号
        add_log("Waiting %.1fs for empty slot..." % PLACE_WAIT_INTERVAL_S, ctx=ctx)
        for _ in range(int(PLACE_WAIT_INTERVAL_S)):
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("流程被用户取消")
            time.sleep(1.0)
        # 处理小数部分
        remainder = PLACE_WAIT_INTERVAL_S - int(PLACE_WAIT_INTERVAL_S)
        if remainder > 0:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("流程被用户取消")
            time.sleep(remainder)



def main(ctx=None) -> None:
    """
    主流程入口。

    参数:
        ctx: ApplicationContext 可选参数。如果提供，将支持取消操作。
             当用户点击停止按钮时，流程会响应取消信号并退出。
    """
    cancel_event = ctx.cancel_event if ctx else None

    if not ctx or not ctx.flow_session_ready or not ctx.robot or not ctx.gripper:
        raise RuntimeError("请先执行 init 流程（由 GUI/Worker 自动调用 init_flow.init_session）")
    arm = ctx.robot
    gripper = ctx.gripper
    _, _, cfg = load_from_config()

    start_time = time.time()
    recorder = EpisodeRecorder(arm, gripper, cfg, cancel_event=cancel_event, ctx=ctx)
    recorder.task = "Pick up the sheet metal parts and then place it in the slot"
    recorder.subtask = "pick up the sheet metal in the first layer"
    recorder.start()
    save_episode = False
    try:
        robot_flow.pre_action_check(arm)
        while True:
            # 检查取消信号
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("流程被用户取消")
            if SHEET_NUM == 1:
                add_log("抓取目标为1号钣金物料, 执行程序：PROG_FIRST_PICK_PRC ", ctx=ctx)
                robot_flow.run_cabinet_program(arm, robot_flow.PROG_FIRST_PICK_PRC, cancel_event=cancel_event) #机器人程序内部判定是否已经完成预拍照动作，系统变量PRE_CAP
            elif SHEET_NUM == 2:
                add_log("抓取目标为2号钣金物料, 执行程序：PROG_FIRST_PICK_PRC2 ", ctx=ctx)
                robot_flow.run_cabinet_program(arm, robot_flow.PROG_FIRST_PICK_PRC2, cancel_event=cancel_event) # 对应2号物料
            else:
                add_log("物料错误", ctx=ctx)
                break
            # 如果料框是空的，则等待10秒重新拍照。
            # TODO： 后续，可以加入agv将料放好之后，开始取料的信号同时判断，开始流程。
            if robot_flow.get_sys_val(arm, "SYS_NO_PARTS") == 1:
                add_log("There is no parts in the basket, wait for 10s...", ctx=ctx)
                # 分段 sleep，每秒检查取消信号
                for _ in range(10):
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("流程被用户取消")
                    time.sleep(1.0)
            else:
                break

        gripper.close()

        recorder.subtask = "place the sheet metal in the slot"

        # 放置物料：有空位则 PROG_LIFT_n；全满则仅抓取并等待空位
        run_place_phase(arm, cfg, SN=SHEET_NUM, cancel_event=cancel_event, ctx=ctx)

        robot_flow.pre_action_check(arm)
        # 阻塞：力控伺服结束（|Fx|>阈值）后才继续
        robot_flow.force_servo_control(
            arm,
            cfg=cfg,
            cancel_event=cancel_event,
            ctx=ctx,
            sensor=ctx.force_sensor,
        )
        add_log("Force servo done, opening gripper", ctx=ctx)

        gripper.open()

        robot_flow.pre_action_check(arm)
        if SHEET_NUM == 1:
            add_log("抓取目标为1号钣金物料, 执行程序：PROG_AFTER_PLACE ", ctx=ctx)
            robot_flow.run_cabinet_program(arm, robot_flow.PROG_AFTER_PLACE, cancel_event=cancel_event)
        else:
            add_log("抓取目标为2号钣金物料, 执行程序：PROG_AFTER_PLACE2 ", ctx=ctx)
            robot_flow.run_cabinet_program(arm, robot_flow.PROG_AFTER_PLACE2, cancel_event=cancel_event)

        save_episode = True
    finally:
        recorder.stop(save=save_episode)

    end_time = time.time()
    add_log(f"Cycle time: {end_time - start_time} seconds", ctx=ctx)


    # 向前推传送带
    # loader_forward()
    # add_log("loader forward one slot", ctx=ctx)


if __name__ == "__main__":
    import init_flow
    from jaka_app.context import build_application_context

    cfg = load_application_config(_APPLICATION_YAML)
    _ctx = build_application_context(cfg)
    try:
        init_flow.init_session(_ctx)
        main(ctx=_ctx)
    finally:
        init_flow.teardown_session(_ctx)
