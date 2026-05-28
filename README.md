# Industrial Robot Control Platform (JAKA + PyQt5)

## Author: Benny Lu

工业机器人控制平台（JAKA + PyQt5 HMI），支持：

- 手动操作（连接、上电、使能、拖拽、点动、柜内程序）
- 示教点管理（记录、删除、点位移动）
- 主流程执行（单次 / 自动循环）
- 生产统计（CT、良率、OK/NG）
- 关键状态快照（成功/异常留档）

当前项目要求：

- Python `3.10.x`（`>=3.10,<3.11`）
- 建议在 Windows 11 IPC 运行（开发调试也可在其他平台）

---

## 1. 快速开始

### 1.1 创建环境并安装依赖

Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
```

macOS / Linux:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
```

### 1.2 准备配置文件

```bash
cp config/application.example.yaml config/application.yaml
```

按现场参数修改 `config/application.yaml`，重点字段：

- `robot.ip`: 控制器 IP
- `robot.use_grpc`: 是否 gRPC 登录
- `robot.username`: SDK 用户名（可空）
- `robot.password_env`: 从环境变量读取密码（推荐）
- `paths.teach_points`: 示教点 JSON 路径
- `paths.default_main_flow`: GUI 默认主流程
- `paths.snapshot_dir`: 主流程快照目录
- `logging.level`: 日志等级

---

## 2. JAKA SDK 说明（必需）

`jkrc` 不在 PyPI，需要从厂商 SDK 包中提供。

请确保运行环境可导入 `jkrc`，并且 `jakaAPI.dll`（Windows）可被加载。可选方式：

- 将 SDK 目录加入 `PYTHONPATH`
- 使用厂商提供的 wheel 安装
- 按官方文档部署：[JAKA Python SDK Guide](https://www.jaka.com/docs/en/guide/V3/SDK/python.html)

若未安装 `jkrc`，程序可启动但连接机器人会失败，并抛出明确错误。

---

## 3. 启动方式

### 3.1 启动 GUI（推荐）

```bash
python scripts/run_gui.py --config config/application.yaml
```

可选参数：

- `--flow /path/to/main_flow.py`：覆盖 GUI 中默认主流程脚本

### 3.2 无头运行主流程

```bash
python scripts/run_main_flow.py --flow flows/main_flow.py
```

说明：

- `run_main_flow.py` 只负责加载并执行指定 Python 文件中的 `main()`。
- 当前 `flows/main_flow.py` 内部参数（如机器人 IP、是否真实运动）由文件顶部常量控制。

---

## 4. 主流程开发约定

默认主流程文件：`flows/main_flow.py`

当前实现的标准节拍：

1. 连接机器人
2. 执行初始化子程序（`INIT_ROBOT`）
3. 视觉判型（`vision_flow.detect_object_type`）
4. 路径决策（`ai_flow.select_pick_place_path`）
5. 执行抓取放置（A/B 路径）
6. 回原点（`GO_HOME`）
7. 更新统计并保存快照

异常时：

- 记录失败统计和异常快照
- 执行回退子程序（`SAFE_RETRACT` + `ALARM_POSE`）
- 继续抛出异常，便于上层感知失败

### 4.1 子程序映射（`flows/robot_flow.py`）

- `INIT_ROBOT`
- `PICK_A` / `PLACE_A`
- `PICK_B` / `PLACE_B`
- `GO_HOME`
- `SAFE_RETRACT`
- `ALARM_POSE`

### 4.2 统计与快照文件

- 统计文件：`logs/production_stats.json`
- 快照目录：`logs/snapshots/`

---

## 5. GUI 功能概览

`src/jaka_app/gui/main_window.py` 提供 5 个页面：

- `状态`：机器人状态 + 生产统计
- `手动`：连接、使能、拖拽、点动、柜程序、单次函数执行
- `示教点`：记录/删除/移动
- `主流程`：单次执行、自动循环、停止请求
- `日志`：操作日志输出

示教点默认持久化到 `data/teach_points.json`。

---

## 6. 可扩展设备接口（当前为 NoOp）

以下接口默认是空实现（便于离线开发）：

- `PlcClient`
- `IotLink`
- `IODeviceFacade`
- `LineEquipmentFacade`
- `VisionInspection`

对应文件在 `src/jaka_app/devices/`。接入现场设备时，建议先替换为真实实现，再在 `ApplicationContext` 里注入。

---

## 7. 常见问题

### Q1: 为什么 GUI 能打开但无法连接机器人？

通常是 `jkrc` / `jakaAPI.dll` 未正确部署，或控制器 IP/账号配置错误。

### Q2: 为什么主流程没按 `application.yaml` 的 IP 运行？

当前 `flows/main_flow.py` 直接使用文件内常量（例如 `ROBOT_IP`）。这符合“现场直接改脚本”的设计。

### Q3: 如何安全空跑流程？

将 `flows/main_flow.py` 中 `ENABLE_REAL_MOTION = False`，流程会打印子程序名但不下发真实运动。

---

## 8. 安全提示

- 首次调试务必低速、空夹具、单步验证
- 确认急停、围栏、复位流程可用
- 真实生产前请完成示教点与干涉检查

