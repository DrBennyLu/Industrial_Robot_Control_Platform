# Industrial Robot Control Platform (JAKA + PyQt5)
## author：Benny Lu

Windows **11**, **Python 3.10** (64-bit). Main orchestration is **Python** (`flows/main_flow.py`); optional YAML is only for **static configuration**.

## 1. Python environment

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
```

## 2. JAKA SDK (`jkrc` + `jakaAPI.dll`)

The JAKA Python SDK is **not** on PyPI. From the vendor package:

- Place `jkrc` (package or `.pyd`) and `jakaAPI.dll` in the same folder, or follow the official [Python SDK guide](https://www.jaka.com/docs/en/guide/V3/SDK/python.html).
- Ensure that folder is on `PYTHONPATH`, or `pip install` a vendor-supplied wheel if available.

Without `jkrc`, the app starts but **robot connect** will fail with a clear error.

## 3. Hikvision MVS (optional, for real vision)

Install MVS on the IPC and add the Python binding path (often `MvImport`) to `PYTHONPATH`. Replace the `NoOpVisionInspection` wiring in `ApplicationContext` with your implementation when ready.

## 4. Run GUI

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/run_gui.py --config config/application.yaml
```

## 5. Run main flow (headless)

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/run_main_flow.py --config config/application.yaml --flow flows/main_flow.py
```

## 5.1 Main flow writing guide (cabinet subprogram style)

Write your production logic in `flows/main_flow.py` with entry `main()`.

Recommended pattern:

1. Create and connect robot controller in `main()`
2. Get `object_type` from vision/PLC
3. Run cabinet jobs by name via `arm.run_remote_job("JOB_NAME")`
4. Disconnect in `finally`

Example:

```python
from jaka_app.robot_controller import JakaRobotController


def main():
    arm = JakaRobotController("192.168.1.100", use_grpc=True)
    try:
        arm.connect()
        object_type = "Type_A"  # replace with vision result
        arm.run_remote_job("INIT_ROBOT")
        if object_type == "Type_A":
            arm.run_remote_job("PICK_A")
            arm.run_remote_job("PLACE_A")
        else:
            arm.run_remote_job("PICK_B")
            arm.run_remote_job("PLACE_B")
        arm.run_remote_job("GO_HOME")
    finally:
        arm.disconnect()
```

`run_remote_job()` is implemented as:

- `program_load("JOB_NAME")`
- `program_run()`
- wait until `get_program_state()` reports stop (or timeout/cancel)

## 6. PLC / IoT

`src/jaka_app/devices/plc_client.py` and `iot_link.py` define **Protocols** with **NoOp** implementations. Replace with Modbus/S7/MQTT/etc. when requirements are fixed.

## Safety

Use low speed and verified teach points on a real robot. Ensure emergency stop and safe procedures are available on site.
