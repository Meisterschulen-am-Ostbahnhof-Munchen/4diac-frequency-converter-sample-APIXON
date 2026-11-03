<template>
  <div class="app" :class="{ hell }">
    <header>
      <div class="kopfzeile">
        <h1>FU-Demo &ndash; DELIXI H300G0R75P1R1T4B (0,75 kW)</h1>
        <button class="anzeige thema" :title="hell ? 'Dunkle Darstellung' : 'Helle Darstellung'" @click="toggleThema">
          {{ hell ? '☾ Dunkel' : '☀ Hell' }}
        </button>
      </div>
      <div class="connection">
        <span class="dot" :class="{ on: connected }"></span>
        <span v-if="connected" class="tick-badge" :class="{ pulse: tickChanged }" title="Lebenszeichen der APIXON">{{ tick }}</span>
        <input v-model="endpointUrl" class="url-input" :disabled="connected || connecting" />
        <button @click="connected || connecting ? disconnect() : connect()">
          {{ connected ? 'Trennen' : connecting ? 'Abbrechen' : 'Verbinden' }}
        </button>
        <button class="anzeige" :class="{ aktiv: istVollbild }" @click="toggleVollbild">
          {{ istVollbild ? '⤢ Vollbild aus' : '⛶ Vollbild' }}
        </button>
        <button class="anzeige" :class="{ aktiv: wachHalten }" title="Bildschirm nicht abschalten" @click="toggleWachHalten">
          {{ wachHalten ? '☀ Wach' : '☾ Standby' }}
        </button>
      </div>
      <p class="status-line">{{ verbindungsText }}</p>
    </header>

    <section class="zustand" :class="{ laeuft: istLaeuft, stoerung: hatStoerung }">
      <div class="zustand-text">{{ statusText(werte.status) }}</div>
      <div v-if="hatStoerung" class="fehler">
        Störung {{ werte.fehlercode }}: {{ fehlerText(werte.fehlercode) }}
      </div>
    </section>

    <section class="kacheln">
      <div class="kachel gross">
        <span class="label">Ist-Frequenz</span>
        <span class="wert">{{ fmt(werte.istFrequenz, 2) }}<small> Hz</small></span>
        <span class="neben">Sollwert aktiv: {{ fmt(werte.sollFrequenzAktiv, 2) }} Hz</span>
      </div>
      <div class="kachel">
        <span class="label">Strom</span>
        <span class="wert">{{ fmt(werte.strom, 2) }}<small> A</small></span>
      </div>
      <div class="kachel">
        <span class="label">Ausgangsspannung</span>
        <span class="wert">{{ fmt(werte.ausgangsspannung, 0) }}<small> V</small></span>
      </div>
      <div class="kachel">
        <span class="label">Zwischenkreis</span>
        <span class="wert">{{ fmt(werte.zwischenkreisspannung, 1) }}<small> V</small></span>
      </div>
      <div class="kachel">
        <span class="label">Leistung</span>
        <span class="wert">{{ fmt(werte.leistung, 1) }}<small> kW</small></span>
      </div>
    </section>

    <div class="unten">
      <section class="trend">
        <div class="trend-kopf">
          <span>Verlauf 60 s</span>
          <span class="legende"><i class="f"></i>Frequenz (0&ndash;{{ FMAX_HZ }} Hz) <i class="a"></i>Strom (auto)</span>
        </div>
        <div class="trend-flaeche">
          <canvas ref="trendCanvas" width="860" height="160"></canvas>
        </div>
      </section>

      <section class="bedienung">
        <h2>Bedienung</h2>
        <div class="buttons">
          <button class="start" :disabled="!connected || hatStoerung" @click="sendeKommando(KOMMANDO.VORWAERTS)">▶ Vorwärts</button>
          <button class="start" :disabled="!connected || hatStoerung" @click="sendeKommando(KOMMANDO.RUECKWAERTS)">◀ Rückwärts</button>
          <button class="stopp" :disabled="!connected" @click="sendeKommando(KOMMANDO.RAMPENSTOPP)">■ Stopp (Rampe)</button>
          <button class="stopp" :disabled="!connected" @click="sendeKommando(KOMMANDO.FREIER_AUSLAUF)">Freier Auslauf</button>
          <button class="quitt" :disabled="!connected || !hatStoerung" @click="sendeKommando(KOMMANDO.QUITTIEREN)">Störung quittieren</button>
        </div>
        <p class="hinweis">Zuletzt gesendet: {{ kommandoText(letztesKommando) }}</p>

        <div class="soll">
          <label>Sollfrequenz</label>
          <input type="range" min="0" :max="FMAX_HZ" step="0.5" v-model.number="sollEingabe" :disabled="!connected" />
          <input type="number" min="0" :max="FMAX_HZ" step="0.1" v-model.number="sollEingabe" :disabled="!connected" class="zahl" />
          <span>Hz</span>
          <button :disabled="!connected" @click="sendeSollFrequenz">Senden</button>
        </div>
        <p class="hinweis">Am OPC-UA-Knoten: {{ fmt(letzteSollFrequenz, 1) }} Hz (Begrenzung 0&ndash;{{ FMAX_HZ }} Hz macht die 4diac-Applikation)</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import NoSleep from 'nosleep.js'
