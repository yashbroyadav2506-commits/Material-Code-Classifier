"""Procurement-savings estimation.

Demand aggregation opportunity: when several CPSEs source the same item at
different unit prices, pooling demand at the best observed price yields a
potential saving.

savings = (max_unit_price - min_unit_price) * total_quantity_per_cluster
"""


def compute_savings(clusters, material_by_id, procurement_by_material):
    """clusters: list of material-id lists."""
    rows = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        prices, qty = [], 0.0
        cpse_set = set()
        name = ""
        category = ""
        code = ""
        for mid in cluster:
            m = material_by_id.get(mid)
            if not m:
                continue
            cpse_set.add(m["cpse"])
            name = name or m.get("standardized_name") or m.get("desc") or m["legacy_code"]
            category = category or m.get("category") or ""
            code = code or m.get("national_code") or ""
            for row in procurement_by_material.get(mid, []):
                prices.append(row["unit_price"])
                qty += row["quantity"]
        if not prices:
            continue
        min_p, max_p = min(prices), max(prices)
        if min_p == max_p:
            continue
        rows.append(
            {
                "national_code": code or None,
                "standardized_name": name,
                "category": category,
                "cpse_count": len(cpse_set),
                "total_quantity": round(qty, 2),
                "min_price": min_p,
                "max_price": max_p,
                "potential_savings": round((max_p - min_p) * qty, 2),
            }
        )
    rows.sort(key=lambda r: r["potential_savings"], reverse=True)
    return rows


def total_savings(rows) -> float:
    return round(sum(r["potential_savings"] for r in rows), 2)