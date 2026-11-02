#!/usr/bin/env python3
"""Gemeinsame Konfiguration/Hilfsfunktion zum Finden der lokalen FU-Demo-
Deploy-Dateien (fboot, .libs.json) - genutzt von make_fu_demo_deploy.py
(Upload) UND make_libs_manifest.py (lokale Manifest-Erzeugung, kein Upload).
Uebernommen aus Krauternter (Ventilsteuerung/scripts_central/deploy_common.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# Im Repo liegt dieses Modul unter Ventilsteuerung/scripts_central/. Liegen
# alle Dateien flach nebeneinander (Release-Ordner), ist "parent" bereits das
# Basisverzeichnis. Erkennung ueber 4diacIDE-workspace/ (existiert nur im Repo).
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR.parent / "4diacIDE-workspace").is_dir():
    VENTILSTEUERUNG_DIR = _SCRIPT_DIR.parent
else:
    VENTILSTEUERUNG_DIR = _SCRIPT_DIR

# Ein Knoten: die APIXON (feste IP aus APIXON/ethernet.ini). Kein VT-Pool.
NODE_BASES: dict[str, list[str]] = {
    # fu-demo-dashboard.html: Single-File-Build des OPC-UA-Dashboards, danach
    # direkt vom Geraet aufrufbar: http://192.168.1.11/fu-demo-dashboard.html
    "192.168.1.11": ["FU_Demo_APIXON.fboot", "fu-demo-dashboard.html"],
}

# Pfade im Repo (relativ zu Ventilsteuerung/).
REPO_PATHS: dict[str, str] = {
    "FU_Demo_APIXON.fboot": "boot-files/FU_Demo_APIXON.fboot",
    # Von make_libs_manifest.py erzeugtes Manifest, wird beim Deploy bevorzugt.
    "FU_Demo_APIXON.libs.json": "boot-files/FU_Demo_APIXON.libs.json",
    # Vorher bauen: cd Web-Clients/opcua-dashboard && npm run build
    "fu-demo-dashboard.html": "Web-Clients/opcua-dashboard/dist/fu-demo-dashboard.html",
}

# Kein VT-Pool im FU-Demo - nur fuer die aus Krauternter uebernommene
# Pool-Logik in make_fu_demo_deploy.py (dort ohne .iop wirkungslos).
STAMPED_POOL_NAMES = False


def pool_vis_for(iop: Path) -> Path:
    """Sichtbarkeitstabelle zum Pool: gleicher Stamm, Endung .vis.json."""
    return iop.with_name(iop.name[: -len(".iop")] + ".vis.json")


NODE_ORDER: list[str] = [
    "192.168.1.11",
]


def resolve_local_path(base: str) -> Optional[Path]:
    """Liefert den tatsaechlichen lokalen Pfad zu einer Basisdatei: zuerst
    gestempelte Variante im Ventilsteuerung-Wurzelverzeichnis (Release-
    Ordner), dann unbestempelte Variante dort, dann Repo-Fallback-Pfad.
    None, wenn nichts gefunden (entspricht resolve_local_path() in
    deploy_common.sh)."""
    if base.endswith(".vis.json"):
        # Doppelte Endung: Stempel vor ".vis.json" (DefaultPool_<v>.vis.json)
        name, ext = base[: -len(".vis.json")], "vis.json"
    else:
        name, _, ext = base.rpartition(".")
    stamped = sorted(VENTILSTEUERUNG_DIR.glob(f"{name}_*.{ext}"))
    if stamped:
        return stamped[0]
    plain = VENTILSTEUERUNG_DIR / base
    if plain.is_file():
        return plain
    repo_rel = REPO_PATHS.get(base)
    if repo_rel:
        repo = VENTILSTEUERUNG_DIR / repo_rel
        if repo.is_file():
            return repo
    return None
