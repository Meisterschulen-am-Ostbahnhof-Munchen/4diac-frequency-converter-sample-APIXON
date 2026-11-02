#!/usr/bin/env python3
"""Verteilt die aktuellen FU-Demo-Boot-Dateien per HTTP auf die APIXON
(file_server-Baustein, POST /upload/<datei> mit rohem Binaerinhalt nach
/data/<datei>): FU_Demo_APIXON.fboot, FU_Demo_APIXON.libs.json und die
benoetigten ELF-Libs nach /data/elf-libs/.

Uebernommen aus Krauternter (make_krauternter_deploy.py), reine Stdlib
(http.client) - `python make_fu_demo_deploy.py` laeuft ohne pip-Installation.
Knoten und Dateien stehen in deploy_common.py.

Laedt nur hoch, rebootet NICHT automatisch - FORTE liest *.fboot nur beim
Booten neu ein, die APIXON muss also danach neu gestartet werden (z.B. ueber
den "Reboot"-Button auf http://<ip>/).

Baut selbst nichts - das Boot-File (4diac IDE) und das Manifest
(make_libs_manifest.py) muessen vorher aktuell erzeugt sein.
"""

from __future__ import annotations

import http.client
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from deploy_common import NODE_BASES, NODE_ORDER, REPO_PATHS, STAMPED_POOL_NAMES, pool_vis_for, resolve_local_path
from elf_libs_manifest_lib import (
    IS_REPO_CONTEXT,
    NODE_ARCH,
    build_libs_manifest,
    resolve_elf_path,
    resolve_required_libs,
    sha256_of,
)

# 2026-10-10 (Franz, explizit freigegeben): eingeschaltet. ELF-Laden wurde am
# selben Tag live auf dem echten training1-Knoten mit bis zu 15 gleichzeitig
# geladenen Libs auf einem S31 erfolgreich getestet, siehe
# elf_libs_manifest_lib.py fuer Format/Firmware-Verhalten/offene Punkte.
# STG1-STG4 (22-27 Libs) und der P4-Chip sind damit dennoch ERSTMALIG auf
# dieser Groessenordnung/diesem Chip - nach dem ersten echten Deploy die
# Stationen genau beobachten.
ENABLE_ELF_LIBS = True

# 2026-10-10: Die eigentliche Ursache des fehlenden logiBUS_utils auf STG1
# war ein Firmware-Bug im ALTEN Upload-Handler (Zielverzeichnis kam aus dem
# zuletzt in der Weboberflaeche angezeigten Ordner, nach einem Boot ohne
# Browser-Zugriff leer -> "Failed to create file", aber trotzdem HTTP 303
# "Erfolg" zurueckgemeldet) - nicht der SHA256-Vorab-Check (siehe
# Cross-Session-Austausch mit ELFLOADER). Mit ELFLOADER abgestimmtes neues
# Protokoll (Firmware-seitig noch nicht gebaut/geflasht):
#   - GET /sha256/ (ohne Pfad) liefert ALLE bekannten Hashes in einem
#     Request ("<hash>  <pfad>" je Zeile) - wird EINMAL pro Knoten geholt,
#     nicht pro Datei (vermeidet genau die N-Verbindungen-Sorge von eben).
#   - GET /sha256/<pfad> verifiziert NACH einem Upload, ob die Datei
#     wirklich angekommen ist - deckt genau den 303-aber-nicht-gespeichert-
#     Fall auf.
# Auto-Erkennung: antwortet GET /sha256/ mit 200, gilt der Knoten als
# "sha256-faehig" (neue Firmware) und bekommt den vollen Skip+Verify-Ablauf;
# jede andere Antwort (404 = alte Firmware, Verbindungsfehler) schaltet
# BEIDES komplett ab - dann laeuft es exakt wie vor dieser Erweiterung,
# keine zusaetzliche Verbindung pro Datei.
_SHA256_LISTING_RE = re.compile(r'^([0-9a-f]{64})\s+(\S+)$', re.MULTILINE)


