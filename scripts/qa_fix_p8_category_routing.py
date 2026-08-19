from pathlib import Path

PATH = Path("src/product_intelligence/product_classification.py")
text = PATH.read_text(encoding="utf-8")
anchor = '''        ("AUDIO", ("headphones", "headphone", "headset", "earbuds", "earphones", "speaker", "microphone", "audio device")),\n        ("ACCESSORY", ("mouse accessory", "wireless mouse", "computer mouse", "keyboard", "dock", "docking station", "charger", "charging cable", "usb cable", "accessory")),\n'''
replacement = '''        ("AUDIO", ("headphones", "headphone", "headset", "earbuds", "earphones", "speaker", "microphone", "audio device")),\n        ("TOOL", ("power tool", "cordless drill", "power drill", "impact driver", "angle grinder", "rotary hammer", "taladro", "amoladora", "esmeril angular")),\n        ("APPLIANCE", ("microwave oven", "refrigerator", "washing machine", "dishwasher", "vacuum cleaner", "air fryer", "blender appliance", "microondas", "refrigeradora", "lavadora", "aspiradora")),\n        ("BABY_CARE", ("baby diapers", "baby diaper", "diapers size", "pañales bebe", "pañales bebé", "panales bebe", "panales bebé")),\n        ("ACCESSORY", ("mouse accessory", "wireless mouse", "computer mouse", "keyboard", "dock", "docking station", "charger", "charging cable", "usb cable", "accessory")),\n'''
if replacement in text:
    print("P8_CATEGORY_ROUTING_PATCH=ALREADY_APPLIED")
elif anchor in text:
    PATH.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")
    print("P8_CATEGORY_ROUTING_PATCH=APPLIED")
else:
    raise SystemExit("P8 category patch abort: classifier anchor missing")
