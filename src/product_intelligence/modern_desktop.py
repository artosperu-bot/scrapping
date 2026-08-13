import tkinter as tk
from tkinter import ttk
from .price_desktop import App as PriceApp
from .ui_process import ProcessRegistry
from .ui_theme import configure_business_theme

class App(PriceApp):
    def __init__(self):
        self.process_registry=ProcessRegistry(); self.process_log_tabs={}; self._media_session_id=None; self._price_session_id=None
        super().__init__(); configure_business_theme(self); self.title('Product Intelligence'); self.geometry('1440x900')
    def _build_logs_tab(self):
        self.logs_tab=ttk.Frame(self.notebook,padding=10); self.notebook.add(self.logs_tab,text='6. Logs / auditoría')
        ttk.Label(self.logs_tab,text='Logs / Auditoría',font=('Segoe UI Semibold',11)).pack(anchor='w'); ttk.Label(self.logs_tab,text='Todos los procesos y cada ejecución por separado.').pack(anchor='w',pady=(1,6))
        self.log_notebook=ttk.Notebook(self.logs_tab); self.log_notebook.pack(fill='both',expand=True); self.log=self._add_log_tab('__all__','Todos')
        row=ttk.Frame(self.logs_tab); row.pack(fill='x',pady=(6,0)); ttk.Button(row,text='Limpiar Todos',command=lambda:self.log.delete('1.0','end')).pack(side='left'); ttk.Button(row,text='Abrir carpeta de salida',command=self.open_output_folder).pack(side='left',padx=8)
    def _add_log_tab(self,key,label):
        frame=ttk.Frame(self.log_notebook,padding=5); text=tk.Text(frame,wrap='word',font=('Consolas',9),relief='flat'); text.pack(fill='both',expand=True); self.log_notebook.add(frame,text=label); self.process_log_tabs[key]=text; return text
    def start_process_session(self,kind,label,total=1):
        s=self.process_registry.start(kind,label,total); self._add_log_tab(s.session_id,f'{kind} #{s.session_id.rsplit("-",1)[-1]}'); return s.session_id
    def _start_media_indices(self,indices):
        if not self._media_running:
            valid=[i for i in indices if self._identity_for_index(i) is not None]
            if valid:self._media_session_id=self.start_process_session('Multimedia',f'{len(valid)} producto(s)',len(valid))
        return super()._start_media_indices(indices)
    def _start_price_indices(self,indices):
        if not self._price_running:
            valid=[i for i in indices if self._identity_for_index(i) is not None]
            if valid:self._price_session_id=self.start_process_session('Precios',f'{len(valid)} producto(s)',len(valid))
        return super()._start_price_indices(indices)


def main():App().mainloop()
if __name__=='__main__':main()
