"""Clustering of related material records.

Union-find over candidate mappings (score >= threshold) produces groups of
records that describe the same item — the raw material for duplicate
clusters, demand aggregation and savings estimation.
"""


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent.get(self.parent[x], self.parent[x])
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster_materials(pairs, min_score=50.0):
    """pairs: iterable of (material_id_a, material_id_b, score)."""
    uf = UnionFind()
    for a, b, score in pairs:
        if score >= min_score:
            uf.union(a, b)
    groups = {}
    for node in uf.parent:
        root = uf.find(node)
        groups.setdefault(root, []).append(node)
    return list(groups.values())


def cluster_stats(clusters):
    """Summaries for the dashboard."""
    multi = [c for c in clusters if len(c) >= 2]
    return {
        "total": len(multi),
        "largest_size": max((len(c) for c in multi), default=0),
        "covered_records": sum(len(c) for c in multi),
    }