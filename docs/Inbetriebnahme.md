# Inbetriebnahme FU-Demo (DELIXI H300G0R75P1R1T4B, 0,75 kW)

Reihenfolge: Umrichter → Waveshare-Gateway → APIXON (4diac) → Dashboard.

Typenschild: 3~ 380–480 V Eingang (4,4/5,0 A), Ausgang 3,0/3,5 A, HW 1.2.01, SW 1.21.
Netzanschluss also **dreiphasig 400 V**. Bei Volllast sind Strom-Messwerte bis etwa 3 A zu
erwarten, die Zwischenkreisspannung liegt im Leerlauf bei etwa 540–560 V.

## 1. Verdrahtung RS485

| Waveshare RS232/485/422 TO POE ETH (B) | DELIXI H300 |
|---|---|
| RS485 A+ | 485+ |
| RS485 B- | 485- |
| GND | GND (Steuerklemmen) |

- Leitung: verdrillt, geschirmt. Schirm einseitig auflegen.
- Kurze Punkt-zu-Punkt-Strecke: Abschlusswiderstand 120 Ω am Umrichterende nur bei Problemen (falls am H300 per DIP vorhanden).
- Gateway per PoE (802.3af) oder 5–36 V DC versorgen.

## 2. Parameter am H300

| Parameter | Wert | Bedeutung |
|---|---|---|
| P0.1.06 | **2** | Betriebsbefehl über Kommunikation |
| P0.1.09 | **9** | Frequenzquelle A = Kommunikation (Register 9301H) |
| P0.1.16 | **80.00** | Maximalfrequenz (Werksdefault 50.00). Muss zu `FU_FMAX_HZ`/`FU_SOLLWERT_FAKTOR` (GCF) und `FMAX_HZ` (Dashboard `src/h300.ts`) passen |
| P0.1.18 | **80.00** | Obere Grenzfrequenz (Werksdefault 50.00, Quelle P0.1.17 = 0). Ohne diesen Wert bleibt der Umrichter trotz P0.1.16 bei 50 Hz stehen |
| P0.1.40 | 1 | Slave-Adresse (Werksdefault). Steht im Modbus-ID-String |
| P2.8.00 | 3 | 9600 Baud (Werksdefault) |
| P2.8.01 | 0 | 8-N-2 (Werksdefault, **2 Stoppbits**) |
| P2.8.05 | 1 | RTU |
| P2.8.06 | 0 | Antwort senden |
| P2.8.04 / P2.8.07 | 5,0 s / **1** | **Pflicht (Kommunikations-Watchdog):** Err47, wenn länger als 5 s keine Anfrage kommt, Motor stoppt. Wert 1 = Fehler bleibt bis zur Quittierung stehen. Am Demo-Umrichter am 2026-11-02 gesetzt und getestet. Err47 kommt auch im Stillstand, also nach jedem Start der APIXON einmal im Dashboard quittieren |

Motordaten (P1.0.x) vom Motor-Typenschild eintragen. Nennstrom höchstens 3,0 A (G-Typ),
damit der Motorschutz des Umrichters passt.

Am Demo-Umrichter wurden P0.1.06 = 2 und P0.1.09 = 9 am 2026-11-02 per Modbus (06H) auf die EEPROM-Adressen
0x0106/0x0109 geschrieben und zurückgelesen. Die RAM-Adressen wären +0x0A00 (0x0B06/0x0B09) gewesen.

Rückwärtslauf muss am Umrichter erlaubt sein, sonst wird Kommando 2 ignoriert. Rampen (P0.2.00/P0.2.01) passend zum Motor einstellen.

## 3. Waveshare-Gateway

Werks-IP ist laut Waveshare-Wiki `192.168.1.200`. Weboberfläche oder VirCom:

1. IP `192.168.1.200` lassen oder ändern. Bei Änderung die IP in allen drei `FU_MODBUS_*`-Konstanten der GCF anpassen.
2. Serielle Parameter **explizit** setzen: 9600 Baud, 8 Datenbits, keine Parität, **2 Stoppbits** (kein verlässlicher Werksdefault).
3. Transfer protocol: **Modbus TCP ↔ RTU**. Laut Wiki wechselt der Port dabei auf 502. Am Demo-Gateway läuft Modbus TCP aber auf **4196** (am 2026-11-02 mit `tools/h300_modbus_test.py` gemessen; 502 ist dort zu). Die GCF verwendet deshalb 4196.
4. Prüfen, ob „Storage Mode“ (Gateway pollt selbst zyklisch nach) aktiv ist. Für den Demo-Betrieb möglichst **non-storage**: Anfragen werden nur durchgereicht.

