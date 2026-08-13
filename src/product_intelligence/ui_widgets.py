import sys
from pathlib import Path
from tkinter import ttk
from PIL import Image,ImageSequence,ImageTk
from .ui_status import StatusCard

def desktop_asset_path(name,*,frozen_root=None):
    root=frozen_root or getattr(sys,'_MEIPASS',None)
    return Path(root)/'product_intelligence'/'assets'/name if root else Path(__file__).resolve().parent/'assets'/name

class AnimatedStateGif(ttk.Label):
    def __init__(self,parent):
        super().__init__(parent,anchor='center'); self.frames=[]; self.i=0; self.job=None; self.state=None
    def set_state(self,state):
        self.state=state; self.frames=[]
        name='process_complete.gif' if state=='complete' else 'process_running.gif' if state=='running' else None
        if name:
            try:
                with Image.open(desktop_asset_path(name)) as im:
                    for frame in ImageSequence.Iterator(im):
                        x=frame.convert('RGBA'); x.thumbnail((185,96)); self.frames.append(ImageTk.PhotoImage(x.copy()))
            except Exception: pass
        self.i=0
        if self.frames:self._tick()
        else:self.configure(image='',text={'running':'Procesando…','complete':'✓ Completado','error':'! Error'}.get(state,'Listo'))
    def _tick(self):
        if not self.frames:return
        f=self.frames[self.i%len(self.frames)]; self.i+=1; self.configure(image=f,text=''); self.image=f; self.job=self.after(90,self._tick)

class ProcessStatusCard(StatusCard):
    pass
