import win32api
import win32con
import time
import random
import math

class HumanMouse:
    def __init__(self, settings):
        self.settings = settings
        self.min_delay = settings["min_delay_ms"] / 1000.0
        self.max_delay = settings["max_delay_ms"] / 1000.0
        self.curve_strength = settings["human_curve_strength"]
    
    def move_mouse(self, target_x, target_y):
        """
        Move mouse with realistic human behavior:
        - Overshoots target then corrects
        - Small jerky movements
        - Non-linear acceleration
        - Random pauses and hesitations
        """
        current_x, current_y = win32api.GetCursorPos()
        
        # Calculate distance
        dx = target_x - current_x
        dy = target_y - current_y
        distance = math.sqrt(dx**2 + dy**2)
        
        if distance < 1:
            return
        
        # Phase 1: Move with overshoot
        overshoot_factor = random.uniform(1.05, 1.25)  # Overshoot by 5-25%
        overshoot_x = target_x + (dx * (overshoot_factor - 1))
        overshoot_y = target_y + (dy * (overshoot_factor - 1))
        
        # Movement to overshoot point with jerky motion
        steps = max(int(distance / 10), 5)
        
        for i in range(steps):
            t = i / max(steps - 1, 1)
            
            # Non-linear acceleration (ease-in-out)
            t_eased = self._ease_in_out_cubic(t)
            
            # Add small random jitter for jerky feel
            if random.random() < 0.3:  # 30% chance of small pause/jitter
                time.sleep(random.uniform(0.01, 0.03))
            
            # Calculate position with some noise
            noise_x = random.uniform(-2, 2) if random.random() < 0.4 else 0
            noise_y = random.uniform(-2, 2) if random.random() < 0.4 else 0
            
            x = current_x + dx * t_eased + noise_x
            y = current_y + dy * t_eased + noise_y
            
            win32api.SetCursorPos((int(x), int(y)))
            
            # Variable step delay (slower start, faster middle, slower end)
            if t < 0.2:
                delay = random.uniform(0.001, 0.005)
            elif t > 0.8:
                delay = random.uniform(0.002, 0.006)
            else:
                delay = random.uniform(0.0005, 0.003)
            
            time.sleep(delay)
        
        # Phase 2: Overshoot and wait a moment
        win32api.SetCursorPos((int(overshoot_x), int(overshoot_y)))
        time.sleep(random.uniform(0.05, 0.15))
        
        # Phase 3: Correct back to target with smaller, deliberate movements
        correction_steps = random.randint(3, 8)
        for i in range(correction_steps):
            t = i / max(correction_steps - 1, 1)
            
            # Faster, more deliberate correction
            x = overshoot_x + (target_x - overshoot_x) * t
            y = overshoot_y + (target_y - overshoot_y) * t
            
            win32api.SetCursorPos((int(x), int(y)))
            time.sleep(random.uniform(0.003, 0.008))
        
        # Final position
        win32api.SetCursorPos((int(target_x), int(target_y)))
        
        # Small pause after reaching target (human hesitation before clicking)
        time.sleep(random.uniform(0.05, 0.12))
    
    @staticmethod
    def _ease_in_out_cubic(t):
        """Smooth easing function for more natural acceleration"""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2
    
    def click(self):
        """Human-like click with realistic timing"""
        # Small random jitter before click (aiming)
        current_x, current_y = win32api.GetCursorPos()
        jitter_x = current_x + random.randint(-1, 1)
        jitter_y = current_y + random.randint(-1, 1)
        win32api.SetCursorPos((jitter_x, jitter_y))
        
        # Slight pause before pressing
        time.sleep(random.uniform(0.02, 0.06))
        
        # Mouse down (variable press time)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        press_duration = random.uniform(0.06, 0.12)
        time.sleep(press_duration)
        
        # Mouse up
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    
    def move_and_click(self, target_pos):
        """Move to target and click with human-like behavior and post-click wait"""
        # Minimal jitter to keep within hitbox
        jitter_x = random.randint(-2, 2)
        jitter_y = random.randint(-2, 2)
        target_x = target_pos[0] + jitter_x
        target_y = target_pos[1] + jitter_y
        
        # Move with realistic human overshoot/correction
        self.move_mouse(target_x, target_y)
        
        # Click
        self.click()
        
        # Post-click wait (very important for game responsiveness)
        post_click_delay = random.uniform(0.15, 0.35)
        time.sleep(post_click_delay)