def http_remote_sha256_listing(ip: str, timeout: float = 10) -> Optional[dict[str, str]]:
    """GET /sha256/ - liefert alle bekannten (Pfad -> Hash)-Paare in einem
    Request. None wenn die neue Firmware (noch) nicht vorhanden ist (Status
    != 200, Verbindungsfehler) - dann ist der Knoten NICHT sha256-faehig,
    auch wenn er zufaellig gar keine Dateien hat (leeres dict waere sonst
    nicht von "Firmware unterstuetzt es nicht" zu unterscheiden).

    Live beobachtet (2026-10-10, training1): das Listing liefert die Pfade mit
    "/data/"-Praefix (z.B. "/data/adapter-3.0.0-riscv32.elf",
    "/data/elf-libs/adapter-3.0.0-riscv32.elf"). Nur dieses Praefix wird
    entfernt - NICHT auf den nackten Dateinamen kuerzen! Ein ELF liegt seit
    der elf-libs/-Umstellung unter "elf-libs/<name>", eine gleichnamige Datei
    direkt in /data/ (von einem aelteren Deploy) ist etwas ANDERES - beim
    Kuerzen auf den nackten Namen wuerden beide auf denselben Schluessel
    fallen und ein Upload faelschlich uebersprungen (genau das ist am
    2026-10-10 bei training1 passiert, siehe http_upload_file())."""
    try:
        status, body = _http(ip, "GET", "/sha256/", timeout)
        if status != 200:
            return None
        text = body.decode("ascii", errors="ignore")
        result = {}
        for h, path in _SHA256_LISTING_RE.findall(text):
            name = path[len("/data/"):] if path.startswith("/data/") else path
            result[name] = h.lower()
        return result
    except OSError:
        return None


_FBOOT_HREF_RE = re.compile(r'href="/([^"]*\.fboot)"')
_MANIFEST_HREF_RE = re.compile(r'href="/([^"]*\.libs\.json)"')
_ELF_LIBS_HREF_RE = re.compile(r'href="/elf-libs/([^"]*\.elf)"')
_IOP_HREF_RE = re.compile(r'href="/([^"]*\.iop)"')
_VIS_HREF_RE = re.compile(r'href="/([^"]*\.vis\.json)"')


def _http(ip: str, method: str, path: str, timeout: float, body: Optional[bytes] = None) -> tuple[int, bytes]:
    conn = http.client.HTTPConnection(ip, timeout=timeout)
    try:
        conn.request(method, path, body=body)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def http_warmup(ip: str) -> None:
    """Manche Knoten-Webserver antworten auf den allerersten Request nach dem
    Booten nicht zuverlaessig (Franz: "scheint einen Request vorher zu
    brauchen") - ein Aufwaerm-Request VOR der eigentlichen Erreichbarkeits-
    pruefung behebt das. Ergebnis wird bewusst ignoriert."""
    try:
        _http(ip, "GET", "/", 5)
    except OSError:
        pass


def http_reachable(ip: str) -> bool:
    """Wie curl -m 5 -o /dev/null ...: jede empfangene HTTP-Antwort (auch
    4xx/5xx) zaehlt als erreichbar, nur ein Verbindungsfehler/Timeout als
    nicht erreichbar."""
    try:
        _http(ip, "GET", "/application/", 5)
        return True
    except OSError:
        return False


def http_listing(ip: str, path: str = "/", timeout: float = 5, missing_ok: bool = False) -> Optional[str]:
    """GET <path> (Default "/") als Text fuer die href-Listing-Regexe. None
    bei Verbindungsfehler ODER einem nicht-200-Status - ANDERS als fruehere
    Versionen (leerer String bzw. der rohe Body jedes Status): ein leeres
    Verzeichnis, eine Fehlerseite und ein fehlgeschlagener Request waren
    sonst nicht zu unterscheiden, eine 404-Fehlerseite waere sogar versucht
    worden als Listing zu parsen (CodeRabbit-Finding, PR #288).

    missing_ok=True: ein HTTP 404 gilt als "Verzeichnis existiert (noch)
    nicht" und liefert "" (keine hrefs) statt None - Normalfall fuer
    /elf-libs/ auf einem Knoten vor dem allerersten ELF-Upload (z.B. nach
    "Format File System"), kein Fehler. path kann ein Unterverzeichnis sein
    (z.B. "/elf-libs/")."""
    try:
        status, data = _http(ip, "GET", path, timeout)
        if status == 404 and missing_ok:
            return ""
        if status != 200:
            return None
        return data.decode("utf-8", errors="replace")
    except OSError:
        return None


def http_delete(ip: str, name: str, timeout: float = 10) -> bool:
    """POST /delete/<name>. Gibt True nur bei HTTP 303 (dokumentierter
    Erfolgsstatus, wie bei POST /upload/<name>) oder 404 (Datei war schon
    weg - ebenfalls ein Erfolg aus Aufrufersicht) zurueck, sonst False -
    sowohl bei einem Verbindungsfehler als auch bei jedem anderen HTTP-
    Status (z.B. 500), den die fruehere Version faelschlich als Erfolg
    gewertet haette (CodeRabbit-Finding, PR #288)."""
    try:
        status, _body = _http(ip, "POST", f"/delete/{name}", timeout)
        return status in (303, 404)
    except OSError:
        return False