**Eingestellt am Demo-Gateway (Firmware V1.523, Stand 2026-11-02):**

| Feld | Wert | Bemerkung |
|---|---|---|
| Device IP / Subnet / Gateway | 192.168.1.200 / 255.255.255.0 / 192.168.1.1 | IP mode Static |
| Work Mode / Device Port | TCP Server / **4196** | Modbus TCP läuft hier auf 4196, nicht auf 502 |
| Baud / Datenbits / Parität / Stoppbits | 9600 / 8 / None / **2** | = H300 P2.8.00 = 3, P2.8.01 = 0 (8-N-2) |
| Flow control | None | |
| Protocol | **Modbus TCP to RTU** | Multi-host damit automatisch an |
| Instruction Time out | **320 ms** | Werkswert 32 ms ist zu knapp: Anfrage + Antwort bei 9600 Baud ≈ 30 ms. Nur Vielfache von 32 |
| RS232/485/422 Conflict Time Gap | 5 ms | Werkswert |
| No-Data-Restart | **Disable** | Sonst Neustart des Gateways, wenn > 300 s nicht gepollt wird (z. B. beim Deploy) |
| Destination IP/Port, Reconnect-time | egal | gelten nur im Client-Modus |

Schnelltest vom PC: `python tools/h300_modbus_test.py 192.168.1.200 4196 1 tcp` (liest nur). Alternativ mit `mbpoll` oder Modbus Poll: Holding Register **36864** (= 9000H) lesen, Slave 1. Im Stillstand kommt 0 zurück, im Lauf die Frequenz × 100.

## 4. APIXON / 4diac

**Feste IP:** `Ventilsteuerung/APIXON/ethernet.ini` als `/data/ethernet.ini` auf die APIXON
legen und neu starten (Abschnitt `ETH_INT`, `DHCP_CLIENT = 0`, IP 192.168.1.11). Ohne diese Datei
nutzt die Firmware DHCP und fällt ohne DHCP-Server auf eine 169.254.x.x-Adresse zurück.


1. 4diac IDE (3.4, wie Krauternter) mit Workspace `Ventilsteuerung/4diacIDE-workspace` starten und das Projekt `FU_Demo` importieren.
2. In `FU_Demo_Konstanten.gcf` die IP der APIXON (`APIXON`) und die des Gateways prüfen.
3. Deploy wie in Krauternter: Boot-File erzeugen, `libs.json` mit `make_libs_manifest.py` (Krauternter `scripts_central`) erzeugen und hochladen. Benötigte ELF-Libs: `events`, `iec61131-3`, `signalprocessing`, `logiBUS_signalprocessing`. `net`/Modbus/OPC UA kommen aus der Firmware.
4. Im FORTE-Log sollte `Connection to Modbus server succeded` erscheinen.

## 5. Dashboard

`Ventilsteuerung/Web-Clients/opcua-dashboard/dist/fu-demo-dashboard.html` ist eine einzelne Datei und läuft ohne Server, z. B. auf dem Tablet. Endpoint `ws://<APIXON-IP>:4841` eintragen und „Verbinden“ klicken.

Erste Fahrt: Sollfrequenz 10 Hz senden → „Vorwärts“ → Ist-Frequenz steigt mit der Rampe → „Stopp (Rampe)“.

## Fahrtest am 2026-11-02 (direkt per Modbus, ohne APIXON)

Gateway 192.168.1.200:4196, Schreiben mit Funktionscode 0x10 (wie FORTE):

| Kommando | Ergebnis |
|---|---|
| 9301H := 2000 (10 Hz), 9300H := 1 | vorwärts, nach ~4 s 10,00 Hz, 1,56 A, 93 V |
| 9300H := 6 | Rampenstopp, ~3 s bis 0 Hz |
| 9301H := 2000, 9300H := 2 | rückwärts, 10,00 Hz, 1,55 A, 93 V (Rückwärtslauf erlaubt) |
| 9300H := 6 | Rampenstopp, ~3 s bis 0 Hz |

