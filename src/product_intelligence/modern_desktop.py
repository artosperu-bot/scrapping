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
  self.process_registry=ProcessRegistry();self.process_log_tabs={};self._media_session_id=None;self._price_session_id=None;self._excel_session_id=None;self._ui_thread=threading.get_ident();self._session_logs=queue.Queue();self._last_price_status='';self._last_media_status='';self.price_state_gif=None;self.excel_state_gif=None
  super().__init__();configure_business_theme(self);self.title('Product Intelligence');self.geometry('1440x900');self.after(120,self._drain_process_events)
 def _build_logs_tab(self):
  self.logs_tab=ttk.Frame(self.notebook,padding=10);self.notebook.add(self.logs_tab,text='6. Logs / auditoría');ttk.Label(self.logs_tab,text='Logs / Auditoría',font=('Segoe UI Semibold',11)).pack(anchor='w');ttk.Label(self.logs_tab,text='Todos los procesos y cada ejecución por separado.').pack(anchor='w')
  self.log_notebook=ttk.Notebook(self.logs_tab);self.log_notebook.pack(fill='both',expand=True);self.log=self._add_log_tab('__all__','Todos')
 def _add_log_tab(self,key,label):
  f=ttk.Frame(self.log_notebook,padding=5);t=tk.Text(f,wrap='word',font=('Consolas',9),relief='flat');t.pack(fill='both',expand=True);self.log_notebook.add(f,text=label);self.process_log_tabs[key]=t;return t
 def _session_log(self,sid,text,all_view=False):
  t=self.process_log_tabs.get(sid)
  if t:t.insert('end',str(text)+'\n');t.see('end')
  if all_view:self.log.insert('end',str(text)+'\n');self.log.see('end')
 def start_process_session(self,kind,label,total=1):
  s=self.process_registry.start(kind,label,total);self._add_log_tab(s.session_id,f'{kind} #{s.session_id.rsplit("-",1)[-1]}');return s.session_id
 def emit(self,msg):
  text=str(msg);self.q.put(text);self._session_logs.put((threading.get_ident(),text))
 def _build_run_tab(self):
  super()._build_run_tab();tab=self.runbtn.master.master;box=ttk.LabelFrame(tab,text='Estado del proceso',padding=8);box.pack(fill='x',pady=(8,0),before=self.runbtn.master);self.excel_state_gif=AnimatedStateGif(box);self.excel_state_gif.pack(side='right',padx=10);self.excel_process_status=tk.StringVar(value='Listo para ejecutar');ttk.Label(box,textvariable=self.excel_process_status,font=('Segoe UI Semibold',10)).pack(anchor='w');self.excel_process_bar=ttk.Progressbar(box,mode='indeterminate');self.excel_process_bar.pack(fill='x',pady=5);self.excel_state_gif.set_state('idle')
 def run(self):
  result=super().run()
  if str(self.runbtn.cget('state'))=='disabled' and self._excel_session_id is None:
   n=max(1,len(self.product_rows));self._excel_session_id=self.start_process_session('Excel',f'{n} producto(s)',n);self.excel_process_status.set('Scraping y generación de Excel en proceso');self.excel_process_bar.start(10);self.excel_state_gif.set_state('running')
  return result
 def _build_media_tab(self):
  MediaBaseApp._build_media_tab(self);g=self.media_canvas.master;g.pack_forget();box=ttk.LabelFrame(self.media_tab,text='Proceso actual',padding=8);box.pack(fill='x',pady=(8,0));self.media_state_gif=AnimatedStateGif(box);self.media_state_gif.pack(side='right',padx=10);left=ttk.Frame(box);left.pack(fill='both',expand=True);self.media_progress_title=tk.StringVar(value='Listo para buscar multimedia');ttk.Label(left,textvariable=self.media_progress_title,font=('Segoe UI Semibold',10)).pack(anchor='w');self.media_product_progress=ttk.Progressbar(left,maximum=100);self.media_product_progress.pack(fill='x');self.media_product_percent=tk.StringVar(value='0%');self.media_overall_progress=ttk.Progressbar(left,maximum=100);self.media_overall_progress.pack(fill='x',pady=4);self.media_overall_percent=tk.StringVar(value='0%');self.media_progress_detail=tk.StringVar(value='0 productos completados');ttk.Label(left,textvariable=self.media_progress_detail).pack(anchor='w');self.media_state_gif.set_state('idle');g.pack(fill='both',expand=True)
 def _load_wolf_gif(self):pass
 def _animate_wolf(self):pass
 def _set_progress_ui(self):
  super()._set_progress_ui()
  if hasattr(self,'media_state_gif'):self.media_state_gif.set_state('complete' if self._wolf_state=='done' else 'error' if self._wolf_state=='error' else 'running' if self._media_running else 'idle')
 def _start_media_indices(self,indices):
  was=self._media_running;result=super()._start_media_indices(indices)
  if not was and self._media_running:
   v=[i for i in indices if self._identity_for_index(i) is not None];self._media_session_id=self.start_process_session('Multimedia',f'{len(v)} producto(s)',len(v));self.media_state_gif.set_state('running')
  return result
 def _build_price_tab(self):
  super()._build_price_tab();p=self.price_product_progress.master.master;box=ttk.LabelFrame(self.price_tab,text='Resumen y estado',padding=8);box.pack(fill='x',pady=(8,0),before=p);self.price_state_gif=AnimatedStateGif(box);self.price_state_gif.pack(side='right',padx=10);self.price_metric=tk.StringVar(value='Sin resultados todavía');ttk.Label(box,textvariable=self.price_metric,font=('Segoe UI Semibold',10)).pack(anchor='w');ttk.Label(box,text='Mejor precio · ofertas · canales objetivo · tiendas individuales').pack(anchor='w');self.price_state_gif.set_state('idle')
 def _start_price_indices(self,indices):
  was=self._price_running;result=super()._start_price_indices(indices)
  if not was and self._price_running:
   v=[i for i in indices if self._identity_for_index(i) is not None];self._price_session_id=self.start_process_session('Precios',f'{len(v)} producto(s)',len(v));self.price_state_gif.set_state('running')
  return result
 def _drain_process_events(self):
  try:
   while True:
    origin,text=self._session_logs.get_nowait()
    if text.startswith('[MEDIA]') and self._media_session_id:self._session_log(self._media_session_id,text)
    elif origin!=self._ui_thread and self._excel_session_id:
     self._session_log(self._excel_session_id,text)
     if text.startswith('Traceback'):self.process_registry.apply(self._excel_session_id,{'type':'fatal'})
     elif text=='=== TERMINADO ===':self.process_registry.apply(self._excel_session_id,{'type':'done'})
  except queue.Empty:pass
  if self._media_session_id:
   s=str(self.media_status.get())
   if s and s!=self._last_media_status:self._last_media_status=s;self._session_log(self._media_session_id,s)
  if self._price_session_id:
   s=str(self.price_status.get())
   if s and s!=self._last_price_status:self._last_price_status=s;self._session_log(self._price_session_id,s,True)
   if not self._price_running:
    failed='Error general' in s;self.price_state_gif.set_state('error' if failed else 'complete');self.price_metric.set(str(self.price_summary.get()))
  if self._excel_session_id:
   x=self.process_registry.get(self._excel_session_id)
   if x and x.state in {'complete','error'}:
    self.excel_process_bar.stop();self.excel_process_status.set('Proceso completado' if x.state=='complete' else 'Proceso con error · revisa su log');self.excel_state_gif.set_state(x.state);self._excel_session_id=None
  self.after(120,self._drain_process_events)

def main():App().mainloop()
if __name__=='__main__':main()
