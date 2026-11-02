# 4diac-frequency-converter-sample-APIXON

Demo: **ein** DELIXI-H300-Frequenzumrichter (0,75 kW), gesteuert von einer
4diac-FORTE-Applikation auf der APIXON, mit OPC-UA-Web-Dashboard.

Umrichter laut Typenschild: **H300G0R75P1R1T4B**, Eingang 3~ 380–480 V
4,4/5,0 A, Ausgang 0–480 V 0–599 Hz 3,0/3,5 A (0,75 kW G-Typ / 1,1 kW P-Typ),
HW 1.2.01, SW 1.21. Gleiche Serie wie U1–U6 (H300G7R5P11T4B) im
Getreideannahme-Projekt, deshalb gilt dieselbe Registerkarte (Handbuch Kap. 9.1).

```
 Browser/Tablet ──ws://APIXON:4841 (OPC UA)──► APIXON (4diac FORTE)
                                                  │ Modbus TCP, Port 4196
                                                  ▼
                              Waveshare RS232/485/422 TO POE ETH (B)
                                                  │ Modbus RTU, 9600 8-N-2
                                                  ▼
                                      DELIXI H300 0,75 kW (Slave 1)
```

Referenzen: `GetreideannahmeSchaltplan` (Register-/I/O-Liste der sechs H300,
Handbücher) und `Krauternter` (APIXON-Deploy, OPC-UA-Dashboard-Muster).

## Inhalt

| Pfad | Was |
|---|---|
| `Ventilsteuerung/4diacIDE-workspace/FU_Demo/` | 4diac-Projekt: System `FU_Demo.sys`, SubApp `FU_Demo_H300.SUB` mit den drei SubApps `FU_Messwerte` (darin `FU_Skalierung`), `FU_Kommando`, `FU_Sollwert`; alle Adressen in `FU_Demo_Konstanten.gcf` |
| `Ventilsteuerung/APIXON/ethernet.ini` | Feste IP 192.168.1.11 für die APIXON (→ `/data/ethernet.ini`) |
| `Ventilsteuerung/4diacIDE-workspace/.lib/` | Benötigte Bibliotheken 3.0.x inkl. riscv32/xtensa-ELFs (aus Krauternter übernommen) |
| `Ventilsteuerung/scripts_central/` | Deploy (Boot-File, Libs-Manifest, ELF-Libs per HTTP auf die APIXON) und Manifest-Erzeugung, aus Krauternter übernommen |
| `Ventilsteuerung/Web-Clients/opcua-dashboard/` | Vue-3-Dashboard (`@wsopcua`). `dist/fu-demo-dashboard.html` ist eine einzelne Datei |
| **`docs/SICHERHEIT_Offene_Punkte.md`** | **Vor jeder Vorführung lesen:** Motor läuft weiter, wenn das Dashboard wegfällt; STOP-Taste und Not-Halt noch offen |
| `docs/Inbetriebnahme.md` | Verdrahtung, H300-Parameter, Gateway-Einstellungen, Fehlersuche |

## Die 4diac-Applikation

Sie verwendet bewusst **nur Typen, die auf der APIXON schon als ELF-Lib oder in
der Firmware vorhanden sind**. Es gibt keinen eigenen FB-Typ, also auch keinen
Lib-Build für riscv32.

1. **Lesen** (`FU_Messwerte`) – `CLIENT_0_8` (9000H–9004H, 9006H, 9332H, 9333H) pollt selbst
   alle 500 ms und löst nach jeder erfolgreichen Abfrage `CNF` aus (kein `REQ`,
   kein `E_CYCLE`) → SubApp `FU_Skalierung` (`FIELDBUS_UINT_TO_SIGNAL_SCALED` je Messwert) → `PUBLISH_8` auf den
   lokalen OPC-UA-Server.
2. **Kommando** (`FU_Kommando`) – `SUBSCRIBE_1` (`FU1.Kommando`, UInt16) → `F_UINT_TO_WORD` →
   `CLIENT_1_0` auf 9300H. Ein Dashboard-Klick erzeugt genau einen Modbus-Write.
   Es gibt kein zyklisches Nachsenden: Nach einem Fehler oder einem Stopp am
   Bedienteil läuft der Antrieb erst wieder, wenn jemand bewusst „Vorwärts“ drückt.
3. **Sollwert** (`FU_Sollwert`) – `SUBSCRIBE_1` (`FU1.SollFrequenz`, Float, Hz) →
   `F_ClampReal` (0…Fmax) → `F_MUL` (×10000/Fmax) → `F_REAL_TO_UINT` →
   `CLIENT_1_0` auf 9301H (RAM, kein EEPROM-Verschleiß).

Zwischen ANY-Pins (`CLIENT`/`PUBLISH`/`SUBSCRIBE`) und generischen Funktionen
liegt immer ein typisierter Baustein. FORTE typisiert einen ANY-Ausgang über
sein Verbindungsziel. Ein generischer Ausgang (`F_MUL.OUT`) ist vor dem ersten
Lauf `SINT` und würde direkt an `PUBLISH` einen falsch typisierten OPC-UA-Knoten
anlegen.

