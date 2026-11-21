"""
Fire Safety Monitoring System - Modern Dashboard UI (Tkinter)
"""
import json
import sys
import threading
import time
import warnings
from datetime import datetime
from queue import Queue, Empty

import paho.mqtt.client as mqtt
import tkinter as tk
from tkinter import messagebox
from types import SimpleNamespace
from modern_ui import ModernDashboardMixin

warnings.filterwarnings("ignore", message="Callback API version 1 is deprecated")

# ------------------------- Configuration -------------------------
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60
MQTT_TOPIC_GAS = "sensor/gas"
MQTT_TOPIC_SENSOR = "sensor/suhu"
MQTT_TOPIC_RFID = "sistem/rfid"
MQTT_TOPIC_ALARM = "sistem/alarm"
THRESHOLD_GAS = 3600
THRESHOLD_TEMPERATURE = 40.0
STALE_AFTER = 15
ALARM_RESET_HOLD_SECONDS = 2
GAS_ALARM_DELAY_SECONDS = 5

# ------------------------- Design tokens -------------------------
CLR = {
    "bg": "#0B0B0D", "panel": "#101012", "card": "#141416",
    "card_alt": "#1C1C20", "track": "#2A2A2E", "border": "#232326",
    "border_hi": "#353539", "text": "#F7F7F8", "text_dim": "#C8C8CE",
    "text_muted": "#9A9AA2", "accent": "#FF7A1A", "accent_hi": "#FF9A49",
    "selected": "#392719", "safe_tint": "#153329",
    "safe": "#3DDC84", "safe_hi": "#72E7A6",
    "warning": "#FFB660", "warning_hi": "#FFD1A0",
    "danger": "#E34A54", "danger_hi": "#FF777F",
    "info": "#FF7A1A", "info_hover": "#FF9A49",
}

FONT_DISPLAY = ("Segoe UI", 30, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_LABEL = ("Segoe UI", 10, "bold")
FONT_BODY = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 9)

state = {
    "gas": {"value": None, "timestamp": None},
    "temperature": {"value": None, "timestamp": None},
    "humidity": {"value": None, "timestamp": None},
    "rfid": {"uid": None, "timestamp": None},
    "alarm_status": "AMAN",
    "connection": "DISCONNECTED",
    "log": [],
}
mqtt_queue = Queue()
mqtt_client = None


def log(message):
    entry = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
    state["log"].append(entry)
    if len(state["log"]) > 300:
        state["log"] = state["log"][-300:]


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        state["connection"] = "CONNECTED"
        log("MQTT terhubung ke broker %s:%s" % (MQTT_BROKER, MQTT_PORT))
        client.subscribe([(MQTT_TOPIC_GAS, 0), (MQTT_TOPIC_SENSOR, 0),
                          (MQTT_TOPIC_RFID, 0), (MQTT_TOPIC_ALARM, 0)])
    else:
        state["connection"] = "DISCONNECTED"
        log("Gagal terhubung ke MQTT, rc=%s" % rc)


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
    except Exception:
        payload = None
    mqtt_queue.put({"topic": msg.topic, "payload": payload})


def on_disconnect(client, userdata, rc):
    state["connection"] = "DISCONNECTED"
    if rc != 0:
        log("MQTT terputus; mencoba terhubung kembali secara otomatis")


def on_connect_fail(client, userdata):
    state["connection"] = "DISCONNECTED"
    log("Broker MQTT belum tersedia; koneksi akan dicoba kembali")


