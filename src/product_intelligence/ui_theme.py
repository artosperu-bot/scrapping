from tkinter import ttk

BG="#f4f7fb"; CARD="#ffffff"; INK="#172033"; MUTED="#667085"; BLUE="#1f5fbf"; BLUE_DARK="#174a96"; BORDER="#d8e0ea"; OK="#16794b"; ERROR="#b42318"

def configure_business_theme(root):
    root.configure(bg=BG)
    style=ttk.Style(root)
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("TFrame",background=BG)
    style.configure("Card.TFrame",background=CARD,relief="solid",borderwidth=1)
    style.configure("TLabel",background=BG,foreground=INK,font=("Segoe UI",9))
    style.configure("Card.TLabel",background=CARD,foreground=INK,font=("Segoe UI",9))
    style.configure("Title.TLabel",background=BG,foreground=INK,font=("Segoe UI Semibold",18))
    style.configure("Section.TLabel",background=BG,foreground=INK,font=("Segoe UI Semibold",11))
    style.configure("Muted.TLabel",background=BG,foreground=MUTED,font=("Segoe UI",9))
    style.configure("Primary.TButton",font=("Segoe UI Semibold",9),padding=(14,8),foreground="white",background=BLUE)
    style.map("Primary.TButton",background=[("active",BLUE_DARK),("disabled","#9bb7dd")])
    style.configure("TButton",font=("Segoe UI",9),padding=(10,6))
    style.configure("TNotebook",background=BG,borderwidth=0)
    style.configure("TNotebook.Tab",font=("Segoe UI Semibold",9),padding=(12,8))
    style.map("TNotebook.Tab",background=[("selected",CARD)],foreground=[("selected",BLUE)])
    style.configure("Treeview",font=("Segoe UI",9),rowheight=27,background=CARD,fieldbackground=CARD,bordercolor=BORDER)
    style.configure("Treeview.Heading",font=("Segoe UI Semibold",9),background="#edf2f8",foreground=INK)
    style.configure("Horizontal.TProgressbar",background=BLUE,troughcolor="#e8eef6")
    style.configure("TLabelframe",background=BG,bordercolor=BORDER)
    style.configure("TLabelframe.Label",background=BG,foreground=INK,font=("Segoe UI Semibold",9))