### OPC-UA-Knoten (ns=1)

| NodeId | Typ | Richtung | Inhalt |
|---|---|---|---|
| `FU1.IstFrequenz` | Float | lesen | Hz (9000H × 0,01) |
| `FU1.SollFrequenzAktiv` | Float | lesen | vom FU verwendeter Sollwert, Hz (9001H) |
| `FU1.Strom` | Float | lesen | A (9002H × 0,01) |
| `FU1.Ausgangsspannung` | Float | lesen | V (9003H) |
| `FU1.Zwischenkreisspannung` | Float | lesen | V (9004H × 0,1) |
| `FU1.Leistung` | Float | lesen | kW (9006H × 0,1) |
| `FU1.Status` | UInt16 | lesen | 1 = vorwärts, 2 = rückwärts, 3 = Stopp |
| `FU1.Fehlercode` | UInt16 | lesen | 0 = OK, sonst H300-Fehlercode |
| `FU1.Kommando` | UInt16 | schreiben | 1 vorwärts, 2 rückwärts, 5 freier Auslauf, 6 Rampenstopp, 7 quittieren |
| `FU1.SollFrequenz` | Float | schreiben | Hz, wird auf 0…Fmax begrenzt |
| `FU1.SYSTEM_TICK` | Int32 | lesen | Lebenszeichen 0…99 alle 200 ms (`Ticker`, `MyLib::sys::SystemTickSender_OPC`), im Dashboard neben der Verbindungsanzeige |

Die Knoten lassen sich auch mit UaExpert über `opc.tcp://<APIXON>:4840` prüfen.

## Dashboard bauen

```
cd Ventilsteuerung/Web-Clients/opcua-dashboard
npm install
npm run dev        # Entwicklung
npm test           # vitest
npm run build      # -> dist/fu-demo-dashboard.html
```

## Deploy auf die APIXON

In der 4diac IDE (Projekt `FU_Demo`, Ordner `Launches/`) oder direkt per Python:

1. Boot-File in der IDE erzeugen (`boot-files/FU_Demo_APIXON.fboot`).
2. `RunSkript_MakeLibsManifest` (`scripts_central/make_libs_manifest.py`): schreibt
   `boot-files/FU_Demo_APIXON.libs.json` mit den benötigten ELF-Libs (riscv32), ohne Netzwerk.
3. `RunSkript_Deploy` (`scripts_central/make_fu_demo_deploy.py`): lädt fboot, Manifest und
   ELF-Libs nach `http://192.168.1.11/` hoch (unveränderte Dateien per SHA256 übersprungen)
   und löscht danach andere `*.fboot`. Danach die APIXON neu starten.

Nie ein neues fboot ohne neu erzeugtes Manifest hochladen: Das Manifest enthält Hash und
Größe des fboot.

## Fallstricke, die im Code berücksichtigt sind

- **Modbus-Adressen sind dezimal.** FORTE parst die Adresslisten mit
  `strtoul(..., 10)`, `h9000` wäre also Register 9000 und nicht 0x9000.
  0x9000 = `h36864`, 0x9300 = `h37632`.
  (`Umrichter_IO_Liste.md` im Schaltplan-Repo schreibt noch `h9000` usw.)
- **Maximalfrequenz ist P0.1.16**, nicht P0.2.00 (das ist die Hochlaufzeit).
- **`pollFrequency` der Schreib-FBs ist 500 und nicht 0.** Bei 0 entsteht auf der
  gemeinsamen TCP-Verbindung ein Leerpoll im 1-ms-Takt. Dieser zählt als
  „erfolgreich“ und verhindert damit den Auto-Reconnect nach Lesefehlern
  (`tryPolling`: Reconnect nur bei `nrErrors == nrPolls`). Mit 500 landen alle
  drei FBs im selben Poll-Objekt. `REQ` schreibt trotzdem sofort.
- Die drei Modbus-FBs teilen sich automatisch **eine** TCP-Verbindung
  (FORTE gruppiert nach `ip:port`).

## Offene Risiken (am echten Gerät prüfen)

1. ~~**Funktionscode 0x10**~~ – **erledigt (2026-11-02, am Gerät getestet):** Der H300
   (SW 1.21) nimmt 0x10 für 9300H und 9301H an. Der Motor lief mit 10 Hz vorwärts
   (1,56 A, 93 V) und stoppte über die Rampe. FORTE braucht also keinen Patch.
2. **Kein Kommunikations-Status:** Der Modbus-Layer meldet Lesefehler nicht an
   `QO` weiter (`recvData`: „TODO check if errors occured during polling“).
   Fällt das Gateway aus, frieren die Werte im Dashboard ein. Erkennbar ist das
   nur am FORTE-Log oder am Err47 des Umrichters.
3. Skalierung von 9003H (V) und 9006H (0,1 kW) stammt aus den Default-Formaten
   des Handbuchs und ist noch nicht am Gerät verifiziert.
