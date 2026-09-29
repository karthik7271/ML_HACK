"""Scam-network graph: link calls that share a UPI ID, phone, account or IFSC.

Different "officers" calling different victims often pay out to the same mule
account. Connected components with 2+ calls are reported as rings.
"""

from __future__ import annotations

import networkx as nx

KIND_LABEL = {"upi_ids": "UPI", "phones": "Phone", "accounts": "Account", "ifsc": "IFSC"}


def build(records: list[dict]) -> nx.Graph:
    g = nx.Graph()
    for r in records:
        g.add_node(r["id"], type="call", scam_type=r.get("scam_type"), wasted_s=r.get("wasted_s", 0),
                   seed=r.get("seed", False), started_at=r.get("started_at"))
        for kind in KIND_LABEL:
            for value in r.get("intel", {}).get(kind, []):
                node = f"{kind}:{value}"
                g.add_node(node, type="identifier", kind=KIND_LABEL[kind], value=value)
                g.add_edge(r["id"], node)
    return g


def rings(g: nx.Graph) -> list[dict]:
    out = []
    for comp in nx.connected_components(g):
        calls = [n for n in comp if g.nodes[n]["type"] == "call"]
        if len(calls) < 2:
            continue
        idents = [g.nodes[n] for n in comp if g.nodes[n]["type"] == "identifier"]
        # identifiers that link 2+ calls are the ones worth reporting first
        shared = [f'{g.nodes[n]["kind"]} {g.nodes[n]["value"]}' for n in comp
                  if g.nodes[n]["type"] == "identifier" and g.degree(n) >= 2]
        out.append({
            "calls": sorted(calls),
            "n_calls": len(calls),
            "n_identifiers": len(idents),
            "shared_identifiers": sorted(shared),
            "scam_types": sorted({g.nodes[c]["scam_type"] or "unknown" for c in calls}),
            "wasted_s": sum(g.nodes[c]["wasted_s"] for c in calls),
        })
    out.sort(key=lambda r: -r["n_calls"])
    for i, r in enumerate(out, 1):
        r["ring_id"] = f"R{i}"
    return out


def ring_of(g: nx.Graph, call_id: str) -> dict | None:
    for r in rings(g):
        if call_id in r["calls"]:
            return r
    return None


def to_json(g: nx.Graph) -> dict:
    ring_by_call = {c: r["ring_id"] for r in rings(g) for c in r["calls"]}
    nodes = []
    for n, d in g.nodes(data=True):
        item = {"id": n, **d}
        if d["type"] == "call":
            item["ring"] = ring_by_call.get(n)
        nodes.append(item)
    return {"nodes": nodes, "links": [{"source": a, "target": b} for a, b in g.edges()], "rings": rings(g)}
