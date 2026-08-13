from .price_desktop import App as PriceApp
from .ui_process import ProcessRegistry
from .ui_theme import configure_business_theme

class App(PriceApp):
    def __init__(self):
        self.process_registry=ProcessRegistry()
        super().__init__()
        configure_business_theme(self)
        self.title("Product Intelligence")
        self.geometry("1440x900")


def main():
    App().mainloop()

if __name__=="__main__":
    main()
