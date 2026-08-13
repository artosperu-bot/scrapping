import tkinter as tk
from tkinter import ttk

class StatusCard(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent,padding=8)
        self.text=tk.StringVar(value="Listo")
        ttk.Label(self,textvariable=self.text).pack(anchor="w")
        self.bar=ttk.Progressbar(self,maximum=100)
        self.bar.pack(fill="x",pady=(5,0))