def http_reset_current_directory(ip: str, timeout: float = 5) -> bool:
    """GET / - die Firmware merkt sich serverseitig das zuletzt per GET
    angezeigte Verzeichnis und legt dort JEDEN nachfolgenden pfadlosen Upload
    ab (live bestaetigt 2026-10-10 mit ELFLOADER: ein Manifest-Upload nach
    der ELF-Upload-Runde landete dadurch in /data/elf-libs/ statt /data/ -
    der Loader sucht *.libs.json aber nur direkt in /data/ und findet dort
    dann keins, FORTE startet ohne Libs). Vor jedem pfadlosen Upload, der auf
    eine Unterverzeichnis-Listung (z.B. /elf-libs/) folgen koennte, wird das
    Verzeichnis hierueber wieder auf /data/ zurueckgesetzt. Gibt True nur bei
    HTTP 200 zurueck - der Aufrufer kann einen Fehlschlag so wenigstens
    melden (keine echte Serialisierung gegen einen GLEICHZEITIGEN Zugriff
    eines anderen Clients auf denselben Knoten, das bleibt ein bekanntes,
    akzeptiertes Restrisiko bei diesem unauthentifizierten Protokoll)."""
    try:
        status, _body = _http(ip, "GET", "/", timeout)
        return status == 200
    except OSError:
        return False


_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


def http_remote_sha256(ip: str, remote_name: str, timeout: float = 5) -> Optional[str]:
    """GET /sha256/<remote_name> - optionale Firmware-Erweiterung (Stand
    2026-10-10: noch nicht gebaut, mit ELFLOADER-Session abgestimmt), die die
    SHA256 einer bereits vorhandenen Datei zurueckgibt, um unveraenderte
    ELF-Uploads einzusparen. None bei JEDEM Fehler (Endpunkt existiert noch
    nicht -> 404, Datei fehlt, falsche Firmware, Verbindungsfehler) - der
    Aufrufer laedt dann einfach wie bisher hoch, keine Fehlerbehandlung
    noetig, kein Verhaltensunterschied zu vorher."""
    try:
        status, body = _http(ip, "GET", f"/sha256/{remote_name}", timeout)
        if status != 200:
            return None
        text = body.decode("ascii", errors="ignore").strip().lower()
        return text if _SHA256_RE.match(text) else None
    except OSError:
        return None


