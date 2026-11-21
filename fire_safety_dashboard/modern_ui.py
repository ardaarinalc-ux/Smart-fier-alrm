"""Modern Tkinter presentation layer. No network calls or safety decisions here."""
import tkinter as tk
from tkinter import ttk, font as tkfont
from datetime import datetime
from collections import deque
import math
import time

from ui_model import sensor_presentation


class Surface(tk.Canvas):
    """Rounded surface with a regular Frame for native, accessible widgets."""

    def __init__(self, master, colors, padding=18, **kwargs):
        super().__init__(master, bg=master.cget('bg'), highlightthickness=0, bd=0, **kwargs)
        self.colors = colors
        self.padding = padding
        self.body = tk.Frame(self, bg=colors['card'])
        self.window = self.create_window(padding, padding, window=self.body, anchor='nw')
        self.body.bind('<Configure>', self._body_changed)
        self.bind('<Configure>', self._resize)

    def _body_changed(self, _event=None):
        height = self.body.winfo_reqheight() + self.padding * 2
        if self.winfo_pixels(self.cget('height')) != height:
            self.configure(height=height)

    def _resize(self, _event=None):
        w, h, r = self.winfo_width(), self.winfo_height(), 16
        self.delete('surface')
        points = [r, 1, w-r, 1, w-1, 1, w-1, r, w-1, h-r, w-1, h-1,
                  w-r, h-1, r, h-1, 1, h-1, 1, h-r, 1, r, 1, 1]
        self.create_polygon(points, smooth=True, fill=self.colors['card'],
                            outline=self.colors['border'], tags='surface')
        self.tag_lower('surface')
        self.itemconfigure(self.window, width=max(1, w - self.padding * 2))
        self.coords(self.window, self.padding, self.padding)


class SensorChart(tk.Frame):
    """Crisp Tk vector plot of readings already received by the dashboard."""

    def __init__(self, master, colors, title, unit, limit, family, embedded=False):
        super().__init__(master, bg=colors['card'],
                         highlightbackground=colors['card'] if embedded else colors['border'],
                         highlightthickness=0 if embedded else 1,
                         padx=0 if embedded else 14, pady=0 if embedded else 12)
        self.colors, self.limit, self.unit = colors, limit, unit
        tk.Label(self, text=title, bg=colors['card'], fg=colors['text'],
                 font=(family, 11, 'bold')).pack(anchor='w')
        self.empty_label = tk.Label(self, text='Menunggu pembacaan sensor',
                                    bg=colors['card'], fg=colors['text_muted'],
                                    font=(family, 9))
        self.plot = tk.Canvas(self, height=116, bg=colors['card'], bd=0, highlightthickness=0)
        self.plot.pack(fill='x', expand=True, pady=(7, 0))
        self.plot.bind('<Configure>', lambda event: self.draw())
        self.points = ()
        self.has_line = False
        self.line_color = colors['accent']
        self.family = family
        self.draw()

    def update_points(self, points):
        self.points = tuple(points)
        self.draw()

    def draw(self):
        c = self.plot
        c.delete('all')
        width, height = max(c.winfo_width(), 160), max(c.winfo_height(), 100)
        left, right, top, bottom = 32, width - 12, 10, height - 22
        c.create_line(left, bottom, right, bottom, fill=self.colors['border_hi'], width=1)
        c.create_line(left, top, left, bottom, fill=self.colors['border_hi'], width=1)
        c.create_text(left, height-8, text='Pembacaan terbaru', anchor='w',
                      fill=self.colors['text_muted'], font=(self.family, 8))
        self.has_line = False
        if not self.points:
            self.empty_label.place(relx=.5, rely=.48, anchor='center')
            return
        self.empty_label.place_forget()
        values = [v for _, v in self.points]
        minimum = min(values)
        maximum = max(values)
        if maximum == minimum:
            padding = max(abs(maximum) * .05, 1)
        else:
            padding = (maximum - minimum) * .15
        minimum = max(0, minimum - padding)
        maximum += padding
        span = maximum - minimum or 1
        c.create_text(left-4, top, text=f'{maximum:g}', anchor='e',
                      fill=self.colors['text_muted'], font=(self.family, 8))
        c.create_text(left-4, bottom, text=f'{minimum:g}', anchor='e',
                      fill=self.colors['text_muted'], font=(self.family, 8))
        start, end = self.points[0][0], self.points[-1][0]
        timespan = end - start
        coordinates = []
        for index, (timestamp, value) in enumerate(self.points):
            x = left + (right-left) * ((timestamp-start)/timespan if timespan > 0 else
                                       index / max(1, len(self.points)-1))
            y = bottom - (bottom-top) * (value-minimum) / span
            coordinates.extend((round(x), round(y)))
        if len(coordinates) >= 4:
            c.create_line(*coordinates, fill=self.line_color, width=2,
                          smooth=False, tags='sensor_line')
            self.has_line = True
        c.create_oval(coordinates[-2]-3, coordinates[-1]-3,
                      coordinates[-2]+3, coordinates[-1]+3,
                      outline='', fill=self.line_color)