Nach Aus-/Einschalten: P0.1.06/P0.1.09 bleiben erhalten, 9301H startet mit 0 Hz.

## Fehlersuche

| Symptom | Ursache / Prüfung |
|---|---|
| Alle Werte bleiben 0 | Gateway nicht im Modbus-TCP-Modus, falscher Port in der GCF (Test: `python tools/h300_modbus_test.py 192.168.1.200 4196 1 tcp`), falsche IP, oder Baud/Stoppbits passen nicht |
| Werte kommen, Kommandos wirken nicht | P0.1.06 ≠ 2, oder der H300 lehnt Funktionscode 0x10 ab (siehe README „Offene Risiken“) |
| Frequenz-Sollwert wirkt nicht | P0.1.09 ≠ 9, oder P0.1.16 passt nicht zu `FU_FMAX_HZ` |
| Frequenz bleibt bei 50 Hz hängen | P0.1.18 (obere Grenzfrequenz) noch auf 50.00 |
| Err47 am Umrichter | Kommunikationstimeout (P2.8.04). Polling läuft nicht: APIXON oder Netz prüfen |

## Befund 2026-11-02: Waveshare-Gateway defekt

**Symptom:** Er47.1 bzw. Er47.2 am Umrichter, auch bei 1 Hz. Im APIXON-Log `Error reading input status ::
Connection timed out`, danach mehrere Sekunden `Connection to Modbus server failed`. Dashboard ohne Anzeige
(siehe [SICHERHEIT_Offene_Punkte.md](SICHERHEIT_Offene_Punkte.md), Punkt 6).

**Ablauf der Fehlersuche (Dauer-Ping PC → Gateway/APIXON, Switch-Log, LEDs):**

| Beobachtung | Folgerung |
|---|---|
| Ping zum Gateway fällt 4–17 s aus, APIXON bleibt erreichbar | Problem am Gateway-Port bzw. Gateway, nicht im Netz |
| FORTE-Log und Ping zeitgleich, gleiche Dauer | Er47 ist Folge, nicht Ursache (5 s ohne Abfrage = P2.8.04) |
| Switch-Log: `LINK-UPDOWN … GigabitEthernet 1/2`, keine PoE-Ereignisse | reiner Ethernet-Linkverlust |
| Kabel getauscht, altes Kabel am PC ohne Probleme | Kabel ausgeschlossen |
| Gateway an Port 3 statt 2: wieder Ausfälle | Switch-Port ausgeschlossen |
| Switch: EEE, ActiPHY, PerfectReach aus; PoE PD-Alive aus | Switch-Funktionen ausgeschlossen |
| Gateway: Instruction Time out 32→320 ms, No-Data-Restart aus, Reconnect-time 255 | Gateway-Einstellungen ausgeschlossen |
| Gateway zeitweise komplett dunkel, zuletzt dauerhaft | Versorgung im Gateway setzt aus |
| Separates 9-V-Steckernetzteil (am Stecker gemessen) an DC-Eingang: bleibt dunkel | **Gateway defekt** (interner Spannungswandler, über den PoE und DC laufen) |

**Ersatz:** Gateway gleichen Typs mit der Tabelle in Abschnitt 3 einstellen (IP 192.168.1.200, Port 4196,
9600/8/N/2, Modbus TCP to RTU, Instruction Time out 320 ms, No-Data-Restart aus). 4diac und Dashboard
brauchen dann keine Änderung.

**Nebenbefunde:**
- Mit Instruction Time out 320 ms beantwortet das Gateway auch die erste Anfrage nach dem Verbindungsaufbau.
  Bei 32 ms ging sie verloren.
- Der Switch ALL-SGI8106PMJ hat ab Werk **192.168.2.1** (admin/admin), also ein anderes Subnetz als die Demo.
  Zum Konfigurieren dem PC eine Zweit-IP 192.168.2.x geben. Empfehlung: Switch-IP auf 192.168.1.x setzen
  und Passwort ändern.

