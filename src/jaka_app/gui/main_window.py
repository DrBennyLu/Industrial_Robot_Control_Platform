from __future__ import annotations

import logging
import sys
from functools import partial
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jaka_app.config_loader import load_application_config
from jaka_app.context import ApplicationContext, build_application_context
from jaka_app.gui.robot_worker import RobotWorker

logger = logging.getLogger(__name__)


class MainWindow(QWidget):
    """Flat HMI: one QWidget-based window + signals into RobotWorker."""

    req_status = pyqtSignal()
    req_connect = pyqtSignal(object)
    req_disconnect = pyqtSignal()
    req_power_on = pyqtSignal()
    req_enable = pyqtSignal()
    req_disable = pyqtSignal()
    req_drag = pyqtSignal(bool)
    req_jog_start = pyqtSignal(int, float, float)
    req_jog_stop = pyqtSignal()
    req_record_teach = pyqtSignal(object)
    req_delete_teach = pyqtSignal(str)
    req_run_flow = pyqtSignal(str)
    req_run_flow_function = pyqtSignal(object)
    req_auto_start = pyqtSignal(object)
    req_auto_stop = pyqtSignal()
    req_cancel_flow = pyqtSignal()
    req_move_named = pyqtSignal(object)
    req_program_load = pyqtSignal(str)
    req_program_run = pyqtSignal()
    req_program_abort = pyqtSignal()
    req_collision_recover = pyqtSignal()

    def __init__(self, ctx: ApplicationContext, default_flow: str) -> None:
        super().__init__()
        self._ctx = ctx
        self._default_flow = default_flow
        self._worker_thread = QThread()
        self._worker = RobotWorker(ctx)
        self._worker.moveToThread(self._worker_thread)
        self._wire_worker()
        self._worker_thread.start()
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.req_status.emit)
        self._timer.start(350)

    def _wire_worker(self) -> None:
        w = self._worker
        self.req_status.connect(w.slot_refresh_status, Qt.QueuedConnection)
        self.req_connect.connect(w.slot_connect, Qt.QueuedConnection)
        self.req_disconnect.connect(w.slot_disconnect, Qt.QueuedConnection)
        self.req_power_on.connect(w.slot_power_on, Qt.QueuedConnection)
        self.req_enable.connect(w.slot_enable, Qt.QueuedConnection)
        self.req_disable.connect(w.slot_disable, Qt.QueuedConnection)
        self.req_drag.connect(w.slot_drag, Qt.QueuedConnection)
        self.req_jog_start.connect(w.slot_jog_start, Qt.QueuedConnection)
        self.req_jog_stop.connect(w.slot_jog_stop, Qt.QueuedConnection)
        self.req_record_teach.connect(w.slot_record_teach, Qt.QueuedConnection)
        self.req_delete_teach.connect(w.slot_delete_teach, Qt.QueuedConnection)
        self.req_run_flow.connect(w.slot_run_flow, Qt.QueuedConnection)
        self.req_run_flow_function.connect(w.slot_run_flow_function, Qt.QueuedConnection)
        self.req_auto_start.connect(w.slot_auto_start, Qt.QueuedConnection)
        self.req_auto_stop.connect(w.slot_auto_stop, Qt.QueuedConnection)
        self.req_cancel_flow.connect(w.slot_cancel_flow, Qt.QueuedConnection)
        self.req_move_named.connect(w.slot_move_named, Qt.QueuedConnection)
        self.req_program_load.connect(w.slot_program_load, Qt.QueuedConnection)
        self.req_program_run.connect(w.slot_program_run, Qt.QueuedConnection)
        self.req_program_abort.connect(w.slot_program_abort, Qt.QueuedConnection)
        self.req_collision_recover.connect(w.slot_collision_recover, Qt.QueuedConnection)
        w.status_ready.connect(self._on_status)
        w.production_ready.connect(self._on_production)
        w.log_line.connect(self._append_log)
        w.connect_result.connect(self._on_connect_result)
        w.teach_list_changed.connect(self._refresh_teach_table)
        w.flow_finished.connect(self._on_flow_finished)

    def _build_ui(self) -> None:
        self.setWindowTitle("Sheet metal parts feeding system (Author: Lu Xingguo)")
        root = QVBoxLayout(self)
        self._tabs = QTabWidget()
        root.addWidget(self._tabs)
        self._tabs.addTab(self._page_status(), "状态")
        self._tabs.addTab(self._page_manual(), "手动")
        self._tabs.addTab(self._page_teach(), "示教点")
        self._tabs.addTab(self._page_auto(), "主流程")
        self._tabs.addTab(self._page_log(), "日志")

    def _page_status(self) -> QWidget:
        p = QWidget()
        lay = QFormLayout(p)
        self.lbl_err = QLabel("-")
        self.lbl_estop = QLabel("-")
        self.lbl_power = QLabel("-")
        self.lbl_enable = QLabel("-")
        self.lbl_rapid = QLabel("-")
        self.lbl_inpos = QLabel("-")
        self.lbl_prog = QLabel("-")
        self.lbl_line = QLabel("-")
        self.lbl_file = QLabel("-")
        self.lbl_step = QLabel("-")
        self.lbl_run_state = QLabel("-")
        self.lbl_cycle_total = QLabel("0")
        self.lbl_cycle_ok = QLabel("0")
        self.lbl_cycle_ng = QLabel("0")
        self.lbl_yield = QLabel("0.0")
        self.lbl_last_cycle = QLabel("0.0")
        self.lbl_avg_cycle = QLabel("0.0")
        self.lbl_best_cycle = QLabel("0.0")
        self.lbl_fail_reason = QLabel("-")
        self.lbl_last_error = QLabel("-")
        for lbl in (
            self.lbl_err,
            self.lbl_estop,
            self.lbl_power,
            self.lbl_enable,
            self.lbl_rapid,
            self.lbl_inpos,
            self.lbl_prog,
            self.lbl_line,
            self.lbl_file,
            self.lbl_step,
            self.lbl_run_state,
            self.lbl_cycle_total,
            self.lbl_cycle_ok,
            self.lbl_cycle_ng,
            self.lbl_yield,
            self.lbl_last_cycle,
            self.lbl_avg_cycle,
            self.lbl_best_cycle,
            self.lbl_fail_reason,
            self.lbl_last_error,
        ):
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addRow("错误码", self.lbl_err)
        lay.addRow("急停状态", self.lbl_estop)
        lay.addRow("上电/伺服", self.lbl_power)
        lay.addRow("使能状态", self.lbl_enable)
        lay.addRow("倍率", self.lbl_rapid)
        lay.addRow("到位状态", self.lbl_inpos)
        lay.addRow("程序状态", self.lbl_prog)
        lay.addRow("逻辑行号", self.lbl_line)
        lay.addRow("已加载文件", self.lbl_file)
        lay.addRow("当前流程步骤", self.lbl_step)
        lay.addRow("运行状态", self.lbl_run_state)
        lay.addRow("循环总数", self.lbl_cycle_total)
        lay.addRow("循环OK数", self.lbl_cycle_ok)
        lay.addRow("循环NG数", self.lbl_cycle_ng)
        lay.addRow("良率(%)", self.lbl_yield)
        lay.addRow("最近CT(s)", self.lbl_last_cycle)
        lay.addRow("平均CT(s)", self.lbl_avg_cycle)
        lay.addRow("最佳CT(s)", self.lbl_best_cycle)
        lay.addRow("失败原因", self.lbl_fail_reason)
        lay.addRow("最近错误", self.lbl_last_error)
        return p

    def _page_manual(self) -> QWidget:
        p = QWidget()
        v = QVBoxLayout(p)
        conn = QGroupBox("连接")
        cf = QFormLayout(conn)
        self.ed_ip = QLineEdit(str((self._ctx.config.get("robot") or {}).get("ip", "192.168.2.64")))
        self.chk_power = QCheckBox("power_on after login")
        self.chk_enable = QCheckBox("enable after login")
        cf.addRow("IP", self.ed_ip)
        cf.addRow(self.chk_power)
        cf.addRow(self.chk_enable)
        hb = QHBoxLayout()
        b_connect = QPushButton("连接")
        b_connect.clicked.connect(self._on_connect_clicked)
        b_disc = QPushButton("断开")
        b_disc.clicked.connect(self.req_disconnect.emit)
        hb.addWidget(b_connect)
        hb.addWidget(b_disc)
        cf.addRow(hb)
        v.addWidget(conn)

        ops = QGroupBox("上电 / 使能 / 拖拽")
        og = QGridLayout(ops)
        b_po = QPushButton("power_on")
        b_po.clicked.connect(self.req_power_on.emit)
        b_en = QPushButton("enable")
        b_en.clicked.connect(self.req_enable.emit)
        b_di = QPushButton("disable")
        b_di.clicked.connect(self.req_disable.emit)
        og.addWidget(b_po, 0, 0)
        og.addWidget(b_en, 0, 1)
        og.addWidget(b_di, 0, 2)
        b_drag_on = QPushButton("drag ON")
        b_drag_on.clicked.connect(partial(self.req_drag.emit, True))
        b_drag_off = QPushButton("drag OFF")
        b_drag_off.clicked.connect(partial(self.req_drag.emit, False))
        b_col = QPushButton("collision_recover")
        b_col.clicked.connect(self.req_collision_recover.emit)
        og.addWidget(b_drag_on, 1, 0)
        og.addWidget(b_drag_off, 1, 1)
        og.addWidget(b_col, 1, 2)
        v.addWidget(ops)

        jog = QGroupBox("关节点动 (按住移动, 松开停止)")
        jg = QGridLayout(jog)
        vel = 0.15
        for j in range(6):
            jg.addWidget(QLabel("J%d" % (j + 1)), j, 0)
            bp = QPushButton("+")
            bm = QPushButton("-")
            bp.pressed.connect(partial(self._emit_jog, j, vel, 1.0))
            bp.released.connect(self.req_jog_stop.emit)
            bm.pressed.connect(partial(self._emit_jog, j, vel, -1.0))
            bm.released.connect(self.req_jog_stop.emit)
            jg.addWidget(bp, j, 1)
            jg.addWidget(bm, j, 2)
        v.addWidget(jog)

        prog = QGroupBox("柜内程序 (program_load / run / abort)")
        pg = QHBoxLayout(prog)
        self.ed_prog = QLineEdit()
        pg.addWidget(self.ed_prog)
        b_pl = QPushButton("load")
        b_pl.clicked.connect(self._emit_program_load)
        b_pr = QPushButton("run")
        b_pr.clicked.connect(self.req_program_run.emit)
        b_pa = QPushButton("abort")
        b_pa.clicked.connect(self.req_program_abort.emit)
        pg.addWidget(b_pl)
        pg.addWidget(b_pr)
        pg.addWidget(b_pa)
        v.addWidget(prog)

        mgrp = QGroupBox("手动运行脚本功能（单次）")
        mg = QGridLayout(mgrp)
        self.ed_manual_flow = QLineEdit(self._default_flow)
        self.ed_manual_func = QLineEdit("main")
        b_m_browse = QPushButton("浏览脚本")
        b_m_browse.clicked.connect(self._browse_manual_flow)
        b_m_run = QPushButton("执行函数")
        b_m_run.clicked.connect(self._on_manual_run_function)
        mg.addWidget(QLabel("脚本"), 0, 0)
        mg.addWidget(self.ed_manual_flow, 0, 1)
        mg.addWidget(b_m_browse, 0, 2)
        mg.addWidget(QLabel("函数"), 1, 0)
        mg.addWidget(self.ed_manual_func, 1, 1)
        mg.addWidget(b_m_run, 1, 2)
        v.addWidget(mgrp)
        return p

    def _page_teach(self) -> QWidget:
        p = QWidget()
        v = QVBoxLayout(p)
        row = QHBoxLayout()
        self.ed_teach_name = QLineEdit()
        self.ed_teach_name.setPlaceholderText("point name")
        row.addWidget(self.ed_teach_name)
        b_rec = QPushButton("记录当前点")
        b_rec.clicked.connect(self._on_record_teach)
        b_ref = QPushButton("刷新表")
        b_ref.clicked.connect(self._refresh_teach_table)
        row.addWidget(b_rec)
        row.addWidget(b_ref)
        v.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["name", "joint_rad (first 3)", "tcp (first 3)", "note"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        v.addWidget(self.table)
        go = QHBoxLayout()
        self.cmb_move = QComboBox()
        self.cmb_move.addItem("joint")
        self.cmb_move.addItem("linear")
        go.addWidget(QLabel("策略"))
        go.addWidget(self.cmb_move)
        b_mv = QPushButton("移动到选中点")
        b_mv.clicked.connect(self._on_move_named)
        b_del = QPushButton("删除选中点")
        b_del.clicked.connect(self._on_delete_teach)
        go.addWidget(b_mv)
        go.addWidget(b_del)
        v.addLayout(go)
        self._refresh_teach_table()
        return p

    def _page_auto(self) -> QWidget:
        p = QWidget()
        v = QVBoxLayout(p)
        row = QHBoxLayout()
        self.ed_flow = QLineEdit(self._default_flow)
        row.addWidget(self.ed_flow)
        b_br = QPushButton("浏览…")
        b_br.clicked.connect(self._browse_flow)
        row.addWidget(b_br)
        v.addLayout(row)
        hb = QHBoxLayout()
        b_run = QPushButton("执行主流程")
        b_run.clicked.connect(self._on_run_flow)
        b_auto = QPushButton("启动全自动循环")
        b_auto.clicked.connect(self._on_auto_start)
        b_auto_stop = QPushButton("停止全自动循环")
        b_auto_stop.clicked.connect(self.req_auto_stop.emit)
        b_can = QPushButton("请求停止当前流程")
        b_can.clicked.connect(self.req_cancel_flow.emit)
        hb.addWidget(b_run)
        hb.addWidget(b_auto)
        hb.addWidget(b_auto_stop)
        hb.addWidget(b_can)
        v.addLayout(hb)
        row2 = QHBoxLayout()
        self.ed_auto_interval = QLineEdit("0.0")
        row2.addWidget(QLabel("循环间隔(s)"))
        row2.addWidget(self.ed_auto_interval)
        v.addLayout(row2)
        auto_box = QGroupBox("自动运行统计（CT/良率）")
        ag = QFormLayout(auto_box)
        self.lbl_auto_state = QLabel("-")
        self.lbl_auto_ct = QLabel("0.0")
        self.lbl_auto_avg = QLabel("0.0")
        self.lbl_auto_best = QLabel("0.0")
        self.lbl_auto_ok = QLabel("0")
        self.lbl_auto_ng = QLabel("0")
        self.lbl_auto_total = QLabel("0")
        self.lbl_auto_yield = QLabel("0.0")
        self.lbl_auto_error = QLabel("-")
        ag.addRow("状态", self.lbl_auto_state)
        ag.addRow("CT(s)", self.lbl_auto_ct)
        ag.addRow("平均CT(s)", self.lbl_auto_avg)
        ag.addRow("最佳CT(s)", self.lbl_auto_best)
        ag.addRow("OK", self.lbl_auto_ok)
        ag.addRow("NG", self.lbl_auto_ng)
        ag.addRow("总数", self.lbl_auto_total)
        ag.addRow("良率(%)", self.lbl_auto_yield)
        ag.addRow("最近错误", self.lbl_auto_error)
        v.addWidget(auto_box)
        v.addWidget(QLabel("主流程为 Python 文件，需包含 main()。"))
        return p

    def _page_log(self) -> QWidget:
        p = QWidget()
        lay = QVBoxLayout(p)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        lay.addWidget(self.log)
        return p

    def _emit_jog(self, joint: int, vel: float, direction: float) -> None:
        self.req_jog_start.emit(joint, vel, direction)

    def _emit_program_load(self) -> None:
        self.req_program_load.emit(self.ed_prog.text().strip())

    def _append_log(self, text: str) -> None:
        self.log.appendPlainText(text)

    def _on_connect_clicked(self) -> None:
        bundle = {
            "ip": self.ed_ip.text().strip(),
            "power_on": self.chk_power.isChecked(),
            "enable": self.chk_enable.isChecked(),
        }
        self.req_connect.emit(bundle)

    def _on_connect_result(self, ok: bool, msg: str) -> None:
        if not ok and msg != "disconnected":
            QMessageBox.warning(self, "连接", msg)

    def _on_status(self, snap: dict) -> None:
        def fmt(v: object) -> str:
            return "-" if v is None else str(v)

        self.lbl_err.setText(fmt(snap.get("errcode")))
        self.lbl_estop.setText(fmt(snap.get("emergency_stop", snap.get("estoped"))))
        self.lbl_power.setText(fmt(snap.get("powered_on", snap.get("power_on_state"))))
        self.lbl_enable.setText(fmt(snap.get("enabled", snap.get("servo_enabled"))))
        self.lbl_rapid.setText(fmt(snap.get("rapidrate")))
        self.lbl_inpos.setText(fmt(snap.get("inpos")))
        self.lbl_prog.setText(fmt(snap.get("program_state")))
        self.lbl_line.setText(fmt(snap.get("logic_line")))
        self.lbl_file.setText(fmt(snap.get("loaded_file")))
        self.lbl_step.setText(self._ctx.current_step or "-")

    def _on_production(self, p: dict) -> None:
        def fmt(v: object) -> str:
            return "-" if v is None else str(v)

        self.lbl_run_state.setText(fmt(p.get("run_state")))
        self.lbl_cycle_total.setText(fmt(p.get("cycle_total")))
        self.lbl_cycle_ok.setText(fmt(p.get("cycle_ok")))
        self.lbl_cycle_ng.setText(fmt(p.get("cycle_ng")))
        self.lbl_yield.setText(fmt(p.get("yield_rate")))
        self.lbl_last_cycle.setText(fmt(p.get("last_cycle_s")))
        self.lbl_avg_cycle.setText(fmt(p.get("avg_cycle_s")))
        self.lbl_best_cycle.setText(fmt(p.get("best_cycle_s")))
        self.lbl_fail_reason.setText(fmt(p.get("fail_reason") or "-"))
        self.lbl_last_error.setText(fmt(p.get("last_error") or "-"))
        self.lbl_auto_state.setText(fmt(p.get("run_state")))
        self.lbl_auto_ct.setText(fmt(p.get("last_cycle_s")))
        self.lbl_auto_avg.setText(fmt(p.get("avg_cycle_s")))
        self.lbl_auto_best.setText(fmt(p.get("best_cycle_s")))
        self.lbl_auto_ok.setText(fmt(p.get("cycle_ok")))
        self.lbl_auto_ng.setText(fmt(p.get("cycle_ng")))
        self.lbl_auto_total.setText(fmt(p.get("cycle_total")))
        self.lbl_auto_yield.setText(fmt(p.get("yield_rate")))
        self.lbl_auto_error.setText(fmt(p.get("last_error") or "-"))

    def _refresh_teach_table(self) -> None:
        rows = self._ctx.teach.list_points()
        self.table.setRowCount(len(rows))
        for i, (name, data) in enumerate(rows):
            jr = data.get("joint_rad") or []
            tcp = data.get("tcp") or []
            note = str(data.get("note", ""))
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(str(jr[:3])))
            self.table.setItem(i, 2, QTableWidgetItem(str(tcp[:3]) if tcp else ""))
            self.table.setItem(i, 3, QTableWidgetItem(note))

    def _on_record_teach(self) -> None:
        name = self.ed_teach_name.text().strip()
        if not name:
            QMessageBox.information(self, "示教", "请输入点位名称")
            return
        self.req_record_teach.emit({"name": name})

    def _on_delete_teach(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        item = self.table.item(r, 0)
        if item:
            self.req_delete_teach.emit(item.text())

    def _on_move_named(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        item = self.table.item(r, 0)
        if not item:
            return
        self.req_move_named.emit(
            {
                "name": item.text(),
                "strategy": self.cmb_move.currentText(),
                "require_program_idle": False,
            }
        )

    def _browse_flow(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "主流程 Python", str(Path(self.ed_flow.text()).parent), "Python (*.py)")
        if path:
            self.ed_flow.setText(path)
            self.ed_manual_flow.setText(path)

    def _browse_manual_flow(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "手动脚本 Python", str(Path(self.ed_manual_flow.text()).parent), "Python (*.py)")
        if path:
            self.ed_manual_flow.setText(path)

    def _on_run_flow(self) -> None:
        if (
            QMessageBox.question(
                self,
                "主流程",
                "确定执行主流程？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self.req_run_flow.emit(self.ed_flow.text().strip())

    def _on_manual_run_function(self) -> None:
        self.req_run_flow_function.emit(
            {
                "path": self.ed_manual_flow.text().strip(),
                "function": self.ed_manual_func.text().strip() or "main",
            }
        )

    def _on_auto_start(self) -> None:
        try:
            interval_s = float(self.ed_auto_interval.text().strip() or "0")
        except ValueError:
            QMessageBox.warning(self, "自动循环", "循环间隔必须是数字")
            return
        self.req_auto_start.emit({"path": self.ed_flow.text().strip(), "interval_s": interval_s})

    def _on_flow_finished(self, ok: bool, msg: str) -> None:
        self._append_log("flow finished ok=%s %s" % (ok, msg))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._timer.stop()
        self.req_disconnect.emit()
        self._worker_thread.quit()
        self._worker_thread.wait(3000)
        event.accept()


def run_hmi(config_path: Path, flow_path: Path | None = None) -> int:
    from PyQt5.QtWidgets import QApplication

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_application_config(config_path)
    paths = cfg.get("paths") or {}
    default_flow = str(flow_path or paths.get("default_main_flow", "flows/main_flow.py"))
    ctx = build_application_context(cfg)
    app = QApplication(sys.argv)
    win = MainWindow(ctx, default_flow=default_flow)
    win.resize(900, 640)
    win.show()
    return app.exec_()
