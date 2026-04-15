import tkinter as tk
from tkinter import ttk

class DragDropList(ttk.Frame):
    def __init__(self, parent, items=None):
        super().__init__(parent)
        
        self.items = items if items else []
        self.drag_start_index = None
        
        self.listbox = tk.Listbox(self, height=8, selectmode=tk.SINGLE, 
                                   activestyle='none', font=('Arial', 10))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
        
        self.refresh_listbox()
        
        # Bind drag-drop events
        self.listbox.bind('<Button-1>', self.on_drag_start)
        self.listbox.bind('<B1-Motion>', self.on_drag_motion)
        self.listbox.bind('<ButtonRelease-1>', self.on_drag_release)
    
    def refresh_listbox(self):
        self.listbox.delete(0, tk.END)
        for item in self.items:
            display_name = item.replace("_", " ").title()
            self.listbox.insert(tk.END, display_name)
    
    def on_drag_start(self, event):
        self.drag_start_index = self.listbox.nearest(event.y)
    
    def on_drag_motion(self, event):
        if self.drag_start_index is None:
            return
        
        current_index = self.listbox.nearest(event.y)
        if current_index != self.drag_start_index and 0 <= current_index < len(self.items):
            # Swap items
            self.items[self.drag_start_index], self.items[current_index] = \
                self.items[current_index], self.items[self.drag_start_index]
            self.drag_start_index = current_index
            self.refresh_listbox()
            self.listbox.selection_set(current_index)
    
    def on_drag_release(self, event):
        self.drag_start_index = None
    
    def get_items(self):
        return self.items
    
    def set_items(self, items):
        self.items = items
        self.refresh_listbox()