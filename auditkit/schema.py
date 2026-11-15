"""Format identifiers of the files auditkit writes (kept free of heavy imports)."""
SCHEMA = "clustaudit-audit/1"
INDEX_SCHEMA = "clustaudit-audit-index/1"
PROFILE_ORDER = ["overlap", "anisotropy", "inter_density", "intra_density", "imbalance", "eta_int"]


def note_of(ari_mean):
    """Note of a sweep: mean inlier ARI over its levels, each level clipped to [0, 1]."""
    vals = [min(1.0, max(0.0, v if v is not None else 0.0)) for v in ari_mean]
    return round(sum(vals) / len(vals), 4) if vals else None