def mqtt_thread():
    global mqtt_client
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
    mqtt_client = client
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.on_connect_fail = on_connect_fail
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.connect_async(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
    client.loop_forever(retry_first_connection=True)


def evaluate_safety():
    reasons = []
    gas_val = state["gas"]["value"]
    if gas_val is not None and gas_val > THRESHOLD_GAS:
        reasons.append("Kadar gas %s ppm melewati batas %s ppm" % (gas_val, THRESHOLD_GAS))
    temp_val = state["temperature"]["value"]
    if temp_val is not None and temp_val > THRESHOLD_TEMPERATURE:
        reasons.append("Suhu %s C melewati batas %s C" % (temp_val, THRESHOLD_TEMPERATURE))
    now = time.time()
    for key, label in (("gas", "gas"), ("temperature", "suhu"), ("humidity", "kelembapan")):
        ts = state[key]["timestamp"]
        if ts is not None and now - ts > STALE_AFTER:
            reasons.append("Data %s tidak pernah diperbarui" % label)
    danger = bool(reasons)
    new_status = "BAHAYA" if danger else "AMAN"
    if new_status != state["alarm_status"]:
        state["alarm_status"] = new_status
        log("Status sistem berubah menjadi %s" % new_status)
    return danger, reasons



class RoundedButton(tk.Canvas):
    """Flat modern button drawn on a canvas with hover states."""

    def __init__(self, master, text, command, color, hover, text_color="#061019", radius=10, **kwargs):
        super().__init__(master, height=46, highlightthickness=0, bd=0, bg=master.cget("bg"), **kwargs)
        self._text = text
        self._command = command
        self._color = color
        self._hover = hover
        self._text_color = text_color
        self._radius = radius
        self._pressed = False
        self._active = False
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Configure>", lambda e: self._draw())

    def _on_press(self, _event):
        self._pressed = True
        self._draw()

    def _on_release(self, event):
        self._pressed = False
        self._draw()
        if self._active and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            if self._command:
                self._command()

    def _on_enter(self, _event):
        self._active = True
        self._draw()

    def _on_leave(self, _event):
        self._active = False
        self._pressed = False
        self._draw()

    def _draw(self):
        self.delete("all")
        w = max(self.winfo_width(), 10)
        h = max(self.winfo_height(), 10)
        r = self._radius
        color = self._hover if self._active else self._color
        if self._pressed:
            color = self._color
        self._round_rect(0, 0, w, h, r, fill=color, outline="")
        self.create_text(w / 2, h / 2, text=self._text, fill=self._text_color,
                         font=("Segoe UI", 11, "bold"))

    def _round_rect(self, x0, y0, x1, y1, r, **kwargs):
        points = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
                  x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
                  x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.create_polygon(points, smooth=True, **kwargs)


class ProgressBar(tk.Canvas):
    """Slim rounded progress bar with fill colour."""

    def __init__(self, master, **kwargs):
        super().__init__(master, height=10, highlightthickness=0, bd=0, bg=master.cget("bg"), **kwargs)
        self._value = 0.0
        self._color = CLR["safe"]
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value, color=None):
        self._value = max(0.0, min(1.0, float(value)))
        if color:
            self._color = color
        self._draw()

    def _draw(self):
        self.delete("all")
        w = max(self.winfo_width(), 10)
        h = max(self.winfo_height(), 10)
        r = h / 2
        self._round_rect(0, 0, w, h, r, fill=CLR["track"], outline="")
        fill = w * self._value
        if fill > 1:
            self._round_rect(0, 0, max(fill, r * 2), h, r, fill=self._color, outline="")

    def _round_rect(self, x0, y0, x1, y1, r, **kwargs):
        points = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
                  x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
                  x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.create_polygon(points, smooth=True, **kwargs)


