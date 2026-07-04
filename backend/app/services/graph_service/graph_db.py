# graph_db.py
"""
GraphDB — обёртка над Neo4j с реализацией методов:
  isCorrect(graph_json) -> (is_ok, fixed_graph_json, list_of_fixes)
  add(graph_json)       -> stats dict
  remove(node_selector) -> stats dict
  find(query_subgraph)  -> list of publications with context
"""
from __future__ import annotations
import copy
import json
from collections import defaultdict
from typing import Any
from neo4j import GraphDatabase
import json as json_lib
from typing import Union, Any

from app.services.graph_service.schema import (
    VALID_NODE_TYPES, VALID_EDGE_TYPES, ADJACENCY_MATRIX,
    LEAF_TYPES, PARAMETER_OUT_DEGREE,
)


class GraphDB:
    def __init__(self, driver: GraphDatabase.driver):
        self.driver = driver

    def clear(self, batch_size: int = 10000) -> dict:
        """
        Полностью очищает базу данных Neo4j.

        Args:
            batch_size: размер пакета для удаления (для больших графов).
                        Если None — удаляет всё за один запрос.

        Returns:
            dict со статистикой: nodes_deleted, edges_deleted, iterations
        """
        stats = {"nodes_deleted": 0, "edges_deleted": 0, "iterations": 0}

        with self.driver.session() as session:
            if batch_size is None:
                # Простой вариант — для небольших графов
                result = session.run("""
                    MATCH (n)
                    WITH count(n) AS nodes_before
                    OPTIONAL MATCH (n)-[r]-()
                    WITH nodes_before, count(r) / 2 AS edges_before
                    DETACH DELETE n
                    RETURN nodes_before, edges_before
                """).single()

                if result:
                    stats["nodes_deleted"] = result.get("nodes_before", 0) or 0
                    stats["edges_deleted"] = result.get("edges_before", 0) or 0
                stats["iterations"] = 1
            else:
                # Пакетное удаление — для больших графов (без падения по памяти)
                while True:
                    result = session.run("""
                        MATCH (n)
                        WITH n LIMIT $batch
                        OPTIONAL MATCH (n)-[r]-()
                        WITH n, count(r) AS rel_count
                        DETACH DELETE n
                        RETURN count(n) AS deleted_nodes, sum(rel_count) AS deleted_rels
                    """, batch=batch_size).single()

                    deleted_nodes = result.get("deleted_nodes", 0) or 0
                    deleted_rels = result.get("deleted_rels", 0) or 0

                    stats["nodes_deleted"] += deleted_nodes
                    # Каждое ребро считается дважды (с обоих концов)
                    stats["edges_deleted"] += deleted_rels // 2
                    stats["iterations"] += 1

                    if deleted_nodes == 0:
                        break

        return stats

    # ------------------------------------------------------------------ #
    #  0) Нормализация JSON                                              #
    # ------------------------------------------------------------------ #
    def _normalize_graph(self, data: Union[str, dict]) -> dict:
        """
        Принимает JSON-строку или dict и приводит к каноническому формату:
        {
            "nodes": [{"id": ..., "type": ..., "name": ..., "props": {...}}, ...],
            "edges": [{"from": ..., "to": ..., "type": ..., "pages": [...], "params": {...}}, ...]
        }

        Добавляет недостающие поля, проверяет обязательные.
        """
        # 1. Парсим строку
        if isinstance(data, str):
            try:
                data = json_lib.loads(data)
            except json_lib.JSONDecodeError as e:
                raise ValueError(f"Невалидный JSON: {e}")
        if not isinstance(data, dict):
            raise TypeError(f"Ожидается str или dict, получено {type(data)}")

        # 2. Нормализуем узлы
        nodes = []
        for i, n in enumerate(data.get("nodes", [])):
            if not isinstance(n, dict):
                raise ValueError(f"Узел #{i} не является dict: {n}")
            if "id" not in n:
                raise ValueError(f"Узел #{i} без id: {n}")
            if "type" not in n:
                raise ValueError(f"Узел {n['id']} без type")

            node = {
                "id": n["id"],
                "type": n["type"],
                "name": n.get("name", ""),
                "props": n.get("props", {}) or {},
            }
            nodes.append(node)

        # 3. Нормализуем рёбра
        edges = []
        node_ids = {n["id"] for n in nodes}
        for i, e in enumerate(data.get("edges", [])):
            if not isinstance(e, dict):
                raise ValueError(f"Ребро #{i} не является dict: {e}")
            if "from" not in e or "to" not in e:
                raise ValueError(f"Ребро #{i} без from/to: {e}")
            if e["from"] not in node_ids:
                raise ValueError(f"Ребро #{i}: узел from={e['from']} не найден")
            if e["to"] not in node_ids:
                raise ValueError(f"Ребро #{i}: узел to={e['to']} не найден")
            if "type" not in e:
                raise ValueError(f"Ребро {e['from']}->{e['to']} без type")

            edge = {
                "from": e["from"],
                "to": e["to"],
                "type": e["type"],
                "pages": e.get("pages", []) or [],
                "params": e.get("params", {}) or {},
            }
            edges.append(edge)

        return {"nodes": nodes, "edges": edges}

    def _normalize_selector(self, data: Union[str, dict]) -> dict:
        """
        Нормализует селектор для remove.
        Принимает JSON-строку или dict вида:
        {
            "type": "publication",
            "name": "..." | None,
            "id": "..." | None,
            "cascade": True|False
        }
        """
        if isinstance(data, str):
            try:
                data = json_lib.loads(data)
            except json_lib.JSONDecodeError as e:
                raise ValueError(f"Невалидный JSON: {e}")
        if not isinstance(data, dict):
            raise TypeError(f"Ожидается str или dict, получено {type(data)}")

        if "type" not in data:
            raise ValueError("Селектор должен содержать 'type'")

        return {
            "type": data["type"],
            "name": data.get("name"),
            "id": data.get("id"),
            "cascade": bool(data.get("cascade", False)),
        }

    def _normalize_query(self, data: Union[str, dict]) -> dict:
        """
        Нормализует запрос для find.
        Принимает JSON-строку или dict вида:
        {
            "nodes": [{"id": ..., "type": ..., "name": ... | [...], "props": {...}}, ...],
            "edges": [{"from": ..., "to": ..., "type": ...}, ...]
        }
        """
        if isinstance(data, str):
            try:
                data = json_lib.loads(data)
            except json_lib.JSONDecodeError as e:
                raise ValueError(f"Невалидный JSON: {e}")
        if not isinstance(data, dict):
            raise TypeError(f"Ожидается str или dict, получено {type(data)}")

        # Узлы
        nodes = []
        for i, n in enumerate(data.get("nodes", [])):
            if not isinstance(n, dict):
                raise ValueError(f"Узел запроса #{i} не является dict")
            if "id" not in n:
                raise ValueError(f"Узел запроса #{i} без id")
            if "type" not in n:
                raise ValueError(f"Узел запроса {n['id']} без type")

            node = {
                "id": n["id"],
                "type": n["type"],
                "name": n.get("name"),  # может быть None, str или list
                "props": n.get("props", {}) or {},
            }
            nodes.append(node)

        # Рёбра
        edges = []
        for i, e in enumerate(data.get("edges", [])):
            if not isinstance(e, dict):
                raise ValueError(f"Ребро запроса #{i} не является dict")
            if "from" not in e or "to" not in e:
                raise ValueError(f"Ребро запроса #{i} без from/to")

            edge = {
                "from": e["from"],
                "to": e["to"],
                "type": e.get("type", "ANY"),  # тип ребра опционален для find
            }
            edges.append(edge)

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------ #
    #  Публичные обёртки                                                  #
    # ------------------------------------------------------------------ #
    def add(self, data: Union[str, dict]) -> dict:
        """
        Публичная обёртка над _add.
        Принимает JSON-строку или dict, нормализует и добавляет в БД.
        """
        graph = self._normalize_graph(data)
        return self._add(graph)

    def remove(self, data: Union[str, dict]) -> dict:
        """
        Публичная обёртка над _remove.
        Принимает JSON-строку или dict-селектор.
        """
        selector = self._normalize_selector(data)
        return self._remove(selector)

    def find(self, data: Union[str, dict], max_path_length: int = 3) -> list[dict]:
        """
        Публичная обёртка над _find.
        Принимает JSON-строку или dict-шаблон.
        """
        query = self._normalize_query(data)
        return self._find(query, max_path_length=max_path_length)

    def isCorrect(self, data: Union[str, dict]) -> tuple[bool, dict, list[str]]:
        """
        Публичная обёртка.
        Принимает JSON-строку или dict.
        """
        graph = self._normalize_graph(data)
        return self._isCorrect(graph)

    # ------------------------------------------------------------------ #
    #  1) isCorrect — проверка и лёгкое исправление графа                #
    # ------------------------------------------------------------------ #
    def _isCorrect(self, graph: dict) -> tuple[bool, dict, list[str]]:
        """
        Проверяет граф на соответствие инвариантам.
        Возвращает:
          - is_ok: были ли нарушения
          - fixed_graph: исправленная копия графа
          - fixes: список применённых исправлений (описания)
        """
        g = copy.deepcopy(graph)
        fixes: list[str] = []

        nodes = g.get("nodes", [])
        edges = g.get("edges", [])

        # --- 1. Проверка типов узлов ---
        valid_nodes = []
        node_ids = set()
        for n in nodes:
            if n.get("type") not in VALID_NODE_TYPES:
                fixes.append(f"Удалён узел {n.get('id')} с недопустимым типом '{n.get('type')}'")
                continue
            valid_nodes.append(n)
            node_ids.add(n["id"])
        g["nodes"] = valid_nodes

        # --- 2. Проверка и исправление рёбер ---
        valid_edges = []
        for e in edges:
            src_id, dst_id, etype = e.get("from"), e.get("to"), e.get("type")

            # узлы существуют?
            if src_id not in node_ids or dst_id not in node_ids:
                fixes.append(f"Удалено ребро {src_id}->{dst_id}: узел не существует")
                continue

            # тип ребра допустим?
            if etype not in VALID_EDGE_TYPES:
                # попробуем перевернуть
                rev_key = (self._type_of(g, dst_id), etype, self._type_of(g, src_id))
                if (self._type_of(g, dst_id), etype) in {
                    (k[0], k[1]) for k in ADJACENCY_MATRIX
                } and self._type_of(g, src_id) in ADJACENCY_MATRIX.get(
                    (self._type_of(g, dst_id), etype), set()
                ):
                    e["from"], e["to"] = e["to"], e["from"]
                    fixes.append(f"Ребро {src_id}->{dst_id} ({etype}) перевернуто")
                    valid_edges.append(e)
                else:
                    fixes.append(f"Удалено ребро {src_id}->{dst_id} ({etype}): недопустимый тип")
                continue

            src_t = self._type_of(g, e["from"])
            dst_t = self._type_of(g, e["to"])
            allowed_dsts = ADJACENCY_MATRIX.get((src_t, etype), set())

            if dst_t not in allowed_dsts:
                # пробуем перевернуть
                rev_allowed = ADJACENCY_MATRIX.get((dst_t, etype), set())
                if src_t in rev_allowed:
                    e["from"], e["to"] = e["to"], e["from"]
                    fixes.append(f"Ребро {src_id}->{dst_id} ({etype}) перевернуто")
                    valid_edges.append(e)
                else:
                    fixes.append(f"Удалено ребро {src_id}->{dst_id} ({etype}): {src_t}-[{etype}]->{dst_t} запрещено")
                continue

            valid_edges.append(e)

        g["edges"] = valid_edges

        # --- 3. Листовые узлы: удаляем исходящие рёбра у Material/Equipment/Facility ---
        new_edges = []
        for e in g["edges"]:
            src_t = self._type_of(g, e["from"])
            if src_t in LEAF_TYPES:
                fixes.append(f"Удалено исходящее ребро от листа {e['from']} ({src_t})")
                continue
            new_edges.append(e)
        g["edges"] = new_edges

        # --- 4. Параметр: ровно одно исходящее ребро ---
        out_counts: dict[int, list] = defaultdict(list)
        for e in g["edges"]:
            if self._type_of(g, e["from"]) == "parameter":
                out_counts[e["from"]].append(e)

        new_edges = []
        kept_edges_ids = set()
        for pid, outs in out_counts.items():
            if len(outs) == 0:
                fixes.append(f"Параметр {pid} удалён: нет исходящих рёбер (лист)")
                # удалим узел
                g["nodes"] = [n for n in g["nodes"] if n["id"] != pid]
                # и все входящие к нему
                g["edges"] = [e for e in g["edges"] if e["to"] != pid]
                continue
            if len(outs) > 1:
                # оставляем первое, остальные удаляем
                kept = outs[0]
                kept_edges_ids.add(id(kept))
                for extra in outs[1:]:
                    fixes.append(
                        f"У параметра {pid} было {len(outs)} исходящих — оставлено одно, "
                        f"удалено {extra['from']}->{extra['to']} ({extra['type']})"
                    )
            else:
                kept_edges_ids.add(id(outs[0]))

        g["edges"] = [
            e for e in g["edges"]
            if self._type_of(g, e["from"]) != "parameter" or id(e) in kept_edges_ids
        ]

        # --- 5. Удаление транзитивных дублей: если Process->Parameter->Material,
        #        то Process->Material (через uses_material) можно убрать,
        #        т.к. есть путь через параметр. ---
        # (опционально — делаем по запросу; ниже простая эвристика)
        g["edges"] = self._remove_transitive_redundancy(g, fixes)

        is_ok = len(fixes) == 0
        return is_ok, json.dumps(g), fixes

    # ------------------------------------------------------------------ #
    #  2) add — добавление графа в БД с дедупликацией                    #
    # ------------------------------------------------------------------ #
    def _add(self, graph: dict) -> dict:
        """
        Добавляет корректный граф в Neo4j.
        Дедупликация:
          - Material/Equipment/Facility/Expert/Publication/Process/Experiment — по (type, name)
          - Parameter — всегда создаётся новый (по ТЗ)
        Возвращает статистику: сколько узлов создано/найдено, сколько рёбер добавлено.
        """
        # Сначала проверяем/чиним
        is_ok, fixed, fixes = self.isCorrect(graph)
        fixed = self._normalize_graph(fixed)
        # (можно залогировать fixes)

        stats = {"nodes_created": 0, "nodes_matched": 0, "edges_created": 0}

        # Словарь: старый id -> новый (внутренний) id в БД
        id_map: dict[int, int] = {}

        with self.driver.session() as session:
            # --- Узлы ---
            for n in fixed["nodes"]:
                ntype = n["type"]
                name = n.get("name", "")
                props = n.get("props", {}) or {}
                props["name"] = name

                # Parameter — всегда новый
                if ntype == "parameter":
                    result = session.run(
                        f"CREATE (n:{ntype.capitalize()} $props) RETURN elementId(n) AS nid",
                        props=props,
                    )
                    new_id = result.single()["nid"]
                    id_map[n["id"]] = new_id
                    stats["nodes_created"] += 1
                else:
                    # MERGE по (type, name)
                    result = session.run(
                        f"""
                        MERGE (n:{ntype.capitalize()} {{name: $name}})
                        ON CREATE SET n += $props, n.created_at = timestamp()
                        ON MATCH  SET n.updated_at = timestamp()
                        RETURN elementId(n) AS nid,
                               CASE WHEN n.created_at = timestamp()
                                    THEN 'created' ELSE 'matched' END AS status
                        """,
                        props=props, name=name,
                    )
                    rec = result.single()
                    id_map[n["id"]] = rec["nid"]
                    if rec["status"] == "created":
                        stats["nodes_created"] += 1
                    else:
                        stats["nodes_matched"] += 1

            # --- Рёбра ---
            for e in fixed["edges"]:
                src = id_map.get(e["from"])
                dst = id_map.get(e["to"])
                if src is None or dst is None:
                    continue
                etype = e["type"].upper()

                # Сериализуем params в JSON-строку, т.к. Neo4j не поддерживает вложенные словари
                import json
                props = {
                    "pages": e.get("pages", []),
                    "params_json": json.dumps(e.get("params", {}), ensure_ascii=False),
                }

                # MERGE ребра, чтобы не дублировать
                session.run(
                    f"""
                    MATCH (a), (b)
                    WHERE elementId(a) = $src AND elementId(b) = $dst
                    MERGE (a)-[r:{etype}]->(b)
                    SET r += $props
                    """,
                    src=src, dst=dst, props=props,
                )
                stats["edges_created"] += 1

        return stats

    # ------------------------------------------------------------------ #
    #  3) remove — удаление сущностей                                    #
    # ------------------------------------------------------------------ #
    def _remove(self, selector: dict) -> dict:
        """
        Удаляет сущности по селектору.
        selector = {
            "type": "publication" | "process" | "material" | ...,
            "name": "название" | None,
            "id":   внутренний id Neo4j | None,
            "cascade": True|False  # удалять ли осиротевшие узлы
        }

        Правила:
          - Publication: удаляется вместе со всеми своими рёбрами;
                         если cascade=True — удаляются осиротевшие Experiment/Parameter,
                         у которых не осталось других Publication-предков.
          - Expert: удаляется, рёбра 'wrote' удаляются.
          - Material/Equipment/Facility: удаляются только если cascade=True
                         (иначе — отказ, т.к. они разделяемые); при удалении
                         обрываются все входящие рёбра.
          - Process/Experiment: удаляются со всеми своими рёбрами;
                         при cascade=True — удаляются осиротевшие Parameter.
          - Parameter: удаляется всегда (он и так «одноразовый»).
        """
        ntype = selector.get("type")
        name = selector.get("name")
        nid = selector.get("id")
        cascade = bool(selector.get("cascade", False))

        if ntype not in VALID_NODE_TYPES:
            raise ValueError(f"Недопустимый тип: {ntype}")

        stats = {"nodes_deleted": 0, "edges_deleted": 0, "refused": False, "reason": ""}

        # Для разделяемых сущностей без cascade — отказываем, если есть связи
        shared_types = {"material", "equipment", "facility"}
        if ntype in shared_types and not cascade:
            with self.driver.session() as session:
                q = f"""
                MATCH (n:{ntype.capitalize()})
                WHERE ($id IS NULL OR elementId(n) = $id)
                  AND ($name IS NULL OR n.name = $name)
                OPTIONAL MATCH (n)-[r]-()
                WITH n, count(r) AS degree
                RETURN count(n) AS cnt, avg(degree) AS avg_deg
                """
                rec = session.run(q, id=nid, name=name).single()
                if rec["cnt"] == 0:
                    return stats
                if rec["avg_deg"] and rec["avg_deg"] > 0:
                    stats["refused"] = True
                    stats["reason"] = (
                        f"{ntype} — разделяемая сущность с {rec['cnt']} узлами и связями. "
                        "Укажите cascade=True для принудительного удаления."
                    )
                    return stats

        with self.driver.session() as session:
            # Собираем целевые узлы
            q_match = f"""
            MATCH (n:{ntype.capitalize()})
            WHERE ($id IS NULL OR elementId(n) = $id)
              AND ($name IS NULL OR n.name = $name)
            RETURN elementId(n) AS nid
            """
            targets = [r["nid"] for r in session.run(q_match, id=nid, name=name)]
            if not targets:
                return stats

            if cascade:
                # Находим осиротевших детей (Parameter, Experiment),
                # у которых не останется родителей после удаления
                # Для простоты: удаляем всех детей-параметров, у которых степень входа == 1
                session.run(
                    """
                    MATCH (target)
                    WHERE elementId(target) IN $targets
                    OPTIONAL MATCH (target)-[r]->(child:Parameter)
                    WITH child, count(r) AS in_deg
                    WHERE child IS NOT NULL AND in_deg = 1
                    DETACH DELETE child
                    """,
                    targets=targets,
                )

            # Считаем рёбра ПЕРЕД удалением
            res = session.run(
                """
                MATCH (n) WHERE elementId(n) IN $targets
                OPTIONAL MATCH (n)-[r]-()
                WITH n, count(r) AS deg
                RETURN sum(deg) AS edges
                """,
                targets=targets,
            ).single()

            # Каждое ребро считается дважды (один раз для каждого конца),
            # но если ребро соединяет два удаляемых узла, оно считается 4 раза.
            # Для простоты: делим на 2
            stats["edges_deleted"] = (res["edges"] or 0) // 2

            # DETACH DELETE
            session.run(
                "MATCH (n) WHERE elementId(n) IN $targets DETACH DELETE n",
                targets=targets,
            )
            stats["nodes_deleted"] = len(targets)

        return stats
    # ------------------------------------------------------------------ #
    #  4) find — поиск подграфа-шаблона и подъём к публикациям           #
    # ------------------------------------------------------------------ #

    def _find(self, query_subgraph: dict, max_path_length: int = 3) -> list[dict]:
        """
        Ищет подграф-шаблон в БД с поддержкой путей переменной длины.

        Для каждого узла в шаблоне поле 'name' может быть:
          - строкой: точное совпадение (name = 'X')
          - списком строк: совпадение с одним из (name IN ['X', 'Y', 'Z'])
          - None или отсутствует: фильтр не применяется (подходит любой узел данного типа)

        Для каждого ребра в шаблоне ищутся пути длиной от 1 до max_path_length
        с ЛЮБЫМИ типами рёбер. Это позволяет находить связи через промежуточные узлы.
        """
        nodes = query_subgraph.get("nodes", [])
        edges = query_subgraph.get("edges", [])

        if not nodes:
            return []

        # 1. Собираем узлы шаблона
        match_parts = []
        where_parts = []
        params = {}
        var_map = {}

        for i, n in enumerate(nodes):
            var = f"n{i}"
            var_map[n["id"]] = var
            label = n["type"].capitalize()
            match_parts.append(f"({var}:{label})")

            # Обработка name: строка / список / None
            name = n.get("name")
            if name is not None:
                if isinstance(name, list):
                    # Список → IN [...]
                    where_parts.append(f"{var}.name IN $name_{i}")
                    params[f"name_{i}"] = name
                else:
                    # Строка → точное совпадение
                    where_parts.append(f"{var}.name = $name_{i}")
                    params[f"name_{i}"] = name

            # Прочие свойства (только точное совпадение)
            for k, v in (n.get("props") or {}).items():
                if k == "name":
                    continue
                where_parts.append(f"{var}.{k} = ${k}_{i}")
                params[f"{k}_{i}"] = v

        # 2. Строим Cypher с путями переменной длины (любой тип ребра)
        cypher = "MATCH " + ",\n  ".join(match_parts)

        if where_parts:
            cypher += "\nWHERE " + " AND ".join(where_parts)

        # Для каждого ребра в шаблоне — путь переменной длины с ЛЮБЫМИ типами рёбер
        path_vars = []
        for idx, e in enumerate(edges):
            src_var = var_map.get(e["from"])
            dst_var = var_map.get(e["to"])
            if src_var and dst_var:
                path_var = f"path{idx}"
                path_vars.append(path_var)
                cypher += f"\nMATCH {path_var} = ({src_var})-[*1..{max_path_length}]->({dst_var})"

        # 3. Поднимаемся к Publication и собираем страницы БЕЗ дублирования
        vars_list = list(var_map.values())

        cypher += f"""
        // Собираем все рёбра со всех найденных путей
        WITH {', '.join(vars_list)}, {', '.join(path_vars)}
        UNWIND [{', '.join(path_vars)}] AS path
        UNWIND relationships(path) AS rel
        WITH {', '.join(vars_list)}, collect(distinct rel) AS all_path_rels

        // Поднимаемся к Publication
        OPTIONAL MATCH (pub:Publication)-[d:DESCRIBES|DESCRIBES_PARAMETER]->(any_matched)
        WHERE any_matched IN [{', '.join(vars_list)}]
        WITH {', '.join(vars_list)}, all_path_rels,
             collect(distinct pub) AS pubs,
             collect(distinct d) AS desc_rels

        // Собираем страницы ОТДЕЛЬНО для path_rels (избегаем декартова произведения)
        UNWIND all_path_rels AS path_rel
        WITH {', '.join(vars_list)}, pubs, desc_rels, collect(distinct path_rel.pages) AS path_pages_list

        // Собираем страницы ОТДЕЛЬНО для desc_rels
        UNWIND desc_rels AS desc_rel
        WITH {', '.join(vars_list)}, pubs, path_pages_list, collect(distinct desc_rel.pages) AS desc_pages_list

        RETURN pubs, 
               path_pages_list + desc_pages_list AS all_pages_list,
               {', '.join([f'{v} AS {v}' for v in vars_list])}
        """

        results = []
        with self.driver.session() as session:
            recs = session.run(cypher, **params)
            for rec in recs:
                pubs = rec["pubs"] or []
                all_pages_list = rec["all_pages_list"] or []

                # Собираем все страницы в один набор
                pages = set()
                for p_list in all_pages_list:
                    if isinstance(p_list, list):
                        pages.update(p_list)

                for pub in pubs:
                    # Исправляем работу с labels (frozenset)
                    matched_nodes = []
                    for v in vars_list:
                        if rec.get(v) is not None:
                            node = rec[v]
                            node_type = next(iter(node.labels)) if node.labels else None
                            matched_nodes.append({
                                "var": v,
                                "type": node_type,
                                "name": node.get("name"),
                            })

                    results.append({
                        "publication": {
                            "id": pub.element_id,
                            "name": pub.get("name"),
                            "year": pub.get("year"),
                        },
                        "pages": sorted(pages),
                        "matched_nodes": matched_nodes,
                    })
        return results

    # ------------------------------------------------------------------ #
    #  Вспомогательные методы                                            #
    # ------------------------------------------------------------------ #
    def _type_of(self, graph: dict, node_id: int) -> str:
        for n in graph["nodes"]:
            if n["id"] == node_id:
                return n["type"]
        raise KeyError(f"Узел {node_id} не найден")

    def _remove_transitive_redundancy(self, graph: dict, fixes: list) -> list:
        """
        Если есть Process -[has_parameter]-> Parameter -[relates_to]-> Material,
        то прямое ребро Process -[uses_material]-> Material можно удалить
        (информация уже закодирована через параметр).
        """
        # строим индекс рёбер
        edges = graph["edges"]
        # ищем пары: (P -has_parameter-> Param -relates_to-> M)
        indirect_pairs = set()
        for e1 in edges:
            if e1["type"] != "has_parameter":
                continue
            P = e1["from"]
            Param = e1["to"]
            for e2 in edges:
                if e2["type"] == "relates_to" and e2["from"] == Param:
                    M = e2["to"]
                    indirect_pairs.add((P, M))

        new_edges = []
        for e in edges:
            if e["type"] == "uses_material" and (e["from"], e["to"]) in indirect_pairs:
                fixes.append(
                    f"Удалено транзитивно избыточное ребро "
                    f"{e['from']} -[uses_material]-> {e['to']} (есть путь через параметр)"
                )
                continue
            new_edges.append(e)
        return new_edges

    def close(self):
        self.driver.close()