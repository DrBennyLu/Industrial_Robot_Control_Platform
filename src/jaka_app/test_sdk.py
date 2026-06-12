import sys
import jkrc
import time
import numpy as np

from DHController import GripperController

robot = jkrc.RC("169.254.5.10")

def find_value_by_key(data_tuple: tuple, target_key: str):
    """
    从嵌套元组中查找指定标识对应的数值
    :param data_tuple: 原始的大元组（你提供的result数据）
    :param target_key: 要查找的【第三个元素】字符串（如'SYS_NO_PARTS'）
    :return: 匹配到的【第二个元素】数值，未找到返回None
    """
    # 跳过元组第一个元素（0），遍历所有子元组
    for item in data_tuple[1:]:
        # 安全校验：确保是三元组，避免报错
        if isinstance(item, tuple) and len(item) == 3:
            # 解包子元组：(编号, 数值, 标识)
            id, value, key = item
            # 匹配目标标识
            if key == target_key:
                return value
    # 未找到匹配项返回None
    return None

robot.login()

ret = robot.get_user_var()
print("get_user_var result is: ", ret)
value = find_value_by_key(ret, "SYS_NO_PARTS")
print(value)


gripper = GripperController("COM7")
gripper.connect()
gripper.initialize()


gripper.open()


ret = robot.get_joint_position()
# if ret[0] == 0:
#     print("the joint position is :",np.rad2deg(ret[1]))
# else:
#     print("some things happend,the errcode is: ",ret[0])
ret = robot.program_load("demohome")#加载回零脚本
ret = robot.get_loaded_program()
print("the loaded program is:",ret[1])
robot.program_run()
while True:
    state = robot.get_program_state()
    print(state)
    if state[1] == 0:
        break
    time.sleep(0.1)

time.sleep(0.01)

ret = robot.program_load("demopick0430")#加载抓取脚本
ret = robot.get_loaded_program()
print("the loaded program is:",ret[1])
robot.program_run()
while True:
    state = robot.get_program_state()
    if state[1] == 0:
        break
    time.sleep(0.1)

gripper.close()

ret = robot.program_load("demolift0506")#加载提起脚本
ret = robot.get_loaded_program()
print("the loaded program is:",ret[1])
robot.program_run()
while True:
    state = robot.get_program_state()
    if state[1] == 0:
        break
    time.sleep(0.1)

gripper.open()

ret = robot.program_load("demoafterplace0506")#加载避让脚本
ret = robot.get_loaded_program()
print("the loaded program is:",ret[1])
robot.program_run()
while True:
    state = robot.get_program_state()
    if state[1] == 0:
        break
    time.sleep(0.1)


ret = robot.program_load("demohome")#加载回零脚本
ret = robot.get_loaded_program()
print("the loaded program is:",ret[1])
robot.program_run()
while True:
    state = robot.get_program_state()
    if state[1] == 0:
        break
    time.sleep(0.1)


robot.logout()
gripper.disconnect()