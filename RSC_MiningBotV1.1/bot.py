import time
import random
import threading
import win32gui
import win32con
import win32api
from mss import mss
import numpy as np
from detector import Detector
from mouse import HumanMouse
import cv2
import winsound
import ctypes

try:
    import easyocr
    _HAVE_OCR = True
    # Initialize EasyOCR reader (lazy load - only when needed)
    _ocr_reader = None
except Exception:
    _HAVE_OCR = False


# Thread-safe frame buffer so the GUI can poll the latest annotated frame.
class _OverlayBuffer:
    def __init__(self):
        self._frame = None
        self._region = None
        self._detections = []
        self._lock = threading.Lock()

    def update_frame(self, frame, region=None, detections=None):
        with self._lock:
            self._frame = frame
            if region is not None:
                self._region = region
            if detections is not None:
                self._detections = detections

    def get(self):
        with self._lock:
            return self._frame, self._region, self._detections


class MiningBot:
    def __init__(self, config, gui):
        self.config = config
        self.gui = gui
        self.running = False
        self.hwnd = None
        self.detector = Detector(config)
        self.mouse = HumanMouse(config["mouse_settings"])
        self.sct = None
        self.inventory_count = 0
        self._inv_fallback_limit = random.randint(35, 40)
        self._click_attempts = {}
        self._blacklist = {}  # key -> expire_time
        
        # Overlay timing: update every 500ms, not every frame
        self.last_overlay_update = 0
        self.overlay_update_interval = 0.5  # 500ms
        
        # Live tracking
        self.current_fatigue = 0  # Fatigue percentage (0-100)
        self.last_click_time = 0  # Time of last click in milliseconds since epoch
        self.mouse_x = 0  # Current mouse X coordinate
        self.mouse_y = 0  # Current mouse Y coordinate
        
        # Ore tracking by type
        self.ore_counts = {
            "tin": 0,
            "copper": 0,
            "coal": 0,
            "iron": 0,
            "mithril": 0,
            "adamantite": 0,
        }
        
        self.last_break_time = time.time()
        self.next_break_interval = self.get_random_break_interval()
        
        self._mine_count = 0  # Click counter for throttling OCR reads
        self._overlay_buf = _OverlayBuffer()
        
        self.no_ore_counter = 0
        self.max_no_ore_moves = 5
        self.consecutive_no_ore_count = 0  # For antiban failsafe
        
        # Mining speed mode (Fast vs Lazy)
        self.fast_mining_enabled = config.get('fast_mining_enabled', True)
        
    def get_click_position(self, box):
        """Get center of YOLO detection box with small natural jitter"""
        x1, y1, x2, y2 = box
        # True center of the bounding box
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        # Small gaussian jitter (±5% of box size) so clicks aren't pixel-perfect
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        jitter_x = random.gauss(0, w * 0.05)
        jitter_y = random.gauss(0, h * 0.05)

        # Clamp so we always land inside the box
        x = int(max(x1 + 2, min(x2 - 2, cx + jitter_x)))
        y = int(max(y1 + 2, min(y2 - 2, cy + jitter_y)))
        return (x, y)
    
    def get_distance_from_center(self, box, frame_width, frame_height):
        """Calculate distance from ore center to screen center"""
        x1, y1, x2, y2 = box
        ore_cx = (x1 + x2) / 2.0
        ore_cy = (y1 + y2) / 2.0
        
        screen_cx = frame_width / 2.0
        screen_cy = frame_height / 2.0
        
        # Euclidean distance
        distance = ((ore_cx - screen_cx) ** 2 + (ore_cy - screen_cy) ** 2) ** 0.5
        return distance
    
    def get_random_break_interval(self):
        """Get random interval before next break"""
        min_sec = self.config["break_settings"].get("min_seconds_between_breaks", 900)
        max_sec = self.config["break_settings"].get("max_seconds_between_breaks", 900)
        return random.uniform(min_sec, max_sec)
    
    def get_random_break_duration(self):
        """Get random break duration"""
        min_sec = self.config["break_settings"].get("min_break_duration_seconds", 1)
        max_sec = self.config["break_settings"].get("max_break_duration_seconds", 20)
        return random.uniform(min_sec, max_sec)
    
    def find_window(self):
        target_title = self.config["window_title"]
        
        def enum_callback(hwnd, hwnd_list):
            if target_title.lower() in win32gui.GetWindowText(hwnd).lower():
                hwnd_list.append(hwnd)
            return True
        
        hwnd_list = []
        win32gui.EnumWindows(enum_callback, hwnd_list)
        
        if hwnd_list:
            self.hwnd = hwnd_list[0]
            return True
        return False
    
    def bring_window_to_front(self):
        if self.hwnd:
            try:
                # AttachThreadInput trick — lets SetForegroundWindow work
                # even when another window in our process has focus
                foreground_hwnd = win32gui.GetForegroundWindow()
                fg_tid = ctypes.windll.user32.GetWindowThreadProcessId(
                    foreground_hwnd, None)
                cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
                attached = False
                if fg_tid != cur_tid:
                    ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, True)
                    attached = True
                win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(self.hwnd)
                if attached:
                    ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, False)
            except Exception:
                try:
                    win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(self.hwnd)
                except Exception:
                    pass
            time.sleep(0.2)
    
    def move_camera(self):
        # rotate only on every other no-ore cycle to avoid jittery constant movement
        self.no_ore_counter += 1
        if self.no_ore_counter % 2 != 0:
            time.sleep(random.uniform(0.25, 0.45))
            return

        if random.random() < 0.35:
            self._mouse_rotate()
        else:
            self._keyboard_rotate()

        if self.no_ore_counter >= self.max_no_ore_moves:
            self.no_ore_counter = 0
            time.sleep(random.uniform(0.7, 1.1))
    
    def _force_rotate(self):
        """Force camera rotation immediately without the odd/even check"""
        if random.random() < 0.35:
            self._mouse_rotate()
        else:
            self._keyboard_rotate()
        time.sleep(random.uniform(0.3, 0.8))

    def _keyboard_rotate(self):
        actions = [
            (win32con.VK_LEFT, 0),
            (win32con.VK_RIGHT, 0),
            (win32con.VK_UP, 0),
            (win32con.VK_DOWN, 0)
        ]
        sequence_length = random.randint(1, 3)
        for _ in range(sequence_length):
            key, _ = random.choice(actions)
            press_duration = random.uniform(0.18, 0.4)
            win32api.keybd_event(key, 0, 0, 0)
            time.sleep(press_duration)
            win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(random.uniform(0.1, 0.25))

    def _mouse_rotate(self):
        # hold middle button and drag slightly for more natural camera rotation
        start_x, start_y = win32api.GetCursorPos()
        target_x = start_x + random.randint(-120, 120)
        target_y = start_y + random.randint(-30, 30)

        win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
        time.sleep(random.uniform(0.04, 0.08))
        steps = random.randint(8, 16)
        for i in range(1, steps + 1):
            t = i / steps
            x = int(start_x + (target_x - start_x) * t)
            y = int(start_y + (target_y - start_y) * t)
            win32api.SetCursorPos((x, y))
            time.sleep(random.uniform(0.01, 0.03))
        time.sleep(random.uniform(0.05, 0.12))
        win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
        time.sleep(random.uniform(0.15, 0.25))

    def _read_inventory_from_frame(self, frame):
        """Read inventory count (X/30) from top-right corner of RSC window.
        Based on RSC UI: the "3/30" text sits at the very top-right corner,
        roughly X:88-100%, Y:0-6% of the game window.
        """
        if not _HAVE_OCR:
            return None
        import re
        h, w = frame.shape[:2]

        # RSC inventory counter: top-right corner (e.g. "3/30")
        x1 = int(w * 0.90)
        y1 = 0
        x2 = w
        y2 = int(h * 0.10)
        roi = frame[y1:y2, x1:x2]

        if roi.size == 0:
            return None

        try:
            global _ocr_reader
            if _ocr_reader is None:
                _ocr_reader = easyocr.Reader(['en'], gpu=False)

            # Try raw ROI first
            results = _ocr_reader.readtext(roi, detail=0, allowlist='0123456789/')
            detected_text = " ".join(results).strip() if results else ""

            # Fallback: grayscale threshold (white text on brown bg)
            if not detected_text or not re.search(r'\d', detected_text):
                import cv2
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
                results = _ocr_reader.readtext(thresh, detail=0, allowlist='0123456789/')
                detected_text = " ".join(results).strip() if results else ""

            if detected_text:
                m = re.search(r'(\d+)\s*/\s*(\d+)', detected_text)
                if m:
                    cur = int(m.group(1))
                    total = int(m.group(2))
                    if 0 <= cur <= 31 and 25 <= total <= 31:
                        return cur, total
                # Fallback: "7130" → parse as "7" and "30" (OCR often drops "/")
                m2 = re.search(r'(\d{1,2})1?(\d{2})', detected_text)
                if m2:
                    cur = int(m2.group(1))
                    total = int(m2.group(2))
                    if 0 <= cur <= 31 and 25 <= total <= 31:
                        return cur, total
        except Exception:
            pass
        return None

    def _extract_ore_name(self, text):
        """Extract ore name from 'You manage to obtain [ore_name]' message"""
        text_lower = text.lower().strip()
        
        # List of ore types to check
        ore_types = ["tin", "copper", "coal", "iron", "mithril", "adamantite"]
        
        # Try to find ore name in the text
        for ore in ore_types:
            if ore in text_lower:
                return ore
        
        return None
    
    def _wait_for_obtain_message(self, window_region, timeout=8.0):
        """Poll for 'You manage to obtain' message using basic EasyOCR (no preprocessing)"""
        start = time.time()
        while time.time() - start < timeout and self.running:
            screenshot = self.sct.grab(window_region)
            frame = np.array(screenshot)[:, :, :3]
            h, w = frame.shape[:2]
            
            # RSC chat/message area: bottom portion of screen (Y:72-92%)
            # This is the 1-inch text box above the tab bar
            roi = frame[int(h * 0.72):int(h * 0.92), 0:int(w * 0.95)]
            
            try:
                if _HAVE_OCR:
                    global _ocr_reader
                    if _ocr_reader is None:
                        _ocr_reader = easyocr.Reader(['en'], gpu=False)
                    
                    # Quick OCR without preprocessing
                    results = _ocr_reader.readtext(roi, detail=0)
                    detected_text = " ".join(results).lower() if results else ""
                    
                    if detected_text and ("manage to obtain" in detected_text or "managed to obtain" in detected_text):
                        ore_name = self._extract_ore_name(detected_text)
                        print(f"[OCR] Ore obtained: {ore_name if ore_name else 'unknown'}")
                        try:
                            self.gui.log_debug(f'✓ {ore_name.upper() if ore_name else "Ore"} obtained')
                        except:
                            pass
                        return True, ore_name
            
            except Exception as e:
                print(f"[OCR Error] {e}")
            
            time.sleep(0.2)
        
        return False, None
    
    def check_fatigue_message(self, frame, window_region):
        """
        Check if OCR detects fatigue message using EasyOCR.
        Checks for: "You are too tired to mine this rock" + other fatigue messages
        """
        if not _HAVE_OCR:
            return False
        
        if not self.config.get("fatigue_detection_enabled", True):
            return False
        
        try:
            global _ocr_reader
            
            # Lazy initialize OCR reader (on first use)
            if _ocr_reader is None:
                _ocr_reader = easyocr.Reader(['en'], gpu=False)
            
            h, w = frame.shape[:2]
            
            # Define fatigue keywords to check
            fatigue_keywords = [
                "too tired to mine",
                "you are too tired",
                "tired to mine",
                "feel tired",
                "should get some rest",
                "tired"
            ]
            
            # Check multiple ROI regions where messages might appear
            roi_regions = [
                ("top-center", frame[int(h * 0.15):int(h * 0.50), int(w * 0.15):int(w * 0.85)]),
                ("middle-center", frame[int(h * 0.25):int(h * 0.60), int(w * 0.2):int(w * 0.8)]),
                ("lower-center", frame[int(h * 0.60):int(h * 0.95), int(w * 0.05):int(w * 0.95)]),
            ]
            
            for roi_name, roi in roi_regions:
                if roi.size == 0:
                    continue
                
                try:
                    # Use EasyOCR directly on the ROI
                    results = _ocr_reader.readtext(roi)
                    
                    if results:
                        # Combine all detected text
                        detected_text = " ".join([text[1] for text in results]).lower()
                        
                        if detected_text.strip():
                            # Check for fatigue keywords
                            for keyword in fatigue_keywords:
                                if keyword.lower() in detected_text:
                                    print(f"[FATIGUE] {roi_name} - Detected: '{detected_text}'")
                                    try:
                                        self.gui.log_debug(f'🚨 FATIGUE DETECTED: {keyword} | Full text: {detected_text}')
                                    except Exception:
                                        pass
                                    return True
                
                except Exception as e:
                    print(f"[FATIGUE OCR] Error processing {roi_name}: {e}")
                    continue
        
        except Exception as e:
            print(f"[FATIGUE OCR] Critical error: {e}")
        
        return False
    
    
    def check_fatigue_bar_topleft(self, frame):
        """
        Alternative fatigue detection: Check the fatigue bar on top-left of game window.
        The fatigue indicator is usually in the top-left stats area.
        Returns True if fatigue bar appears to be at 100% (red/full).
        """
        try:
            h, w = frame.shape[:2]
            
            # Top-left corner where stats/fatigue bar typically is (roughly first 15% width, first 20% height)
            roi_topleft = frame[0:int(h * 0.25), 0:int(w * 0.20)]
            
            if roi_topleft.size == 0:
                return False
            
            # Look for red color (fatigue bar is typically red at high fatigue)
            # Red in BGR is (B, G, R) = (0-50, 0-100, 200-255)
            b, g, r = cv2.split(roi_topleft)
            
            # Create mask for red pixels (high fatigue indicator)
            red_mask = (r > 180) & (g < 120) & (b < 120)
            
            # If more than 5% of top-left area is red, fatigue is likely high
            red_percentage = np.count_nonzero(red_mask) / roi_topleft.size * 100
            
            if red_percentage > 5:
                print(f"[FATIGUE BAR] Detected high fatigue bar (red: {red_percentage:.1f}%)")
                try:
                    self.gui.log_debug(f'⚠️ FATIGUE BAR: High fatigue detected ({red_percentage:.1f}% red)')
                except Exception:
                    pass
                return True
            
        except Exception as e:
            print(f"[FATIGUE BAR] Error checking fatigue bar: {e}")
        
        return False

    def _fatigue_line_variants(self, fat_line):
        """Yield image variants for OCR: raw, green-threshold, red-threshold."""
        yield fat_line
        for ch_idx in (1, 2):  # green, then red (BGR)
            ch = fat_line[:, :, ch_idx]
            ch_up = cv2.resize(ch, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            _, binary = cv2.threshold(ch_up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            yield binary

    def read_menu_bar_fatigue(self, frame):
        """
        Read Hits/Prayer/Fatigue/FPS from top-left green text in RSC.
        RSC renders stats green normally but turns RED at high fatigue.
        Strategy: raw ROI OCR, then green/red channel fallback, then digit+% crop.
        """
        if not _HAVE_OCR or not self.config.get("fatigue_detection_enabled", True):
            return None

        try:
            global _ocr_reader
            if _ocr_reader is None:
                _ocr_reader = easyocr.Reader(['en'], gpu=False)

            h, w = frame.shape[:2]

            # RSC stats area: top-left — Hits, Prayer, Fatigue, FPS
            y1_roi = 0
            y2_roi = int(h * 0.28)
            x1_roi = 0
            x2_roi = int(w * 0.22)
            roi = frame[y1_roi:y2_roi, x1_roi:x2_roi]

            if roi.size == 0:
                return None

            import re

            # Method 1: Raw ROI OCR — allow letters + digits + %
            results = _ocr_reader.readtext(roi, detail=0)
            detected_text = " ".join(results).lower() if results else ""

            # Method 2: Channel-based fallback (green for normal, red for high fatigue)
            # RSC renders stats green normally but turns RED at high fatigue
            if not detected_text or 'fatigu' not in detected_text:
                for ch_idx in (1, 2):  # 1=green channel, 2=red channel (BGR)
                    ch = roi[:, :, ch_idx]
                    ch_up = cv2.resize(ch, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
                    _, binary = cv2.threshold(ch_up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    results2 = _ocr_reader.readtext(binary, detail=0)
                    text2 = " ".join(results2).lower() if results2 else ""
                    if 'fatigu' in text2:
                        detected_text = text2
                        break

            if not detected_text:
                return None

            # ── Parse fatigue from detected_text ──
            # Try explicit "fatigue XX%" first (best quality match)
            fat_pct = re.search(r'fatigu\w*\s*[:\.\-]?\s*(\d{1,3})\s*%', detected_text)
            if fat_pct:
                val = int(fat_pct.group(1))
                if 0 <= val <= 100:
                    self.current_fatigue = val
                    return val

            # Try "fatigue XX" without % — but watch for %-glyph artifacts
            fat_match = re.search(r'fatigu\w*\s*[:\.\-]?\s*(\d+)', detected_text)
            if fat_match:
                num_str = fat_match.group(1)
                val = int(num_str)
                if 0 <= val <= 100:
                    # Detect %-glyph misread as trailing '9': "69"="6%", "29"="2%"
                    if len(num_str) == 2 and num_str.endswith('9') and val > 9:
                        stripped = int(num_str[0])
                        self.current_fatigue = stripped
                        return stripped
                    self.current_fatigue = val
                    return val
                # Truncate: try first 2 digits, then first 1
                if len(num_str) >= 3:
                    val2 = int(num_str[:2])
                    if 0 <= val2 <= 100:
                        self.current_fatigue = val2
                        return val2
                if len(num_str) >= 2:
                    val1 = int(num_str[0])
                    self.current_fatigue = val1
                    return val1

            # Method 3: targeted digit+% crop as last resort
            if 'fatigu' in detected_text:
                fat_roi_y1 = int(roi.shape[0] * 0.45)
                fat_roi_y2 = int(roi.shape[0] * 0.80)
                fat_line = roi[fat_roi_y1:fat_roi_y2, :]
                if fat_line.size > 0:
                    for src in self._fatigue_line_variants(fat_line):
                        fat_results = _ocr_reader.readtext(src, detail=0, allowlist='0123456789%')
                        fat_digit_text = " ".join(fat_results).strip() if fat_results else ""
                        if re.search(r'\d', fat_digit_text):
                            break
                    pct_m = re.search(r'(\d{1,3})\s*%', fat_digit_text)
                    if pct_m:
                        pval = int(pct_m.group(1))
                        if 0 <= pval <= 100:
                            self.current_fatigue = pval
                            return pval

        except Exception:
            pass

        return None
    
    def should_take_break(self):
        if not self.config["break_settings"].get("breaks_enabled", True):
            return False
        return time.time() - self.last_break_time >= self.next_break_interval
    
    def take_break(self):
        print(f"Taking break...")
        time.sleep(self.get_random_break_duration())
        self.last_break_time = time.time()
        self.next_break_interval = self.get_random_break_interval()
    
    def get_micro_break(self):
        """Get a random micro break duration if enabled"""
        if self.config["break_settings"].get("micro_breaks_enabled", True):
            min_ms = self.config["break_settings"].get("micro_break_min_ms", 100)
            max_ms = self.config["break_settings"].get("micro_break_max_ms", 500)
            return random.randint(min_ms, max_ms) / 1000.0
        return 0
    
    def update_ore_display(self):
        """Update GUI with current ore counts"""
        try:
            # Create a summary of ore counts
            ore_summary = " | ".join([f"{ore.upper()}: {count}" for ore, count in self.ore_counts.items() if count > 0])
            
            if ore_summary:
                self.gui.root.after(0, lambda text=ore_summary: self.gui.log_debug(f"Ore counts: {text}"))
            else:
                self.gui.root.after(0, lambda: self.gui.log_debug("Ore tracking active..."))
        except Exception as e:
            print(f"[ORE DISPLAY] Error updating display: {e}")
    
    def print_ore_statistics(self):
        """Print final ore statistics when bot stops"""
        total_ore = sum(self.ore_counts.values())
        if total_ore > 0:
            print("\n" + "="*60)
            print("ORE MINING STATISTICS")
            print("="*60)
            for ore, count in sorted(self.ore_counts.items(), key=lambda x: x[1], reverse=True):
                if count > 0:
                    print(f"  {ore.upper():12} : {count:3} ore(s)")
            print("-"*60)
            print(f"  {'TOTAL':12} : {total_ore:3} ore(s)")
            print("="*60 + "\n")
            try:
                self.gui.log_debug(f'Final Ore Counts: {dict((k, v) for k, v in self.ore_counts.items() if v > 0)}')
            except Exception:
                pass
        else:
            print("\nNo ores detected during mining session.")
    
    def run(self):
        if not self.find_window():
            raise Exception(f"Window '{self.config['window_title']}' not found")
        
        self.bring_window_to_front()
        self.running = True
        self.last_break_time = time.time()
        print("Bot started!")
        try:
            self.gui.log_debug('Bot started')
        except Exception:
            pass

        try:
            # reset GUI counters on start
            self.gui.root.after(0, self.gui.reset_obtain_count)
            self.gui.root.after(0, lambda: self.gui.update_inventory(0, 30))
        except Exception:
            pass

        # instantiate mss in the bot thread to avoid cross-thread issues
        from mss import mss as _mss
        self.sct = _mss()

        frame_time = 0.200  # 200ms per frame = 5 FPS
        last_frame_time = time.time()
        
        while self.running:
            # Enforce 640ms frame rate
            elapsed = time.time() - last_frame_time
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
            last_frame_time = time.time()
            
            try:
                if self.should_take_break():
                    self.take_break()
                    self.bring_window_to_front()
                
                rect = win32gui.GetClientRect(self.hwnd)
                pt = win32gui.ClientToScreen(self.hwnd, (0, 0))
                window_region = {
                    "left": pt[0],
                    "top": pt[1],
                    "width": rect[2] - rect[0],
                    "height": rect[3] - rect[1]
                }
                
                # Capture screen
                screenshot = self.sct.grab(window_region)
                frame = np.array(screenshot)
                frame = frame[:, :, :3]  # Remove alpha
                frame = np.ascontiguousarray(frame)
                
                # Detect ores
                detections, annotated_frame = self.detector.detect_with_vis(frame, window_region)
                
                # Update overlay in main thread (only every 500ms to avoid lag after clicks)
                current_time = time.time()
                if annotated_frame is not None and (current_time - self.last_overlay_update) >= self.overlay_update_interval:
                    self.last_overlay_update = current_time
                    self._overlay_buf.update_frame(
                        annotated_frame,
                        region=(window_region["left"], window_region["top"],
                                window_region["width"], window_region["height"]),
                        detections=detections
                    )
                
                # Filter mineable ores
                mineable = []
                for det in detections:
                    ore_name = det["class_name"]
                    if ore_name == "empty_ore_rock":
                        continue
                    
                    if self.config["ore_checkboxes"].get(ore_name, False):
                        mineable.append(det)
                
                try:
                    self.gui.root.after(0, lambda count=len(mineable): self.gui.update_ore_count(count))
                except Exception:
                    pass
                
                if mineable:
                    self.no_ore_counter = 0
                    self.consecutive_no_ore_count = 0  # Reset antiban counter when ores found
                    
                    # PRIMARY: Sort by distance from center (closest ore to character)
                    # SECONDARY: Sort by priority order (if configured)
                    priority_order = self.config["priority_order"]
                    frame_h, frame_w = frame.shape[:2]
                    
                    # Sort: closest to center first, then by priority order if same distance
                    mineable.sort(key=lambda x: (
                        self.get_distance_from_center(x["box"], frame_w, frame_h),  # Primary: closest to center
                        priority_order.index(x["class_name"]) if x["class_name"] in priority_order else 999  # Secondary: priority
                    ))
                    
                    target = mineable[0]
                    target_distance = self.get_distance_from_center(target["box"], frame_w, frame_h)
                    
                    print(f"Mining: {target['class_name']} (distance: {target_distance:.1f}px from center)")
                    try:
                        self.gui.log_debug(f"Mining: {target['class_name']} (distance: {target_distance:.1f}px from center)")
                    except Exception:
                        pass
                    # compute a coarse key for this target to detect repeated clicks
                    bx1, by1, bx2, by2 = target["box"]
                    center = (int((bx1+bx2)/2), int((by1+by2)/2))
                    key = (center[0]//10, center[1]//10)
                    # purge expired blacklist entries
                    now = time.time()
                    for bk in list(self._blacklist.keys()):
                        if self._blacklist[bk] <= now:
                            del self._blacklist[bk]
                    if key in self._blacklist:
                        try:
                            self.gui.log_debug('Ore blacklisted, rotating camera for new target')
                        except Exception:
                            pass
                        # Force aggressive rotation when blacklisted
                        self._force_rotate()
                        time.sleep(self.config["detection_settings"]["no_ore_retry_delay_ms"] / 1000.0)
                        continue
                    # increment attempt count
                    self._click_attempts[key] = self._click_attempts.get(key, 0)
                    if self._click_attempts[key] >= 3:
                        # blacklist for a short while
                        self._blacklist[key] = now + 30.0
                        try:
                            self.gui.log_debug('Ore stuck (3 clicks), blacklisting 30s & rotating')
                        except Exception:
                            pass
                        # Force rotation when blacklisting
                        self._force_rotate()
                        time.sleep(self.config["detection_settings"]["no_ore_retry_delay_ms"] / 1000.0)
                        continue
                    
                    # get click position (frame-local) and convert to screen coords
                    click_pos = self.get_click_position(target["box"])
                    click_pos = (int(click_pos[0] + window_region["left"]), int(click_pos[1] + window_region["top"]))
                    
                    # Ensure window is focused before clicking
                    self.bring_window_to_front()
                    time.sleep(0.1)
                    
                    # Track mouse position
                    self.mouse_x = click_pos[0]
                    self.mouse_y = click_pos[1]
                    
                    self.mouse.move_and_click(click_pos)
                    
                    # Record the time of this click (in milliseconds since epoch)
                    self.last_click_time = int(time.time() * 1000)

                    # Antiban: move mouse outside the game window after clicking
                    if self.config.get('mouse_outside_window', False):
                        try:
                            left = window_region['left']
                            top = window_region['top']
                            w = window_region['width']
                            h = window_region['height']
                            # Pick a random edge (0=left, 1=right, 2=top, 3=bottom)
                            edge = random.randint(0, 3)
                            offset = random.randint(5, 40)
                            if edge == 0:
                                ox, oy = left - offset, random.randint(top, top + h)
                            elif edge == 1:
                                ox, oy = left + w + offset, random.randint(top, top + h)
                            elif edge == 2:
                                ox, oy = random.randint(left, left + w), top - offset
                            else:
                                ox, oy = random.randint(left, left + w), top + h + offset
                            self.mouse.move_mouse(ox, oy)
                            # Brief pause outside, then return mouse into the game window
                            time.sleep(random.uniform(0.3, 1.0))
                            # Move back to a random spot inside the game window
                            rx = random.randint(left + int(w * 0.15), left + int(w * 0.85))
                            ry = random.randint(top + int(h * 0.15), top + int(h * 0.85))
                            self.mouse.move_mouse(rx, ry)
                        except Exception:
                            pass

                    # record attempt
                    self._click_attempts[key] = self._click_attempts.get(key, 0) + 1

                    self._mine_count += 1

                    # In fast mode, skip the expensive obtain-message OCR wait entirely.
                    # In lazy mode, keep a short wait so we can track ore types.
                    got = False
                    ore_name = None
                    if not self.fast_mining_enabled:
                        msg_timeout = 3.0
                        try:
                            got, ore_name = self._wait_for_obtain_message(window_region, timeout=msg_timeout)
                        except Exception:
                            got = False
                            ore_name = None

                    if got:
                        try:
                            self.gui.root.after(0, self.gui.increment_obtain_count)
                        except Exception:
                            pass
                        if ore_name and ore_name in self.ore_counts:
                            self.ore_counts[ore_name] += 1
                            print(f"[ORE TRACKER] {ore_name.upper()}: {self.ore_counts[ore_name]}")
                            try:
                                self.gui.root.after(0, self.update_ore_display)
                            except Exception:
                                pass

                    # Post-click delay
                    if self.fast_mining_enabled:
                        post_delay = random.uniform(0.10, 1.2)
                    else:
                        post_delay = random.uniform(0.50, 2.9)
                    micro_break = self.get_micro_break()
                    post_delay += micro_break
                    time.sleep(post_delay)

                    # --- Inventory + fatigue OCR every 3rd click (saves ~5s/cycle) ---
                    should_stop = False
                    if self._mine_count % 3 == 0:
                        try:
                            screenshot = self.sct.grab(window_region)
                            frame_check = np.array(screenshot)[:, :, :3]
                            inv = self._read_inventory_from_frame(frame_check)

                            if inv is not None:
                                cur, total = inv
                                try:
                                    self.gui.root.after(0, lambda c=cur, t=total: self.gui.update_inventory(c, t))
                                except Exception:
                                    pass
                                self.inventory_count = cur

                                # Stop when full (respects both config flags)
                                if self.config.get('stop_on_full_inventory', True) and not self.config.get('powermine_enabled', False):
                                    if total >= 30 and cur >= total:
                                        print(f"[INVENTORY] Full inventory detected ({cur}/{total})! Stopping.")
                                        try:
                                            self.gui.log_debug(f'Inventory full ({cur}/{total}) — stopping')
                                        except Exception:
                                            pass
                                        try:
                                            winsound.Beep(1200, 300)
                                            winsound.Beep(1200, 300)
                                            winsound.Beep(1500, 500)
                                        except Exception:
                                            pass
                                        self.running = False
                                        self.gui.root.after(0, self.gui.stop_bot)
                                        should_stop = True
                            else:
                                # OCR failed – increment counter optimistically
                                self.inventory_count += 1
                                try:
                                    self.gui.root.after(0, lambda c=self.inventory_count: self.gui.update_inventory(c, 30))
                                except Exception:
                                    pass
                                if self.config.get('stop_on_full_inventory', True) and not self.config.get('powermine_enabled', False):
                                    if self.inventory_count >= self._inv_fallback_limit:
                                        try:
                                            self.gui.log_debug(f'Inventory full ({self.inventory_count}/30) — stopping')
                                        except Exception:
                                            pass
                                        try:
                                            winsound.Beep(1200, 300)
                                            winsound.Beep(1200, 300)
                                            winsound.Beep(1500, 500)
                                        except Exception:
                                            pass
                                        self.running = False
                                        self.gui.root.after(0, self.gui.stop_bot)
                                        should_stop = True

                            # Read fatigue while we already have a fresh frame
                            self.read_menu_bar_fatigue(frame_check)
                            # Also check for "too tired" chat message
                            if self.check_fatigue_message(frame_check, window_region):
                                print("[FATIGUE] 'Too tired' message detected! Stopping.")
                                try:
                                    winsound.Beep(1000, 200)
                                    winsound.Beep(1000, 200)
                                except Exception:
                                    pass
                                self.running = False
                                self.gui.root.after(0, self.gui.stop_bot)
                                should_stop = True
                        except Exception:
                            pass
                    else:
                        # Lightweight: just bump the counter every click
                        self.inventory_count += 1
                        if self.config.get('stop_on_full_inventory', True) and not self.config.get('powermine_enabled', False):
                            if self.inventory_count >= self._inv_fallback_limit:
                                try:
                                    self.gui.log_debug(f'Inventory full ({self.inventory_count}/30) — stopping')
                                except Exception:
                                    pass
                                try:
                                    winsound.Beep(1200, 300)
                                    winsound.Beep(1200, 300)
                                    winsound.Beep(1500, 500)
                                except Exception:
                                    pass
                                self.running = False
                                self.gui.root.after(0, self.gui.stop_bot)
                                should_stop = True

                    if should_stop:
                        break

                    # Fatigue threshold stop (uses value from read_menu_bar_fatigue)
                    if self.config.get('fatigue_detection_enabled', True) and self.current_fatigue >= 96:
                        print(f"[FATIGUE] Fatigue at {self.current_fatigue}%! Stopping bot.")
                        try:
                            winsound.Beep(1000, 200)
                            winsound.Beep(1000, 200)
                        except Exception:
                            pass
                        self.running = False
                        self.gui.root.after(0, self.gui.stop_bot)
                        break
                else:
                    print("No ores found, moving camera...")
                    try:
                        self.gui.log_debug('No ores found, rotating camera')
                    except Exception:
                        pass
                    
                    # Antiban failsafe: if no ores found 30+ times, stop bot
                    self.consecutive_no_ore_count += 1
                    if self.config.get("antiban_failsafe_enabled", True) and self.consecutive_no_ore_count >= 30:
                        print("Antiban failsafe triggered! No ores found 30+ times, stopping bot.")
                        try:
                            self.gui.log_debug('ANTIBAN FAILSAFE: Stopping after 30+ empty rotations')
                        except Exception:
                            pass
                        try:
                            winsound.Beep(1500, 300)
                            winsound.Beep(1500, 300)
                        except Exception:
                            pass
                        self.running = False
                        self.gui.root.after(0, self.gui.stop_bot)
                        break
                    
                    self.move_camera()
                    time.sleep(self.config["detection_settings"]["no_ore_retry_delay_ms"] / 1000.0)
                
                time.sleep(self.config["detection_settings"]["update_interval_ms"] / 1000.0)
                
            except Exception as e:
                print(f"Error in bot loop: {e}")
                time.sleep(1)
        
        # Print ore statistics before stopping
        self.print_ore_statistics()
        
        try:
            self.gui.log_debug('Bot stopped')
        except Exception:
            pass
        print("Bot stopped!")
    
    def stop(self):
        self.running = False