# Sicherheit – offene Punkte FU-Demo

Stand 2026-11-02. **Vor jeder Vorführung mit drehendem Motor durchgehen.**

## 1. Motor läuft weiter, wenn das Dashboard wegfällt ⚠️ OFFEN

Die Kommunikationsüberwachung am Umrichter (P2.8.07 = 1, P2.8.04 = 5,0 s, Err47)
prüft nur, ob **irgendwer** den Umrichter regelmäßig abfragt. Das macht die APIXON von selbst
alle 500 ms (`FU_Messwerte`, `CLIENT_0_8`).

| Ausfall | Folge |
|---|---|
| APIXON, FORTE oder Netz APIXON ↔ Gateway | Nach 5 s Err47, Motor stoppt ✅ |
| Gateway oder RS485-Leitung | Nach 5 s Err47, Motor stoppt ✅ |
| **Browser zu, Tablet aus, WLAN weg, Dashboard-Tab hängt** | **Motor läuft mit der letzten Frequenz weiter**, und über das Dashboard kann ihn niemand mehr stoppen ❌ |

Grund: Die 4diac-Applikation schreibt das Steuerwort (9300H) nur, wenn das Dashboard einen Befehl schickt.
Fällt das Dashboard aus, bleibt der letzte Befehl (z. B. „Vorwärts“) im Umrichter stehen.

**Bis das gelöst ist:**

- Not-Halt bzw. STOP-Taste am Umrichter muss während der Demo **immer erreichbar** sein
  (STOP-Taste wirkt auch im Modbus-Betrieb, siehe Punkt 2).
- Den Motor nicht unbeaufsichtigt laufen lassen.

**Mögliche Lösung (noch nicht umgesetzt):** Lebenszeichen vom Dashboard

- Das Dashboard schreibt z. B. alle 1 s einen Zähler auf einen OPC-UA-Knoten `FU1.Lebenszeichen`.
- Eine vierte SubApp in 4diac überwacht ihn. Kommt länger als z. B. 3 s nichts, schreibt sie
  Steuerwort **6 (Rampenstopp)** auf 9300H. Dafür reichen Standard-FBs, z. B. `SUBSCRIBE_1` → `E_DELAY`
  (bei jedem neuen Wert neu gestartet) → Stopp-Write.
- Bei mehreren Dashboards gleichzeitig muss festgelegt werden, wessen Lebenszeichen zählt.

## 2. STOP-Taste am Bedienteil im Kommunikationsbetrieb ✅ erledigt

Am 2026-11-02 getestet: Die STOP-Taste am H300 stoppt den Motor auch bei P0.1.06 = 2
(Steuerung über Modbus).

Nach einem Stopp am Bedienteil läuft der Motor nicht von selbst wieder an. Die 4diac-Applikation
schreibt das Steuerwort (9300H) nur, wenn im Dashboard ein Befehl gedrückt wird. Ein geänderter
Sollwert geht nur auf 9301H und startet nicht. Wieder anlaufen lässt ihn erst ein bewusstes
„Vorwärts“ oder „Rückwärts“.

## 3. Kein hardwareseitiger Not-Halt in der Demo ⚠️ OFFEN

Alle Stopp-Wege laufen bisher über Software oder Kommunikation. Für eine Demo mit
berührbaren drehenden Teilen braucht es einen Not-Halt, der unabhängig davon wirkt:
- Schütz bzw. Trennung in der Netzzuleitung, oder
- ein für Not-Halt geeigneter Klemmeneingang des H300, z. B. ein DI als „Externer Fehler“ oder
  „Freier Auslauf“. Das gilt nicht als Sicherheitsfunktion im Sinne der Norm, solange es kein STO ist.

## 4. Err47 nach jedem Start der APIXON ℹ️ so gewollt

Pollt niemand (APIXON aus, bootet, wird neu deployt), geht der Umrichter nach 5 s auf Err47,
auch im Stillstand. Nach dem Start einmal im Dashboard „Störung quittieren“ drücken.
Der Fehler bleibt bewusst stehen (P2.8.07 = 1, nicht 2), damit nach einem Verbindungsausfall
niemand überrascht wird.

## 5. Sollwert nach Netz-Aus ℹ️ erledigt

9301H wird nicht gespeichert. Nach dem Einschalten steht der Sollwert auf 0 Hz, ein Anlauf mit
der alten Frequenz ist nicht möglich. Getestet am 2026-11-02.

## 6. Ausfall der Modbus-Kommunikation wird nicht angezeigt ⚠️ OFFEN

Fällt das Gateway oder die RS485-Seite aus, merkt das nur die FORTE-Konsole. Die 4diac-Applikation und das
Dashboard zeigen die **letzten Werte unverändert weiter an**: eingefroren, aber scheinbar gültig. Grund:
Der FORTE-Modbus-Layer meldet nur Erfolg (`CNF` nur bei `nrVals > 0`, `modbuspoll.cpp`), Lesefehler
landen nur im Log.

Der Umrichter selbst stoppt nach 5 s mit Err47 (Punkt 4), die Sicherheit ist also gegeben. Die Anzeige täuscht aber.

**Geplante Lösung:** Watchdog in 4diac (`E_RDELAY` wird von jedem erfolgreichen `CNF` nachgeladen, nach 2 s ohne
Abfrage wird `FU1.KommunikationOK` FALSE). Das Dashboard zeigt dann einen Warnbalken, graut die Messwerte aus
und sperrt die Fahrknöpfe. Später zusätzlich in FORTE: Lesefehler als `CNF` mit `QO = FALSE` melden.

## Erledigt

| Punkt | Datum | Ergebnis |
|---|---|---|
| Kommunikationsüberwachung P2.8.07 = 1 / P2.8.04 = 5,0 s | 2026-11-02 | Err47 nach 8 s ohne Abfrage, Quittieren (Steuerwort 7) funktioniert |
| Sollwert 0 Hz nach Netz-Aus | 2026-11-02 | geprüft |
| STOP-Taste am Bedienteil im Modbus-Betrieb | 2026-11-02 | stoppt den Motor |
