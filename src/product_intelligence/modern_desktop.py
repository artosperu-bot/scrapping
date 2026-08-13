from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from .price_desktop import App as PriceApp


NAV_ITEMS = [
    ("Inicio", "dashboard"),
    ("Productos", "products"),
    ("Fuentes", "sources"),
    ("Atributos", "attributes"),
    ("Multimedia", "media"),
    ("Precios", "prices"),
    ("Ejecutar", "run"),
    ("Auditoría", "audit"),
]

_PAGE_COPY = {
    "dashboard": ("Inicio", "Resumen del archivo, productos y estado del proceso."),
    "products": ("Productos", "Revisa y corrige la identidad de cada producto antes de investigar."),
    "sources": ("Fuentes", "Controla URLs prioritarias y revisa el plan real de búsqueda."),
    "attributes": ("Atributos", "Comprueba qué campos exige el Excel y cómo se resolverán."),
    "media": ("Multimedia", "Busca, valida y descarga fotos y videos sin mezclar el flujo de Excel."),
    "prices": ("Precios", "Compara ofertas validadas, canal, vendedor, stock y confianza."),
    "run": ("Ejecutar", "Genera el Excel final conservando las protecciones de datos STECH/seller."),
    "audit": ("Auditoría", "Sigue en vivo fuentes, validaciones, errores y decisiones del proceso."),
}

_NAV_GLYPHS = {
    "dashboard": "⌂",
    "products": "▦",
    "sources": "◎",
    "attributes": "≡",
    "media": "▧",
    "prices": "$",
    "run": "▶",
    "audit": "☰",
}


