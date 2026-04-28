NUMERIC_TYPES = {
    "int", "bigint", "smallint",
    "decimal", "numeric",
    "float", "real"
}


def validate_aggregation(col_meta, agg):
    dtype = col_meta["type"]
    role = col_meta["role"]

    if agg in ["SUM", "AVG"]:
        if role in ["date", "name", "identifier"]:
            return False

        if dtype not in NUMERIC_TYPES:
            return False

    return True