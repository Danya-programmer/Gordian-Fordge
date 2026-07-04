# schema.py
"""
Матрица допустимых связей и инварианты графа.
"""

# Допустимые типы узлов
VALID_NODE_TYPES = {
    "publication", "expert", "facility", "process",
    "experiment", "equipment", "material", "parameter"
}

# Допустимые типы рёбер
VALID_EDGE_TYPES = {
    "describes", "describes_parameter", "wrote",
    "uses_material", "uses_equipment", "uses_facility",
    "produces_material", "produces_experiment",
    "has_parameter", "characterizes", "relates_to",
    "confirms", "contradicts", "contains_subprocess"
}

# Матрица связей: (src_type, edge_type) -> set of allowed dst_types
ADJACENCY_MATRIX = {
    ("publication", "describes"):            {"experiment", "process", "material", "equipment", "facility"},
    ("publication", "describes_parameter"):  {"parameter"},
    ("expert", "wrote"):                     {"publication"},
    ("process", "uses_material"):            {"material"},
    ("process", "uses_equipment"):           {"equipment"},
    ("process", "uses_facility"):            {"facility"},
    ("process", "produces_material"):        {"material"},
    ("process", "produces_experiment"):      {"experiment"},
    ("process", "contains_subprocess"):      {"process"},
    ("process", "has_parameter"):            {"parameter"},
    ("experiment", "uses_material"):         {"material"},
    ("experiment", "uses_equipment"):        {"equipment"},
    ("experiment", "produces_material"):     {"material"},
    ("experiment", "confirms"):              {"experiment"},
    ("experiment", "contradicts"):           {"experiment"},
    ("experiment", "has_parameter"):         {"parameter"},
    ("parameter", "characterizes"):          {"process", "experiment", "equipment", "facility"},
    ("parameter", "relates_to"):             {"material"},
}

# Узлы-листья: не имеют исходящих рёбер
LEAF_TYPES = {"material", "equipment", "facility"}

# Параметр — не лист, ровно одно исходящее ребро
PARAMETER_OUT_DEGREE = 1