import {
  OPCUAClient,
  MessageSecurityMode,
  SecurityPolicy,
  ClientSubscription,
  AttributeIds,
  TimestampsToReturn,
  DataType,
  coerceNodeId,
  WriteValue,
  DataValue,
  Variant,
} from '@wsopcua/wsopcua'
import {
  FMAX_HZ,
  MESSWERT_NODES,
  KOMMANDO_NODE,
  SOLLFREQUENZ_NODE,
  TICK_NODE,
  KOMMANDO,
  kommandoText,
  statusText,
  fehlerText,
  laeuft,
  begrenzeSollFrequenz,
  type MesswertKey,
} from './h300'

// Port 4841 = OPC UA ueber WebSocket der APIXON-FORTE (wie im Krauternter-Dashboard).
// Vom Geraet selbst ausgeliefert (http://<APIXON>/fu-demo-dashboard.html) -> dessen Host,
// als lokale Datei geoeffnet (file://) -> feste APIXON-IP.
const endpointUrl = ref(
  `ws://${window.location.protocol.startsWith('http') && window.location.hostname ? window.location.hostname : '192.168.1.11'}:4841`
)
const connected = ref(false)
const verbindungsText = ref('Getrennt')

const werte = reactive<Record<MesswertKey, number>>({
  istFrequenz: 0,
  sollFrequenzAktiv: 0,
  strom: 0,
  ausgangsspannung: 0,
  zwischenkreisspannung: 0,
  leistung: 0,
  status: 0,
  fehlercode: 0,
})
const letztesKommando = ref(0)
const letzteSollFrequenz = ref(0)
const sollEingabe = ref(25)

const istLaeuft = computed(() => laeuft(werte.status))
const hatStoerung = computed(() => werte.fehlercode !== 0)

function fmt(v: number, stellen: number): string {
  return connected.value ? v.toFixed(stellen).replace('.', ',') : '–'
}

let client: any = null
let session: any = null

// Lebenszeichen der APIXON (SystemTickSender_OPC: 0..99 alle 200 ms)
const tick = ref<number | string>('–')
const tickChanged = ref(false)
let tickPulseTimer: ReturnType<typeof setTimeout> | undefined

// Eigene Wiederholung statt connectionStrategy (bleibt maxRetry 0): die APIXON
// ist nach einem Neustart erst nach einigen Sekunden erreichbar.
const CONNECT_ATTEMPTS = 5
const CONNECT_RETRY_MS = 3000
const connecting = ref(false)
// Jeder connect()/disconnect() erhoeht den Zaehler; laufende Versuche mit
// altem Stand brechen ab.
let connectRun = 0
let reconnectTimer: ReturnType<typeof setTimeout> | undefined

function resetWerte() {
  for (const n of MESSWERT_NODES) werte[n.key] = 0
  tick.value = '–'
}