def http_upload_file(
    ip: str,
    local_path: Path,
    remote_name: str,
    timeout: float,
    local_sha256: Optional[str] = None,
    remote_hashes: Optional[dict[str, str]] = None,
    verify_after_upload: bool = False,
) -> str:
    """POST /upload/<remote_name> mit dem rohen Binaerinhalt von local_path,
    OHNE Redirects zu folgen (http.client folgt nie automatisch, wie curl
    ohne -L). Gibt zurueck:
    - "SKIP": remote_hashes[remote_name] == local_sha256 (aus einem vorher
      per http_remote_sha256_listing() geholten Listing) UND eine zusaetzliche
      Einzelpruefung per http_remote_sha256() bestaetigt das - Datei liegt
      bereits unveraendert vor, kein Upload noetig.
    - "VERIFY_FAILED": Upload wurde mit HTTP 303 quittiert, aber
      verify_after_upload ist gesetzt und die anschliessende
      http_remote_sha256()-Pruefung zeigt einen abweichenden/fehlenden Hash -
      die Firmware hat "Erfolg" gemeldet, obwohl die Datei nicht (korrekt)
      gespeichert wurde (siehe Kommentar oben zum logiBUS_utils-Vorfall).
    - "RECOVERED": der Upload-Request selbst ist mit einem Verbindungsfehler/
      Timeout abgebrochen (frueher "000"), die Datei liegt laut
      http_remote_sha256() aber vollstaendig mit dem erwarteten Hash auf dem
      Knoten - wird vom Aufrufer wie "303" als Erfolg gewertet.
    - den HTTP-Status als String sonst ("303" = echter, verifizierter
      Erfolg), "000" bei jedem Verbindungsfehler/nicht lesbarer Datei, der
      sich auch per Hash-Abfrage nicht als angekommen bestaetigen laesst.
    Alle neuen Parameter sind optional, damit alte Aufrufer unveraendert
    funktionieren (kein lokaler Hash -> kein Skip, keine Verifikation).
    remote_name darf einen Unterordner enthalten (z.B. "elf-libs/x.elf") -
    der SKIP-Vergleich nutzt den VOLLEN remote_name als Schluessel (nicht nur
    den Dateinamen!), siehe Kommentar in http_remote_sha256_listing()."""
    if remote_hashes is not None and local_sha256 is not None and remote_hashes.get(remote_name) == local_sha256:
        # Die Batch-Liste (http_remote_sha256_listing()) kommt laut
        # ELFLOADER (2026-10-10, training1) aus einem RAM-Cache, der ein
        # "Format File System" nicht leert und nicht prueft, ob die Datei
        # noch existiert - der Einzel-Endpunkt macht vorher einen stat() und
        # liefert bei fehlender Datei zuverlaessig 404/None, deshalb hier vor
        # jedem SKIP nochmal einzeln gegenpruefen.
        if http_remote_sha256(ip, remote_name) == local_sha256:
            return "SKIP"
    try:
        data = local_path.read_bytes()
    except OSError:
        return "000"
    # Die Firmware (file_server.cpp, upload_post_handler) berechnet nach dem
    # letzten Byte noch den SHA-256 der ganzen Datei, BEVOR sie antwortet -
    # bei grossen Dateien (2,4 MB STG1-fboot) und laufendem FORTE reichten
    # 30 s am 2026-10-18 nicht (HTTP 000, Datei war aber vollstaendig da,
    # Analyse ELFMASTER). Zeitlimit daher mit der Dateigroesse wachsen lassen.
    timeout = max(timeout, 30 + 20 * len(data) / 1_000_000)
    try:
        status, _body = _http(ip, "POST", f"/upload/{remote_name}", timeout, body=data)
    except OSError:
        # Antwort verloren (Timeout/Verbindungsabriss) heisst nicht, dass die
        # Datei fehlt: per Hash nachsehen, ob sie vollstaendig angekommen ist
        # (der Hash kann kurz noch in Berechnung sein, daher mehrfach).
        if verify_after_upload and local_sha256 is not None:
            for _ in range(10):
                if http_remote_sha256(ip, remote_name) == local_sha256:
                    return "RECOVERED"
                time.sleep(3)
        return "000"
    if status == 303 and verify_after_upload and local_sha256 is not None:
        # Live gegen die erste echte sha256-faehige Firmware beobachtet
        # (2026-10-10, training1): der Hash wird laut ELFLOADER "nach jedem
        # Upload neu" im Hintergrund berechnet - eine Verifikation
        # UNMITTELBAR nach dem Upload kann dadurch kurz einen veralteten/
        # fehlenden Hash sehen, obwohl die Datei korrekt gespeichert wurde
        # (manuelle Nachpruefung Sekunden spaeter zeigte den richtigen
        # Hash). Deshalb kurz erneut versuchen, bevor ein echter Fehler
        # gemeldet wird.
        verified = http_remote_sha256(ip, remote_name)
        if verified != local_sha256:
            time.sleep(1)
            verified = http_remote_sha256(ip, remote_name)
        if verified != local_sha256:
            return "VERIFY_FAILED"
    return str(status)


def _load_prebuilt_manifest(path: Path, arch: str) -> Optional[list[Path]]:
    """Liest ein bereits fertiges <Basis>.libs.json UNVERAENDERT (wird vom
    Aufrufer 1:1 hochgeladen, siehe BERICHT_Manifest_ohne_requires_2026-10-14.md)
    und loest zu jedem darin gelisteten Lib-Eintrag den lokalen ELF-Pfad auf.
    None, wenn die Datei nicht lesbar/zur falschen Architektur ist oder ein
    ELF fehlt - der Aufrufer markiert den Knoten dann als fehlgeschlagen,
    statt mit einem unvollstaendigen Upload fortzufahren."""
    try:
        manifest_data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  WARNUNG: Vorgebautes Manifest {path} nicht lesbar ({exc}).")
        return None
    if manifest_data.get("arch") != arch:
        print(f"  WARNUNG: Vorgebautes Manifest {path} ist fuer Architektur '{manifest_data.get('arch')}', erwartet '{arch}'.")
        return None
    elf_paths: list[Path] = []
    for entry in manifest_data.get("libs", []):
        elf_path = resolve_elf_path(entry["name"], entry["version"], arch)
        if elf_path is None:
            print(f"  WARNUNG: ELF fuer {entry['name']}-{entry['version']}-{arch} (aus vorgebautem Manifest) nicht gefunden.")
            return None
        elf_paths.append(elf_path)
    return elf_paths


