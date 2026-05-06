from DHController import  GripperController

gripper = GripperController("COM3")
gripper.connect()
gripper.initialize()
gripper.close()
gripper.disconnect()
