from __future__ import annotations

from jaka_app.robot_controller import JakaRobotController, find_value_by_key

# 控制柜程序名（与 test_sdk 一致，现场可改）
PROG_HOME = "demohome"
# 对应1号钣金
PROG_PICK = "demopick0430"
PROG_LIFT = "demolift0506"
PROG_LIFT_1 = "demolift_1_0507"
PROG_LIFT_2 = "demolift_2_0518"
# PROG_LIFT_3 = "demolift0506_3"
PROG_AFTER_PLACE = "demoafterplace0514"
PROG_PICK_ONLY = "demopickonly0518"
PROG_FIRST_PICK = "first_pick_0513"
PROG_FIRST_PICK_PRC = "first_pick_0513prc"
# 对应2号钣金
PROG_FIRST_PICK_PRC2 = "first_pick_0528prc2"
PROG_LIFT_21 = "demolift_21_0528"
PROG_LIFT_22 = "demolift_22_0528"
PROG_AFTER_PLACE2 = "demoafterplace2_0528"
PROG_PICK_ONLY2 = "demopickonly2_0528"



# 1号钣金，料槽下标 0..n-1 对应放置子程序
LIFT_SN1_PROGRAM_BY_SLOT: list[str] = [
    PROG_LIFT_1,
    PROG_LIFT_2,
    # PROG_LIFT_3,
]

# 2号钣金，料槽下标 0..n-1 对应放置子程序
LIFT_SN2_PROGRAM_BY_SLOT: list[str] = [
    PROG_LIFT_21,
    PROG_LIFT_22,
    # PROG_LIFT_3,
]


def lift_program_for_slot(slot_index: int, SN: int) -> str:
    if slot_index < 0 or slot_index >= len(LIFT_SN1_PROGRAM_BY_SLOT) or slot_index >= len(LIFT_SN2_PROGRAM_BY_SLOT):
        raise IndexError(
            f"slot_index {slot_index} out of range"
        )
    if SN == 1:
        return LIFT_SN1_PROGRAM_BY_SLOT[slot_index]
    else:
        return LIFT_SN2_PROGRAM_BY_SLOT[slot_index]
    # return LIFT_PROGRAM_BY_SLOT[slot_index]





def pre_action_check(
    arm: JakaRobotController,
    *,
    allow_program_busy: bool = False,
    auto_enable: bool = False,
) -> None:
    """
    下发机器人指令前的安全检查；失败抛出 RuntimeError。
    """
    ok, msg = arm.is_safe_to_move(auto_enable=auto_enable, allow_program_busy=allow_program_busy)
    if not ok:
        raise RuntimeError(msg)


def run_cabinet_program(
    arm: JakaRobotController,
    program_name: str,
    *,
    timeout_s: float = 1200.0,
    poll_s: float = 0.1,
    cancel_event=None,
) -> None:
    """
    不含前置安全检查：请先调用 pre_action_check。
    program_load → program_run → 启动确认 → 带监护的等待直到停止。
    支持通过 cancel_event 中断等待。
    """
    arm.program_load(program_name)
    arm.program_run()
    arm.confirm_cabinet_program_started()
    arm.wait_cabinet_program_complete(timeout_s=timeout_s, poll_s=poll_s, cancel_event=cancel_event)


def connect_gripper(port: str) -> GripperController:
    """连接并初始化夹爪；失败抛 RuntimeError。"""
    from DHGripper.DHController import GripperController

    g = GripperController(port=port)
    if not g.connect():
        raise RuntimeError(f"夹爪串口连接失败: {port}")
    if not g.initialize():
        raise RuntimeError("夹爪初始化超时或失败")
    # 配置参数
    g.configure(force=100, speed=50)
    # print("参数配置完成")
    return g

def get_sys_val(arm: JakaRobotController, varname: str):
    var = arm.get_robot_system_var()
    val = find_value_by_key(var, varname)
    return val
