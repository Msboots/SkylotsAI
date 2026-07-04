from modules_skylots import get_lots

lots = get_lots()

print(f"Получено {len(lots)} лотов\n")

for lot in lots[:10]:
    print("=" * 60)
    print(lot["title"])
    print(lot["price"])
    print(lot["seller"])
    print(lot["end"])
    print(lot["url"])