def _upload_manifest_and_elfs(
    ip: str,
    node_fboot_file: Path,
    manifest_path: Path,
    elf_paths: list[Path],
    remote_hashes: dict[str, str],
    sha256_capable: bool,
) -> bool:
    """Laedt die ELFs aus elf_paths sowie manifest_path (bewusst ZULETZT,
    siehe unten) auf den Knoten hoch. manifest_path wird unveraendert
    hochgeladen - egal ob frisch gebaut (Repo-Kontext) oder ein bereits
    fertiges Manifest (Release-Ordner, siehe _load_prebuilt_manifest()).
    Gibt False zurueck, wenn irgendein Upload fehlschlaegt."""
    manifest_name = f"{node_fboot_file.stem}.libs.json"
    ok = True

    # Manifest-Kandidaten liegen in /data/ (root), ELFs in /data/elf-libs/ -
    # getrennte Listings/Cleanups. Lose ELFs direkt in /data/ von AELTEREN
    # Deploys (vor dieser Umstellung) werden bewusst NICHT automatisch
    # entfernt (Franz raeumt das einmalig per "Format File System" auf).
    listing = http_listing(ip)
    if listing is None:
        print("  WARNUNG: Verzeichnis-Listing fehlgeschlagen - alte Manifest-Kandidaten NICHT geprueft/entfernt.")
        ok = False
    else:
        for existing in _MANIFEST_HREF_RE.findall(listing):
            if existing != manifest_name:
                print(f"  Entferne alten Lib-Kandidaten: {existing}")
                if not http_delete(ip, existing):
                    print(f"  WARNUNG: Loeschen von {existing} fehlgeschlagen.")
                    ok = False

    keep_names = {p.name for p in elf_paths}
    elf_listing = http_listing(ip, "/elf-libs/", missing_ok=True)
    if elf_listing is None:
        print("  WARNUNG: elf-libs/-Listing fehlgeschlagen - alte ELF-Kandidaten NICHT geprueft/entfernt.")
        ok = False
    else:
        for existing in _ELF_LIBS_HREF_RE.findall(elf_listing):
            if existing not in keep_names:
                print(f"  Entferne alten Lib-Kandidaten: elf-libs/{existing}")
                if not http_delete(ip, f"elf-libs/{existing}"):
                    print(f"  WARNUNG: Loeschen von elf-libs/{existing} fehlgeschlagen.")
                    ok = False
    if not ok:
        return False

    elf_ok = True
    for elf_path in elf_paths:
        elf_name = elf_path.name
        elf_remote_path = f"elf-libs/{elf_name}"
        http_code = http_upload_file(
            ip, elf_path, elf_remote_path, 60,
            sha256_of(elf_path), remote_hashes, sha256_capable,
        )
        if http_code == "SKIP":
            print(f"  {elf_path} -> {elf_remote_path}: unveraendert (Hash stimmt), Upload uebersprungen")
        elif http_code == "VERIFY_FAILED":
            print(f"  FEHLER: {elf_path} -> {elf_remote_path}: Upload mit HTTP 303 quittiert, Datei laut Geraet aber nicht/falsch gespeichert!")
            elf_ok = False
        else:
            print(f"  Lade {elf_path} -> http://{ip}/upload/{elf_remote_path}")
            if http_code == "303":
                print(f"  OK (HTTP {http_code})")
            elif http_code == "RECOVERED":
                print("  OK (Antwort verloren, Datei laut Hash aber vollstaendig angekommen)")
            else:
                print(f"  WARNUNG: ELF-Upload fehlgeschlagen (HTTP {http_code})")
                elf_ok = False

    # Manifest bewusst ZULETZT hochladen: fehlt es, laedt die Firmware keine
    # Lib - ein abgebrochener Upload ist so erkennbar.
    if elf_ok and not http_reset_current_directory(ip):
        # Zurueck auf /data/ - siehe http_reset_current_directory(): ohne das
        # wuerde der pfadlose Manifest-Upload nach der /elf-libs/-Listung oben
        # dort landen statt in /data/.
        print("  WARNUNG: Verzeichnis-Reset vor dem Manifest-Upload fehlgeschlagen - Manifest-Upload uebersprungen.")
        ok = False
    elif elf_ok:
        print(f"  Lade {manifest_path} -> http://{ip}/upload/{manifest_name}")
        http_code = http_upload_file(
            ip, manifest_path, manifest_name, 30,
            sha256_of(manifest_path), None, sha256_capable,
        )
        if http_code == "303":
            print(f"  OK (HTTP {http_code})")
        elif http_code == "RECOVERED":
            print("  OK (Antwort verloren, Datei laut Hash aber vollstaendig angekommen)")
        else:
            reason ="Datei laut Geraet nicht/falsch gespeichert" if http_code == "VERIFY_FAILED" else f"HTTP {http_code}"
            print(
                f"  WARNUNG: Manifest-Upload fehlgeschlagen ({reason}) - "
                "Libs auf dem Knoten sind damit unvollstaendig/inkonsistent.",
            )
            ok = False
    else:
        print(
            "  WARNUNG: Mindestens ein ELF-Upload fehlgeschlagen - Manifest wird bewusst "
            "NICHT hochgeladen (sonst wuerde die kuenftige Firmware eine Lib erwarten, die "
            "nicht vollstaendig da ist).",
        )
        ok = False

    return ok