// Alten Client immer trennen, sonst bleibt die Verbindung auf der APIXON
// belegt, bis sie dort in den Timeout laeuft.
async function closeClient() {
  const c = client
  client = null
  session = null
  if (!c) return
  c.off('connection_lost', handleLost)
  c.off('close', handleLost)
  try {
    await c.disconnectP()
  } catch {
    // war schon getrennt
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function handleLost() {
  if (!connected.value) return
  connected.value = false
  void closeClient()
  clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(connect, CONNECT_RETRY_MS)
  verbindungsText.value = 'Fehler: Verbindung verloren, neuer Versuch…'
  resetWerte()
}

async function connect() {
  const run = ++connectRun
  clearTimeout(reconnectTimer)
  connecting.value = true
  await closeClient()

  for (let attempt = 1; ; attempt++) {
    if (run !== connectRun) return
    verbindungsText.value = attempt === 1 ? 'Verbinde…' : `Verbinde… (Versuch ${attempt}/${CONNECT_ATTEMPTS})`
    client = new OPCUAClient({
      securityMode: MessageSecurityMode.None,
      securityPolicy: SecurityPolicy.None,
      endpoint_must_exist: false,
      connectionStrategy: { maxRetry: 0 },
    })
    try {
      await client.connectP(endpointUrl.value)
      break
    } catch (err) {
      await closeClient()
      if (run !== connectRun) return
      if (attempt >= CONNECT_ATTEMPTS) {
        console.error('FU-Demo connect failed:', err)
        verbindungsText.value = `Fehler: ${err}`
        connecting.value = false
        return
      }
      await sleep(CONNECT_RETRY_MS)
    }
  }
  if (run !== connectRun) return

  try {
    client.on('connection_lost', handleLost)
    client.on('close', handleLost)
    session = await client.createSessionP({})
    if (run !== connectRun) return
    connected.value = true
    connecting.value = false
    verbindungsText.value = 'Verbunden'

    const subscription = new ClientSubscription(session, {
      requestedPublishingInterval: 200,
      requestedLifetimeCount: 100,
      requestedMaxKeepAliveCount: 10,
      maxNotificationsPerPublish: 100,
      publishingEnabled: true,
      priority: 10,
    })

    const messwertGroup = await subscription.monitorItemsP(
      MESSWERT_NODES.map((n) => ({ nodeId: coerceNodeId(n.nodeId), attributeId: AttributeIds.Value })),
      { samplingInterval: 200, discardOldest: true, queueSize: 2 },
      TimestampsToReturn.Neither
    )
    messwertGroup.on('changed', (_item: any, dataValue: any, index: number) => {
      werte[MESSWERT_NODES[index].key] = Number(dataValue.value?.value ?? 0)
    })

    // Die Kommando-Knoten selbst mitlesen: zeigt, was zuletzt (von irgendeinem Client) gesendet wurde
    const kommandoGroup = await subscription.monitorItemsP(
      [
        { nodeId: coerceNodeId(KOMMANDO_NODE), attributeId: AttributeIds.Value },
        { nodeId: coerceNodeId(SOLLFREQUENZ_NODE), attributeId: AttributeIds.Value },
      ],
      { samplingInterval: 200, discardOldest: true, queueSize: 2 },
      TimestampsToReturn.Neither
    )
    kommandoGroup.on('changed', (_item: any, dataValue: any, index: number) => {
      const v = Number(dataValue.value?.value ?? 0)
      if (index === 0) letztesKommando.value = v
      else letzteSollFrequenz.value = v
    })

    const tickGroup = await subscription.monitorItemsP(
      [{ nodeId: coerceNodeId(TICK_NODE), attributeId: AttributeIds.Value }],
      { samplingInterval: 100, discardOldest: true, queueSize: 2 },
      TimestampsToReturn.Neither
    )
    tickGroup.on('changed', (_item: any, dataValue: any) => {
      tick.value = dataValue.value?.value ?? '–'
      tickChanged.value = true
      clearTimeout(tickPulseTimer)
      tickPulseTimer = setTimeout(() => { tickChanged.value = false }, 400)
    })
  } catch (err) {
    if (run !== connectRun) return
    console.error('FU-Demo connect failed:', err)
    verbindungsText.value = `Fehler: ${err}`
    connected.value = false
    connecting.value = false
    await closeClient()
  }
}

async function disconnect() {
  connectRun++
  clearTimeout(reconnectTimer)
  connecting.value = false
  await closeClient()
  connected.value = false
  verbindungsText.value = 'Getrennt'
  resetWerte()
}

async function schreibe(nodeId: string, dataType: DataType, value: number) {
  if (!session) return
  try {
    const wv = new WriteValue({
      nodeId: coerceNodeId(nodeId),
      attributeId: AttributeIds.Value,
      value: new DataValue({ value: new Variant({ dataType, value }) }),
    })
    await session.writeP([wv])
  } catch (err) {
    console.error(`FU-Demo write ${nodeId} failed:`, err)
  }
}

function sendeKommando(wort: number) {
  // Jeder Write loest in FORTE genau einen Modbus-Write auf 9300H aus
  return schreibe(KOMMANDO_NODE, DataType.UInt16, wort)
}

function sendeSollFrequenz() {
  sollEingabe.value = begrenzeSollFrequenz(sollEingabe.value)
  return schreibe(SOLLFREQUENZ_NODE, DataType.Float, sollEingabe.value)
}

// Trend: Ringpuffer, 5 Samples/s ueber 60 s
const TREND_PUNKTE = 300
const trendFrequenz: number[] = []
const trendStrom: number[] = []
const trendCanvas = ref<HTMLCanvasElement | null>(null)
let trendTimer: ReturnType<typeof setInterval> | undefined

function trendSample() {
  trendFrequenz.push(connected.value ? werte.istFrequenz : NaN)
  trendStrom.push(connected.value ? werte.strom : NaN)
  if (trendFrequenz.length > TREND_PUNKTE) trendFrequenz.shift()
  if (trendStrom.length > TREND_PUNKTE) trendStrom.shift()
  zeichneTrend()
}

function zeichneLinie(ctx: CanvasRenderingContext2D, daten: number[], max: number, farbe: string) {
  const w = ctx.canvas.width
  const h = ctx.canvas.height
  ctx.strokeStyle = farbe
  ctx.lineWidth = 2
  ctx.beginPath()
  let offen = false
  daten.forEach((v, i) => {
    if (Number.isNaN(v)) { offen = false; return }
    const x = (i / (TREND_PUNKTE - 1)) * w
    const y = h - 4 - (Math.min(v, max) / max) * (h - 8)
    if (offen) ctx.lineTo(x, y)
    else ctx.moveTo(x, y)
    offen = true
  })
  ctx.stroke()
}

function zeichneTrend() {
  const canvas = trendCanvas.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx) return
  // Zeichenflaeche wird per CSS gestreckt (fuellt im Tablet-Layout die Resthoehe):
  // Pixelaufloesung an die tatsaechliche Groesse anpassen, sonst verzerrte Linien
  const breite = Math.round(canvas.clientWidth)
  const hoehe = Math.round(canvas.clientHeight)
  if (breite > 0 && hoehe > 0 && (canvas.width !== breite || canvas.height !== hoehe)) {
    canvas.width = breite
    canvas.height = hoehe
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.strokeStyle = hell.value ? '#c3cddc' : '#2a3a5e'
  ctx.lineWidth = 1
  for (let i = 1; i < 4; i++) {
    const y = (canvas.height / 4) * i
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke()
  }
  const stromMax = Math.max(1, ...trendStrom.filter((v) => !Number.isNaN(v))) * 1.2
  zeichneLinie(ctx, trendFrequenz, FMAX_HZ, hell.value ? '#0277bd' : '#4fc3f7')
  zeichneLinie(ctx, trendStrom, stromMax, hell.value ? '#e65100' : '#ffb74d')
}

// Helle/dunkle Darstellung, pro Geraet im Browser gemerkt (localStorage kann fehlen
// oder werfen, z. B. im privaten Modus - dann einfach dunkel).
const THEMA_KEY = 'fu-demo-thema'
function leseThema(): boolean {
  try { return localStorage.getItem(THEMA_KEY) === 'hell' } catch { return false }
}
const hell = ref(leseThema())

function wendeThemaAn() {
  // Seitenhintergrund ausserhalb von .app (Ueberscrollen, Raender) mitziehen
  document.body.style.background = hell.value ? '#eef1f6' : '#1a1a2e'
  zeichneTrend()
}

function toggleThema() {
  hell.value = !hell.value
  try { localStorage.setItem(THEMA_KEY, hell.value ? 'hell' : 'dunkel') } catch { /* egal */ }
  wendeThemaAn()
}

// Vollbild (Fullscreen-API, geht auch ueber http://) und Bildschirm wach halten.
// Die Wake-Lock-API gibt es in Chrome nur auf sicheren Seiten (HTTPS/localhost) -
// die APIXON liefert aber http:// aus. NoSleep.js nimmt den echten Wake Lock, wenn
// vorhanden, sonst ein unsichtbares stummes Endlos-Video. Beides nur aus einem Klick heraus.
const istVollbild = ref(false)
const wachHalten = ref(false)
let noSleep: NoSleep | null = null

async function wachHaltenAn() {
  noSleep ??= new NoSleep()
  try {
    await noSleep.enable()
    wachHalten.value = true
  } catch (err) {
    console.error('Wach halten nicht moeglich:', err)
  }
}

function wachHaltenAus() {
  noSleep?.disable()
  wachHalten.value = false
}

function toggleWachHalten() {
  return wachHalten.value ? wachHaltenAus() : wachHaltenAn()
}

async function toggleVollbild() {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen()
    } else {
      // wachHaltenAn() zuerst: braucht wie requestFullscreen() die Klick-Geste
      if (!wachHalten.value) await wachHaltenAn()
      await document.documentElement.requestFullscreen({ navigationUI: 'hide' })
    }
  } catch (err) {
    console.error('Vollbild nicht moeglich:', err)
  }
}

