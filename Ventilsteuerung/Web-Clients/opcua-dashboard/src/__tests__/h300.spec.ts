import { describe, it, expect } from 'vitest'
import { FMAX_HZ, begrenzeSollFrequenz, fehlerText, kommandoText, laeuft, statusText } from '../h300'

describe('h300', () => {
  it('maps the 9332H run status', () => {
    expect(statusText(1)).toBe('Läuft vorwärts')
    expect(statusText(3)).toBe('Gestoppt')
    expect(laeuft(2)).toBe(true)
    expect(laeuft(3)).toBe(false)
  })

  it('maps 9333H fault codes, including unknown ones', () => {
    expect(fehlerText(0)).toBe('Keine Störung')
    expect(fehlerText(47)).toContain('RS485')
    expect(fehlerText(99)).toBe('Fehlercode 99')
  })

  it('names the 9300H control words', () => {
    expect(kommandoText(6)).toBe('Rampenstopp')
    expect(kommandoText(42)).toBe('unbekannt (42)')
  })

  it('clamps the frequency setpoint to 0..FMAX', () => {
    expect(begrenzeSollFrequenz(-5)).toBe(0)
    expect(begrenzeSollFrequenz(FMAX_HZ + 10)).toBe(FMAX_HZ)
    expect(begrenzeSollFrequenz(Number.NaN)).toBe(0)
  })
})
