"""Lance et arrête un graphe de nœuds (un sous-processus par nœud)."""

from __future__ import annotations

import multiprocessing as mp
import queue
import time

from visionaid.bus.nodes import NodeSpec, run_node
from visionaid.utils.logging import get_logger

log = get_logger("runner")


def assign_ports(specs: list[NodeSpec], base_port: int) -> dict[str, int]:
    """Un port par nœud producteur ; `topic:<sujet>` → port du producteur."""
    ports: dict[str, int] = {}
    for i, s in enumerate(specs):
        ports[s.name] = base_port + i
        for t in s.outputs:
            if "topic:" + t in ports:
                raise ValueError(f"Sujet {t} publié par plusieurs nœuds")
            ports["topic:" + t] = base_port + i
    for s in specs:
        for t in s.inputs:
            if "topic:" + t not in ports:
                raise ValueError(f"Sujet {t} lu par {s.name} mais jamais publié")
    return ports


def specs_from_config(graph: list[dict]) -> list[NodeSpec]:
    return [NodeSpec(**g) for g in graph]


class GraphRunner:
    """Démarre les nœuds en processus séparés (spawn) et les arrête proprement."""

    def __init__(
        self,
        specs: list[NodeSpec],
        cfg_raw: dict,
        base_port: int = 5550,
        stop_timeout_s: float = 2.0,
    ) -> None:
        self.specs = specs
        self.cfg_raw = cfg_raw
        self.ports = assign_ports(specs, base_port)
        self.stop_timeout_s = stop_timeout_s
        self.ctx = mp.get_context("spawn")
        self.stop_event = self.ctx.Event()
        self.stats_queue = self.ctx.Queue()
        self.procs: list[mp.Process] = []
        self.stats: dict[str, dict] = {}

    def start(self) -> None:
        # Les consommateurs d'abord (évite de perdre les premiers messages), producteurs ensuite.
        for spec in reversed(self.specs):
            p = self.ctx.Process(
                target=run_node,
                args=(spec, self.ports, self.cfg_raw, self.stop_event, self.stats_queue),
                name=f"node-{spec.name}",
                daemon=True,
            )
            p.start()
            self.procs.append(p)
        log.info("Graphe démarré : %s", [s.name for s in self.specs])

    def alive(self) -> list[str]:
        return [p.name for p in self.procs if p.is_alive()]

    def stop(self) -> float:
        """Arrête tous les nœuds ; retourne la durée d'arrêt (s)."""
        t0 = time.perf_counter()
        self.stop_event.set()
        deadline = t0 + self.stop_timeout_s
        while time.perf_counter() < deadline and len(self.stats) < len(self.procs):
            try:
                name, summ = self.stats_queue.get(timeout=0.05)
                self.stats[name] = summ
            except queue.Empty:
                if not self.alive():
                    break
        for p in self.procs:
            p.join(timeout=max(0.0, deadline - time.perf_counter()))
        for p in self.procs:
            if p.is_alive():
                log.warning("Nœud %s ne s'arrête pas : terminate", p.name)
                p.terminate()
                p.join(0.5)
            if p.is_alive():
                p.kill()
                p.join(0.5)
        while True:
            try:
                name, summ = self.stats_queue.get_nowait()
                self.stats[name] = summ
            except (queue.Empty, OSError, ValueError):
                break
        self.stats_queue.close()
        self.stats_queue.join_thread()
        return time.perf_counter() - t0

    def __enter__(self) -> GraphRunner:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


class SequentialRunner:
    """Mode mono-processus déterministe : mêmes blocs, appelés en séquence à chaque tick.

    Les nœuds sont appelés dans l'ordre de `specs`. Un nœud sans déclencheur (source) est
    appelé à chaque tick ; un nœud déclenché ne l'est que si son sujet a été produit pendant
    le tick. Les nœuds à cadence (`rate_hz`) sont sous-échantillonnés selon le temps des
    messages (`t`), pas l'horloge murale, d'où le déterminisme.
    """

    def __init__(self, specs: list[NodeSpec], cfg_raw: dict, blocks: dict | None = None) -> None:
        from visionaid.bus.nodes import load_factory

        assign_ports(specs, 0)  # validation du graphe
        self.specs = specs
        self.blocks = blocks or {s.name: load_factory(s.factory)(cfg_raw) for s in specs}
        self.latest: dict = {}
        self._last_run_t: dict[str, float] = {}

    def tick(self) -> dict:
        """Exécute un tick ; retourne les messages produits (None si la source est épuisée)."""
        produced: dict = {}
        for s in self.specs:
            if s.trigger is not None and s.trigger not in produced:
                continue
            if s.trigger is not None and s.rate_hz > 0:
                t = getattr(produced[s.trigger], "t", None)
                last = self._last_run_t.get(s.name)
                if t is not None and last is not None and t - last < 1.0 / s.rate_hz - 1e-9:
                    continue
                if t is not None:
                    self._last_run_t[s.name] = t
            out = self.blocks[s.name].process(dict(self.latest))
            if s.trigger is None and not out:
                return {}
            for k, v in (out or {}).items():
                if v is not None:
                    self.latest[k] = v
                    produced[k] = v
        return produced

    def run(self, max_ticks: int | None = None) -> int:
        n = 0
        while max_ticks is None or n < max_ticks:
            if not self.tick():
                break
            n += 1
        for b in self.blocks.values():
            close = getattr(b, "close", None)
            if callable(close):
                close()
        return n