def _remote_name_for(base: str, local_file: Path) -> str:
    """.iop und .vis.json muessen auf dem Knoten unter dem festen Namen
    liegen, den VT-Client bzw. ECU-Firmware fest einprogrammiert erwarten
    (kein Wildcard-Scan wie bei *.fboot) - der Versions-Stempel im
    Dateinamen (Google-Drive-Release-Ordner) bleibt daher auf das lokale
    Dateisystem beschraenkt. .fboot-Dateien gehen dagegen unter ihrem
    (ggf. gestempelten) lokalen Namen auf den Knoten, siehe die Bootfile-
    Cleanup-Logik unten, die genau deshalb noetig ist.
    Mit STAMPED_POOL_NAMES (Firmware mit *.iop-Suche) gehen auch .iop und
    .vis.json unter ihrem gestempelten Namen hoch, alte Pools raeumt
    _remove_other_pools() weg."""
    if not STAMPED_POOL_NAMES and (base.endswith(".iop") or base.endswith(".vis.json")):
        return base
    return local_file.name


def _remove_other_pools(ip: str, iop_name: str, vis_name: str) -> bool:
    """Nach erfolgreichem Pool-Upload alle anderen *.iop und *.vis.json in
    /data loeschen - die Firmware nimmt die alphabetisch erste *.iop, ein
    aelterer Stempel (2026-09-... < 2026-10-...) wuerde sonst gewinnen.
    *.part (laufender Upload) matcht die Regexe nicht."""
    listing = http_listing(ip)
    if listing is None:
        print("  WARNUNG: Verzeichnis-Listing fehlgeschlagen - alte Pool-Kandidaten NICHT geprueft/entfernt.")
        return False
    ok = True
    others = [n for n in _IOP_HREF_RE.findall(listing) if n != iop_name]
    others += [n for n in _VIS_HREF_RE.findall(listing) if n != vis_name]
    for existing in others:
        print(f"  Entferne alten Pool-Kandidaten: {existing}")
        if not http_delete(ip, existing):
            print(f"  WARNUNG: Loeschen von {existing} fehlgeschlagen.")
            ok = False
    return ok


