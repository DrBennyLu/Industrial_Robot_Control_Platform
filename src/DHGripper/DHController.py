import time
from typing import Optional
from pymodbus.client import ModbusSerialClient


class GripperController:
    """
    DH Gripper控制器类
    
    提供夹爪的初始化、打开、关闭、参数设置等功能
    """
    
    # 寄存器地址定义 (根据文档2.3.2节)
    ADDR_INIT = 0x0100       # 初始化寄存器
    ADDR_FORCE = 0x0101      # 力值寄存器
    ADDR_POS = 0x0103        # 位置寄存器
    ADDR_SPEED = 0x0104      # 速度寄存器
    ADDR_INIT_STATUS = 0x0200 # 初始化状态反馈
    
    # 位置范围
    POS_MIN = 0              # 完全闭合
    POS_MAX = 1000           # 完全张开
    
    def __init__(self, 
                 port: str = 'COM3',
                 baudrate: int = 115200,
                 device_id: int = 1,
                 timeout: float = 1.0):
        """
        初始化夹爪控制器
        
        Args:
            port: 串口号 (Windows: 'COM3', Linux: '/dev/ttyUSB0')
            baudrate: 波特率，默认115200
            device_id: 设备ID，默认1
            timeout: 超时时间(秒)，默认1.0
        """
        self.port = port
        self.baudrate = baudrate
        self.device_id = device_id
        self.timeout = timeout
        
        self.client: Optional[ModbusSerialClient] = None
        self._is_connected = False
        self._is_initialized = False
        self._commanded_open: bool | None = None
        
    def connect(self) -> bool:
        """
        连接到夹爪设备
        
        Returns:
            bool: 连接成功返回True，失败返回False
        """
        self.client = ModbusSerialClient(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=self.timeout
        )
        
        self._is_connected = self.client.connect()
        return self._is_connected
    
    def disconnect(self):
        """断开与夹爪的连接"""
        if self.client:
            self.client.close()
            self._is_connected = False
            self._is_initialized = False
    
    def initialize(self, timeout: float = 10.0) -> bool:
        """
        初始化夹爪（回零位）
        
        Args:
            timeout: 初始化超时时间(秒)，默认10秒
            
        Returns:
            bool: 初始化成功返回True，失败返回False
            
        Raises:
            RuntimeError: 如果未连接设备
        """
        if not self._is_connected or not self.client:
            raise RuntimeError("设备未连接，请先调用connect()")
        
        # 写入1到初始化寄存器
        self.client.write_register(self.ADDR_INIT, 1, device_id=self.device_id)
        
        # 等待初始化完成
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.client.read_holding_registers(
                self.ADDR_INIT_STATUS, 
                count=1, 
                device_id=self.device_id
            )
            if not result.isError() and result.registers[0] == 1:
                self._is_initialized = True
                return True
            time.sleep(0.5)
        
        return False
    
    def set_force(self, force: int) -> bool:
        """
        设置夹爪力值
        
        Args:
            force: 力值百分比，范围20-100
            
        Returns:
            bool: 设置成功返回True
            
        Raises:
            ValueError: 如果力值超出范围
            RuntimeError: 如果设备未初始化
        """
        if not self._is_initialized:
            raise RuntimeError("设备未初始化，请先调用initialize()")
        
        if not 20 <= force <= 100:
            raise ValueError(f"力值必须在20-100之间，当前值: {force}")
        
        result = self.client.write_register(
            self.ADDR_FORCE, 
            force, 
            device_id=self.device_id
        )
        return not result.isError()
    
    def set_speed(self, speed: int) -> bool:
        """
        设置夹爪速度
        
        Args:
            speed: 速度百分比，范围1-100
            
        Returns:
            bool: 设置成功返回True
            
        Raises:
            ValueError: 如果速度超出范围
            RuntimeError: 如果设备未初始化
        """
        if not self._is_initialized:
            raise RuntimeError("设备未初始化，请先调用initialize()")
        
        if not 1 <= speed <= 100:
            raise ValueError(f"速度必须在1-100之间，当前值: {speed}")
        
        result = self.client.write_register(
            self.ADDR_SPEED, 
            speed, 
            device_id=self.device_id
        )
        return not result.isError()
    
    def set_position(self, position: int) -> bool:
        """
        设置夹爪位置
        
        Args:
            position: 位置值，范围0-1000 (0=完全闭合, 1000=完全张开)
            
        Returns:
            bool: 设置成功返回True
            
        Raises:
            ValueError: 如果位置超出范围
            RuntimeError: 如果设备未初始化
        """
        if not self._is_initialized:
            raise RuntimeError("设备未初始化，请先调用initialize()")
        
        if not self.POS_MIN <= position <= self.POS_MAX:
            raise ValueError(f"位置必须在{self.POS_MIN}-{self.POS_MAX}之间，当前值: {position}")
        
        result = self.client.write_register(
            self.ADDR_POS, 
            position, 
            device_id=self.device_id
        )
        return not result.isError()
    
    def open(self, position: Optional[int] = None) -> bool:
        """
        打开/张开夹爪
        
        Args:
            position: 可选，指定打开位置(0-1000)，默认完全打开(1000)
            
        Returns:
            bool: 操作成功返回True
        """
        if position is None:
            position = self.POS_MAX
        ok = self.set_position(position)
        if ok:
            self._commanded_open = True
        return ok
    
    def close(self, position: Optional[int] = None) -> bool:
        """
        关闭/闭合夹爪
        
        Args:
            position: 可选，指定关闭位置(0-1000)，默认完全关闭(0)
            
        Returns:
            bool: 操作成功返回True
        """
        if position is None:
            position = self.POS_MIN
        ok = self.set_position(position)
        if ok:
            self._commanded_open = False
        return ok
    
    def configure(self, force: int = 50, speed: int = 50) -> bool:
        """
        配置夹爪参数（力值和速度）
        
        Args:
            force: 力值百分比，范围20-100，默认50
            speed: 速度百分比，范围1-100，默认50
            
        Returns:
            bool: 配置成功返回True
        """
        force_ok = self.set_force(force)
        speed_ok = self.set_speed(speed)
        return force_ok and speed_ok
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._is_connected
    
    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._is_initialized

    @property
    def commanded_is_open(self) -> bool | None:
        """最近一次 open/close 指令对应的开合状态；None 表示尚未下发指令。"""
        return self._commanded_open
    
    def __enter__(self):
        """支持上下文管理器"""
        if not self.connect():
            raise RuntimeError(f"无法连接到设备: {self.port}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理器"""
        self.disconnect()


def main():
    """示例：使用GripperController控制夹爪"""
    
    # 方式1: 使用上下文管理器（推荐）
    try:
        with GripperController(port='COM3') as gripper:
            print("连接成功")
            
            # 初始化夹爪
            print("正在初始化夹爪...")
            if not gripper.initialize():
                print("初始化失败")
                return
            print("初始化完成")
            
            # 配置参数
            gripper.configure(force=100, speed=50)
            print("参数配置完成")
            
            # 交互式控制
            while True:
                user_input = input("请输入指令 (1:打开/张开, 2:关闭/闭合, q:退出): ")
                
                if user_input == '1':
                    print("正在张开夹爪...")
                    gripper.open()
                    print("已发送张开指令")
                    
                elif user_input == '2':
                    print("正在闭合夹爪...")
                    gripper.close()
                    print("已发送闭合指令")
                    
                elif user_input.lower() == 'q':
                    print("程序退出")
                    break
                else:
                    print("无效指令，请重新输入")
                    
    except Exception as e:
        print(f"发生错误: {e}")


if __name__ == "__main__":
    main()