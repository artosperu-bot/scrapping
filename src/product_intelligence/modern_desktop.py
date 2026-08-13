import queue,threading
import tkinter as tk
from tkinter import ttk
from .price_desktop import App as PriceApp
from .media_desktop import App as MediaBaseApp
from .ui_process import ProcessRegistry
from .ui_theme import configure_business_theme
from .ui_widgets import AnimatedStateGif

class App(PriceApp):
    def __init__(self):
        self.process_registry=ProcessRegistry(); self.process_log_tabs={}; self._media_session_id=None; self._price_session_id=None; self._excel_session_id=None; self._excel_worker_thread=None; self._process_events=queue.Queue(); self.price_state_gif=None; self.excel_state_gif=None
        super().__init__(); configure_business_theme(self); self.title('Product Intelligence'); self.geometry('1440x900'); self.after(120,self._drain_process_events)
    def _build_logs_tab(self):
        self.logs_tab=ttk.Frame(self.notebook,padding=10); self.notebook.add(self.logs_tab,text='6. Logs / auditoría')
        ttk.Label(self.logs_tab,text='Logs / Auditoría',font=('Segoe UI Semibold',11)).pack(anchor='w'); ttk.Label(self.logs_tab,text='Todos los procesos y cada ejecución por separado.').pack(anchor='w',pady=(1,6))
        self.log_notebook=ttk.Notebook(self.logs_tab); self.log_notebook.pack(fill='both',expand=True); self.log=self._add_log_tab('__all__','Todos')
        row=ttk.Frame(self.logs_tab); row.pack(fill='x',pady=(6,0)); ttk.Button(row,text='Limpiar Todos',command=lambda:self.log.delete('1.0','end')).pack(side='left'); ttk.Button(row,text='Abrir carpeta de salida',command=self.open_output_folder).pack(side='left',padx=8)
    def _add_log_tab(self,key,label):
        frame=ttk.Frame(self.log_notebook,padding=5); text=tk.Text(frame,wrap='word',font=('Consolas',9),relief='flat'); text.pack(fill='both',expand=True); self.log_notebook.add(frame,text=label); self.process_log_tabs[key]=text; return text
    def start_process_session(self,kind,label,total=1):
        s=self.process_registry.start(kind,label,total); self._add_log_tab(s.session_id,f'{kind} #{s.session_id.rsplit("-",1)[-1]}'); return s.session_id
    def emit(self,msg):
        self.q.put(str(msg))
    def _build_run_tab(self):
        super()._build_run_tab(); tab=self.runbtn.master.master; box=ttk.LabelFrame(tab,text='Estado del proceso',padding=8); box.pack(fill='x',pady=(8,0),before=self.runbtn.master)
        self.excel_state_gif=AnimatedStateGif(box); self.excel_state_gif.pack(side='right',padx=(12,0)); left=ttk.Frame(box); left.pack(side='left',fill='both',expand=True); self.excel_process_status=tk.StringVar(value='Listo para ejecutar'); ttk.Label(left,textvariable=self.excel_process_status,font=('Segoe UI Semibold',10)).pack(anchor='w'); self.excel_process_bar=ttk.Progressbar(left,mode='indeterminate'); self.excel_process_bar.pack(fill='x',pady=(8,0)); self.excel_state_gif.set_state('idle')
    def run(self):
        return super().run()
    def _drain_process_events(self):
        self.after(120,self._drain_process_events)
    def _build_media_tab(self):
        MediaBaseApp._build_media_tab(self)
        gallery=self.media_canvas.master; gallery.pack_forget(); box=ttk.LabelFrame(self.media_tab,text='Proceso actual',padding=8); box.pack(fill='x',pady=(8,0))
        left=ttk.Frame(box); left.pack(side='left',fill='both',expand=True); self.media_state_gif=AnimatedStateGif(box); self.media_state_gif.pack(side='right',padx=(12,0))
        self.media_progress_title=tk.StringVar(value='Listo para buscar multimedia'); ttk.Label(left,textvariable=self.media_progress_title,font=('Segoe UI Semibold',10)).pack(anchor='w')
        self.media_product_progress=ttk.Progressbar(left,maximum=100); self.media_product_progress.pack(fill='x',pady=(7,2)); self.media_product_percent=tk.StringVar(value='0%'); ttk.Label(left,textvariable=self.media_product_percent).pack(anchor='e')
        self.media_overall_progress=ttk.Progressbar(left,maximum=100); self.media_overall_progress.pack(fill='x',pady=(3,2)); self.media_overall_percent=tk.StringVar(value='0%'); ttk.Label(left,textvariable=self.media_overall_percent).pack(anchor='e')
        self.media_progress_detail=tk.StringVar(value='0 productos completados'); ttk.Label(left,textvariable=self.media_progress_detail).pack(anchor='w'); self.media_state_gif.set_state('idle'); gallery.pack(fill='both',expand=True)
    def _load_wolf_gif(self):pass
    def _animate_wolf(self):pass
    def _set_progress_ui(self):
        super()._set_progress_ui()
        if hasattr(self,'media_state_gif'):
            state='complete' if self._wolf_state=='done' else 'error' if self._wolf_state=='error' else 'running' if self._media_running else 'idle'; self.media_state_gif.set_state(state)
    def _start_media_indices(self,indices):
        if not self._media_running:
            valid=[i for i in indices if self._identity_for_index(i) is not None]
            if valid:self._media_session_id=self.start_process_session('Multimedia',f'{len(valid)} producto(s)',len(valid))
        return super()._start_media_indices(indices)
    def _build_price_tab(self):
        super()._build_price_tab(); progress=self.price_product_progress.master.master; box=ttk.LabelFrame(self.price_tab,text='Resumen y estado',padding=8); box.pack(fill='x',pady=(8,0),before=progress)
        self.price_state_gif=AnimatedStateGif(box); self.price_state_gif.pack(side='right',padx=(12,0)); left=ttk.Frame(box); left.pack(side='left',fill='both',expand=True); self.price_metric=tk.StringVar(value='Sin resultados todavía'); ttk.Label(left,textvariable=self.price_metric,font=('Segoe UI Semibold',10)).pack(anchor='w'); ttk.Label(left,text='Mejor precio · ofertas · canales objetivo · tiendas individuales').pack(anchor='w',pady=(3,0)); self.price_state_gif.set_state('idle')
    def _start_price_indices(self,indices):
        if not self._price_running:
            valid=[i for i in indices if self._identity_for_index(i) is not None]
            if valid:self._price_session_id=self.start_process_session('Precios',f'{len(valid)} producto(s)',len(valid))
        return super()._start_price_indices(indices)


def main():App().mainloop()
if __name__=='__main__':main()
