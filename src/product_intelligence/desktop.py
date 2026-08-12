from __future__ import annotations

import json
import os
import queue
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def _configure_frozen_browser():
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
    bundled=base/'vendor'/'ms-playwright'
    if bundled.exists():os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(bundled))
_configure_frozen_browser()

from .batch import run_batch
from .input_identity import parse_product_entries
from .excel_mapper_v8 import fill_excel_v8
from .models import ProductRecord
from .repair import repair_existing_record


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Product Intelligence — Excel + Scraping web sin IA')
        self.geometry('1040x930');self.minsize(900,720)
        self.q=queue.Queue();self._build();self.after(150,self._drain)

    def _build(self):
        main=ttk.Frame(self,padding=14);main.pack(fill='both',expand=True)
        ttk.Label(main,text='Product Intelligence — scraping sin IA',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(main,text='El Excel define qué datos se necesitan. Puedes pegar fichas web y el programa completa faltantes con búsqueda gratuita.').pack(anchor='w',pady=(2,10))

        f=ttk.LabelFrame(main,text='1. Plantilla Excel',padding=10);f.pack(fill='x')
        self.excel=tk.StringVar();ttk.Entry(f,textvariable=self.excel).pack(side='left',fill='x',expand=True)
        ttk.Button(f,text='Elegir...',command=self.pick_excel).pack(side='left',padx=(8,0))

        pbox=ttk.LabelFrame(main,text='2. Productos a buscar — basta UN dato principal por producto',padding=10);pbox.pack(fill='x',pady=8)
        self.product_queries=tk.Text(pbox,height=5,wrap='word',font=('Consolas',10));self.product_queries.pack(fill='x')
        ttk.Label(pbox,text='Acepta MPN, EAN, UPC/GTIN o nombre. Opcional: | brand=... | model=... | color=... | url=https://... (url= se puede repetir)').pack(anchor='w',pady=(4,0))
        ttk.Label(pbox,text='Ejemplo: JBLENDURRUN3BTBAM | url=https://www.jbl.com.pe/JBLENDURRUN3BTBAM.html').pack(anchor='w')
        ttk.Label(pbox,text='Si queda vacío, el programa detecta las identidades presentes en el Excel.').pack(anchor='w')

        g=ttk.LabelFrame(main,text='3. Carpeta de salida',padding=10);g.pack(fill='x',pady=8)
        self.out=tk.StringVar(value=str(Path.home()/'ProductIntelligence_Output'));ttk.Entry(g,textvariable=self.out).pack(side='left',fill='x',expand=True)
        ttk.Button(g,text='Elegir...',command=self.pick_out).pack(side='left',padx=(8,0))

        opts=ttk.Frame(main);opts.pack(fill='x',pady=(0,8))
        self.overwrite=tk.BooleanVar(value=False)
        ttk.Checkbutton(opts,text='Sobrescribir datos de producto existentes; proteger precio/SKU/stock y demás datos del vendedor',variable=self.overwrite).pack(side='left')

        searchbox=ttk.LabelFrame(main,text='4. Descubrimiento web',padding=10);searchbox.pack(fill='x',pady=(0,8))
        ttk.Label(searchbox,text='✓ Búsqueda web gratuita SIEMPRE ACTIVA — DuckDuckGo HTML, Bing/Bing RSS, Brave web, Mojeek y Yahoo. No requiere API key.',font=('Segoe UI',9,'bold')).pack(anchor='w')
        ttk.Label(searchbox,text='Busca MPN/EAN/UPC/GTIN/nombre y refuerza consultas con official, specifications, datasheet, manual y support. Después el scraper valida cada URL.').pack(anchor='w',pady=(3,0))

        info=ttk.LabelFrame(main,text='5. Política de fuentes',padding=10);info.pack(fill='x',pady=(0,8))
        ttk.Label(info,text='1) URLs que pegues → se prueban primero y se validan.').pack(anchor='w')
        ttk.Label(info,text='2) Fabricante / ficha técnica / PDF / soporte oficial → máxima prioridad.').pack(anchor='w')
        ttk.Label(info,text='3) Búsqueda web gratuita → completa datos o imágenes que falten.').pack(anchor='w')
        ttk.Label(info,text='4) Fuentes secundarias → solo si son compatibles y no hay evidencia oficial suficiente.').pack(anchor='w')

        btns=ttk.Frame(main);btns.pack(fill='x')
        self.runbtn=ttk.Button(btns,text='EJECUTAR SCRAPING Y COMPLETAR EXCEL',command=self.run);self.runbtn.pack(side='left')
        ttk.Button(btns,text='Reprocesar JSON antiguos...',command=self.repair_jsons).pack(side='left',padx=8)

        ttk.Separator(main).pack(fill='x',pady=12)
        ttk.Label(main,text='Actividad / auditoría').pack(anchor='w')
        self.log=tk.Text(main,height=18,wrap='word',font=('Consolas',9));self.log.pack(fill='both',expand=True,pady=(4,0))
        self.log.insert('end','Listo. Búsqueda web gratuita activa. Selecciona una plantilla Excel.\n')

    def pick_excel(self):
        p=filedialog.askopenfilename(filetypes=[('Excel','*.xlsx')])
        if p:self.excel.set(p);self.out.set(str(Path(p).parent/(Path(p).stem+'_salida')))
    def pick_out(self):
        p=filedialog.askdirectory()
        if p:self.out.set(p)
    def emit(self,msg):self.q.put(str(msg))
    def _drain(self):
        try:
            while True:
                m=self.q.get_nowait();self.log.insert('end',m+'\n');self.log.see('end')
        except queue.Empty:pass
        self.after(150,self._drain)

    def _manual_entries(self):
        return parse_product_entries(self.product_queries.get('1.0','end').strip())

    def _manual_identities(self):
        return [entry.identity for entry in self._manual_entries()]

    def run(self):
        if not self.excel.get() or not Path(self.excel.get()).exists():messagebox.showerror('Falta archivo','Selecciona una plantilla .xlsx.');return
        entries=self._manual_entries();identities=[e.identity for e in entries];source_urls=[e.source_urls for e in entries]
        self.runbtn.configure(state='disabled')
        def work():
            try:
                self.emit('=== INICIO ===')
                self.emit('Búsqueda web gratuita: ACTIVA (sin API key de búsqueda).')
                if identities:
                    for i,x in enumerate(identities,1):self.emit(f'Entrada {i}: '+json.dumps({k:v for k,v in x.model_dump().items() if v not in (None,'')},ensure_ascii=False))
                res=run_batch(self.excel.get(),self.out.get(),overwrite=self.overwrite.get(),log=self.emit,manual_identities=identities or None,manual_source_urls=source_urls or None)
                self.emit(json.dumps(res,ensure_ascii=False,indent=2));self.emit('=== TERMINADO ===')
                self.after(0,lambda:messagebox.showinfo('Terminado',f"Excel: {res['output_excel']}\nTrazabilidad: {res['trace']}"))
            except Exception as e:
                self.emit(traceback.format_exc());self.after(0,lambda:messagebox.showerror('Error',str(e)))
            finally:self.after(0,lambda:self.runbtn.configure(state='normal'))
        threading.Thread(target=work,daemon=True).start()

    def repair_jsons(self):
        files=filedialog.askopenfilenames(filetypes=[('JSON','*.json')])
        if not files:return
        template=self.excel.get()
        if not template or not Path(template).exists():messagebox.showerror('Falta plantilla','Selecciona primero el Excel a completar.');return
        out=Path(self.out.get());out.mkdir(parents=True,exist_ok=True)
        try:
            recs=[repair_existing_record(ProductRecord.model_validate_json(Path(p).read_text(encoding='utf-8'))) for p in files]
            dest=out/(Path(template).stem+'_reprocesado.xlsx');trace=out/'trazabilidad_reprocesado.json'
            rep=fill_excel_v8(template,str(dest),recs,overwrite=self.overwrite.get(),trace_path=str(trace))
            self.emit(f'Reprocesado: {dest}');self.emit(json.dumps(rep['summary'],ensure_ascii=False));messagebox.showinfo('Reprocesado',str(dest))
        except Exception as e:self.emit(traceback.format_exc());messagebox.showerror('Error',str(e))


def main():App().mainloop()
if __name__=='__main__':main()
