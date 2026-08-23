import pickle
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "walk_graph_cache.pkl"


class WalkGraph:
    def __init__(self, cache, neighbors=None):
        self._cache = cache  # (from_node, to_node, mode) -> {"distance_m", "geometry"}
        # (from_node, mode) -> [to_node, ...], or None if this cache predates the neighbors
        # precompute, callers must fall back to a live radius scan in that case, not treat
        # a None here the same as "precomputed empty list".
        self._neighbors = neighbors

    def lookup(self, from_node, to_node, mode):
        entry = self._cache.get((from_node, to_node, mode))
        if entry is None:
            return None
        # `geometry` is deliberately left as the raw numpy array here (not .tolist()'d) since
        # this is called for every candidate edge a Dijkstra search considers, most of which
        # are discarded, not just the ones that end up on the winning route. The caller
        # converts to a plain list only for the handful of legs that survive to the final
        # itinerary (see _dijkstra_search's backtrace in router.py).
        return {
            "distance_m": entry["distance_m"],
            "geometry": entry["geometry"],
            "ascend_m": entry.get("ascend_m", 0.0),
            "descend_m": entry.get("descend_m", 0.0),
        }

    def neighbors(self, node, mode):
        if self._neighbors is None:
            return None
        return self._neighbors.get((node, mode), [])


def load_walk_graph():
    if not CACHE_PATH.exists():
        return WalkGraph({})
    with open(CACHE_PATH, "rb") as f:
        data = pickle.load(f)
    if isinstance(data, dict) and "edges" in data and "neighbors" in data:
        return WalkGraph(data["edges"], data["neighbors"])
    return WalkGraph(data)  # older cache format: bare edge dict, no neighbors precompute yet