class ModernDashboardMixin:
    page_names = ('Dashboard', 'Sensor', 'Riwayat aktivitas')
    page_descriptions = (
        'Kondisi lingkungan dan status perangkat secara langsung.',
        'Nilai sensor terkini beserta waktu pembaruan dan batas pemantauan.',
        'Catatan koneksi, pembacaan sensor, dan tindakan operator.',
    )
    page_sections = {
        0: ('condition', 'sensors', 'status', 'rfid', 'activity'),
        1: ('sensors', 'rfid'), 2: ('history',),
    }

    def _label(self, parent, text='', role='body', color=None, **kwargs):
        fonts = {'body': (self._font_family, 11), 'small': (self._font_family, 9),
                 'title': (self._font_family, 13, 'bold'), 'heading': (self._font_family, 23, 'bold'),
                 'number': (self._font_family, 36, 'bold'), 'mono': ('Consolas' if self._font_family == 'Segoe UI' else 'DejaVu Sans Mono', 10)}
        return tk.Label(parent, text=text, bg=parent.cget('bg'),
                        fg=color or self.C['text'], font=fonts[role], bd=0, **kwargs)

    def _create_widgets(self):
        self.C = self.model.colors
        self._font_family = 'Segoe UI' if 'Segoe UI' in tkfont.families(self) else 'DejaVu Sans'
        self._last_log = None
        self._last_reasons = ()
        self.chart_history = {key: deque(maxlen=60) for key in ('gas', 'temperature', 'humidity')}
        self.sections = {}
        shell = tk.Frame(self, bg=self.C['bg'])
        shell.pack(fill='both', expand=True)
        self._build_sidebar(shell)
        main = tk.Frame(shell, bg=self.C['bg'])
        main.pack(side='left', fill='both', expand=True)
        self._build_header(main)
        viewport = tk.Frame(main, bg=self.C['bg'])
        viewport.pack(fill='both', expand=True)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('Modern.Vertical.TScrollbar', background=self.C['border_hi'],
                        troughcolor=self.C['bg'], borderwidth=0, arrowsize=10)
        style.map('Modern.Vertical.TScrollbar', background=[('active', self.C['text_muted'])])
        self.content_canvas = tk.Canvas(viewport, bg=self.C['bg'], bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, orient='vertical', style='Modern.Vertical.TScrollbar',
                                  command=self.content_canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.content_canvas.pack(side='left', fill='both', expand=True)
        self.content_canvas.configure(yscrollcommand=scrollbar.set)
        self.content = tk.Frame(self.content_canvas, bg=self.C['bg'])
        self._content_window = self.content_canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', self._sync_scroll)
        self.content_canvas.bind('<Configure>', self._resize_content)
        self.bind('<MouseWheel>', self._wheel)
        self.bind('<Button-4>', self._wheel)
        self.bind('<Button-5>', self._wheel)
        heading = tk.Frame(self.content, bg=self.C['bg'])
        heading.pack(fill='x', padx=24, pady=(22, 18))
        self.page_title_lbl = self._label(heading, role='heading')
        self.page_title_lbl.pack(anchor='w')
        self._build_condition(self.content)
        self._build_status_card(self.content)
        self._build_sensors(self.content)
        self._build_rfid(self.content)
        self._build_activity(self.content)
        self._build_history(self.content)
        self._select_nav(0)

    def _sync_scroll(self, _event=None):
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox('all'))

    def _resize_content(self, event):
        self.content_canvas.itemconfigure(self._content_window, width=event.width)
        self._sync_scroll()

    def _wheel(self, event):
        # Native log widgets retain their own scrolling behavior.
        if isinstance(event.widget, (tk.Text, ttk.Scrollbar)):
            return
        if self.content.winfo_height() <= self.content_canvas.winfo_height():
            return
        if getattr(event, 'num', None) in (4, 5):
            units = -3 if event.num == 4 else 3
        else:
            units = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        self.content_canvas.yview_scroll(units, 'units')

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=self.C['bg'], height=74)
        header.pack(fill='x')
        header.pack_propagate(False)
        self.clock_lbl = self._label(header, role='small', color=self.C['text_dim'])
        self.clock_lbl.pack(side='right', padx=(16, 24))
        connection = tk.Frame(header, bg=self.C['card_alt'], padx=12, pady=6)
        connection.pack(side='right', pady=19)
        self.conn_dot = self._label(connection, '\u25cf', color=self.C['text_muted'])
        self.conn_dot.pack(side='left', padx=(0, 7))
        self.mqtt_status_lbl = self._label(connection, 'MQTT OFFLINE', role='small', color=self.C['text_dim'])
        self.mqtt_status_lbl.pack(side='left')
        tk.Frame(parent, bg=self.C['border'], height=1).pack(fill='x')

    def _build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=self.C['panel'], width=250)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        self._label(sidebar, '●  FIRE SAFETY', role='title', color=self.C['accent']).pack(anchor='w', padx=22, pady=(27, 5))
        self._label(sidebar, 'IoT Monitoring', role='small', color=self.C['text_muted']).pack(anchor='w', padx=22, pady=(0, 35))
        self._label(sidebar, 'MENU', role='small', color=self.C['text_muted']).pack(anchor='w', padx=22, pady=(0, 12))
        labels = self.page_names
        self.nav_items = []
        for index, label in enumerate(labels):
            button = tk.Button(sidebar, text=label, anchor='w',
                               command=lambda idx=index: self._select_nav(idx),
                               font=(self._font_family, 10), bg=self.C['panel'], fg=self.C['text_dim'],
                               activebackground=self.C['accent'], activeforeground=self.C['bg'],
                               relief='flat', bd=0, padx=14, pady=12, cursor='hand2',
                               highlightthickness=1, highlightbackground=self.C['panel'],
                               highlightcolor=self.C['accent'])
            button.pack(side='top', fill='x', padx=12, pady=3)
            self.nav_items.append(button)
        self._build_actions(sidebar)


    def _select_nav(self, idx):
        if idx not in self.page_sections or not hasattr(self, 'sections'):
            return
        self._current_page = idx
        for index, item in enumerate(self.nav_items):
            active = index == idx
            item.configure(bg=self.C['accent'] if active else self.C['panel'],
                           fg=self.C['bg'] if active else self.C['text_dim'],
                           highlightbackground=self.C['accent'] if active else self.C['panel'])
        self.page_title_lbl.configure(text=self.page_names[idx])
        for widget in self.sections.values():
            widget.pack_forget()
        for name in self.page_sections[idx]:
            self.sections[name].pack(fill='x', padx=24, pady=(0, 12))
        self.content_canvas.yview_moveto(0)
        self._sync_scroll()

    def _build_condition(self, parent):
        card = Surface(parent, self.C, padding=18, height=94)
        self.sections['condition'] = card
        self.condition_title_lbl = self._label(card.body, 'KONDISI LINGKUNGAN: WARNING',
                                               role='title', color=self.C['warning'])
        self.condition_title_lbl.pack(anchor='w')
        self.condition_detail_lbl = self._label(card.body,
                                                'Data sensor belum lengkap. Status aman belum dapat dipastikan.',
                                                role='small', color=self.C['text_dim'],
                                                wraplength=570, justify='left')
        self.condition_detail_lbl.pack(anchor='w', pady=(7, 0))
        card.body.bind('<Configure>', lambda event: self.condition_detail_lbl.configure(
            wraplength=max(210, event.width-12)), add='+')

    def _build_status_card(self, parent):
        card = Surface(parent, self.C, padding=16, height=78)
        self.sections['status'] = card
        self.status_icon = self._label(card.body, '\u25cb', role='heading', color=self.C['warning'])
        self.status_icon.pack(side='left', padx=(0, 14))
        text = tk.Frame(card.body, bg=self.C['card'])
        text.pack(side='left', fill='x', expand=True)
        self.status_title_lbl = self._label(text, 'MENUNGGU DATA SENSOR', role='title', color=self.C['warning'])
        self.status_title_lbl.pack(anchor='w')
        self.status_detail_lbl = self._label(text, 'Belum ada pembacaan sensor. Status aman belum dapat dipastikan.',
                                             role='small', color=self.C['text_dim'], wraplength=520, justify='left')
        self.status_detail_lbl.pack(anchor='w', pady=(4, 0))
        self.sensor_count_lbl = self._label(card.body, '0 / 3\nsensor terbaru', role='small', color=self.C['text_dim'], justify='right')
        self.sensor_count_lbl.pack(side='right', padx=(12, 0))
        card.body.bind('<Configure>', lambda event: self.status_detail_lbl.configure(wraplength=max(220, event.width-170)), add='+')

    def _build_sensors(self, parent):
        row = tk.Frame(parent, bg=self.C['bg'])
        self.sections['sensors'] = row
        for index in range(2):
            row.grid_columnconfigure(index, weight=1, uniform='sensors')
        specs = [('Kadar gas', 'ppm', 'MQ-2', 'gas', self.model.gas_threshold),
                 ('Suhu ruangan', '\u00b0C', 'AHT10', 'temperature', self.model.temp_threshold),
                 ('Kelembapan', '%', 'AHT10', 'humidity', 100)]
        cards = []
        for index, (title, unit, sensor, key, threshold) in enumerate(specs):
            card = Surface(row, self.C, padding=16, height=328, width=200)
            card.grid(row=index // 2, column=index % 2, sticky='nsew',
                      padx=(0, 6) if index % 2 == 0 else (6, 0), pady=(0, 12))
            top = tk.Frame(card.body, bg=self.C['card'])
            top.pack(fill='x')
            self._label(top, title, role='small', color=self.C['text_dim']).pack(side='left')
            self._label(top, sensor, role='small', color=self.C['text_muted']).pack(side='right')
            value = tk.Frame(card.body, bg=self.C['card'])
            value.pack(fill='x', pady=(10, 8))
            card.value_lbl = self._label(value, '--', role='number')
            card.value_lbl.pack(side='left')
            self._label(value, unit, color=self.C['text_dim']).pack(side='left', padx=(6, 0), pady=(18, 0))
            card.progress = self.model.progress_class(card.body)
            card.progress.configure(height=5)
            card.progress.pack(fill='x')
            card.freshness_lbl = self._label(card.body, 'Menunggu data', role='small', color=self.C['text_muted'])
            card.freshness_lbl.pack(anchor='w', pady=(8, 0))
            caption = ('Rentang kelembapan 0\u2013100 %' if key == 'humidity'
                       else f'Batas pemantauan {threshold:g} {unit}')
            self._label(card.body, caption, role='small', color=self.C['text_muted']).pack(anchor='w', pady=(2, 0))
            card.unit, card.key = unit, key
            chart = SensorChart(card.body, self.C, 'Grafik pembacaan', unit, threshold,
                                self._font_family, embedded=True)
            chart.pack(fill='x', pady=(17, 0))
            setattr(self, {'gas': 'gas_chart', 'temperature': 'temp_chart',
                           'humidity': 'hum_chart'}[key], chart)
            cards.append(card)
        self.gas_card, self.temp_card, self.hum_card = cards
        coverage = Surface(row, self.C, padding=16, width=200)
        coverage.grid(row=1, column=1, sticky='nsew', padx=(6, 0), pady=(0, 12))
        self._label(coverage.body, 'PERANGKAT & KONEKSI', role='small', color=self.C['text_dim']).pack(anchor='w')
        self._label(coverage.body, 'MQTT', role='number').pack(anchor='w', pady=(10, 8))
        self._label(coverage.body, f'{self.model.broker}:{self.model.port}', role='mono').pack(anchor='w')
        self._label(coverage.body, 'MQ-2  /  AHT10  /  RFID', role='small', color=self.C['text_dim']).pack(anchor='w', pady=(8, 0))
        self._label(coverage.body, 'Status koneksi langsung di bagian atas.', role='small', color=self.C['text_muted']).pack(anchor='w', pady=(2, 0))

    def _build_rfid(self, parent):
        card = Surface(parent, self.C, padding=14, height=64)
        self.sections['rfid'] = card
        self._label(card.body, 'RFID', role='small', color=self.C['accent_hi']).pack(side='left', padx=(0, 20))
        self.rfid_value_lbl = self._label(card.body, 'Belum ada kartu', role='mono')
        self.rfid_value_lbl.pack(side='left')
        self.rfid_time_lbl = self._label(card.body, 'Menunggu pemindaian', role='small', color=self.C['text_muted'])
        self.rfid_time_lbl.pack(side='right')


    def _build_activity(self, parent):
        activity = Surface(parent, self.C, padding=16, height=190)
        self.sections['activity'] = activity
        self._label(activity.body, 'Aktivitas terkini', role='title').pack(anchor='w')
        self._label(activity.body, '60 catatan terakhir', role='small', color=self.C['text_muted']).pack(anchor='w', pady=(3, 10))
        self.log_text = self._make_log(activity.body, height=6)

    def _make_log(self, parent, height=15):
        frame = tk.Frame(parent, bg=self.C['card'])
        frame.pack(fill='both', expand=True)
        text = tk.Text(frame, width=1, height=height, wrap='word', bg=self.C['card'], fg=self.C['text_dim'],
                       font=('Consolas', 9), relief='flat', bd=0, highlightthickness=0,
                       padx=0, pady=4, spacing1=4, spacing3=5, insertbackground=self.C['text'],
                       selectbackground=self.C['selected'], state='disabled')
        scroll = ttk.Scrollbar(frame, orient='vertical', command=text.yview, style='Modern.Vertical.TScrollbar')
        scroll.pack(side='right', fill='y')
        text.pack(side='left', fill='both', expand=True)
        text.configure(yscrollcommand=scroll.set)
        return text

    def _build_history(self, parent):
        card = Surface(parent, self.C, height=400)
        self.sections['history'] = card
        self._label(card.body, 'Riwayat sesi ini', role='title').pack(anchor='w')
        self._label(card.body, 'Maksimal 300 catatan di memori. Tidak tersimpan setelah aplikasi ditutup.',
                    role='small', color=self.C['text_muted'], wraplength=580, justify='left').pack(anchor='w', pady=(4, 12))
        self.history_text = self._make_log(card.body, height=22)

    def _build_actions(self, parent):
        self.action_bar = tk.Frame(parent, bg=self.C['panel'])
        self.action_bar.pack(side='top', fill='x', pady=(26, 0))
        tk.Frame(self.action_bar, height=1, bg=self.C['border']).pack(fill='x', padx=16)
        status_row = tk.Frame(self.action_bar, bg=self.C['panel'])
        status_row.pack(fill='x', padx=16, pady=(16, 12))
        self._label(status_row, 'KONTROL OPERATOR', role='small',
                    color=self.C['text_muted']).pack(anchor='w', pady=(0, 9))
        self.global_status_lbl = self._label(status_row, 'MENUNGGU DATA SENSOR',
                                             role='small', color=self.C['warning'],
                                             wraplength=175, justify='left')
        self.global_status_lbl.pack(anchor='w')
        buttons = tk.Frame(self.action_bar, bg=self.C['panel'])
        buttons.pack(fill='x', padx=16, pady=(0, 10))
        specs = [('Bunyikan alarm', self._send_alarm, 'danger', 'danger_hi', '#FFFFFF'),
                 ('Reset aman', self._send_reset, 'accent', 'accent_hi', self.C['bg']),
                 ('Reset dashboard', self._reset_dashboard, 'card_alt', 'border_hi', self.C['text_dim'])]
        self.action_buttons = []
        for index, (label, callback, color, hover, foreground) in enumerate(specs):
            button = self.model.button_class(buttons, label, callback, self.C[color], self.C[hover],
                                              text_color=foreground, radius=9, width=100, takefocus=1, cursor='hand2')
            button.configure(height=40)
            button.pack(side='top', fill='x', pady=(0, 7))
            button.bind('<Return>', lambda event, action=callback: action())
            button.bind('<space>', lambda event, action=callback: action())
            button.bind('<FocusIn>', lambda event, b=button: b.configure(highlightthickness=1, highlightbackground=self.C['accent']))
            button.bind('<FocusOut>', lambda event, b=button: b.configure(highlightthickness=0))
            self.action_buttons.append(button)
        self._label(self.action_bar, 'Reset aman mengirim perintah MQTT. Reset dashboard hanya mengosongkan tampilan lokal.',
                    role='small', color=self.C['text_muted'], wraplength=175, justify='left').pack(anchor='w', padx=16, pady=(0, 10))

    def _periodic_update(self):
        now = time.time()
        state = self.model.state
        self.clock_lbl.configure(text=datetime.now().strftime('%d %b %Y  /  %H:%M:%S'))
        connected = state['connection'] == 'CONNECTED'
        color = self.C['safe'] if connected else self.C['text_muted']
        self.mqtt_status_lbl.configure(text='MQTT ONLINE' if connected else 'MQTT OFFLINE', fg=color)
        self.conn_dot.configure(fg=color)
        for card, threshold, fmt in [(self.gas_card, self.model.gas_threshold, '%.0f'),
                                      (self.temp_card, self.model.temp_threshold, '%.1f'),
                                      (self.hum_card, 100, '%.0f')]:
            self._update_card(card, state[card.key], threshold, fmt)
            history = self.chart_history[card.key]
            slot = state[card.key]
            if slot['value'] is None or slot['timestamp'] is None:
                history.clear()
            elif (isinstance(slot['value'], (int, float)) and
                  math.isfinite(slot['value']) and
                  isinstance(slot['timestamp'], (int, float)) and
                  math.isfinite(slot['timestamp']) and
                  (not history or history[-1][0] != slot['timestamp'])):
                history.append((slot['timestamp'], slot['value']))
            getattr(self, {'gas': 'gas_chart', 'temperature': 'temp_chart',
                           'humidity': 'hum_chart'}[card.key]).update_points(history)
        uid, ts = state['rfid']['uid'], state['rfid']['timestamp']
        self.rfid_value_lbl.configure(text=str(uid) if uid else 'Belum ada kartu')
        self.rfid_time_lbl.configure(text=datetime.fromtimestamp(ts).strftime('Terakhir %H:%M:%S') if ts else 'Menunggu pemindaian')
        danger, reasons = self.model.evaluate()
        fresh = sum(slot['value'] is not None and slot['timestamp'] is not None and now-slot['timestamp'] <= self.model.stale_after
                    for slot in (state['gas'], state['temperature'], state['humidity']))
        self.sensor_count_lbl.configure(text=f'{fresh} / 3\nsensor terbaru')
        if danger:
            tone, icon, title = 'danger', '!', 'BAHAYA TERDETEKSI'
            detail = ' \u00b7 '.join(reasons)
            if tuple(reasons) != self._last_reasons:
                for reason in reasons:
                    self.model.log(reason)
        elif fresh < 3:
            tone, icon, title = 'warning', '\u25cb', 'MENUNGGU DATA SENSOR'
            detail = 'Data sensor belum lengkap. Status aman belum dapat dipastikan.'
        else:
            tone, icon, title = 'safe', '\u2713', 'SEMUA SENSOR NORMAL'
            detail = 'Pembacaan sensor terbaru berada dalam batas pemantauan.'
        self._last_reasons = tuple(reasons)
        self.status_icon.configure(text=icon, fg=self.C[tone])
        self.status_title_lbl.configure(text=title, fg=self.C[tone])
        self.global_status_lbl.configure(text=f'{icon}  {title}',
                                         fg=self.C['danger_hi'] if danger else self.C[tone])
        condition = ('BAHAYA' if danger else 'WARNING' if fresh < 3 else 'AMAN')
        self.condition_title_lbl.configure(text=f'KONDISI LINGKUNGAN: {condition}', fg=self.C[tone])
        self.condition_detail_lbl.configure(text=detail)
        self.status_detail_lbl.configure(text=detail)
        self._refresh_log()
        self._schedule_periodic_update()

    def _schedule_periodic_update(self):
        previous = getattr(self, '_periodic_id', None)
        if previous:
            self.after_cancel(previous)
        self._periodic_id = self.after(1000, self._periodic_update)

    def _update_card(self, card, slot, threshold, fmt):
        decimals = 1 if '.1' in fmt else 0
        value = sensor_presentation(slot, threshold, decimals, stale_after=self.model.stale_after)
        color = self.C['text_muted'] if value['tone'] == 'muted' else self.C[value['tone']]
        card.value_lbl.configure(text=value['value'], fg=self.C['text'] if value['tone'] != 'danger' else self.C['danger_hi'])
        card.freshness_lbl.configure(text=value['freshness'], fg=color)
        card.progress.set(value['progress'], self.C['danger'] if value['tone'] == 'danger' else self.C['accent'])

    def _refresh_log(self):
        lines = tuple(self.model.state['log'])
        if lines == self._last_log:
            return
        self._last_log = lines
        for widget, selected in [(self.log_text, lines[-60:]), (self.history_text, lines)]:
            end_visible = widget.yview()[1] >= .99
            old_position = widget.yview()[0]
            widget.configure(state='normal')
            widget.delete('1.0', 'end')
            widget.insert('end', '\n'.join(selected) if selected else 'Belum ada aktivitas.\nMenunggu koneksi dan data sensor.')
            widget.configure(state='disabled')
            if end_visible:
                widget.see('end')
            else:
                widget.yview_moveto(old_position)
