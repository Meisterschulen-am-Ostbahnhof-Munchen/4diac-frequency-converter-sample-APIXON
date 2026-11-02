// DELIXI H300 Kodierungen (Handbuch Kap. 9.1.5.1) und die OPC-UA-Knoten der
// FU-Demo. Die NodeIds muessen zu FU_Demo_Konstanten.gcf passen
// (FU_MESSWERTE_WEB_WRITE / FU_KOMMANDO_WEB_READ / FU_SOLLFREQUENZ_WEB_READ).

// Muss zu FU_FMAX_HZ in der GCF und zu P0.1.16 am Umrichter passen.
export const FMAX_HZ = 50

export const MESSWERT_NODES = [
  { key: 'istFrequenz', nodeId: 'ns=1;s=FU1.IstFrequenz' },
  { key: 'sollFrequenzAktiv', nodeId: 'ns=1;s=FU1.SollFrequenzAktiv' },
  { key: 'strom', nodeId: 'ns=1;s=FU1.Strom' },
  { key: 'ausgangsspannung', nodeId: 'ns=1;s=FU1.Ausgangsspannung' },
  { key: 'zwischenkreisspannung', nodeId: 'ns=1;s=FU1.Zwischenkreisspannung' },
  { key: 'leistung', nodeId: 'ns=1;s=FU1.Leistung' },
  { key: 'status', nodeId: 'ns=1;s=FU1.Status' },
  { key: 'fehlercode', nodeId: 'ns=1;s=FU1.Fehlercode' },
] as const

export type MesswertKey = (typeof MESSWERT_NODES)[number]['key']

export const KOMMANDO_NODE = 'ns=1;s=FU1.Kommando'
export const SOLLFREQUENZ_NODE = 'ns=1;s=FU1.SollFrequenz'
// Lebenszeichen der APIXON, Int32 0..99 alle 200 ms (SystemTickSender_OPC)
export const TICK_NODE = 'ns=1;s=FU1.SYSTEM_TICK'

// Steuerwort 9300H
export const KOMMANDO = {
  VORWAERTS: 1,
  RUECKWAERTS: 2,
  FREIER_AUSLAUF: 5,
  RAMPENSTOPP: 6,
  QUITTIEREN: 7,
} as const

const KOMMANDO_TEXT: Record<number, string> = {
  0: '–',
  1: 'Vorwärts',
  2: 'Rückwärts',
  3: 'Tippen vorwärts',
  4: 'Tippen rückwärts',
  5: 'Freier Auslauf',
  6: 'Rampenstopp',
  7: 'Fehler quittieren',
}

export function kommandoText(wort: number): string {
  return KOMMANDO_TEXT[wort] ?? `unbekannt (${wort})`
}

// Betriebsstatus 9332H
export function statusText(status: number): string {
  switch (status) {
    case 1: return 'Läuft vorwärts'
    case 2: return 'Läuft rückwärts'
    case 3: return 'Gestoppt'
    default: return 'keine Daten'
  }
}

export function laeuft(status: number): boolean {
  return status === 1 || status === 2
}

// Fehlercode 9333H; '/' im Handbuch = reserviert
const FEHLER_TEXT: Record<number, string> = {
  0: 'Keine Störung',
  1: 'Überstrom bei konstanter Drehzahl',
  2: 'Überstrom beim Beschleunigen',
  3: 'Überstrom beim Verzögern',
  4: 'Überspannung bei konstanter Drehzahl',
  5: 'Überspannung beim Beschleunigen',
  6: 'Überspannung beim Verzögern',
  8: 'Unterspannung',
  9: 'Umrichter-Überlast',
  10: 'Motor-Überlast',
  11: 'Phasenausfall Eingang',
  12: 'Phasenausfall Ausgang',
  13: 'Externe Störung',
  14: 'Kommunikationsfehler Erweiterungskarte',
  15: 'IGBT-Übertemperatur',
  16: 'Hardwarefehler Umrichter',
  17: 'Erdschluss beim Einschalten',
  18: 'Fehler Motoridentifikation',
  19: 'Motor-Lastverlust',
  20: 'PID-Rückführung verloren',
  21: 'Benutzerdefinierte Störung 1',
  22: 'Benutzerdefinierte Störung 2',
  23: 'Einschaltzeit erreicht',
  24: 'Betriebszeit erreicht',
  25: 'Geberfehler',
  26: 'Parameter-Lese-/Schreibfehler',
  27: 'Motor-Übertemperatur',
  28: 'Zu große Drehzahlabweichung',
  29: 'Motor-Überdrehzahl',
  30: 'Fehler Anfangsposition',
  31: 'Fehler Stromerfassung',
  34: 'Timeout schnelle Strombegrenzung',
  35: 'Fehler Mehrmotorbetrieb',
  39: 'Kurzschluss Ausgang',
  40: 'Kurzschluss Bremschopper',
  41: 'Hardwarefehler Ladewiderstand-Relais',
  42: 'Logikfehler Polagenerkennung (Synchronmotor)',
  43: 'Fehler Umschaltung Netz/Umrichter',
  44: 'Fehler Motoridentifikation',
  45: 'Überdrehmoment',
  46: 'Kippschutz',
  47: 'RS485-Kommunikationsfehler (Err47)',
  48: 'Ethernet-Kommunikationsfehler',
  49: 'Type-C-Kommunikationsfehler',
}

export function fehlerText(code: number): string {
  return FEHLER_TEXT[code] ?? `Fehlercode ${code}`
}

export function begrenzeSollFrequenz(hz: number): number {
  if (!Number.isFinite(hz)) return 0
  return Math.min(Math.max(hz, 0), FMAX_HZ)
}
