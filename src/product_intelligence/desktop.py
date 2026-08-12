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
from .ai_enrichment import AIConfig
from .input_identity import parse_product_queries
from .model_catalog import DEFAULT_MODELS, capability, list_models
from .excel_mapper_v8 import fill_excel_v8
from .models import ProductRecord
from .repair import repair_existing_record


PROVIDER_DEFAULTS={
    'openai':('https://api.openai.com/v1','gpt-5-mini-2025-08-07'),
    'openrouter':('https://openrouter.ai/api/v1','openai/gpt-5-mini'),
    'mistral':('https://api.mistral.ai/v1','mistral-small-latest'),
    'ollama':('http://127.0.0.1:11434','mistral'),
    'openai_compatible':('',''),
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Product Intelligence 0.10.2 — Excel + Scraping + búsqueda web gratuita')
        self.geometry('1040x930');self.minsize(900,720)
        self.q=queue.Queue();self._build();self.after(150,self._drain)

    def _build(self):
        main=ttk.Frame(self,padding=14);main.pack(fill='both',expand=True)
        ttk.Label(main,text='Product Intelligence 0.10.2',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(main,text='El Excel define qué datos se necesitan. El scraper sigue siendo la autoridad. La búsqueda web normal no requiere API de pago.').pack(anchor='w',pady=(2,10))

        f=ttk.LabelFrame(main,text='1. Plantilla Excel',padding=10);f.pack(fill='x')
        self.excel=tk.StringVar();ttk.Entry(f,textvariable=self.excel).pack(side='left',fill='x',expand=True)
        ttk.Button(f,text='Elegir...',command=self.pick_excel).pack(side='left',padx=(8,0))

        pbox=ttk.LabelFrame(main,text='2. Productos a buscar — basta UN dato principal por producto',padding=10);pbox.pack(fill='x',pady=8)
        self.product_queries=tk.Text(pbox,height=5,wrap='word',font=('Consolas',10));self.product_queries.pack(fill='x')
        ttk.Label(pbox,text='Acepta: Part Number/MPN, EAN, UPC/GTIN o nombre. Uno por línea. Hints opcionales: | brand=... | model=... | color=... | variant=...').pack(anchor='w',pady=(4,0))
        ttk.Label(pbox,text='Ejemplos:  JBLENDURRUN3BTBAM   ·   1234567890123   ·   JBL Tune 530C USB-C | brand=JBL | color=Negro').pack(anchor='w')
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

        ai=ttk.LabelFrame(main,text='5. IA opcional — no necesaria para buscar en Internet',padding=10);ai.pack(fill='x',pady=(0,8))
        self.ai_discovery=tk.BooleanVar(value=False);self.ai_enrichment=tk.BooleanVar(value=False)
        ttk.Checkbutton(ai,text='IA Web Discovery adicional (OPCIONAL, puede generar cargos del proveedor)',variable=self.ai_discovery,command=self._refresh_capability).grid(row=0,column=0,columnspan=5,sticky='w')
        ttk.Checkbutton(ai,text='IA sobre evidencia: ayudar con descripción/campos ambiguos SOLO después del scraping validado',variable=self.ai_enrichment,command=self._refresh_capability).grid(row=1,column=0,columnspan=5,sticky='w')
        ttk.Label(ai,text='Para costo cero total: deja ambas opciones apagadas, o usa Ollama local para interpretación.').grid(row=2,column=0,columnspan=5,sticky='w',pady=(3,4))

        ttk.Label(ai,text='Proveedor').grid(row=3,column=0,sticky='w',pady=(8,0))
        self.ai_provider=tk.StringVar(value='openai')
        self.provider_combo=ttk.Combobox(ai,textvariable=self.ai_provider,values=['openai','openrouter','mistral','ollama','openai_compatible'],state='readonly',width=19)
        self.provider_combo.grid(row=3,column=1,sticky='w',padx=(6,16),pady=(8,0));self.provider_combo.bind('<<ComboboxSelected>>',self._provider_changed)

        ttk.Label(ai,text='Modelo').grid(row=3,column=2,sticky='w',pady=(8,0))
        self.ai_model=tk.StringVar(value='gpt-5-mini-2025-08-07')
        self.model_combo=ttk.Combobox(ai,textvariable=self.ai_model,values=DEFAULT_MODELS['openai'],width=34)
        self.model_combo.grid(row=3,column=3,sticky='ew',padx=(6,6),pady=(8,0));self.model_combo.bind('<<ComboboxSelected>>',lambda _e:self._refresh_capability())
        ttk.Button(ai,text='Cargar modelos',command=self.load_models).grid(row=3,column=4,sticky='w',pady=(8,0))

        ttk.Label(ai,text='Base URL').grid(row=4,column=0,sticky='w',pady=(6,0))
        self.ai_base=tk.StringVar(value='https://api.openai.com/v1');ttk.Entry(ai,textvariable=self.ai_base).grid(row=4,column=1,columnspan=4,sticky='ew',padx=(6,0),pady=(6,0))
        ttk.Label(ai,text='API key').grid(row=5,column=0,sticky='w',pady=(6,0))
        self.ai_key=tk.StringVar();ttk.Entry(ai,textvariable=self.ai_key,show='*').grid(row=5,column=1,columnspan=2,sticky='ew',padx=(6,16),pady=(6,0))
        ttk.Label(ai,text='País preferido').grid(row=5,column=3,sticky='e',pady=(6,0))
        self.ai_country=tk.StringVar(value='PE');ttk.Entry(ai,textvariable=self.ai_country,width=6).grid(row=5,column=4,sticky='w',padx=(6,0),pady=(6,0))
        self.ai_status=tk.StringVar();ttk.Label(ai,textvariable=self.ai_status).grid(row=6,column=0,columnspan=5,sticky='w',pady=(7,0))
        ai.columnconfigure(3,weight=1);self._refresh_capability()

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

    def _provider_changed(self,_event=None):
        provider=self.ai_provider.get();base,model=PROVIDER_DEFAULTS.get(provider,('',''))
        self.ai_base.set(base);self.ai_model.set(model);self.model_combo.configure(values=DEFAULT_MODELS.get(provider,[]));self._refresh_capability()

    def _refresh_capability(self):
        cap=capability(self.ai_provider.get(),self.ai_model.get())
        web='Sí' if cap.web_discovery else 'No'
        evidence='Sí' if cap.evidence_enrichment else 'No'
        suffix=''
        if self.ai_discovery.get() and not cap.web_discovery:
            suffix=' — Este proveedor no ofrece Web Discovery integrada; la búsqueda web gratuita del scraper sigue funcionando.'
        self.ai_status.set(f'IA opcional → Web Discovery integrada: {web} | Interpretar evidencia: {evidence}.{suffix}')

    def load_models(self):
        def work():
            try:
                cfg=AIConfig(enabled=True,provider=self.ai_provider.get(),model=self.ai_model.get(),base_url=self.ai_base.get().strip(),api_key=self.ai_key.get().strip())
                models=list_models(cfg)
                self.after(0,lambda:self.model_combo.configure(values=models))
                self.emit(f'Modelos disponibles ({self.ai_provider.get()}): {len(models)}')
            except Exception as e:self.emit(f'No se pudieron cargar modelos: {e}')
        threading.Thread(target=work,daemon=True).start()

    def _ai_config(self):
        provider=self.ai_provider.get().strip();model=self.ai_model.get().strip();cap=capability(provider,model)
        discovery=bool(self.ai_discovery.get() and cap.web_discovery)
        enrichment=bool(self.ai_enrichment.get() and cap.evidence_enrichment)
        return AIConfig(enabled=discovery or enrichment,provider=provider if discovery or enrichment else 'off',model=model,base_url=self.ai_base.get().strip(),api_key=self.ai_key.get().strip(),discovery_enabled=discovery,enrichment_enabled=enrichment,preferred_country=(self.ai_country.get().strip().upper() or 'PE'))

    def _manual_identities(self):
        return parse_product_queries(self.product_queries.get('1.0','end').strip())

    def run(self):
        if not self.excel.get() or not Path(self.excel.get()).exists():messagebox.showerror('Falta archivo','Selecciona una plantilla .xlsx.');return
        identities=self._manual_identities();cfg=self._ai_config()
        if cfg.discovery_enabled and cfg.provider != 'ollama':
            self.emit('ADVERTENCIA DE COSTO: IA Web Discovery integrada está activada y el proveedor puede cobrar búsquedas/herramientas además de tokens.')
        if cfg.enrichment_enabled and cfg.provider != 'ollama':
            self.emit('Aviso: IA sobre evidencia usa la API del proveedor y puede consumir tokens facturables.')
        if (cfg.discovery_enabled or cfg.enrichment_enabled) and cfg.provider not in {'ollama'} and not cfg.api_key:
            self.emit('Aviso: IA activada sin API key. El scraper y la búsqueda web gratuita seguirán funcionando; las llamadas IA se omitirán si fallan.')
        self.runbtn.configure(state='disabled')
        def work():
            try:
                self.emit('=== INICIO ===')
                self.emit('Búsqueda web gratuita: ACTIVA (sin API key de búsqueda).')
                if identities:
                    for i,x in enumerate(identities,1):self.emit(f'Entrada {i}: '+json.dumps({k:v for k,v in x.model_dump().items() if v not in (None,'')},ensure_ascii=False))
                res=run_batch(self.excel.get(),self.out.get(),overwrite=self.overwrite.get(),log=self.emit,ai_config=cfg,manual_identities=identities or None)
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
            rep=fill_excel_v8(template,str(dest),recs,overwrite=self.overwrite.get(),trace_path=str(trace),ai_config=self._ai_config())
            self.emit(f'Reprocesado: {dest}');self.emit(json.dumps(rep['summary'],ensure_ascii=False));messagebox.showinfo('Reprocesado',str(dest))
        except Exception as e:self.emit(traceback.format_exc());messagebox.showerror('Error',str(e))


def main():App().mainloop()
if __name__=='__main__':main()