def enable_native_dpi():
    """Avoid bitmap scaling of Tk text and vector Canvas on high-DPI Windows."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        # Per-monitor V2; older Windows versions use system-DPI awareness.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


class EvakuasiDashboard(ModernDashboardMixin, tk.Tk):
    def __init__(self):
        enable_native_dpi()
        super().__init__()
        self._alarm_commanded = False
        self._alarm_reset_until = 0.0
        self._gas_danger_since = None
        self._last_gas_sample_at = None
        self._gas_confirmed = False
        self._pending_alarm_echoes = []
        self._last_connection = state["connection"]
        self.title("Fire Safety | IoT Monitoring")
        width = min(1400, self.winfo_screenwidth() - 80)
        height = min(900, self.winfo_screenheight() - 100)
        self.geometry(f"{width}x{height}")
        self.minsize(1000, 650)
        self.configure(bg=CLR["bg"])
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.model = SimpleNamespace(
            colors=CLR, state=state, evaluate=evaluate_safety, log=log,
            broker=MQTT_BROKER, port=MQTT_PORT, topic_gas=MQTT_TOPIC_GAS,
            topic_sensor=MQTT_TOPIC_SENSOR, topic_rfid=MQTT_TOPIC_RFID,
            topic_alarm=MQTT_TOPIC_ALARM, gas_threshold=THRESHOLD_GAS,
            temp_threshold=THRESHOLD_TEMPERATURE, stale_after=STALE_AFTER,
            progress_class=ProgressBar, button_class=RoundedButton,
        )
        self._create_widgets()
        self.after(200, self._process_mqtt_queue)
        self._periodic_id = self.after(500, self._periodic_update)

    def _process_mqtt_queue(self):
        while True:
            try:
                msg = mqtt_queue.get_nowait()
            except Empty:
                break
            self._handle_mqtt_message(msg)
        if state["connection"] == "CONNECTED" and self._last_connection != "CONNECTED" and not self._alarm_commanded:
            self._trigger_alarm_for_sample()
        self._last_connection = state["connection"]
        self.after(200, self._process_mqtt_queue)

    def _periodic_update(self):
        super()._periodic_update()
        if (self._last_gas_sample_at is not None and
                time.time() - self._last_gas_sample_at > STALE_AFTER):
            self._gas_danger_since = None
            self._gas_confirmed = False
        if self._gas_danger_since is not None or (self._alarm_reset_until and not self._alarm_commanded):
            self._trigger_alarm_for_sample()

    def _handle_mqtt_message(self, msg):
        topic = msg["topic"]
        payload = msg["payload"]
        if topic == MQTT_TOPIC_ALARM:
            command = payload.strip().upper() if isinstance(payload, str) else ""
            if command in ("AMAN", "BAHAYA"):
                if self._pending_alarm_echoes and self._pending_alarm_echoes[0] == command:
                    self._pending_alarm_echoes.pop(0)
                    log("Status alarm dikonfirmasi: %s" % command)
                    return
                if command == "AMAN":
                    self._alarm_commanded = False
                    self._alarm_reset_until = max(self._alarm_reset_until,
                                                  time.time() + ALARM_RESET_HOLD_SECONDS)
                    state["alarm_status"] = "AMAN"
                elif time.time() >= self._alarm_reset_until:
                    self._alarm_commanded = True
                    state["alarm_status"] = "BAHAYA"
                log("Status alarm perangkat: %s" % command)
            else:
                log("Perintah alarm tidak dikenal: %s" % payload)
            return
        try:
            data = json.loads(payload) if payload else {}
        except (json.JSONDecodeError, TypeError):
            log("Payload tidak valid JSON pada topic %s" % topic)
            return
        if not isinstance(data, dict):
            data = {}
        now = time.time()

        if topic == MQTT_TOPIC_GAS:
            val = data.get("nilai", data.get("gas"))
            if isinstance(val, (int, float)):
                state["gas"]["value"] = val
                state["gas"]["timestamp"] = now
                if val > THRESHOLD_GAS:
                    if self._gas_danger_since is None or self._last_gas_sample_at is None or now - self._last_gas_sample_at > STALE_AFTER:
                        self._gas_danger_since = now
                        self._gas_confirmed = False
                    elif now > self._last_gas_sample_at:
                        self._gas_confirmed = True
                    self._last_gas_sample_at = now
                else:
                    self._gas_danger_since = None
                    self._gas_confirmed = False
                    self._last_gas_sample_at = now
                log("MQTT diterima %s: %s" % (topic, payload))
                self._trigger_alarm_for_sample()
        elif topic == MQTT_TOPIC_SENSOR:
            suhu = data.get("suhu", data.get("temperature"))
            hum = data.get("humidity", data.get("kelembapan"))
            if isinstance(suhu, (int, float)):
                state["temperature"]["value"] = suhu
                state["temperature"]["timestamp"] = now
            if isinstance(hum, (int, float)):
                state["humidity"]["value"] = hum
                state["humidity"]["timestamp"] = now
            if isinstance(suhu, (int, float)) or isinstance(hum, (int, float)):
                log("MQTT diterima %s: %s" % (topic, payload))
            if isinstance(suhu, (int, float)):
                self._trigger_alarm_for_sample()
        elif topic == MQTT_TOPIC_RFID:
            uid = data.get("rfid", data.get("uid"))
            if uid:
                state["rfid"]["uid"] = uid
                state["rfid"]["timestamp"] = now
                log("RFID terdeteksi: %s" % uid)

    def _trigger_alarm_for_sample(self):
        """Only a fresh gas/temperature sample may sound the physical alarm."""
        gas = state["gas"]
        temp = state["temperature"]
        now = time.time()
        gas_danger = (gas["timestamp"] is not None and now - gas["timestamp"] <= STALE_AFTER
                      and gas["value"] is not None and gas["value"] > THRESHOLD_GAS
                      and self._gas_danger_since is not None
                      and self._gas_confirmed
                      and now - self._gas_danger_since >= GAS_ALARM_DELAY_SECONDS)
        temp_danger = (temp["timestamp"] is not None and now - temp["timestamp"] <= STALE_AFTER
                       and temp["value"] is not None and temp["value"] > THRESHOLD_TEMPERATURE)
        if (gas_danger or temp_danger) and not self._alarm_commanded and now >= self._alarm_reset_until:
            if self._publish(MQTT_TOPIC_ALARM, "BAHAYA"):
                self._alarm_commanded = True
                log("Perintah ALARM otomatis dikirim ke broker")
            self._refresh_log()

    def _publish(self, topic, payload):
        client = mqtt_client
        if client is None or not client.is_connected():
            log("Perintah tidak terkirim: MQTT belum terhubung")
            return False
        try:
            info = client.publish(topic, payload, qos=1)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                log("Perintah gagal dikirim ke %s: kode %s" % (topic, info.rc))
                return False
            info.wait_for_publish(timeout=2)
            if not info.is_published():
                log("Perintah ke %s belum dikonfirmasi broker" % topic)
                return False
            if topic == MQTT_TOPIC_ALARM and payload in ("AMAN", "BAHAYA"):
                self._pending_alarm_echoes.append(payload)
        except Exception as exc:
            log("Gagal publish ke %s: %s" % (topic, exc))
            return False
        return True

    def _send_alarm(self):
        if self._publish(MQTT_TOPIC_ALARM, "BAHAYA"):
            self._alarm_commanded = True
            state["alarm_status"] = "BAHAYA"
            log("Perintah ALARM dikirim ke broker")
        self._refresh_log()

    def _send_reset(self):
        if self._publish(MQTT_TOPIC_ALARM, "AMAN"):
            self._alarm_commanded = False
            self._alarm_reset_until = time.time() + ALARM_RESET_HOLD_SECONDS
            state["alarm_status"] = "AMAN"
            log("Perintah RESET dikirim ke broker")
        self._refresh_log()

    def _reset_dashboard(self):
        confirmed = messagebox.askyesno(
            "Reset Dashboard",
            "Hapus nilai sensor, status alarm lokal, dan log aktivitas?\n"
            "Koneksi MQTT dan perangkat sensor tidak akan diubah.",
            parent=self,
        )
        if not confirmed:
            return

        for key in ("gas", "temperature", "humidity"):
            state[key].update(value=None, timestamp=None)
        state["rfid"].update(uid=None, timestamp=None)
        state["alarm_status"] = "AMAN"
        state["log"].clear()

        while True:
            try:
                mqtt_queue.get_nowait()
            except Empty:
                break

        log("Dashboard direset oleh operator")
        for card in (self.gas_card, self.temp_card, self.hum_card):
            card.value_lbl.configure(text="--")
            card.progress.set(0.0, CLR["text_muted"])
        self.status_icon.configure(text="\u2026", fg=CLR["warning"])
        self.status_title_lbl.configure(text="MENUNGGU DATA SENSOR", fg=CLR["warning"])
        self._refresh_log()

    def on_close(self):
        log("Aplikasi ditutup")
        self.destroy()


def main():
    log("Aplikasi Fire Safety Monitoring dimulai")
    app = EvakuasiDashboard()
    t = threading.Thread(target=mqtt_thread, daemon=True)
    t.start()
    app.mainloop()


if __name__ == "__main__":
    main()
