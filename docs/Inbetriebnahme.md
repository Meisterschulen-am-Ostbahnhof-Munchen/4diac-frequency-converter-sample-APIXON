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
| P0.1.16 | 50.00 | Maximalfrequenz. Muss zu `FU_FMAX_HZ`/`FU_SOLLWERT_FAKTOR` (GCF) und `FMAX_HZ` (Dashboard `src/h300.ts`) passen |
| P0.1.40 | 1 | Slave-Adresse (Werksdefault). Steht im Modbus-ID-String |
| P2.8.00 | 3 | 9600 Baud (Werksdefault) |
| P2.8.01 | 0 | 8-N-2 (Werksdefault, **2 Stoppbits**) |
| P2.8.05 | 1 | RTU |
| P2.8.06 | 0 | Antwort senden |
| P2.8.04 / P2.8.07 | 5,0 s / 2 | Optional: Err47, wenn länger als 5 s keine Anfrage kommt. Bei 500-ms-Polling ist das ein Watchdog gegen ausgefallene SPS oder Netz |

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

Schnelltest vom PC: `python tools/h300_modbus_test.py 192.168.1.200 4196 1 tcp` (liest nur). Alternativ mit `mbpoll` oder Modbus Poll: Holding Register **36864** (= 9000H) lesen, Slave 1. Im Stillstand kommt 0 zurück, im Lauf die Frequenz × 100.

## 4. APIXON / 4diac

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
| Err47 am Umrichter | Kommunikationstimeout (P2.8.04). Polling läuft nicht: APIXON oder Netz prüfen |