def main() -> int:
    missing = False
    for ip in NODE_ORDER:
        for base in NODE_BASES.get(ip, []):
            if resolve_local_path(base) is None:
                print(f"FEHLER: Deploy-Datei fehlt: {base} (weder gestempelt noch unter {REPO_PATHS.get(base)})")
                missing = True
    if missing:
        print("Abbruch: Fehlende Dateien zuerst neu bauen/exportieren (4diac-IDE-/ISO-Designer-Export).")
        return 1

    reboot_needed: list[str] = []
    unreachable: list[str] = []
    upload_failed: list[str] = []

    for ip in NODE_ORDER:
        print("-" * 78)
        print(f"Knoten {ip}")

        http_warmup(ip)

        if not http_reachable(ip):
            print(f"WARNUNG: {ip} nicht erreichbar - uebersprungen.")
            unreachable.append(ip)
            continue

        node_ok = True
        node_local_files: list[Path] = []
        node_fboot_file: Optional[Path] = None
        node_fboot_base: Optional[str] = None
        node_iop_file: Optional[Path] = None
        pool_remote: dict[str, str] = {}
        pool_ok = True

        remote_hashes = http_remote_sha256_listing(ip)
        sha256_capable = remote_hashes is not None
        if remote_hashes is None:
            remote_hashes = {}

        for base in NODE_BASES.get(ip, []):
            local_file = resolve_local_path(base)
            assert local_file is not None  # durch die MISSING-Pruefung oben ausgeschlossen
            if base.endswith(".iop"):
                node_iop_file = local_file
            elif base.endswith(".vis.json") and node_iop_file is not None:
                # Immer die Tabelle mit demselben Stamm wie der hochgeladene
                # Pool - die Firmware sucht genau <pool ohne .iop>.vis.json
                sibling = pool_vis_for(node_iop_file)
                if sibling.is_file():
                    local_file = sibling
            node_local_files.append(local_file)
            if base.endswith(".fboot"):
                node_fboot_file = local_file
                node_fboot_base = base

            remote_name = _remote_name_for(base, local_file)


            http_code = http_upload_file(
                ip, local_file, remote_name, 30,
                sha256_of(local_file), remote_hashes, sha256_capable,
            )
            if http_code == "SKIP":
                print(f"  {local_file} -> {remote_name}: unveraendert (Hash stimmt), Upload uebersprungen")
            elif http_code == "VERIFY_FAILED":
                print(f"  FEHLER: {local_file} -> {remote_name}: Upload mit HTTP 303 quittiert, Datei laut Geraet aber nicht/falsch gespeichert!")
                node_ok = False
            else:
                print(f"  Lade {local_file} -> http://{ip}/upload/{remote_name}")
                if http_code == "303":
                    print(f"  OK (HTTP {http_code})")
                elif http_code == "RECOVERED":
                    print("  OK (Antwort verloren, Datei laut Hash aber vollstaendig angekommen)")
                else:
                    print(f"  WARNUNG: Upload fehlgeschlagen (HTTP {http_code})")
                    node_ok = False

            if base.endswith(".iop") or base.endswith(".vis.json"):
                pool_remote[".iop" if base.endswith(".iop") else ".vis.json"] = remote_name
                if http_code not in ("SKIP", "303", "RECOVERED"):
                    pool_ok = False

            # Anders benannte alte Bootfiles erst NACH einem erfolgreichen
            # Upload entfernen (sonst entscheidet FORTE beim Booten per
            # alphabetischer Sortierung ueber mehrere *.fboot-Kandidaten) -
            # vorher geloescht, wuerde ein fehlgeschlagener Upload den Knoten
            # ganz ohne Bootfile zuruecklassen (wie in 4diac_training1,
            # Sourcery-Finding PR #288).
            if remote_name.endswith(".fboot") and http_code in ("SKIP", "303", "RECOVERED"):
                listing = http_listing(ip)
                if listing is None:
                    print("  WARNUNG: Verzeichnis-Listing fehlgeschlagen - alte Bootfile-Kandidaten NICHT geprueft/entfernt.")
                    node_ok = False
                else:
                    for existing in _FBOOT_HREF_RE.findall(listing):
                        if existing != remote_name:
                            print(f"  Entferne alten Bootfile-Kandidaten: {existing}")
                            if not http_delete(ip, existing):
                                print(f"  WARNUNG: Loeschen von {existing} fehlgeschlagen.")
                                node_ok = False

        # Alte Pools erst NACH erfolgreichem Upload von Pool UND Tabelle
        # entfernen - ein Abbruch laesst den alten Pool so lauffaehig zurueck.
        if STAMPED_POOL_NAMES and pool_ok and ".iop" in pool_remote and ".vis.json" in pool_remote:
            if not _remove_other_pools(ip, pool_remote[".iop"], pool_remote[".vis.json"]):
                node_ok = False

        # ENTWURF/EXPERIMENTAL (siehe ENABLE_ELF_LIBS oben, Standard AUS):
        # ELFs + Libs-Manifest zusaetzlich zum fboot hochladen. Fehlt lokal
        # auch nur ein benoetigtes ELF, wird dieser Teil fuer den Knoten
        # uebersprungen - der normale fboot-Upload oben ist davon
        # unberuehrt.
        if node_ok and ENABLE_ELF_LIBS and node_fboot_file is not None and node_fboot_base is not None:
            arch = NODE_ARCH.get(ip)
            if not arch:
                print(f"  WARNUNG: Keine Architektur fuer {ip} in NODE_ARCH hinterlegt - ELF-Manifest uebersprungen.")
            else:
                manifest_base = node_fboot_base[: -len(".fboot")] + ".libs.json"
                # Release-Ordner: Manifest heisst <gestempeltes fboot>.libs.json
                # und liegt neben dem fboot. resolve_local_path() findet es
                # nicht, weil es nur am letzten Punkt trennt (".libs_*.json").
                sibling_manifest = node_fboot_file.with_name(f"{node_fboot_file.stem}.libs.json")
                prebuilt_manifest = sibling_manifest if sibling_manifest.is_file() else resolve_local_path(manifest_base)

                if prebuilt_manifest is not None:
                    # Bevorzugt: ein bereits von make_libs_manifest.py
                    # fertig gebautes Manifest unveraendert verwenden, statt
                    # es hier neu zu bauen. Noetig, weil resolve_required_libs()/
                    # lib_requires_of() im Google-Drive-Release-Ordner
                    # MANIFEST.MF nicht erreichen koennen (4diacIDE-workspace/
                    # existiert dort nicht) - das fuehrte am 2026-10-14 dazu,
                    # dass STG2-5 mit einem unvollstaendigen, requires-losen
                    # Manifest gebootet sind und FORTE wegen falscher
                    # Lade-Reihenfolge/fehlender transitiver Libs nicht
                    # gestartet ist (siehe BERICHT_Manifest_ohne_requires_2026-10-14.md,
                    # Cross-Session-Meldung ELFMASTER).
                    elf_paths = _load_prebuilt_manifest(prebuilt_manifest, arch)
                    if elf_paths is None:
                        node_ok = False
                    else:
                        print(f"  Verwende vorgebautes Manifest {prebuilt_manifest} ({len(elf_paths)} Libs, unveraendert) statt Neubau.")
                        if not _upload_manifest_and_elfs(ip, node_fboot_file, prebuilt_manifest, elf_paths, remote_hashes, sha256_capable):
                            node_ok = False
                elif IS_REPO_CONTEXT:
                    required_libs = resolve_required_libs(node_fboot_file)
                    if not required_libs:
                        print("  Keine bekannten ausgelagerten Libs in diesem .fboot referenziert - kein Libs-Manifest noetig.")
                    else:
                        with tempfile.TemporaryDirectory() as tmp_dir:
                            manifest_tmp = Path(tmp_dir) / "manifest.json"
                            result = build_libs_manifest(arch, node_local_files, manifest_tmp, required_libs)
                            if result.ok:
                                if not _upload_manifest_and_elfs(ip, node_fboot_file, manifest_tmp, result.elf_paths, remote_hashes, sha256_capable):
                                    node_ok = False
                else:
                    # Kein Repo-Kontext (z.B. Google-Drive-Release-Ordner) UND
                    # kein vorgebautes Manifest gefunden - hier NICHT mehr
                    # still mit (dann zwangslaeufig leeren) requires neu
                    # bauen, siehe BERICHT_Manifest_ohne_requires_2026-10-14.md.
                    print(
                        f"  FEHLER: Kein vorgebautes {manifest_base} gefunden und kein Repo-Kontext "
                        "(MANIFEST.MF nicht erreichbar) - Libs-Upload abgebrochen, um ein Manifest ohne "
                        "requires/fehlende transitive Libs zu vermeiden. Vorher make_libs_manifest.py im "
                        "Repo laufen lassen und die erzeugte .libs.json mit in den Release-Ordner legen.",
                    )
                    node_ok = False

        if node_ok:
            reboot_needed.append(ip)
        else:
            upload_failed.append(ip)

    print("-" * 78)
    print(f"ZUSAMMENFASSUNG ({len(reboot_needed)}/{len(NODE_ORDER)} Knoten erfolgreich):")
    if len(reboot_needed) == len(NODE_ORDER):
        print(f"  ALLE {len(NODE_ORDER)} KNOTEN ERFOLGREICH HOCHGELADEN:")
        for ip in reboot_needed:
            print(f"  - {ip}: OK")
    else:
        for ip in NODE_ORDER:
            if ip in reboot_needed:
                print(f"  - {ip}: OK")
            elif ip in upload_failed:
                print(f"  - {ip}: FEHLER (Upload fehlgeschlagen, siehe Warnungen oben)")
            elif ip in unreachable:
                print(f"  - {ip}: NICHT ERREICHBAR (uebersprungen)")

    if upload_failed:
        print()
        print("ACHTUNG: Diese Knoten jetzt NICHT neu starten, sondern das Deploy einfach wiederholen:")
        for ip in upload_failed:
            print(f"  - {ip}")
        print(
            "  (Nach einem abgebrochenen Upload liegen dort neue und alte Dateien gemischt, z.B. ein neues\n"
            "   Bootfile mit dem alten Libs-Manifest - ein Neustart in diesem Zustand kann FORTE am Start hindern.\n"
            "   Bereits angekommene Dateien werden beim zweiten Lauf per Hash erkannt und uebersprungen.)",
        )

    if reboot_needed:
        print()
        print("Neue Dateien werden erst nach einem Neustart aktiv.")
        print('Manuell neu starten (z.B. "Reboot"-Button auf http://<ip>/):')
        for ip in reboot_needed:
            print(f"  - {ip}")

    return 0 if len(reboot_needed) == len(NODE_ORDER) else 1


if __name__ == "__main__":
    # Ohne stdout zeilengepuffert zu erzwingen, sammelt Python die Ausgabe
    # blockweise, sobald stdout kein echtes Terminal ist (z.B. External Tool
    # in der 4diac IDE, .bat-Aufruf) - die Fortschrittsmeldungen erscheinen
    # dann erst in grossen Schueben oder gar erst am Ende, obwohl der Upload
    # laengst laeuft (sieht aus wie Haengenbleiben, ist nur Pufferung).
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    # Nur im Google-Drive-Release-Ordner (Doppelklick auf die .bat beim
    # Kunden) das Fenster offen halten - aus der 4diac IDE (Repo) nicht.
    # finally: auch bei einer Ausnahme bleibt der Traceback lesbar.
    try:
        rc = main()
    finally:
        if not IS_REPO_CONTEXT:
            try:
                input("Fertig - Enter druecken zum Schliessen ...")
            except EOFError:
                pass
    sys.exit(rc)
