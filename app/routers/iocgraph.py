"""IOC relationship graph — nodes and edges for D3.js force-directed visualization."""
from collections import defaultdict
from itertools import combinations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..core.ioc import extract_from_case

router = APIRouter(prefix="/cases/{case_id}/ioc", tags=["iocgraph"])


@router.get("/graph")
def ioc_graph(case_id: int, db: Session = Depends(get_db)):
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case:
        return JSONResponse({"nodes": [], "edges": [], "stats": {}}, status_code=404)

    iocs = extract_from_case(case)

    # ── Build nodes ───────────────────────────────────────────────
    node_count: dict[str, int] = defaultdict(int)
    node_type:  dict[str, str] = {}
    for ioc in iocs:
        nid = f"{ioc.type}:{ioc.value}"
        node_count[nid] += 1
        node_type[nid] = ioc.type

    # ── Group IOCs by source to build edges ───────────────────────
    by_source: dict[str, list[str]] = defaultdict(list)
    for ioc in iocs:
        by_source[ioc.source].append(f"{ioc.type}:{ioc.value}")

    edge_weight: dict[tuple[str, str], int] = defaultdict(int)
    for src, node_ids in by_source.items():
        uniq = list(dict.fromkeys(node_ids))  # preserve order, dedupe
        for a, b in combinations(uniq, 2):
            key = (min(a, b), max(a, b))
            edge_weight[key] += 1

    nodes = [
        {
            "id":    nid,
            "label": _short(nid.split(":", 1)[1]),
            "full":  nid.split(":", 1)[1],
            "type":  node_type[nid],
            "count": node_count[nid],
        }
        for nid in node_count
    ]

    edges = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in edge_weight.items()
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "ioc_count":  len(iocs),
        },
    }


def _short(v: str, max_len: int = 22) -> str:
    return v if len(v) <= max_len else v[:10] + "…" + v[-9:]