function onFullscreenChange() {
  istVollbild.value = !!document.fullscreenElement
}

function onVisibilityChange() {
  // Nach Tab-Wechsel/Display-Aus haelt der Browser Wake Lock bzw. Video an
  if (wachHalten.value && document.visibilityState === 'visible' && noSleep && !noSleep.isEnabled) {
    noSleep.enable().catch(() => { wachHalten.value = false })
  }
}

onMounted(() => {
  wendeThemaAn()
  trendTimer = setInterval(trendSample, 200)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  clearInterval(trendTimer)
  clearTimeout(tickPulseTimer)
  clearTimeout(reconnectTimer)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  wachHaltenAus()
  disconnect()
})
</script>

<style scoped>
* { box-sizing: border-box; }

/* Farben: dunkel (Standard) und hell, umgeschaltet ueber die Klasse .hell */
.app {
  --bg: #1a1a2e;
  --flaeche: #16213e;
  --feld: #0f1629;
  --rand: #2a3a5e;
  --text: #e0e0e0;
  --text-stark: #fff;
  --text-mittel: #bbb;
  --text-leise: #999;
  --akzent: #4fc3f7;
  --akzent2: #ffb74d;
  --ok-text: #4ade80;
  --stoer-bg: #3b1218;
  --stoer-text: #ff8a80;
  --knopf-bg: #2a3a5e;
  --knopf-text: #fff;
  color-scheme: dark;
}
.app.hell {
  --bg: #eef1f6;
  --flaeche: #ffffff;
  --feld: #ffffff;
  --rand: #c3cddc;
  --text: #1c2333;
  --text-stark: #0b1220;
  --text-mittel: #445064;
  --text-leise: #5f6b7d;
  --akzent: #0277bd;
  --akzent2: #e65100;
  --ok-text: #2e7d32;
  --stoer-bg: #fdecea;
  --stoer-text: #b71c1c;
  --knopf-bg: #dfe5ef;
  --knopf-text: #1c2333;
  color-scheme: light;
}

