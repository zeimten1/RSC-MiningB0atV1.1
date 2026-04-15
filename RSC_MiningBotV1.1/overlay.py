import tkinter as tk
import threading
import time

class Overlay:
    def __init__(self):
        self.root = None
        self.canvas = None
        self.running = False
        self.break_label = None
        self.detection_items = []
        
    def _create_window(self):
        """Create overlay window in main thread"""
        self.root = tk.Tk()
        self.root.title("RSC Mining Bot Overlay")
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.7)  # Semi-transparent
        self.root.overrideredirect(True)  # No window borders
        
        # Make background black
        self.root.configure(bg='black')
        
        # Create canvas for drawing
        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind escape key to close
        self.root.bind('<Escape>', lambda e: self.hide())
        
        self.running = True
        self.root.mainloop()
    
    def start(self):
        """Start overlay in main thread (call from GUI)"""
        if self.root is None:
            threading.Thread(target=self._create_window, daemon=True).start()
            time.sleep(0.5)
    
    def update(self, detections, window_region, show_empty=False):
        """Update overlay with detections"""
        if self.root is None or self.canvas is None:
            return
        
        # Schedule update in main thread
        self.root.after(0, self._update_gui, detections, window_region, show_empty)
    
    def _update_gui(self, detections, window_region, show_empty):
        """Actual GUI update (runs in main thread)"""
        if not self.running or self.root is None:
            return
        
        # Clear previous drawings
        self.canvas.delete("all")
        
        # Set window size and position to match game window
        self.root.geometry(f"{window_region['width']}x{window_region['height']}+{window_region['left']}+{window_region['top']}")
        
        # Draw detections
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["box"]]
            conf = det["confidence"]
            class_name = det["class_name"]
            
            # Skip empty ore if not enabled
            if class_name == "empty_ore_rock" and not show_empty:
                continue
            
            # Color based on ore type
            if "adamantite" in class_name:
                color = "red"
            elif "mithril" in class_name:
                color = "purple"
            elif "coal" in class_name:
                color = "gray"
            elif "iron" in class_name:
                color = "white"
            elif "tin" in class_name:
                color = "cyan"
            elif "copper" in class_name:
                color = "orange"
            elif "empty" in class_name:
                color = "yellow"
            else:
                color = "green"
            
            # Draw rectangle
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2)
            
            # Draw label
            label = f"{class_name.replace('_', ' ').title()} {conf:.2f}"
            self.canvas.create_text(x1, y1 - 10, text=label, fill=color, anchor='sw', font=('Arial', 10, 'bold'))
        
        # Show break message if needed
        if hasattr(self, 'break_showing') and self.break_showing:
            self.canvas.create_text(window_region['width']//2, 50, text="BREAK TIME - Bot Paused", 
                                   fill="red", font=('Arial', 20, 'bold'))
        
        self.root.update_idletasks()
    
    def show_break_message(self):
        self.break_showing = True
    
    def hide_break_message(self):
        self.break_showing = False
    
    def hide(self):
        """Close overlay"""
        self.running = False
        if self.root:
            self.root.after(0, self.root.destroy)
            self.root = None