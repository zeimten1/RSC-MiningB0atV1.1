import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import threading
import time
import win32gui
import win32con
from bot import MiningBot
from drag_drop_list import DragDropList
import ctypes
from ctypes import wintypes
import psutil
from PIL import Image, ImageTk

WM_HOTKEY = 0x0312
VK_F6 = 0x75

# ── Theme Presets ─────────────────────────────────────────────────────────────
THEMES = {
    'Default': {
        'BG': '#0d0d0f', 'SURFACE': '#16161a', 'BORDER': '#2a2a32',
        'FG': '#e2e2e8', 'MUTED': '#9e9eab', 'ACCENT': '#ff6b7a',
        'GREEN': '#4ade80', 'RED': '#ff6b6b', 'AMBER': '#4ade80',
        'TITLE_BG': '#080808',
    },
    'White + Light Blue': {
        'BG': '#eef2f7', 'SURFACE': '#ffffff', 'BORDER': '#b8c9dc',
        'FG': '#1a1a2e', 'MUTED': '#5a6378', 'ACCENT': '#2980b9',
        'GREEN': '#27ae60', 'RED': '#c0392b', 'AMBER': '#f39c12',
        'TITLE_BG': '#d5dfe9',
    },
    'Magenta + Black': {
        'BG': '#0a0008', 'SURFACE': '#180818', 'BORDER': '#3d1540',
        'FG': '#f0c8f4', 'MUTED': '#a068a8', 'ACCENT': '#ff44ff',
        'GREEN': '#00e87b', 'RED': '#ff3368', 'AMBER': '#ff8800',
        'TITLE_BG': '#060006',
    },
    'Red + Black': {
        'BG': '#0a0000', 'SURFACE': '#1a0808', 'BORDER': '#3d1a1a',
        'FG': '#f0c8c8', 'MUTED': '#a07070', 'ACCENT': '#ff3333',
        'GREEN': '#4ade80', 'RED': '#ff4444', 'AMBER': '#ff8800',
        'TITLE_BG': '#060000',
    },
    'Green + Black': {
        'BG': '#000a00', 'SURFACE': '#081808', 'BORDER': '#1a3d1a',
        'FG': '#c8f0c8', 'MUTED': '#70a070', 'ACCENT': '#33ff66',
        'GREEN': '#33ff66', 'RED': '#ff4444', 'AMBER': '#88ff00',
        'TITLE_BG': '#000600',
    },
    'RSC Classic': {
        'BG': '#000000', 'SURFACE': '#0c0c00', 'BORDER': '#333300',
        'FG': '#ffff00', 'MUTED': '#c8c800', 'ACCENT': '#ffcc00',
        'GREEN': '#00ff00', 'RED': '#ff0000', 'AMBER': '#ffff00',
        'TITLE_BG': '#000000',
    },
}
FONT_CHOICES = ['Consolas', 'Segoe UI', 'Courier New', 'Fixedsys']

def _load_active_theme():
    global BG, SURFACE, BORDER, FG, MUTED, ACCENT, GREEN, RED, AMBER, TITLE_BG, FONT_UI, FONT_HDR
    theme_name = 'Default'
    font_name = 'Consolas'
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r') as f:
                cfg = json.load(f)
            theme_name = cfg.get('theme', 'Default')
            font_name = cfg.get('font', 'Consolas')
        except Exception:
            pass
    t = THEMES.get(theme_name, THEMES['Default'])
    BG       = t['BG']
    SURFACE  = t['SURFACE']
    BORDER   = t['BORDER']
    FG       = t['FG']
    MUTED    = t['MUTED']
    ACCENT   = t['ACCENT']
    GREEN    = t['GREEN']
    RED      = t['RED']
    AMBER    = t['AMBER']
    TITLE_BG = t['TITLE_BG']
    if font_name not in FONT_CHOICES:
        font_name = 'Consolas'
    FONT_UI  = (font_name, 9)
    FONT_HDR = (font_name, 10, 'bold')

_load_active_theme()


def card(parent, **kw):
    outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
    inner = tk.Frame(outer, bg=SURFACE, **kw)
    inner.pack(fill='both', expand=True)
    return outer, inner


def section_label(parent, text):
    tk.Label(parent, text=text.upper(), bg=SURFACE, fg=ACCENT,
             font=('Segoe UI', 9, 'bold'), pady=4).pack(anchor='w', padx=8)
    tk.Frame(parent, bg=BORDER, height=1).pack(fill='x', padx=6, pady=(0, 6))


class MiningBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('RSC Mining Bot  v1')
        self.root.geometry('720x750')
        self.root.minsize(680, 700)
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW', self.on_closing)

        # Window icon (pickaxe)
        _icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
        try:
            _ico_img = Image.open(os.path.join(_icons_dir, 'Rune_Pickaxe.png'))
            self._app_icon = ImageTk.PhotoImage(_ico_img)
            self.root.iconphoto(True, self._app_icon)
        except Exception:
            pass

        self.bot = None
        self.bot_thread = None
        self.running = False
        self.obtain_count = 0
        self.ore_count = 0
        self._overlay_win = None
        self._overlay_label = None
        self._overlay_photo = None

        self.load_config()
        self._build_styles()
        self._build_ui()

        self.root.bind_all('<F6>', self.toggle_bot)
        self._hotkey_registered = False
        self.start_hotkey_listener()

    # ── Config ────────────────────────────────────────────────────────────────

    def load_config(self):
        if os.path.exists('config.json'):
            with open('config.json', 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {
                'window_title': 'RScrevolution',
                'ore_checkboxes': {},
                'show_empty_ore': False,
                'priority_order': [],
                'break_settings': {},
                'mouse_settings': {},
                'model_settings': {'use_main_model': True, 'use_adamantite_model': False},
                'detection_settings': {
                    'confidence_threshold': 0.75,
                    'update_interval_ms': 200,
                    'no_ore_retry_delay_ms': 500,
                },
                'powermine_enabled': False,
                'fatigue_detection_enabled': True,
            }

    def save_config(self):
        self.config['window_title'] = self.window_var.get()
        self.config['show_empty_ore'] = self.show_empty_var.get()
        for ore, var in self.checkbox_vars.items():
            self.config['ore_checkboxes'][ore] = var.get()
        self.config['priority_order'] = self.priority_list.get_items()
        self.config['break_settings'] = {
            'breaks_enabled':              self.breaks_enabled_var.get(),
            'min_seconds_between_breaks':  int(self.min_break_interval_var.get()),
            'max_seconds_between_breaks':  int(self.max_break_interval_var.get()),
            'min_break_duration_seconds':  int(self.min_break_duration_var.get()),
            'max_break_duration_seconds':  int(self.max_break_duration_var.get()),
            'micro_breaks_enabled':        self.micro_breaks_enabled_var.get(),
            'micro_break_min_ms':          int(self.micro_break_min_var.get()),
            'micro_break_max_ms':          int(self.micro_break_max_var.get()),
        }
        try:
            self.config['mouse_settings'] = {
                'min_delay_ms':         int(self.min_delay_var.get()),
                'max_delay_ms':         int(self.max_delay_var.get()),
                'human_curve_strength': float(self.human_curve_var.get()),
            }
        except Exception:
            pass
        self.config['model_settings'] = {
            'use_main_model':       self.main_model_var.get(),
            'use_adamantite_model': self.adam_model_var.get(),
        }
        try:
            self.config['detection_settings'] = {
                'confidence_threshold':  float(self.confidence_var.get()),
                'update_interval_ms':    int(self.update_interval_var.get()),
                'no_ore_retry_delay_ms': int(self.no_ore_delay_var.get()),
            }
        except Exception:
            pass
        self.config['antiban_failsafe_enabled'] = True
        self.config['powermine_enabled'] = self.powermine_var.get()
        self.config['fatigue_detection_enabled'] = self.fatigue_detection_var.get()
        self.config['fast_mining_enabled'] = (self.mining_speed_var.get() == 'fast')
        self.config['stop_on_full_inventory'] = self.stop_on_full_var.get()
        self.config['overlay_mode'] = self.overlay_mode_var.get()
        self.config['mouse_outside_window'] = self.mouse_outside_var.get()
        if hasattr(self, 'theme_var'):
            self.config['theme'] = self.theme_var.get()
        if hasattr(self, 'font_var'):
            self.config['font'] = self.font_var.get()
        with open('config.json', 'w') as f:
            json.dump(self.config, f, indent=4)

    def get_java_windows(self):
        """Get list of running Java programs (javaw.exe or java.exe)"""
        java_windows = []
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] in ['javaw.exe', 'java.exe']:
                        # Get window title from process
                        hwnd_list = []
                        def enum_handler(hwnd, ctx):
                            if win32gui.IsWindowVisible(hwnd):
                                try:
                                    # Use ctypes to get the window's process ID
                                    pid = ctypes.wintypes.DWORD()
                                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                                    if pid.value == proc.info['pid']:
                                        hwnd_list.append(hwnd)
                                except:
                                    pass
                            return True
                        
                        win32gui.EnumWindows(enum_handler, None)
                        
                        for hwnd in hwnd_list:
                            title = win32gui.GetWindowText(hwnd)
                            if title and title not in java_windows:
                                java_windows.append(title)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            print(f"Error getting Java windows: {e}")
        
        return java_windows if java_windows else ['RScrevolution', 'RScrevolution 2']

    # ── Style ─────────────────────────────────────────────────────────────────

    def _build_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('TFrame',      background=BG)
        s.configure('TLabel',      background=SURFACE, foreground=FG, font=FONT_UI)
        # Toggle-style checkbuttons: rounded look, teal when selected
        s.configure('TCheckbutton',
                    background=SURFACE, foreground=FG, font=FONT_UI,
                    indicatorcolor=BORDER, indicatorrelief='flat',
                    indicatormargin=4, selectcolor=GREEN)
        s.map('TCheckbutton',
              background=[('active', SURFACE)],
              foreground=[('active', FG)],
              indicatorcolor=[('selected', GREEN), ('!selected', BORDER)])
        s.configure('TEntry',
                    fieldbackground=TITLE_BG, foreground=FG,
                    insertcolor=FG, font=FONT_UI, padding=3, relief='flat')
        s.configure('TScale', background=SURFACE, troughcolor=BORDER, slidercolor=ACCENT)
        s.configure('TRadiobutton', background=SURFACE, foreground=FG, font=FONT_UI,
                    indicatorcolor=BORDER, selectcolor=GREEN)
        s.map('TRadiobutton',
              background=[('active', SURFACE)],
              indicatorcolor=[('selected', GREEN)])
        s.configure('Start.TButton',
                    font=('Segoe UI', 9, 'bold'),
                    background=GREEN, foreground='#0f131a',
                    padding=(18, 7), relief='flat')
        s.map('Start.TButton',
              background=[('active', '#4dd4b6'), ('disabled', BORDER)],
              foreground=[('disabled', MUTED)])
        s.configure('Stop.TButton',
                    font=('Segoe UI', 9, 'bold'),
                    background=RED, foreground='#0f131a',
                    padding=(18, 7), relief='flat')
        s.map('Stop.TButton',
              background=[('active', '#e05555'), ('disabled', BORDER)],
              foreground=[('disabled', MUTED)])
        s.configure('Util.TButton',
                    font=FONT_UI,
                    background=BORDER, foreground=FG,
                    padding=(10, 5), relief='flat')
        s.map('Util.TButton', background=[('active', '#3a4458')])
        s.configure('TNotebook', background=BG, borderwidth=0)
        s.configure('TNotebook.Tab', background=BORDER, foreground=MUTED,
                    font=('Segoe UI', 9, 'bold'), padding=(14, 6))
        s.map('TNotebook.Tab',
              background=[('selected', SURFACE)],
              foreground=[('selected', FG)])

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        _icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
        self._title_icons = []  # prevent GC

        # Titlebar
        bar = tk.Frame(self.root, bg=TITLE_BG, height=44)
        bar.pack(fill='x')
        bar.pack_propagate(False)

        # Pickaxe icon + title text
        try:
            pick_img = Image.open(os.path.join(_icons_dir, 'Rune_Pickaxe.png')).resize((24, 24), Image.LANCZOS)
            pick_photo = ImageTk.PhotoImage(pick_img)
            self._title_icons.append(pick_photo)
            tk.Label(bar, image=pick_photo, bg=TITLE_BG).pack(side='left', padx=(14, 4), pady=10)
        except Exception:
            pass
        tk.Label(bar, text='RSC MINING BOT', bg=TITLE_BG, fg=FG,
                 font=('Segoe UI', 11, 'bold')).pack(side='left', pady=12)

        # Ore icons in order: Copper, Coal, Iron, Mithril, Adamantite, Tin
        ore_files = ['Copper_ore.png', 'Coal.png', 'Iron_ore.png',
                     'Mithril_ore.png', 'Adamantite_ore.png', 'Tin_ore.png']
        for fname in ore_files:
            try:
                ore_img = Image.open(os.path.join(_icons_dir, fname)).resize((20, 20), Image.LANCZOS)
                ore_photo = ImageTk.PhotoImage(ore_img)
                self._title_icons.append(ore_photo)
                tk.Label(bar, image=ore_photo, bg=TITLE_BG).pack(side='left', padx=1, pady=10)
            except Exception:
                pass
        
        self.status_dot = tk.Label(bar, text='● IDLE', bg=TITLE_BG, fg=MUTED,
                                   font=('Segoe UI', 8, 'bold'))
        self.status_dot.pack(side='right', padx=14)

        # ── Notebook with two tabs ───────────────────────────────────────────
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=6, pady=(4, 0))

        # Tab 1: Bot
        bot_tab = tk.Frame(notebook, bg=BG)
        notebook.add(bot_tab, text='  Bot  ')
        self._build_bot_tab(bot_tab)

        # Tab 2: Settings
        settings_tab = tk.Frame(notebook, bg=BG)
        notebook.add(settings_tab, text='  Settings  ')
        self._build_settings_tab(settings_tab)

        # Footer
        footer = tk.Frame(self.root, bg=TITLE_BG, height=54)
        footer.pack(fill='x', side='bottom')
        footer.pack_propagate(False)
        tk.Frame(footer, bg=BORDER, height=1).pack(fill='x', side='top')
        btn_row = tk.Frame(footer, bg=TITLE_BG)
        btn_row.pack(expand=True)
        self.btn_start = ttk.Button(btn_row, text='▶  START', command=self.start_bot,
                                    style='Start.TButton')
        self.btn_start.pack(side='left', padx=6, pady=10)
        self.btn_stop = ttk.Button(btn_row, text='■  STOP', command=self.stop_bot,
                                   state='disabled', style='Stop.TButton')
        self.btn_stop.pack(side='left', padx=6)
        ttk.Button(btn_row, text='SAVE', command=self.save_config,
                   style='Util.TButton').pack(side='left', padx=6)

        # Overlay mode toggle — always visible in footer
        sep = tk.Frame(btn_row, bg=BORDER, width=1, height=24)
        sep.pack(side='left', padx=8, fill='y')
        tk.Label(btn_row, text='OVERLAY:', bg=TITLE_BG, fg=MUTED,
                 font=(FONT_UI[0], 7, 'bold')).pack(side='left')
        self.overlay_mode_var = tk.StringVar(value=self.config.get('overlay_mode', 'ingame'))
        ttk.Radiobutton(btn_row, text='In-Game',
                        variable=self.overlay_mode_var, value='ingame').pack(side='left', padx=2)
        ttk.Radiobutton(btn_row, text='Pop-Out',
                        variable=self.overlay_mode_var, value='popout').pack(side='left', padx=2)

        tk.Label(btn_row, text='F6 = toggle', bg=TITLE_BG, fg=MUTED,
                 font=(FONT_UI[0], 7)).pack(side='left', padx=10)

    # ── Bot Tab (main working view) ──────────────────────────────────────────

    def _build_bot_tab(self, tab):
        # Scrollable wrapper so all cards are reachable
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0, bd=0)
        vscroll = tk.Scrollbar(tab, orient='vertical', command=canvas.yview,
                               bg=BG, troughcolor=BG, width=8, highlightthickness=0, bd=0)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        wrapper = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=wrapper, anchor='nw')

        def _resize(e=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        wrapper.bind('<Configure>', _resize)
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.bind_all('<MouseWheel>',
                        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))

        left  = tk.Frame(wrapper, bg=BG)
        right = tk.Frame(wrapper, bg=BG)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 4))
        right.grid(row=0, column=1, sticky='nsew', padx=(4, 0))
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(0, weight=1)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, p):
        # Window
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'Game Window')
        
        java_windows = self.get_java_windows()
        self.window_var = tk.StringVar(value=self.config['window_title'])
        
        row = tk.Frame(c, bg=SURFACE)
        row.pack(fill='x', padx=8, pady=(0, 4))
        tk.Label(row, text='Window:', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=8, anchor='w').pack(side='left', padx=4)
        window_dropdown = ttk.Combobox(row, textvariable=self.window_var,
                                       values=java_windows, state='readonly', width=25)
        window_dropdown.pack(side='left', padx=4, expand=True, fill='x')
        window_dropdown.bind('<<ComboboxSelected>>', self.on_window_selected)
        ttk.Button(row, text='Refresh', command=self.refresh_windows,
                   style='Util.TButton').pack(side='left', padx=4)
        ttk.Button(row, text='Flash', command=self.flash_window,
                   style='Util.TButton').pack(side='right', padx=4)

        # Models
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'YOLO Models')
        self.main_model_var = tk.BooleanVar(
            value=self.config.get('model_settings', {}).get('use_main_model', True))
        self.adam_model_var = tk.BooleanVar(
            value=self.config.get('model_settings', {}).get('use_adamantite_model', False))
        mr = tk.Frame(c, bg=SURFACE)
        mr.pack(fill='x', padx=8, pady=(0, 4))
        ttk.Checkbutton(mr, text='Main (best.pt)',
                        variable=self.main_model_var).pack(side='left', padx=4)
        ttk.Checkbutton(mr, text='Adamantite',
                        variable=self.adam_model_var).pack(side='left', padx=4)

        # Ores
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'Ore Selection')
        og = tk.Frame(c, bg=SURFACE)
        og.pack(fill='x', padx=8, pady=(0, 4))
        self.checkbox_vars = {}
        ores = ['coal_rock', 'mithril_rock', 'iron_rock',
                'adamantite_rock', 'tin_rock', 'copper_rock']
        col1 = tk.Frame(og, bg=SURFACE); col1.pack(side='left', fill='x', expand=True)
        col2 = tk.Frame(og, bg=SURFACE); col2.pack(side='left', fill='x', expand=True)
        for i, ore in enumerate(ores):
            var = tk.BooleanVar(value=self.config['ore_checkboxes'].get(ore, True))
            self.checkbox_vars[ore] = var
            pc = col1 if i < 3 else col2
            ttk.Checkbutton(pc, text=ore.replace('_rock', '').title(),
                            variable=var).pack(anchor='w', padx=2, pady=1)
        self.show_empty_var = tk.BooleanVar(value=self.config['show_empty_ore'])
        ttk.Checkbutton(og, text='Empty rocks',
                        variable=self.show_empty_var).pack(anchor='w', padx=2, pady=1)

        # Priority
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'Priority Order')
        tk.Label(c, text='drag & drop to reorder', bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 7, 'italic')).pack(anchor='w', padx=10, pady=(0, 2))
        pf = tk.Frame(c, bg=SURFACE, height=60)
        pf.pack(fill='x', padx=8, pady=(0, 4))
        self.priority_list = DragDropList(pf, self.config['priority_order'])
        self.priority_list.pack(fill='both', expand=True)

        # Mining Mode
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'Mining Mode')

        # Speed: Fast / Lazy radio buttons
        speed_init = 'fast' if self.config.get('fast_mining_enabled', True) else 'lazy'
        self.mining_speed_var = tk.StringVar(value=speed_init)
        sr = tk.Frame(c, bg=SURFACE)
        sr.pack(fill='x', padx=8, pady=(0, 2))
        ttk.Radiobutton(sr, text='Fast  (100-1200 ms)',
                        variable=self.mining_speed_var, value='fast',
                        command=self._on_speed_change).pack(side='left', padx=4)
        ttk.Radiobutton(sr, text='Lazy  (500-2900 ms)',
                        variable=self.mining_speed_var, value='lazy',
                        command=self._on_speed_change).pack(side='left', padx=4)

        # Stop behaviour
        self.stop_on_full_var = tk.BooleanVar(value=self.config.get('stop_on_full_inventory', True))
        ttk.Checkbutton(c, text='Stop when inventory full (X/30)',
                        variable=self.stop_on_full_var).pack(anchor='w', padx=8, pady=(2, 2))

        self.powermine_var = tk.BooleanVar(value=self.config.get('powermine_enabled', False))
        ttk.Checkbutton(c, text='Powermine (never stop)',
                        variable=self.powermine_var).pack(anchor='w', padx=8, pady=(0, 4))

        # overlay_mode_var is created in the footer (always visible)
        # just make sure the variable exists before the footer is built
        if not hasattr(self, 'overlay_mode_var'):
            self.overlay_mode_var = tk.StringVar(value=self.config.get('overlay_mode', 'ingame'))

    def _build_right(self, p):
        # Live Statistics
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'Live Statistics')

        # Runtime timer
        r = tk.Frame(c, bg=SURFACE)
        r.pack(fill='x', padx=8, pady=4)
        tk.Label(r, text='Runtime', bg=SURFACE, fg=MUTED,
                 font=('Consolas', 10, 'bold'), width=12, anchor='w').pack(side='left')
        self.live_runtime_label = tk.Label(r, text='00:00', bg=BORDER, fg=GREEN,
                                           font=('Consolas', 12, 'bold'), width=8)
        self.live_runtime_label.pack(side='right', padx=4)

        for attr, label, default, color, font_sz in [
            ('live_fatigue_label',   'Fatigue',   '0%',   RED,   12),
            ('live_inventory_label', 'Inventory', '0/30', AMBER, 12),
        ]:
            r = tk.Frame(c, bg=SURFACE)
            r.pack(fill='x', padx=8, pady=4)
            tk.Label(r, text=label, bg=SURFACE, fg=MUTED,
                     font=('Consolas', 10, 'bold'), width=12, anchor='w').pack(side='left')
            lbl = tk.Label(r, text=default, bg=BORDER, fg=color,
                           font=('Consolas', font_sz, 'bold'), width=8)
            lbl.pack(side='right', padx=4)
            setattr(self, attr, lbl)
        
        r = tk.Frame(c, bg=SURFACE)
        r.pack(fill='x', padx=8, pady=2)
        tk.Label(r, text='Last Click', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=12, anchor='w').pack(side='left')
        self.live_last_click_label = tk.Label(r, text='----', bg=BORDER, fg=RED,
                                              font=('Consolas', 10, 'bold'), width=8)
        self.live_last_click_label.pack(side='right', padx=4)
        
        self.live_mouse_label = None
        
        # Debug Log
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='both', expand=True, pady=(0, 6))
        section_label(c, 'Debug Log')
        self.debug_text = scrolledtext.ScrolledText(
            c, height=10,
            bg=TITLE_BG, fg=GREEN,
            insertbackground=GREEN,
            font=(FONT_UI[0], 9),
            relief='flat', bd=0,
            selectbackground=BORDER)
        self.debug_text.pack(fill='both', expand=True, padx=6, pady=(0, 6))
        self.debug_text.config(state='disabled')
        self.log_debug('Console ready')

    # ── Settings Tab ─────────────────────────────────────────────────────────

    def _build_settings_tab(self, tab):
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0, bd=0)
        vscroll = tk.Scrollbar(tab, orient='vertical', command=canvas.yview,
                               bg=BG, troughcolor=BG, width=8, highlightthickness=0, bd=0)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        body = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=body, anchor='nw')

        def _resize(e=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        body.bind('<Configure>', _resize)
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.bind_all('<MouseWheel>',
                        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))

        # Theme
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(6, 6))
        section_label(c, 'Theme')
        tk.Label(c, text='\u26a0 Warning: Editing theme will restart bot',
                 bg=SURFACE, fg=AMBER, font=(FONT_UI[0], 8, 'bold')).pack(anchor='w', padx=8, pady=(0, 4))
        tr = tk.Frame(c, bg=SURFACE)
        tr.pack(fill='x', padx=8, pady=2)
        tk.Label(tr, text='Preset', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=10, anchor='w').pack(side='left')
        self.theme_var = tk.StringVar(value=self.config.get('theme', 'Default'))
        theme_combo = ttk.Combobox(tr, textvariable=self.theme_var,
                                   values=list(THEMES.keys()), state='readonly', width=20)
        theme_combo.pack(side='left', padx=4)
        theme_combo.bind('<<ComboboxSelected>>', self._on_theme_change)
        fr = tk.Frame(c, bg=SURFACE)
        fr.pack(fill='x', padx=8, pady=(2, 6))
        tk.Label(fr, text='Font', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=10, anchor='w').pack(side='left')
        self.font_var = tk.StringVar(value=self.config.get('font', FONT_UI[0]))
        font_combo = ttk.Combobox(fr, textvariable=self.font_var,
                                  values=FONT_CHOICES, state='readonly', width=20)
        font_combo.pack(side='left', padx=4)
        font_combo.bind('<<ComboboxSelected>>', self._on_theme_change)

        # Detection
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(6, 6))
        section_label(c, 'Detection')
        self.confidence_var = tk.DoubleVar(
            value=self.config.get('detection_settings', {}).get('confidence_threshold', 0.75))
        crow = tk.Frame(c, bg=SURFACE)
        crow.pack(fill='x', padx=8, pady=(0, 4))
        tk.Label(crow, text='Confidence', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=11, anchor='w').pack(side='left')
        self.confidence_value_label = tk.Label(
            crow, text=f'{self.confidence_var.get():.2f}',
            bg=BORDER, fg=ACCENT, font=('Consolas', 8, 'bold'), width=5)
        self.confidence_value_label.pack(side='right', padx=4)
        ttk.Scale(crow, from_=0.05, to=1.0, orient='horizontal',
                  variable=self.confidence_var,
                  command=self.on_confidence_change).pack(side='left', fill='x', expand=True)

        det = self.config.get('detection_settings', {})
        self.update_interval_var = tk.StringVar(value=str(det.get('update_interval_ms', 200)))
        self.no_ore_delay_var    = tk.StringVar(value=str(det.get('no_ore_retry_delay_ms', 500)))
        for lbl, var, unit in [('Update int.', self.update_interval_var, 'ms'),
                                ('No-ore delay', self.no_ore_delay_var, 'ms')]:
            r = tk.Frame(c, bg=SURFACE)
            r.pack(fill='x', padx=8, pady=2)
            tk.Label(r, text=lbl, bg=SURFACE, fg=MUTED,
                     font=FONT_UI, width=11, anchor='w').pack(side='left')
            ttk.Entry(r, textvariable=var, width=7).pack(side='left', padx=4)
            tk.Label(r, text=unit, bg=SURFACE, fg=MUTED, font=FONT_UI).pack(side='left')

        # Mouse
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(0, 6))
        section_label(c, 'Mouse')
        ms = self.config.get('mouse_settings', {})
        self.min_delay_var   = tk.StringVar(value=str(ms.get('min_delay_ms', 50)))
        self.max_delay_var   = tk.StringVar(value=str(ms.get('max_delay_ms', 250)))
        self.human_curve_var = tk.StringVar(value=str(ms.get('human_curve_strength', 0.7)))
        for lbl, var, unit in [('Min delay', self.min_delay_var, 'ms'),
                                ('Max delay', self.max_delay_var, 'ms'),
                                ('Curve str.', self.human_curve_var, '')]:
            r = tk.Frame(c, bg=SURFACE)
            r.pack(fill='x', padx=8, pady=2)
            tk.Label(r, text=lbl, bg=SURFACE, fg=MUTED,
                     font=FONT_UI, width=10, anchor='w').pack(side='left')
            ttk.Entry(r, textvariable=var, width=7).pack(side='left', padx=4)
            if unit:
                tk.Label(r, text=unit, bg=SURFACE, fg=MUTED, font=FONT_UI).pack(side='left')

        # Long Breaks
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(0, 6))
        section_label(c, 'Long Breaks')
        bs = self.config.get('break_settings', {})
        self.breaks_enabled_var = tk.BooleanVar(value=bs.get('breaks_enabled', True))
        ttk.Checkbutton(c, text='Enable', variable=self.breaks_enabled_var).pack(
            anchor='w', padx=8, pady=(0, 4))
        self.min_break_interval_var = tk.StringVar(value=str(bs.get('min_seconds_between_breaks', 900)))
        self.max_break_interval_var = tk.StringVar(value=str(bs.get('max_seconds_between_breaks', 900)))
        self.min_break_duration_var = tk.StringVar(value=str(bs.get('min_break_duration_seconds', 1)))
        self.max_break_duration_var = tk.StringVar(value=str(bs.get('max_break_duration_seconds', 20)))
        for lbl, v1, v2 in [('Interval (s)', self.min_break_interval_var, self.max_break_interval_var),
                             ('Duration (s)', self.min_break_duration_var, self.max_break_duration_var)]:
            r = tk.Frame(c, bg=SURFACE)
            r.pack(fill='x', padx=8, pady=2)
            tk.Label(r, text=lbl, bg=SURFACE, fg=MUTED,
                     font=FONT_UI, width=10, anchor='w').pack(side='left')
            ttk.Entry(r, textvariable=v1, width=6).pack(side='left', padx=2)
            tk.Label(r, text='–', bg=SURFACE, fg=MUTED, font=FONT_UI).pack(side='left', padx=2)
            ttk.Entry(r, textvariable=v2, width=6).pack(side='left', padx=2)

        # Micro Breaks
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(0, 6))
        section_label(c, 'Micro Breaks')
        self.micro_breaks_enabled_var = tk.BooleanVar(value=bs.get('micro_breaks_enabled', True))
        ttk.Checkbutton(c, text='Enable', variable=self.micro_breaks_enabled_var).pack(
            anchor='w', padx=8, pady=(0, 4))
        self.micro_break_min_var = tk.StringVar(value=str(bs.get('micro_break_min_ms', 100)))
        self.micro_break_max_var = tk.StringVar(value=str(bs.get('micro_break_max_ms', 500)))
        r = tk.Frame(c, bg=SURFACE)
        r.pack(fill='x', padx=8, pady=2)
        tk.Label(r, text='Range (ms)', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=10, anchor='w').pack(side='left')
        ttk.Entry(r, textvariable=self.micro_break_min_var, width=6).pack(side='left', padx=2)
        tk.Label(r, text='–', bg=SURFACE, fg=MUTED, font=FONT_UI).pack(side='left', padx=2)
        ttk.Entry(r, textvariable=self.micro_break_max_var, width=6).pack(side='left', padx=2)

        # Antiban
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(0, 6))
        section_label(c, 'Antiban')
        tk.Label(c, text='Auto-stops after 30 empty camera rotations.',
                 bg=SURFACE, fg=MUTED, font=('Consolas', 7)).pack(anchor='w', padx=8, pady=(0, 4))
        self.fatigue_detection_var = tk.BooleanVar(value=self.config.get('fatigue_detection_enabled', True))
        ttk.Checkbutton(c, text='Detect fatigue (OCR) – stop at 96 %',
                        variable=self.fatigue_detection_var).pack(anchor='w', padx=8, pady=(0, 2))
        self.mouse_outside_var = tk.BooleanVar(value=self.config.get('mouse_outside_window', False))
        self._mouse_outside_cb = ttk.Checkbutton(
            c, text='Move mouse outside window after click (Lazy only)',
            variable=self.mouse_outside_var, command=self._on_mouse_outside_change)
        self._mouse_outside_cb.pack(anchor='w', padx=8, pady=(0, 4))

    # ── Speed / antiban interlock ────────────────────────────────────────────

    def _on_speed_change(self):
        """When Fast is selected, force-disable mouse-outside-window."""
        if self.mining_speed_var.get() == 'fast':
            self.mouse_outside_var.set(False)

    def _on_mouse_outside_change(self):
        """When mouse-outside is toggled on, force Lazy mode."""
        if self.mouse_outside_var.get():
            self.mining_speed_var.set('lazy')

    def _on_theme_change(self, event=None):
        """Save theme/font and restart the GUI."""
        theme = self.theme_var.get()
        if theme == 'RSC Classic':
            self.font_var.set('Courier New')
        self.config['theme'] = self.theme_var.get()
        self.config['font'] = self.font_var.get()
        self.save_config()
        self._restart = True
        self.on_closing()

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def update_inventory(self, cur, total):
        pass

    def update_ore_count(self, count):
        try:
            self.ore_count = count
        except Exception:
            pass

    def on_confidence_change(self, value):
        try:
            self.confidence_value_label.config(text=f'{float(value):.2f}')
        except Exception:
            pass

    def increment_obtain_count(self):
        try:
            self.obtain_count += 1
            self.log_debug(f'Ore obtained  ({self.obtain_count} total)')
        except Exception:
            pass

    def reset_obtain_count(self):
        try:
            self.obtain_count = 0
        except Exception:
            pass

    def update_live_stats(self, fatigue=None, ore_counts=None, last_click_ms=None, mouse_x=None, mouse_y=None, inventory_count=None):
        """Update live statistics display in real-time"""
        try:
            # Update runtime
            if hasattr(self, '_start_time') and self._start_time:
                elapsed = int(time.time() - self._start_time)
                hrs, rem = divmod(elapsed, 3600)
                mins, secs = divmod(rem, 60)
                if hrs > 0:
                    self.live_runtime_label.config(text=f'{hrs}:{mins:02d}:{secs:02d}')
                else:
                    self.live_runtime_label.config(text=f'{mins:02d}:{secs:02d}')

            # Update fatigue
            if fatigue is not None:
                color = RED if fatigue > 75 else AMBER if fatigue > 50 else MUTED
                self.live_fatigue_label.config(text=f'{int(fatigue)}%', fg=color)
            
            # Update inventory count (X/30)
            if inventory_count is not None:
                self.live_inventory_label.config(text=f'{int(inventory_count)}/30')
            
            # Update last click time — show elapsed seconds since last click
            if last_click_ms is not None:
                if last_click_ms == 0:
                    self.live_last_click_label.config(text='----')
                else:
                    elapsed_s = (time.time() * 1000 - last_click_ms) / 1000.0
                    self.live_last_click_label.config(text=f'{elapsed_s:.1f}s')
            
            # Update mouse coordinates
            if mouse_x is not None and mouse_y is not None:
                if self.live_mouse_label is not None:
                    self.live_mouse_label.config(text=f'{int(mouse_x)}, {int(mouse_y)}')
        
        except Exception as e:
            print(f"[GUI] Error updating live stats: {e}")

    def log_debug(self, msg):
        try:
            self.debug_text.config(state='normal')
            self.debug_text.insert('end', f'{time.strftime("%H:%M:%S")}  {msg}\n')
            self.debug_text.see('end')
            self.debug_text.config(state='disabled')
        except Exception:
            pass
    def on_window_selected(self, event=None):
        """Flash the selected window 3 times to confirm selection"""
        self.flash_window(times=3)
    
    def refresh_windows(self):
        """Refresh the list of Java windows in the dropdown"""
        java_windows = self.get_java_windows()
        # Find the combobox widget and update its values
        try:
            # Rebuild the dropdown with fresh list
            for widget in self.root.winfo_children():
                if isinstance(widget, tk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Frame):
                            for subchild in child.winfo_children():
                                if isinstance(subchild, ttk.Combobox):
                                    subchild['values'] = java_windows
                                    break
        except:
            pass
        self.log_debug(f'Window list refreshed: {len(java_windows)} Java window(s) found')
    def flash_window(self, times=1):
        """Flash the game window to visually confirm selection"""
        title = self.window_var.get()
        def _flash():
            hwnd_list = []
            def enum_handler(hwnd, ctx):
                if win32gui.IsWindowVisible(hwnd) and title in win32gui.GetWindowText(hwnd):
                    hwnd_list.append(hwnd)
                return True
            
            try:
                win32gui.EnumWindows(enum_handler, None)
                for hwnd in hwnd_list:
                    for _ in range(times):
                        try:
                            win32gui.FlashWindow(hwnd, True)
                            time.sleep(0.2)
                            win32gui.FlashWindow(hwnd, False)
                            time.sleep(0.2)
                        except:
                            pass
            except Exception as e:
                print(f"Flash error: {e}")
        
        threading.Thread(target=_flash, daemon=True).start()

    def flash_window(self):
        title = self.window_var.get()
        def _flash():
            hwnd_list = []
            win32gui.EnumWindows(
                lambda h, l: l.append(h) or True
                if title.lower() in win32gui.GetWindowText(h).lower() else True,
                hwnd_list)
            if hwnd_list:
                for _ in range(3):
                    win32gui.FlashWindow(hwnd_list[0], True)
                    time.sleep(0.2)
                win32gui.SetForegroundWindow(hwnd_list[0])
                messagebox.showinfo('Flash', f'Found: {title}')
            else:
                messagebox.showwarning('Flash', f'Window not found: {title}')
        threading.Thread(target=_flash, daemon=True).start()

    def start_bot(self):
        if self.running:
            return
        self.save_config()
        if not any(v.get() for v in self.checkbox_vars.values()):
            messagebox.showwarning('Warning', 'No ores selected!')
            return
        if not (self.main_model_var.get() or self.adam_model_var.get()):
            messagebox.showwarning('Warning', 'At least one model must be enabled!')
            return
        self.running = True
        self._start_time = time.time()
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.status_dot.config(text='● RUNNING', fg=GREEN)
        self.reset_obtain_count()
        self.update_inventory(0, 30)
        self.update_ore_count(0)
        self.log_debug('Bot starting...')
        self.bot = MiningBot(self.config, self)
        self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self.bot_thread.start()
        self._schedule_live_update()
        self._start_overlay()

    def _schedule_live_update(self):
        """Periodically update live statistics from bot - very fast 50ms updates"""
        if self.running and self.bot:
            try:
                self.update_live_stats(
                    fatigue=self.bot.current_fatigue,
                    ore_counts=self.bot.ore_counts,
                    last_click_ms=self.bot.last_click_time,
                    mouse_x=self.bot.mouse_x,
                    mouse_y=self.bot.mouse_y,
                    inventory_count=self.bot.inventory_count
                )
            except Exception as e:
                pass
            self.root.after(50, self._schedule_live_update)  # Update every 50ms for smooth mouse tracking

    def _run_bot(self):
        try:
            self.bot.run()
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror('Bot Error', str(e)))
            self.root.after(0, self.stop_bot)

    def stop_bot(self):
        if not self.running:
            return
        self.running = False
        if self.bot:
            self.bot.stop()
        self._stop_overlay()
        self._start_time = None
        self.live_runtime_label.config(text='00:00')
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        self.status_dot.config(text='● STOPPED', fg=RED)
        self.log_debug('Bot stopped.')

    # ── Tkinter-based YOLO overlay ───────────────────────────────────────────

    # BGR ore colors from detector → RGB for PIL
    _ORE_COLORS_RGB = {
        'adamantite': (255, 0, 0),
        'mithril':    (128, 0, 128),
        'coal':       (100, 100, 100),
        'iron':       (200, 200, 200),
        'tin':        (0, 255, 255),
        'copper':     (255, 165, 0),
        'empty':      (255, 255, 0),
    }
    CHROMA_KEY = (255, 0, 255)   # magenta — will be invisible in-game

    def _start_overlay(self):
        """Create the overlay Toplevel and start polling frames from the bot."""
        self._overlay_win = None
        self._overlay_label = None
        self._overlay_photo = None

        mode = self.overlay_mode_var.get()
        chroma_hex = '#FF00FF'

        top = tk.Toplevel(self.root)
        top.title('Mining Bot Overlay')
        top.protocol('WM_DELETE_WINDOW', lambda: None)

        if mode == 'ingame':
            top.configure(bg=chroma_hex)
            top.overrideredirect(True)
            top.attributes('-topmost', True)
            self._overlay_label = tk.Label(top, bg=chroma_hex)
            self._overlay_label.pack(fill='both', expand=True)
            top.update_idletasks()
            # Set WS_EX_LAYERED | TRANSPARENT | TOPMOST, then chroma-key
            try:
                # Tk wraps the toplevel in a frame — get the real HWND
                wm_frame = top.wm_frame()
                overlay_hwnd = int(wm_frame, 16) if wm_frame else 0
                if not overlay_hwnd:
                    overlay_hwnd = ctypes.windll.user32.GetParent(
                        top.winfo_id())
                if overlay_hwnd:
                    ex = win32gui.GetWindowLong(overlay_hwnd, win32con.GWL_EXSTYLE)
                    ex |= (win32con.WS_EX_LAYERED |
                           win32con.WS_EX_TRANSPARENT |
                           win32con.WS_EX_TOPMOST)
                    win32gui.SetWindowLong(overlay_hwnd, win32con.GWL_EXSTYLE, ex)
                    # LWA_COLORKEY = 0x01 — makes COLORREF magenta fully transparent
                    ctypes.windll.user32.SetLayeredWindowAttributes(
                        overlay_hwnd, 0x00FF00FF, 0, 0x01)
            except Exception:
                pass
        else:
            top.configure(bg='black')
            top.geometry('512x340')
            top.attributes('-topmost', True)
            self._overlay_label = tk.Label(top, bg='black')
            self._overlay_label.pack(fill='both', expand=True)

        self._overlay_win = top
        # Pop-out Toplevel steals focus from the game window; give it back
        if mode != 'ingame':
            def _refocus_game():
                if self.bot and self.bot.hwnd:
                    try:
                        self.bot.bring_window_to_front()
                    except Exception:
                        pass
            self.root.after(800, _refocus_game)
        self._poll_overlay_frame()

    def _draw_boxes_only(self, detections, width, height):
        """Render detection boxes + stats ROI box on a chroma-key background."""
        from PIL import ImageDraw, ImageFont
        img = Image.new('RGB', (width, height), self.CHROMA_KEY)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype('consola.ttf', 13)
        except Exception:
            font = ImageFont.load_default()

        # Permanent box around Hits/Prayer/Fatigue/FPS area (top-left)
        stats_x1 = 0
        stats_y1 = 0
        stats_x2 = int(width * 0.22)
        stats_y2 = int(height * 0.28)
        draw.rectangle([stats_x1, stats_y1, stats_x2, stats_y2],
                       outline=(0, 255, 255), width=2)
        draw.text((stats_x1 + 3, max(stats_y1 - 14, 0)), 'STATS ROI',
                  fill=(0, 255, 255), font=font)

        # Permanent box around inventory count area (top-right)
        inv_x1 = int(width * 0.90)
        inv_y1 = 0
        inv_x2 = width - 1
        inv_y2 = int(height * 0.10)
        draw.rectangle([inv_x1, inv_y1, inv_x2, inv_y2],
                       outline=(0, 255, 0), width=2)
        draw.text((inv_x1 + 3, max(inv_y1, 0) + 2), 'INV ROI',
                  fill=(0, 255, 0), font=font)

        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det['box']]
            name = det['class_name']
            conf = det['confidence']
            # Pick colour
            color = (0, 255, 0)
            for key, c in self._ORE_COLORS_RGB.items():
                if key in name:
                    color = c
                    break
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            label = f"{name.replace('_', ' ').title()} {conf:.0%}"
            draw.text((x1, max(y1 - 14, 0)), label, fill=color, font=font)
        return img

    def _poll_overlay_frame(self):
        """Periodically grab the latest annotated frame from the bot and show it."""
        if not self.running or self._overlay_win is None:
            return
        try:
            frame, region, detections = self.bot._overlay_buf.get()
            mode = self.overlay_mode_var.get()

            if mode == 'ingame':
                # Draw ONLY boxes on a magenta background (chroma-keyed out)
                if region is not None:
                    x, y, w, h = region
                    self._overlay_win.geometry(f'{w}x{h}+{x}+{y}')
                    img = self._draw_boxes_only(detections or [], w, h)
                    photo = ImageTk.PhotoImage(img)
                    self._overlay_label.configure(image=photo)
                    self._overlay_photo = photo
            else:
                # Pop-out: show the full annotated frame
                if frame is not None:
                    rgb = frame[:, :, ::-1] if frame.shape[2] == 3 else frame
                    img = Image.fromarray(rgb)
                    # Draw stats ROI box on pop-out too
                    from PIL import ImageDraw, ImageFont
                    orig_w, orig_h = img.size
                    draw = ImageDraw.Draw(img)
                    sy1 = 0
                    sy2 = int(orig_h * 0.28)
                    sx2 = int(orig_w * 0.22)
                    draw.rectangle([0, sy1, sx2, sy2], outline=(0, 255, 255), width=2)
                    try:
                        fnt = ImageFont.truetype('consola.ttf', 13)
                    except Exception:
                        fnt = ImageFont.load_default()
                    draw.text((3, max(sy1 - 14, 0)), 'STATS ROI', fill=(0, 255, 255), font=fnt)
                    # Draw inventory ROI box on pop-out too
                    inv_x1 = int(orig_w * 0.90)
                    inv_y1 = 0
                    inv_x2 = orig_w - 1
                    inv_y2 = int(orig_h * 0.10)
                    draw.rectangle([inv_x1, inv_y1, inv_x2, inv_y2],
                                   outline=(0, 255, 0), width=2)
                    draw.text((inv_x1 + 3, inv_y1 + 2), 'INV ROI',
                              fill=(0, 255, 0), font=fnt)
                    win_w = self._overlay_win.winfo_width()
                    win_h = self._overlay_win.winfo_height()
                    if win_w > 10 and win_h > 10:
                        img = img.resize((win_w, win_h), Image.NEAREST)
                    photo = ImageTk.PhotoImage(img)
                    self._overlay_label.configure(image=photo)
                    self._overlay_photo = photo
        except Exception:
            pass
        self.root.after(200, self._poll_overlay_frame)

    def _stop_overlay(self):
        """Destroy the overlay window."""
        try:
            if self._overlay_win is not None:
                self._overlay_win.destroy()
        except Exception:
            pass
        self._overlay_win = None
        self._overlay_label = None
        self._overlay_photo = None

    def toggle_bot(self, event=None):
        if self.running:
            self.stop_bot()
        else:
            self.start_bot()

    def start_hotkey_listener(self):
        def _thread():
            user32 = ctypes.windll.user32
            try:
                if user32.RegisterHotKey(None, 1, 0, VK_F6):
                    self._hotkey_registered = True
                    self.log_debug('Global F6 hotkey registered')
                else:
                    self.log_debug('Global hotkey registration failed')
            except Exception as e:
                self.log_debug(f'Hotkey error: {e}')
            msg = wintypes.MSG()
            while True:
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res in (0, -1):
                    break
                if msg.message == WM_HOTKEY:
                    try:
                        self.root.after(0, self.toggle_bot)
                    except Exception:
                        pass
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        threading.Thread(target=_thread, daemon=True).start()

    def on_closing(self):
        self.stop_bot()
        try:
            if getattr(self, '_hotkey_registered', False):
                ctypes.windll.user32.UnregisterHotKey(None, 1)
        except Exception:
            pass
        self.root.destroy()


if __name__ == '__main__':
    while True:
        _load_active_theme()
        root = tk.Tk()
        app = MiningBotGUI(root)
        root.mainloop()
        if not getattr(app, '_restart', False):
            break
