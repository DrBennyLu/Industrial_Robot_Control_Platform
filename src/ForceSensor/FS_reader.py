#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
坤维 KWR75B 六维力传感器读取脚本

默认：COM8 / 460800 / 8N1，28 字节帧，被动接收。
帧解析与缓冲同步逻辑对齐供应商示例 SerialPortFor28BytesData_python3(2).py。
"""

import serial
import time
import struct
import threading
from collections import deque
from typing import Optional, Callable, List, Dict, Any, Deque
import logging
import numpy as np
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_PORT = 'COM8'
DEFAULT_BAUDRATE = 460800
DEFAULT_FILTER_WINDOW = 5
SENSOR_MODEL = 'KWR75B'
NUM_CHANNELS = 6
CHANNEL_NAMES = ('Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz')
FRAME_SIZE = 28
GRAVITY = 9.80665

# 供应商示例中的启动连续发送命令（默认不发送，仅被动接收）
START_STREAM_CMD = bytes((0x48, 0xAA, 0x0D, 0x0A))


class SensorStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    MONITORING = "monitoring"
    ERROR = "error"


@dataclass
class ForceData:
    """力传感器数据（力 N，力矩 N·m）"""
    fx: float
    fy: float
    fz: float
    mx: float
    my: float
    mz: float
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            'fx': self.fx,
            'fy': self.fy,
            'fz': self.fz,
            'mx': self.mx,
            'my': self.my,
            'mz': self.mz,
            'timestamp': self.timestamp,
        }

    def to_array(self) -> np.ndarray:
        return np.array(
            [self.fx, self.fy, self.fz, self.mx, self.my, self.mz],
            dtype=np.float64,
        )

    @classmethod
    def from_array(cls, values: np.ndarray, timestamp: Optional[float] = None) -> 'ForceData':
        ts = time.time() if timestamp is None else timestamp
        return cls(
            fx=float(values[0]),
            fy=float(values[1]),
            fz=float(values[2]),
            mx=float(values[3]),
            my=float(values[4]),
            mz=float(values[5]),
            timestamp=ts,
        )


class SlidingWindowFilter:
    """六通道滑动窗口均值滤波"""

    def __init__(self, window_size: int = DEFAULT_FILTER_WINDOW):
        if window_size < 1:
            raise ValueError("window_size 必须 >= 1")
        self.window_size = window_size
        self._samples: Deque[np.ndarray] = deque(maxlen=window_size)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()

    def add(self, data: ForceData) -> None:
        with self._lock:
            self._samples.append(data.to_array())

    def get_filtered(self) -> Optional[ForceData]:
        with self._lock:
            if not self._samples:
                return None
            mean = np.mean(np.stack(self._samples), axis=0)
            return ForceData.from_array(mean)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._samples)


class KunweiForceSensor:
    """
    坤维 KWR75B 六维力传感器。

    用法::
        sensor = KunweiForceSensor()
        sensor.connect()
        sensor.start_monitoring()
        data = sensor.get_latest_data()  # 滑动窗口滤波后的 N / N·m
    """

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
        model: str = SENSOR_MODEL,
        filter_window_size: int = DEFAULT_FILTER_WINDOW,
        send_start_command: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.model = model
        self.send_start_command = send_start_command
        self.filter = SlidingWindowFilter(filter_window_size)

        self.serial_conn: Optional[serial.Serial] = None
        self.status = SensorStatus.DISCONNECTED
        self.is_running = False
        self.data_thread: Optional[threading.Thread] = None
        self.latest_raw: Optional[ForceData] = None
        self.data_lock = threading.Lock()
        self.callbacks: List[Callable[[ForceData], None]] = []
        self._rx_buffer = bytearray()

    def connect(self) -> bool:
        try:
            logger.info(
                f"打开 {self.model} @ {self.port}, "
                f"{self.baudrate} 8N1, 28 字节帧"
            )
            self.serial_conn = serial.Serial(self.port, self.baudrate)
            if not self.serial_conn.is_open:
                logger.error(f"无法打开串口 {self.port}")
                return False

            self.serial_conn.reset_input_buffer()
            self._rx_buffer.clear()
            self.filter.reset()
            self.latest_raw = None

            if self.send_start_command:
                self.serial_conn.write(START_STREAM_CMD)
                logger.info("已发送启动流命令 48 AA 0D 0A（供应商示例）")
            else:
                logger.info("被动接收模式，未发送启动命令")

            self.status = SensorStatus.CONNECTED
            return True

        except serial.SerialException as e:
            logger.error(f"连接串口失败: {e}")
            self.status = SensorStatus.ERROR
            return False
        except Exception as e:
            logger.error(f"连接失败: {e}")
            self.status = SensorStatus.ERROR
            return False

    def disconnect(self) -> None:
        try:
            self.stop_monitoring()
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
                logger.info(f"已断开串口 {self.port}")
            self.status = SensorStatus.DISCONNECTED
            self.serial_conn = None
            self._rx_buffer.clear()
            self.filter.reset()
            self.latest_raw = None
        except Exception as e:
            logger.error(f"断开连接时发生错误: {e}")

    @staticmethod
    def _kg_to_si(values_kg: List[float]) -> ForceData:
        """供应商示例输出 Kg / Kg·m，转换为 N / N·m。"""
        fx, fy, fz, mx, my, mz = values_kg
        return ForceData(
            fx=fx * GRAVITY,
            fy=fy * GRAVITY,
            fz=fz * GRAVITY,
            mx=mx * GRAVITY,
            my=my * GRAVITY,
            mz=mz * GRAVITY,
            timestamp=time.time(),
        )

    @classmethod
    def parse_frame_28(cls, buf: bytearray) -> Optional[ForceData]:
        """
        按供应商示例解析 28 字节帧：
        帧尾 buf[26]==0x0D, buf[27]==0x0A；
        各分量 float 为 buf[end-i], i=0..3 后 struct.unpack('!f', ...)。
        """
        if len(buf) < FRAME_SIZE or buf[26] != 0x0D or buf[27] != 0x0A:
            return None

        wrench: List[float] = []
        try:
            for ch in range(NUM_CHANNELS):
                end_idx = 5 + ch * 4
                chunk = bytearray(buf[end_idx - i] for i in range(4))
                wrench.append(struct.unpack('!f', chunk)[0])
        except struct.error:
            return None

        return cls._kg_to_si(wrench)

    def _on_new_frame(self, force_data: ForceData) -> None:
        with self.data_lock:
            self.latest_raw = force_data
            self.filter.add(force_data)

        for callback in self.callbacks:
            try:
                callback(force_data)
            except Exception as e:
                logger.error(f"回调执行失败: {e}")

    def _process_buffer(self) -> bool:
        """缓冲处理，逻辑对齐供应商示例。"""
        parsed_any = False

        while len(self._rx_buffer) > 27:
            buf_len = len(self._rx_buffer)

            if buf_len >= FRAME_SIZE and self._rx_buffer[26] == 0x0D and self._rx_buffer[27] == 0x0A:
                force_data = self.parse_frame_28(self._rx_buffer)
                del self._rx_buffer[:FRAME_SIZE]

                if force_data is not None:
                    self._on_new_frame(force_data)
                    parsed_any = True
                continue

            if buf_len >= FRAME_SIZE:
                if self._rx_buffer[0] == 0x0A:
                    del self._rx_buffer[0]
                else:
                    i = 0
                    while (
                        i <= FRAME_SIZE
                        and len(self._rx_buffer) >= 2
                        and self._rx_buffer[0] != 0x0D
                        and self._rx_buffer[1] != 0x0A
                    ):
                        del self._rx_buffer[0]
                        i += 1
                    if len(self._rx_buffer) >= 2:
                        del self._rx_buffer[0:2]
                    elif len(self._rx_buffer) >= 1:
                        del self._rx_buffer[0]
            else:
                break

        return parsed_any

    def _read_serial_chunk(self) -> None:
        if not self.serial_conn:
            return
        count = self.serial_conn.in_waiting
        if count > 0:
            self._rx_buffer.extend(self.serial_conn.read(count))

    def test_connection(self, timeout: float = 2.0) -> bool:
        logger.info("连接测试（被动接收）...")
        if not self.connect():
            return False

        deadline = time.time() + timeout
        got_frame = False
        try:
            while time.time() < deadline:
                self._read_serial_chunk()
                if self._process_buffer():
                    got_frame = True
                    logger.info("连接测试通过")
                    break
                time.sleep(0.005)
            return got_frame
        finally:
            self.disconnect()

    def _monitoring_thread(self) -> None:
        logger.info("接收线程启动")
        while self.is_running:
            try:
                if not (self.serial_conn and self.serial_conn.is_open):
                    self.is_running = False
                    break

                self._read_serial_chunk()
                self._process_buffer()
                if self.serial_conn.in_waiting == 0:
                    time.sleep(0.001)

            except serial.SerialException as e:
                logger.error(f"串口错误: {e}")
                self.is_running = False
            except Exception as e:
                logger.error(f"接收线程错误: {e}")
                time.sleep(0.05)

        logger.info("接收线程停止")

    def start_monitoring(self) -> bool:
        if self.status != SensorStatus.CONNECTED:
            logger.error("请先 connect()")
            return False
        if self.is_running:
            return True

        self.is_running = True
        self.data_thread = threading.Thread(
            target=self._monitoring_thread,
            daemon=True,
        )
        self.data_thread.start()
        self.status = SensorStatus.MONITORING
        logger.info("监测已启动")
        return True

    def stop_monitoring(self) -> None:
        if not self.is_running:
            return
        self.is_running = False
        if self.data_thread:
            self.data_thread.join(timeout=2.0)
            self.data_thread = None
        if self.status == SensorStatus.MONITORING:
            self.status = SensorStatus.CONNECTED
        logger.info("监测已停止")

    def get_latest_data(self, filtered: bool = True) -> Optional[ForceData]:
        """
        获取最新力数据。

        Args:
            filtered: True 时返回滑动窗口均值滤波结果（默认）；
                      False 时返回最近一帧原始值。
        """
        with self.data_lock:
            if filtered:
                data = self.filter.get_filtered()
                if data is not None:
                    return data
            return self.latest_raw

    def get_latest_raw_data(self) -> Optional[ForceData]:
        """最近一帧未滤波数据。"""
        return self.get_latest_data(filtered=False)

    def register_callback(self, callback: Callable[[ForceData], None]) -> None:
        if callable(callback):
            self.callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[ForceData], None]) -> None:
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


def print_force_data(data: ForceData) -> None:
    print(
        f"Fx={data.fx:.3f}N, Fy={data.fy:.3f}N, Fz={data.fz:.3f}N, "
        f"Mx={data.mx:.3f}N·m, My={data.my:.3f}N·m, Mz={data.mz:.3f}N·m"
    )


def main() -> None:
    print(f"=== {SENSOR_MODEL} 测试 ===")
    print(
        f"{DEFAULT_PORT} | {DEFAULT_BAUDRATE} | {FRAME_SIZE}B | "
        f"滤波窗口 {DEFAULT_FILTER_WINDOW}\n"
    )

    sensor = KunweiForceSensor()

    if not sensor.connect():
        print("连接失败")
        return

    if not sensor.start_monitoring():
        sensor.disconnect()
        print("启动监测失败")
        return

    print("接收中（get_latest_data 为滤波值），Ctrl+C 结束")
    try:
        for i in range(1000000):
            time.sleep(0.1)
            data = sensor.get_latest_data()
            if data:
                print(
                    f"  [{i + 1}] 滤波(n={sensor.filter.count}): "
                    f"Fx={data.fx:.2f}N"
                )
            else:
                print(f"  [{i + 1}s] 等待数据...")
    except KeyboardInterrupt:
        pass
    finally:
        sensor.stop_monitoring()
        sensor.disconnect()
        print("已断开")


if __name__ == "__main__":
    main()
