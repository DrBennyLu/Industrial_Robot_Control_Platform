import sys
import jkrc
import time
import numpy as np

from DHController import GripperController

robot = jkrc.RC("169.254.5.10")

robot.login()

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