.kopfzeile { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; }
button.thema { flex-shrink: 0; padding: 0.3rem 0.7rem; }

.app {
  font-family: system-ui, sans-serif;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0.6rem 1rem;
  background: var(--bg);
  min-height: 100vh;
  color: var(--text);
}

h1 { font-size: 1.15rem; margin: 0 0 0.4rem; color: var(--text-stark); }
h2 { font-size: 1rem; margin: 0 0 0.6rem; color: var(--text-stark); }

.connection { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.url-input { flex: 1; min-width: 200px; padding: 0.35rem; background: var(--feld); color: var(--text); border: 1px solid var(--rand); border-radius: 4px; }
.dot { width: 12px; height: 12px; border-radius: 50%; background: #c62828; }
.dot.on { background: #43a047; }
.tick-badge {
  font-size: 0.75rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--ok-text);
  min-width: 1.5rem;
  text-align: center;
  transition: color 0.2s;
}
.tick-badge.pulse { color: var(--text-stark); }
.status-line { font-size: 0.8rem; color: var(--text-leise); margin: 0.25rem 0 0.5rem; }

button {
  padding: 0.45rem 0.9rem;
  border: none;
  border-radius: 4px;
  background: var(--knopf-bg);
  color: var(--knopf-text);
  cursor: pointer;
  font-size: 0.9rem;
}
button:disabled { opacity: 0.4; cursor: not-allowed; }
button.start { background: #2e7d32; color: #fff; }
button.stopp { background: #b71c1c; color: #fff; }
button.quitt { background: #f9a825; color: #000; }
button.anzeige { background: transparent; border: 1px solid var(--rand); color: var(--text-mittel); }
button.anzeige.aktiv { border-color: var(--akzent); color: var(--akzent); }

section { background: var(--flaeche); border-radius: 8px; padding: 0.75rem; margin-bottom: 0.6rem; }

.zustand { text-align: center; font-size: 1.2rem; font-weight: 600; border: 2px solid transparent; }
.zustand.laeuft { border-color: #43a047; }
.zustand.stoerung { border-color: #c62828; background: var(--stoer-bg); }
.fehler { margin-top: 0.4rem; font-size: 0.95rem; color: var(--stoer-text); }

.kacheln { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; background: none; padding: 0; }
.kachel { background: var(--flaeche); border-radius: 8px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.2rem; }
.kachel.gross { grid-column: 1 / -1; }
.label { font-size: 0.8rem; color: var(--text-leise); }
.wert { font-size: 1.6rem; font-variant-numeric: tabular-nums; color: var(--text-stark); }
.kachel.gross .wert { font-size: 2.6rem; color: var(--akzent); }
.wert small { font-size: 0.9rem; color: var(--text-leise); }
.neben { font-size: 0.85rem; color: var(--text-mittel); }

.trend-kopf { display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--text-leise); margin-bottom: 0.4rem; flex-wrap: wrap; gap: 0.5rem; }
.legende i { display: inline-block; width: 12px; height: 3px; margin: 0 0.3rem 0.2rem 0.6rem; vertical-align: middle; }
.legende i.f { background: var(--akzent); }
.legende i.a { background: var(--akzent2); }
.trend-flaeche { position: relative; height: 160px; }
.trend-flaeche canvas { position: absolute; inset: 0; width: 100%; height: 100%; background: var(--feld); border-radius: 4px; }

.buttons { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.soll { display: flex; gap: 0.5rem; align-items: center; margin-top: 0.75rem; flex-wrap: wrap; }
.soll input[type='range'] { flex: 1; min-width: 160px; }
.zahl { width: 5.5rem; padding: 0.3rem; background: var(--feld); color: var(--text); border: 1px solid var(--rand); border-radius: 4px; }
.hinweis { font-size: 0.8rem; color: var(--text-leise); margin: 0.5rem 0 0; }

/* Tablet quer (z. B. 1280x800): Messwerte in einer Zeile, Verlauf und Bedienung nebeneinander */
@media (min-width: 900px) {
  .kacheln { grid-template-columns: 2fr repeat(4, 1fr); }
  .kachel.gross { grid-column: auto; }
}
@media (min-width: 1000px) {
  .unten { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; align-items: stretch; }
  .unten section { margin-bottom: 0; }
  /* Seite fuellt genau den Bildschirm, der Verlauf bekommt die Resthoehe */
  .app { height: 100vh; display: flex; flex-direction: column; }
  .unten { flex: 1; min-height: 0; }
  .trend { display: flex; flex-direction: column; min-height: 0; }
  .trend-flaeche { flex: 1; height: auto; min-height: 140px; }
}
</style>
