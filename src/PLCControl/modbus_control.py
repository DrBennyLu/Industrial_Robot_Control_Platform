#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modbus TCP 控制脚本
用于向 IP 地址为 169.254.5.31 的设备的 000000 位置发送 0 或 1 值, 可以使传送带向前运动。
新增：读取保持寄存器功能
"""
from unittest import result

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import sys
import time


# 汇川easy521 寄存器 地址

# X0-X1777: 0XF800-0XFBFF (63488-64511) 输入线圈
# Y0-Y1777: 0XFC00-0XFFFF (64512-65535) 输出线圈

INPUT_START_ADDR = 63497   #光电1： X11，0xF809, X16是到位信号

INPUT_NUM = 7 # 输入点数

class ModbusController:
    """Modbus TCP 控制器"""

    def __init__(self, ip_address='169.254.5.31', port=502):
        self.ip_address = ip_address
        self.port = port
        self.client = None

    def connect(self):
        """建立连接"""
        try:
            self.client = ModbusTcpClient(self.ip_address, port=self.port)
            if self.client.connect():
                print(f"✓ 成功连接到 {self.ip_address}:{self.port}")
                return True
            else:
                print(f"✗ 无法连接到 {self.ip_address}:{self.port}")
                return False
        except Exception as e:
            print(f"✗ 连接异常: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.close()
            print(f"✓ 已断开连接")

    def write_coil(self, address, value):
        """写入单个线圈"""
        if not self.client or not self.client.is_socket_open():
            print("✗ 客户端未连接")
            return False

        try:
            # 适配你的源码：使用 device_id 而非 unit
            result = self.client.write_coil(address, bool(value), device_id=1)

            if not result.isError():
                print(f"✓ 成功写入: 地址={address:06d}, 值={value}")
                return True
            else:
                print(f"✗ 写入失败: {result}")
                return False

        except ModbusException as e:
            print(f"✗ Modbus 异常: {e}")
            return False
        except Exception as e:
            print(f"✗ 写入异常: {e}")
            return False

    def read_coil(self, address, count=1):
        """读取线圈状态"""
        if not self.client or not self.client.is_socket_open():
            print("✗ 客户端未连接")
            return None

        try:
            # 纯位置参数，适配你的版本
            result = self.client.read_coils(address, count)

            if not result.isError():
                print(f"✓ 读取线圈成功: 地址={address:06d}, 值={result.bits[:count]}")
                return result.bits[:count]
            else:
                print(f"✗ 读取线圈失败: {result}")
                return None

        except Exception as e:
            print(f"✗ 读取线圈异常: {e}")
            return None

    def write_register(self, address, value):
        """写入单个保持寄存器"""
        if not self.client or not self.client.is_socket_open():
            print("✗ 客户端未连接")
            return False

        try:
            result = self.client.write_register(address, value, device_id=1)

            if not result.isError():
                print(f"✓ 成功写入寄存器: 地址={address:06d}, 值={value}")
                return True
            else:
                print(f"✗ 写入寄存器失败: {result}")
                return False

        except ModbusException as e:
            print(f"✗ Modbus 异常: {e}")
            return False
        except Exception as e:
            print(f"✗ 写入寄存器异常: {e}")
            return False

    # ===================== 新增函数：读取保持寄存器 =====================
    def read_register(self, address, count=1):
        """
        读取保持寄存器（Holding Register）

        Args:
            address: 起始地址
            count: 读取数量

        Returns:
            list: 读取的值列表，失败返回 None
        """
        if not self.client or not self.client.is_socket_open():
            print("✗ 客户端未连接")
            return None

        try:
            # 纯位置参数，无任何多余关键字（完美适配你的pymodbus版本）
            result = self.client.read_holding_registers(address, count=count)

            if not result.isError():
                print(f"✓ 读取寄存器成功: 地址={address:06d}, 值={result.registers}")
                return result.registers
            else:
                print(f"✗ 读取寄存器失败: {result}")
                return None

        except Exception as e:
            print(f"✗ 读取寄存器异常: {e}")
            return None

    # 读取离散输入
    def read_discrete_inputs(self, address, count=1):
        """
        读取光电开关离散输入

        Args:
            address: 起始地址
            count: 读取数量

        Returns:
            list: 读取的值列表，失败返回 None
        """
        if not self.client or not self.client.is_socket_open():
            print("✗ 客户端未连接")
            return None

        try:
            #
            result = self.client.read_discrete_inputs(address=address, count=count)

            if not result.isError():
                print(f"✓ 读取寄存器成功: 地址={address:06d}")
                for i, bit in enumerate(result.bits[:count]):
                    status = 1 if bit else 0
                    print(f"输入 X{i} : {status} (bit = {bit})")
                return result.bits[:count]
            else:
                print(f"✗ 读取寄存器失败: {result}")
                return None

        except Exception as e:
            print(f"✗ 读取寄存器异常: {e}")
            return None


def loader_forward():
    """主函数"""
    controller = ModbusController(ip_address='169.254.5.31', port=502)

    if not controller.connect():
        sys.exit(1)

    try:

        reg_address = 0  # 上料台前进寄存器地址
        print("上料台前进")
        # 写入寄存器
        controller.write_register(reg_address, 0)
        time.sleep(0.1)
        # 读取寄存器
        controller.read_register(reg_address, 1)
        time.sleep(0.1)
        controller.write_register(reg_address, 1)
        time.sleep(0.1)
        controller.read_register(reg_address, 1)
        time.sleep(0.1)
        print("完成")

    except KeyboardInterrupt:
        print("\n\n✗ 用户中断")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
    finally:
        controller.disconnect()

def find_empty_slot():
    """主函数"""
    controller = ModbusController(ip_address='169.254.5.31', port=502)
    if not controller.connect():
        sys.exit(1)
    try:
        print("读取IO输入")
        result = controller.read_discrete_inputs(address=INPUT_START_ADDR, count=INPUT_NUM)
        print("完成")
        remove_index = 5
        result = result[:remove_index] + result[remove_index+1:]
        return result
    except KeyboardInterrupt:
        print("\n\n✗ 用户中断")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
    finally:
        controller.disconnect()



def send_value(value):
    """快捷发送值"""
    controller = ModbusController(ip_address='169.254.5.31', port=502)

    if not controller.connect():
        return False

    try:
        success = controller.write_coil(0, value)
        return success
    finally:
        controller.disconnect()

def test_read_inputs():
    """主函数"""
    controller = ModbusController(ip_address='169.254.5.31', port=502)
    if not controller.connect():
        sys.exit(1)
    try:
        print("读取IO输入")
        controller.read_discrete_inputs(address=INPUT_START_ADDR, count=INPUT_NUM)
        print("完成")

    except KeyboardInterrupt:
        print("\n\n✗ 用户中断")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
    finally:
        controller.disconnect()


if __name__ == "__main__":
    # loader_forward()
    # test_read_inputs()
    print(find_empty_slot())