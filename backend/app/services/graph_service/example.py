# demo.py
from config import get_driver
from graph_db import GraphDB


def main():
    driver = get_driver()
    db = GraphDB(driver)

    # Очищаем БД перед демонстрацией
    db.clear()

    # ============================================================
    # 1) ДОБАВЛЕНИЕ ДАННЫХ
    # ============================================================
    # JSON-строка от парсера — так её выдаёт нейросеть
    graph_json = '''
    {
        "nodes": [
            {"id": 1, "type": "publication", "name": "Отчёт по BCL", "props": {"year": 2011}},
            {"id": 2, "type": "expert",      "name": "Иванов И.И."},
            {"id": 3, "type": "process",     "name": "Взвешенная плавка", "props": {"technology": "Outokumpu"}},
            {"id": 4, "type": "material",    "name": "Никель", "props": {"formula": "Ni"}},
            {"id": 5, "type": "parameter",   "name": "Температура", "props": {"unit": "K", "value": 1673.15}},
            {"id": 6, "type": "equipment",   "name": "Печь взвешенной плавки"}
        ],
        "edges": [
            {"from": 2, "to": 1, "type": "wrote", "pages": [1]},
            {"from": 1, "to": 3, "type": "describes", "pages": [2, 3]},
            {"from": 3, "to": 4, "type": "uses_material", "pages": [3]},
            {"from": 3, "to": 5, "type": "has_parameter", "pages": [4]},
            {"from": 5, "to": 3, "type": "characterizes", "pages": [4]},
            {"from": 3, "to": 6, "type": "uses_equipment", "pages": [3]}
        ]
    }
    '''

    print("=" * 60)
    print("ДОБАВЛЕНИЕ В БД")
    print("=" * 60)
    stats = db.add(graph_json)
    print(f"Создано узлов: {stats['nodes_created']}")
    print(f"Создано рёбер: {stats['edges_created']}")

    # ============================================================
    # 2) ПРОВЕРКА КОРРЕКТНОСТИ
    # ============================================================
    # Граф с нарушением: материал не может иметь исходящих рёбер
    bad_graph_json = '''
    {
        "nodes": [
            {"id": 1, "type": "material", "name": "Медь"},
            {"id": 2, "type": "process",  "name": "Плавка"}
        ],
        "edges": [
            {"from": 1, "to": 2, "type": "uses_material"}
        ]
    }
    '''

    print("\n" + "=" * 60)
    print("ПРОВЕРКА КОРРЕКТНОСТИ")
    print("=" * 60)
    ok, fixed, fixes = db.isCorrect(bad_graph_json)
    print(f"Нарушений нет: {ok}")
    print(f"Исправлений: {len(fixes)}")
    for f in fixes:
        print(f"  • {f}")

    # ============================================================
    # 3) ПОИСК — простые запросы в виде JSON-строк
    # ============================================================
    print("\n" + "=" * 60)
    print("ПОИСК ПО ГРАФУ")
    print("=" * 60)

    # --- Запрос 1: точное совпадение ---
    print("\n[Запрос 1] Какие процессы связаны с Никелем?")
    query1 = '''
    {
        "nodes": [
            {"id": 100, "type": "process",  "name": null},
            {"id": 101, "type": "material", "name": "Никель"}
        ],
        "edges": [{"from": 100, "to": 101}]
    }
    '''
    for r in db.find(query1):
        print(f"  → Публикация: {r['publication']['name']} ({r['publication']['year']})")
        print(f"    Страницы: {r['pages']}")

    # --- Запрос 2: одно из нескольких имён ---
    print("\n[Запрос 2] Оборудование для 'Взвешенная плавка' ИЛИ 'ПВП'")
    query2 = '''
    {
        "nodes": [
            {"id": 100, "type": "process",   "name": ["Взвешенная плавка", "ПВП"]},
            {"id": 101, "type": "equipment", "name": null}
        ],
        "edges": [{"from": 100, "to": 101}]
    }
    '''
    for r in db.find(query2):
        print(f"  → Публикация: {r['publication']['name']}")
        print(f"    Страницы: {r['pages']}")

    # --- Запрос 3: связь через промежуточные узлы ---
    print("\n[Запрос 3] Как 'Взвешенная плавка' связана с 'Никелем'?")
    query3 = '''
    {
        "nodes": [
            {"id": 100, "type": "process",  "name": "Взвешенная плавка"},
            {"id": 101, "type": "material", "name": "Никель"}
        ],
        "edges": [{"from": 100, "to": 101}]
    }
    '''
    for r in db.find(query3, max_path_length=3):
        print(f"  → Публикация: {r['publication']['name']}")
        print(f"    Страницы: {r['pages']}")
        print(f"    Узлы на пути: {[n['name'] for n in r['matched_nodes']]}")

    # ============================================================
    # 4) УДАЛЕНИЕ
    # ============================================================
    print("\n" + "=" * 60)
    print("УДАЛЕНИЕ")
    print("=" * 60)

    # Попытка удалить разделяемый материал — система откажет
    print("\n[Попытка] Удалить 'Никель' без cascade:")
    remove1 = '''
    {
        "type": "material",
        "name": "Никель",
        "cascade": false
    }
    '''
    res = db.remove(remove1)
    print(f"  Отказ: {res['refused']}")
    print(f"  Причина: {res['reason']}")

    # Удаление публикации — свободно
    print("\n[Удаление] Публикация 'Отчёт по BCL' с cascade:")
    remove2 = '''
    {
        "type": "publication",
        "name": "Отчёт по BCL",
        "cascade": true
    }
    '''
    res = db.remove(remove2)
    print(f"  Удалено узлов: {res['nodes_deleted']}")
    print(f"  Удалено рёбер: {res['edges_deleted']}")

    db.close()


if __name__ == "__main__":
    main()