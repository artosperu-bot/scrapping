from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Frozen build can bundle Playwright browsers under vendor/ms-playwright.
def _configure_frozen_browser():
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
    bundled=base/'vendor'/'ms-playwright'
    if bundled.exists():
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(bundled))
_configure_frozen_browser()

from .batch import run_batch
from .ai_enrichment import AIConfig
from .excel_mapper_v8 import fill_excel_v8
from .models import ProductRecord
from .repair import repair_existing_record


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Product Intelligence V9 — Part Numbers + Scraping + Excel')
        self.geometry('940x760')
        self.minsize(820,560)
        self.q=queue.Queue()
        self._build()
        self.after(150,self._drain)

    def _build(self):
        main=ttk.Frame(self,padding=14);main.pack(fill='both',expand=True)
        ttk.Label(main,text='Product Intelligence V9',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(main,text='Pega part numbers o deja el cuadro vacío para detectarlos en el Excel. Valida identidad/variante y completa solo datos respaldados.').pack(anchor='w',pady=(2,12))

        f=ttk.LabelFrame(main,text='1. Plantilla Excel',padding=10);f.pack(fill='x')
        self.excel=tk.StringVar(); ttk.Entry(f,textvariable=self.excel).pack(side='left',fill='x',expand=True)
        ttk.Button(f,text='Elegir...',command=self.pick_excel).pack(side='left',padx=(8,0))

        pn=ttk.LabelFrame(main,text='2. Part numbers a buscar (uno por línea, coma o punto y coma)',padding=10);pn.pack(fill='x',pady=8)
        self.part_numbers=tk.Text(pn,height=4,wrap='word',font=('Consolas',10))
        self.part_numbers.pack(fill='x',expand=True)
        ttk.Label(pn,text='Ejemplo: JBLQ350WLBLKAM, JBLENDURRUN3BTBAM, JBLT530CBLKAM. Si lo dejas vacío, se detectan productos desde el Excel.').pack(anchor='w',pady=(4,0))

        g=ttk.LabelFrame(main,text='3. Carpeta de salida',padding=10);g.pack(fill='x',pady=8)
        self.out=tk.StringVar(value=str(Path.home()/'ProductIntelligence_Output')); ttk.Entry(g,textvariable=self.out).pack(side='left',fill='x',expand=True)
        ttk.Button(g,text='Elegir...',command=self.pick_out).pack(side='left',padx=(8,0))

        opts=ttk.Frame(main);opts.pack(fill='x',pady=(2,8))
        self.overwrite=tk.BooleanVar(value=False)
        ttk.Checkbutton(opts,text='Sobrescribir valores existentes (excepto datos del vendedor protegidos)',variable=self.overwrite).pack(side='left')

        ai_box=ttk.LabelFrame(main,text='IA asistida opcional (solo evidencia scrapeada)',padding=8);ai_box.pack(fill='x',pady=(0,8))
        self.ai_enabled=tk.BooleanVar(value=False)
        ttk.Checkbutton(ai_box,text='Usar IA para descripción y campos ambiguos',variable=self.ai_enabled).grid(row=0,column=0,columnspan=2,sticky='w')
        ttk.Label(ai_box,text='Proveedor').grid(row=1,column=0,sticky='w',pady=(5,0))
        self.ai_provider=tk.StringVar(value='ollama')
        ttk.Combobox(ai_box,textvariable=self.ai_provider,values=['ollama','openai_compatible'],state='readonly',width=20).grid(row=1,column=1,sticky='w',padx=(6,12),pady=(5,0))
        ttk.Label(ai_box,text='Modelo').grid(row=1,column=2,sticky='w',pady=(5,0))
        self.ai_model=tk.StringVar(value='')
        ttk.Entry(ai_box,textvariable=self.ai_model,width=24).grid(row=1,column=3,sticky='ew',padx=(6,12),pady=(5,0))
        ttk.Label(ai_box,text='Base URL').grid(row=2,column=0,sticky='w',pady=(5,0))
        self.ai_base=tk.StringVar(value='http://127.0.0.1:11434')
        ttk.Entry(ai_box,textvariable=self.ai_base).grid(row=2,column=1,columnspan=3,sticky='ew',padx=(6,12),pady=(5,0))
        ttk.Label(ai_box,text='API key (si aplica)').grid(row=3,column=0,sticky='w',pady=(5,0))
        self.ai_key=tk.StringVar(value='')
        ttk.Entry(ai_box,textvariable=self.ai_key,show='*').grid(row=3,column=1,columnspan=3,sticky='ew',padx=(6,12),pady=(5,0))
        ai_box.columnconfigure(3,weight=1)

        btns=ttk.Frame(main);btns.pack(fill='x')
        self.runbtn=ttk.Button(btns,text='EJECUTAR SCRAPING Y COMPLETAR EXCEL',command=self.run);self.runbtn.pack(side='left')
        ttk.Button(btns,text='Reprocesar JSON antiguos...',command=self.repair_jsons).pack(side='left',padx=8)

        ttk.Separator(main).pack(fill='x',pady=12)
        ttk.Label(main,text='Actividad / auditoría').pack(anchor='w')
        self.log=tk.Text(main,height=22,wrap='word',font=('Consolas',9));self.log.pack(fill='both',expand=True,pady=(4,0))
        self.log.insert('end','Listo. Selecciona una plantilla.\n')

    def pick_excel(self):
        p=filedialog.askopenfilename(filetypes=[('Excel','*.xlsx')]);
        if p:self.excel.set(p);self.out.set(str(Path(p).parent/(Path(p).stem+'_salida')))
    def pick_out(self):
        p=filedialog.askdirectory();
        if p:self.out.set(p)
    def emit(self,msg):self.q.put(str(msg))
    def _ai_config(self):
        provider=self.ai_provider.get().strip() if self.ai_enabled.get() else 'off'
        base=self.ai_base.get().strip()
        if provider=='openai_compatible' and not base:
            base='https://api.openai.com/v1'
        if provider=='ollama' and not base:
            base='http://127.0.0.1:11434'
        return AIConfig(enabled=self.ai_enabled.get(),provider=provider,model=self.ai_model.get().strip(),base_url=base,api_key=self.ai_key.get().strip())
    def _drain(self):
        try:
            while True:
                m=self.q.get_nowait();self.log.insert('end',m+'\n');self.log.see('end')
        except queue.Empty:pass
        self.after(150,self._drain)
    def _manual_part_numbers(self):
        raw=self.part_numbers.get('1.0','end').strip()
        if not raw:return []
        parts=re.split(r'[\s,;]+',raw)
        out=[];seen=set()
        for p in parts:
            p=p.strip()
            if not p:continue
            k=p.upper()
            if k in seen:continue
            seen.add(k);out.append(p)
        return out
    def run(self):
        if not self.excel.get() or not Path(self.excel.get()).exists():
            messagebox.showerror('Falta archivo','Selecciona una plantilla .xlsx.');return
        self.runbtn.configure(state='disabled')
        def work():
            try:
                self.emit('=== INICIO ===')
                res=run_batch(self.excel.get(),self.out.get(),overwrite=self.overwrite.get(),log=self.emit,ai_config=self._ai_config(),manual_part_numbers=self._manual_part_numbers())
                self.emit(json.dumps(res,ensure_ascii=False,indent=2))
                self.emit('=== TERMINADO ===')
                messagebox.showinfo('Terminado',f"Excel: {res['output_excel']}\nTrazabilidad: {res['trace']}")
            except Exception as e:
                self.emit(traceback.format_exc());messagebox.showerror('Error',str(e))
            finally:self.runbtn.configure(state='normal')
        threading.Thread(target=work,daemon=True).start()
    def repair_jsons(self):
        files=filedialog.askopenfilenames(filetypes=[('JSON','*.json')]);
        if not files:return
        template=self.excel.get()
        if not template or not Path(template).exists():
            messagebox.showerror('Falta plantilla','Selecciona primero el Excel a completar.');return
        out=Path(self.out.get());out.mkdir(parents=True,exist_ok=True)
        try:
            recs=[]
            for p in files:
                rec=ProductRecord.model_validate_json(Path(p).read_text(encoding='utf-8'))
                recs.append(repair_existing_record(rec))
            dest=out/(Path(template).stem+'_reprocesado_v8.xlsx')
            trace=out/'trazabilidad_reprocesado_v8.json'
            rep=fill_excel_v8(template,str(dest),recs,overwrite=self.overwrite.get(),trace_path=str(trace))
            self.emit(f'Reprocesado: {dest}')
            self.emit(json.dumps(rep['summary'],ensure_ascii=False))
            messagebox.showinfo('Reprocesado',str(dest))
        except Exception as e:
            self.emit(traceback.format_exc());messagebox.showerror('Error',str(e))


def main():
    App().mainloop()

if __name__=='__main__':main()
