from __future__ import annotations

# 控制柜子程序名称（维护区）
JOB_INIT = "INIT_ROBOT"
JOB_PICK_A = "PICK_A"
JOB_PLACE_A = "PLACE_A"
JOB_PICK_B = "PICK_B"
JOB_PLACE_B = "PLACE_B"
JOB_HOME = "GO_HOME"
JOB_SAFE_RETRACT = "SAFE_RETRACT"
JOB_ALARM_POSE = "ALARM_POSE"


def run_init(arm, enable_real_motion: bool) -> None:
    """
    执行机器人初始化子程序。

    输入类型：
    - arm: JakaRobotController，机器人控制器实例。
    - enable_real_motion: bool，是否真实执行运动。

    输出类型：
    - None。
    """
    from flow_utils import run_job

    run_job(arm, JOB_INIT, enable_real_motion)


def run_pick_and_place(arm, path_name: str, enable_real_motion: bool) -> None:
    """
    根据路径类型执行抓取+放置子程序。

    输入类型：
    - arm: JakaRobotController，机器人控制器实例。
    - path_name: str，路径名（通常为 "A" 或 "B"）。
    - enable_real_motion: bool，是否真实执行运动。

    输出类型：
    - None。
    """
    from flow_utils import run_job

    if path_name == "A":
        run_job(arm, JOB_PICK_A, enable_real_motion)
        run_job(arm, JOB_PLACE_A, enable_real_motion)
    else:
        run_job(arm, JOB_PICK_B, enable_real_motion)
        run_job(arm, JOB_PLACE_B, enable_real_motion)


def run_home(arm, enable_real_motion: bool) -> None:
    """
    执行回零位/回原点子程序。

    输入类型：
    - arm: JakaRobotController，机器人控制器实例。
    - enable_real_motion: bool，是否真实执行运动。

    输出类型：
    - None。
    """
    from flow_utils import run_job

    run_job(arm, JOB_HOME, enable_real_motion)


def run_recovery(arm, enable_real_motion: bool) -> None:
    """
    执行异常回退子程序（安全收回 + 报警位）。

    输入类型：
    - arm: JakaRobotController，机器人控制器实例。
    - enable_real_motion: bool，是否真实执行运动。

    输出类型：
    - None。
    """
    from flow_utils import run_job

    run_job(arm, JOB_SAFE_RETRACT, enable_real_motion)
    run_job(arm, JOB_ALARM_POSE, enable_real_motion)

