#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modbus TCP 控制脚本
用于向 IP 地址为 192.168.2.88 的设备的 000001 位置发送 0 或 1 值
"""

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import sys
import time


class ModbusController:
    """Modbus TCP 控制器"""
    
    def __init__(self, ip_address='192.168.2.88', port=502):
        """
        初始化 Modbus 客户端
        
        Args:
            ip_address: 目标设备 IP 地址
            port: Modbus TCP 端口（默认 502）
        """
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
        """
        写入单个线圈（Coil）
        
        Args:
            address: 寄存器地址（0-based，000001 对应地址 0）
            value: 要写入的值（0 或 1，True 或 False）
        
        Returns:
            bool: 写入是否成功
        """
        if not self.client or not self.client.is_socket_open():
            print("✗ 客户端未连接")
            return False
        
        try:
            # Modbus 地址通常是 0-based，000001 对应地址 0
            # 如果您的设备使用 1-based 地址，请使用 address - 1
            result = self.client.write_coil(address, bool(value))
            
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
    
    def write_register(self, address, value):
        """
        写入单个保持寄存器（Holding Register）
        
        Args:
            address: 寄存器地址（0-based）
            value: 要写入的值（0-65535）
        
        Returns:
            bool: 写入是否成功
        """
        if not self.client or not self.client.is_socket_open():
            print("✗ 客户端未连接")
            return False
        
        try:
            result = self.client.write_register(address, value)
            
            if not result.isError():
                print(f"✓ 成功写入寄存器: 地址={address:06d}, 值={value}")
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
        """
        读取线圈状态
        
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
            result = self.client.read_coils(address, count)
            
            if not result.isError():
                print(f"✓ 读取成功: 地址={address:06d}, 值={result.bits[:count]}")
                return result.bits[:count]
            else:
                print(f"✗ 读取失败: {result}")
                return None
                
        except Exception as e:
            print(f"✗ 读取异常: {e}")
            return None


def main():
    """主函数"""
    # 创建控制器实例
    controller = ModbusController(ip_address='192.168.2.88', port=502)
    
    # 连接到设备
    if not controller.connect():
        sys.exit(1)
    
    try:
        # 地址 000001 对应 Modbus 地址 0（0-based）
        # 如果您的设备使用 1-based 地址系统，请使用地址 1
        target_address = 0  # 000001 -> 地址 0
        
        print("\n" + "="*50)
        print("Modbus 控制示例")
        print("="*50)
        
        # 示例 1: 写入值 0
        print("\n[示例 2] 向地址 000001 写入值 0")
        controller.write_coil(target_address, 0)
        time.sleep(0.5)
        
        # 读取验证
        print("\n[验证] 读取地址 000001 的值")
        controller.read_coil(target_address)
        time.sleep(1)
        
        # 示例 2: 写入值 1
        print("\n[示例 1] 向地址 000001 写入值 1")
        controller.write_coil(target_address, 1)
        time.sleep(0.5)
        
        # 读取验证
        print("\n[验证] 读取地址 000001 的值")
        controller.read_coil(target_address)
        
        print("\n" + "="*50)
        print("操作完成")
        print("="*50)
        
    except KeyboardInterrupt:
        print("\n\n✗ 用户中断")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
    finally:
        # 断开连接
        controller.disconnect()


def send_value(value):
    """
    快捷函数：发送单个值到地址 000001
    
    Args:
        value: 要发送的值（0 或 1）
    
    Returns:
        bool: 是否成功
    """
    controller = ModbusController(ip_address='192.168.2.88', port=502)
    
    if not controller.connect():
        return False
    
    try:
        success = controller.write_coil(0, value)
        return success
    finally:
        controller.disconnect()


if __name__ == "__main__":
    # 如果需要命令行参数控制，可以使用以下代码：
    if len(sys.argv) > 1:
        try:
            value = int(sys.argv[1])
            if value not in [0, 1]:
                print("✗ 值必须是 0 或 1")
                print("用法: python modbus_control.py [0|1]")
                sys.exit(1)
            
            print(f"向地址 000001 发送值: {value}")
            success = send_value(value)
            sys.exit(0 if success else 1)
            
        except ValueError:
            print("✗ 无效的值")
            print("用法: python modbus_control.py [0|1]")
            sys.exit(1)
    else:
        # 运行完整示例
        main()