class App(PriceApp):
    """Modern final presentation shell over the preserved Product Intelligence engine."""

    def __init__(self):
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._workspace_tabs: dict[str, object] = {}
        self._dashboard_vars: dict[str, tk.StringVar] = {}
        self._active_workspace = "dashboard"
        super().__init__()
        self.title("Product Intelligence — STECH")
        self.geometry("1480x920")
        self.minsize(1180, 760)

    def _build(self):
        # Build every existing functional workspace first. The modern shell then
        # changes presentation/navigation only; workflow callbacks stay inherited.
        super()._build()
        self._apply_modern_theme()
        self._install_modern_shell()
        self._restyle_existing_pages()
        self._bind_status_sources()
        self._refresh_dashboard()
        self._show_workspace("dashboard")

    def _apply_modern_theme(self):
        self.configure(bg="#f4f6f9")
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background="#f4f6f9")
        style.configure("Page.TFrame", background="#f4f6f9")
        style.configure("Sidebar.TFrame", background="#172033")
        style.configure("Header.TFrame", background="#ffffff")
        style.configure("Status.TFrame", background="#ffffff")
        style.configure(
            "SidebarTitle.TLabel",
            background="#172033",
            foreground="#ffffff",
            font=("Segoe UI", 16, "bold"),
        )
        style.configure(
            "SidebarMuted.TLabel",
            background="#172033",
            foreground="#9da9bd",
            font=("Segoe UI", 9),
        )
        style.configure(
            "Nav.TButton",
            background="#172033",
            foreground="#dbe3ef",
            borderwidth=0,
            relief="flat",
            anchor="w",
            padding=(18, 12),
            font=("Segoe UI", 10),
        )
        style.map(
            "Nav.TButton",
            background=[("active", "#243149"), ("pressed", "#243149")],
            foreground=[("active", "#ffffff")],
        )
        style.configure(
            "NavActive.TButton",
            background="#2f6fed",
            foreground="#ffffff",
            borderwidth=0,
            relief="flat",
            anchor="w",
            padding=(18, 12),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("NavActive.TButton", background=[("active", "#2f6fed"), ("pressed", "#2f6fed")])
        style.configure("PageTitle.TLabel", background="#ffffff", foreground="#172033", font=("Segoe UI", 21, "bold"))
        style.configure("PageSubtitle.TLabel", background="#ffffff", foreground="#647184", font=("Segoe UI", 10))
        style.configure("HeaderFile.TLabel", background="#ffffff", foreground="#506078", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#ffffff", foreground="#415169", font=("Segoe UI", 9))
        style.configure("Card.TFrame", background="#ffffff", relief="flat", borderwidth=1)
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#6b778a", font=("Segoe UI", 9))
        style.configure("CardValue.TLabel", background="#ffffff", foreground="#172033", font=("Segoe UI", 15, "bold"))
        style.configure("CardDetail.TLabel", background="#ffffff", foreground="#647184", font=("Segoe UI", 9))
        style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1, relief="solid", padding=10)
        style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#344258", font=("Segoe UI", 9, "bold"))
        style.configure(
            "Primary.TButton",
            background="#2f6fed",
            foreground="#ffffff",
            borderwidth=0,
            padding=(16, 10),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Primary.TButton", background=[("active", "#255fce"), ("pressed", "#1f52b4")])
        style.configure(
            "Secondary.TButton",
            background="#e9eef7",
            foreground="#26364c",
            borderwidth=0,
            padding=(14, 9),
            font=("Segoe UI", 9, "bold"),
        )
        style.configure("Modern.Treeview", background="#ffffff", fieldbackground="#ffffff", foreground="#27364b", rowheight=30, borderwidth=0)
        style.configure("Modern.Treeview.Heading", background="#e9eef7", foreground="#27364b", relief="flat", font=("Segoe UI", 9, "bold"), padding=(6, 7))
        style.map("Modern.Treeview", background=[("selected", "#dce8ff")], foreground=[("selected", "#172033")])

        style.configure("Modern.TNotebook", background="#f4f6f9", borderwidth=0, tabmargins=0)
        # The notebook is retained as a safe page host, but its numbered tab strip
        # is intentionally removed. Persistent sidebar navigation is the UI shell.
        style.layout("Modern.TNotebook.Tab", [])

    def _install_modern_shell(self):
        main = self.notebook.master
        main.configure(style="App.TFrame", padding=0)

        # The legacy title, workbook bar, status label and notebook were packed.
        # Unmanage them without destroying them so all existing Tk variables and
        # callbacks remain alive, then reuse the notebook inside the new grid shell.
        for child in main.winfo_children():
            child.pack_forget()

        main.columnconfigure(0, minsize=238, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(2, weight=0)

        self.sidebar = ttk.Frame(main, style="Sidebar.TFrame", width=238)
        self.sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self._build_sidebar()

        self.header = ttk.Frame(main, style="Header.TFrame", padding=(24, 16, 24, 13))
        self.header.grid(row=0, column=1, sticky="ew")
        self.header.columnconfigure(0, weight=1)
        self._page_title = tk.StringVar(value="Inicio")
        self._page_subtitle = tk.StringVar(value=_PAGE_COPY["dashboard"][1])
        ttk.Label(self.header, textvariable=self._page_title, style="PageTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.header, textvariable=self._page_subtitle, style="PageSubtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        self._header_file = tk.StringVar(value="Sin archivo seleccionado")
        ttk.Label(self.header, textvariable=self._header_file, style="HeaderFile.TLabel").grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))

        self.notebook.configure(style="Modern.TNotebook")
        self.notebook.grid(row=1, column=1, sticky="nsew", padx=(18, 18), pady=(14, 10))

        self.status_bar = ttk.Frame(main, style="Status.TFrame", padding=(20, 9))
        self.status_bar.grid(row=2, column=1, sticky="ew")
        self.global_status = tk.StringVar(value="Listo · selecciona un Excel para comenzar")
        ttk.Label(self.status_bar, text="●", style="Status.TLabel").pack(side="left")
        ttk.Label(self.status_bar, textvariable=self.global_status, style="Status.TLabel").pack(side="left", padx=(7, 0))
        ttk.Label(self.status_bar, text="Motor preservado · Excel + scraping + multimedia + precios", style="Status.TLabel").pack(side="right")

        self._build_dashboard()
        self._map_existing_workspaces()

    def _build_sidebar(self):
        brand = ttk.Frame(self.sidebar, style="Sidebar.TFrame", padding=(18, 22, 14, 18))
        brand.pack(fill="x")
        ttk.Label(brand, text="PRODUCT", style="SidebarMuted.TLabel").pack(anchor="w")
        ttk.Label(brand, text="INTELLIGENCE", style="SidebarTitle.TLabel").pack(anchor="w")
        ttk.Label(brand, text="STECH workspace", style="SidebarMuted.TLabel").pack(anchor="w", pady=(4, 0))

        ttk.Separator(self.sidebar, orient="horizontal").pack(fill="x", padx=16, pady=(0, 12))
        nav = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        nav.pack(fill="x")
        for label, key in NAV_ITEMS:
            button = ttk.Button(
                nav,
                text=f"{_NAV_GLYPHS.get(key, '•')}   {label}",
                style="Nav.TButton",
                command=lambda k=key: self._show_workspace(k),
            )
            button.pack(fill="x", padx=10, pady=2)
            self._nav_buttons[key] = button

        footer = ttk.Frame(self.sidebar, style="Sidebar.TFrame", padding=(18, 10, 14, 18))
        footer.pack(side="bottom", fill="x")
        ttk.Label(footer, text="Sin IA obligatoria", style="SidebarMuted.TLabel").pack(anchor="w")
        ttk.Label(footer, text="Datos verificables y trazables", style="SidebarMuted.TLabel").pack(anchor="w", pady=(2, 0))

    def _build_dashboard(self):
        self.dashboard_tab = ttk.Frame(self.notebook, style="Page.TFrame", padding=(6, 6, 6, 6))
        self.notebook.insert(0, self.dashboard_tab, text="Inicio")
        self._workspace_tabs["dashboard"] = self.dashboard_tab

        hero = tk.Frame(self.dashboard_tab, bg="#2158c7", padx=24, pady=20, highlightthickness=0)
        hero.pack(fill="x", pady=(0, 14))
        tk.Label(hero, text="Inteligencia de producto, en un solo flujo", bg="#2158c7", fg="#ffffff", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(
            hero,
            text="Analiza el Excel, valida identidades, investiga fuentes, multimedia y precios, y genera una salida auditable sin inventar datos.",
            bg="#2158c7",
            fg="#dfe9ff",
            font=("Segoe UI", 10),
            wraplength=940,
            justify="left",
        ).pack(anchor="w", pady=(5, 13))
        hero_actions = tk.Frame(hero, bg="#2158c7")
        hero_actions.pack(fill="x")
        ttk.Button(hero_actions, text="Seleccionar Excel", style="Primary.TButton", command=self.pick_excel).pack(side="left")
        ttk.Button(hero_actions, text="Analizar archivo", style="Secondary.TButton", command=self.analyze_excel).pack(side="left", padx=8)
        ttk.Button(hero_actions, text="Ir a ejecución", style="Secondary.TButton", command=lambda: self._show_workspace("run")).pack(side="left")

        cards = ttk.Frame(self.dashboard_tab, style="Page.TFrame")
        cards.pack(fill="x")
        for col in range(4):
            cards.columnconfigure(col, weight=1, uniform="dashboard-cards")

        self._dashboard_vars = {
            "workbook": tk.StringVar(value="Sin archivo"),
            "products": tk.StringVar(value="0"),
            "output": tk.StringVar(value="Sin carpeta"),
            "state": tk.StringVar(value="Pendiente"),
        }
        self._dashboard_card(cards, 0, "Archivo de trabajo", self._dashboard_vars["workbook"], "Plantilla Excel activa")
        self._dashboard_card(cards, 1, "Productos detectados", self._dashboard_vars["products"], "Identidades cargadas")
        self._dashboard_card(cards, 2, "Carpeta de salida", self._dashboard_vars["output"], "Excel, JSON y multimedia")
        self._dashboard_card(cards, 3, "Estado", self._dashboard_vars["state"], "Preparación del flujo")

        lower = ttk.Frame(self.dashboard_tab, style="Page.TFrame")
        lower.pack(fill="both", expand=True, pady=(14, 0))
        lower.columnconfigure(0, weight=2)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(0, weight=1)

        flow = ttk.LabelFrame(lower, text="Flujo recomendado", style="Card.TLabelframe")
        flow.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        steps = [
            ("1", "Analiza el Excel", "Detecta productos y atributos antes de buscar."),
            ("2", "Revisa identidades", "Corrige MPN/EAN/modelo si la plantilla necesita ajuste."),
            ("3", "Valida fuentes", "Prioriza URLs manuales y evidencia oficial compatible."),
            ("4", "Enriquece", "Multimedia y precios se procesan en módulos independientes."),
            ("5", "Genera y audita", "Crea la salida final conservando trazabilidad."),
        ]
        for index, (number, title, detail) in enumerate(steps):
            row = ttk.Frame(flow, style="Card.TFrame", padding=(4, 6))
            row.pack(fill="x")
            badge = tk.Label(row, text=number, bg="#dfe9ff", fg="#2158c7", width=3, font=("Segoe UI", 9, "bold"), padx=2, pady=5)
            badge.pack(side="left", padx=(0, 10))
            text = ttk.Frame(row, style="Card.TFrame")
            text.pack(side="left", fill="x", expand=True)
            ttk.Label(text, text=title, style="CardValue.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(text, text=detail, style="CardDetail.TLabel").pack(anchor="w", pady=(1, 0))

        quick = ttk.LabelFrame(lower, text="Accesos rápidos", style="Card.TLabelframe")
        quick.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        for label, key in [
            ("Revisar productos", "products"),
            ("Preparar fuentes", "sources"),
            ("Buscar multimedia", "media"),
            ("Comparar precios", "prices"),
            ("Ver auditoría", "audit"),
        ]:
            ttk.Button(quick, text=label, style="Secondary.TButton", command=lambda k=key: self._show_workspace(k)).pack(fill="x", pady=4)

    def _dashboard_card(self, parent, column: int, title: str, variable: tk.StringVar, detail: str):
        card = ttk.Frame(parent, style="Card.TFrame", padding=(15, 13))
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 3 else 6))
        ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(card, textvariable=variable, style="CardValue.TLabel", wraplength=220).pack(anchor="w", pady=(5, 3))
        ttk.Label(card, text=detail, style="CardDetail.TLabel").pack(anchor="w")

    def _map_existing_workspaces(self):
        for tab_id in self.notebook.tabs():
            text = str(self.notebook.tab(tab_id, "text"))
            low = text.lower()
            if text == "Inicio":
                self._workspace_tabs["dashboard"] = tab_id
            elif "productos" in low:
                self._workspace_tabs["products"] = tab_id
            elif "url" in low and "fuentes" in low:
                self._workspace_tabs["sources"] = tab_id
            elif "atributos" in low:
                self._workspace_tabs["attributes"] = tab_id
            elif "fotos" in low or "videos" in low:
                self._workspace_tabs["media"] = tab_id
            elif "precios" in low:
                self._workspace_tabs["prices"] = tab_id
            elif "ejecutar" in low:
                self._workspace_tabs["run"] = tab_id
            elif "logs" in low or "auditor" in low:
                self._workspace_tabs["audit"] = tab_id

    def _show_workspace(self, key: str):
        tab = self._workspace_tabs.get(key)
        if tab is None:
            return
        self.notebook.select(tab)
        self._active_workspace = key
        title, subtitle = _PAGE_COPY.get(key, (key.title(), ""))
        if hasattr(self, "_page_title"):
            self._page_title.set(title)
            self._page_subtitle.set(subtitle)
        for nav_key, button in self._nav_buttons.items():
            button.configure(style="NavActive.TButton" if nav_key == key else "Nav.TButton")
        if key == "dashboard":
            self._refresh_dashboard()

    def _restyle_existing_pages(self):
        def walk(widget):
            for child in widget.winfo_children():
                try:
                    if isinstance(child, ttk.Treeview):
                        child.configure(style="Modern.Treeview")
                    elif isinstance(child, ttk.LabelFrame):
                        child.configure(style="Card.TLabelframe")
                    elif isinstance(child, ttk.Button):
                        label = str(child.cget("text") or "")
                        if label.startswith(("INICIAR", "BUSCAR Y", "BUSCAR PRECIOS")):
                            child.configure(style="Primary.TButton")
                    elif isinstance(child, tk.Listbox):
                        child.configure(
                            bg="#ffffff",
                            fg="#27364b",
                            selectbackground="#dce8ff",
                            selectforeground="#172033",
                            relief="flat",
                            bd=0,
                            highlightthickness=1,
                            highlightbackground="#d9e0ea",
                        )
                    elif isinstance(child, tk.Text):
                        child.configure(
                            bg="#ffffff",
                            fg="#27364b",
                            relief="flat",
                            bd=0,
                            highlightthickness=1,
                            highlightbackground="#d9e0ea",
                            insertbackground="#27364b",
                        )
                    elif isinstance(child, tk.Canvas):
                        child.configure(bg="#ffffff")
                except (tk.TclError, AttributeError):
                    pass
                walk(child)

        for key, tab in self._workspace_tabs.items():
            if key == "dashboard":
                continue
            try:
                widget = self.nametowidget(str(tab)) if isinstance(tab, str) else tab
                walk(widget)
            except (KeyError, tk.TclError):
                continue

    def _bind_status_sources(self):
        def attach(variable):
            if variable is None:
                return
            try:
                variable.trace_add("write", lambda *_args, v=variable: self._set_global_status(v.get()))
            except (AttributeError, tk.TclError):
                return

        attach(getattr(self, "analysis_status", None))
        attach(getattr(self, "media_status", None))
        attach(getattr(self, "price_status", None))
        try:
            self.excel.trace_add("write", lambda *_args: self._refresh_dashboard())
            self.out.trace_add("write", lambda *_args: self._refresh_dashboard())
        except (AttributeError, tk.TclError):
            pass

    def _set_global_status(self, value: str):
        text = str(value or "").strip()
        if text and hasattr(self, "global_status"):
            self.global_status.set(text)
        self._refresh_dashboard()

    def _refresh_dashboard(self):
        if not self._dashboard_vars:
            return
        excel_path = str(self.excel.get() or "").strip() if hasattr(self, "excel") else ""
        output_path = str(self.out.get() or "").strip() if hasattr(self, "out") else ""
        product_count = len(getattr(self, "product_rows", []) or [])
        status = str(self.analysis_status.get() or "").strip() if hasattr(self, "analysis_status") else ""

        workbook = Path(excel_path).name if excel_path else "Sin archivo"
        output = Path(output_path).name if output_path else "Sin carpeta"
        if product_count:
            state = "Listo para investigar"
        elif excel_path:
            state = "Analiza el archivo"
        else:
            state = "Selecciona un Excel"

        self._dashboard_vars["workbook"].set(workbook)
        self._dashboard_vars["products"].set(str(product_count))
        self._dashboard_vars["output"].set(output)
        self._dashboard_vars["state"].set(state)
        if hasattr(self, "_header_file"):
            self._header_file.set(workbook if excel_path else "Sin archivo seleccionado")
        if status and hasattr(self, "global_status") and self._active_workspace == "dashboard":
            self.global_status.set(status)

    def analyze_excel(self):
        super().analyze_excel()
        self._refresh_dashboard()
        if hasattr(self, "analysis_status"):
            self._set_global_status(self.analysis_status.get())


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
