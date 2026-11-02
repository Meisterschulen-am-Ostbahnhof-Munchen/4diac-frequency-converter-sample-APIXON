<template>
  <div class="app">
    <header>
      <h1>FU-Demo &ndash; DELIXI H300G0R75P1R1T4B (0,75 kW)</h1>
      <div class="connection">
        <span class="dot" :class="{ on: connected }"></span>
        <input v-model="endpointUrl" class="url-input" :disabled="connected" />
        <button @click="connected ? disconnect() : connect()">
          {{ connected ? 'Trennen' : 'Verbinden' }}
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

    <section class="trend">
      <div class="trend-kopf">
        <span>Verlauf 60 s</span>
        <span class="legende"><i class="f"></i>Frequenz (0&ndash;{{ FMAX_HZ }} Hz) <i class="a"></i>Strom (auto)</span>
      </div>
      <canvas ref="trendCanvas" width="860" height="160"></canvas>
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
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
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
  KOMMANDO,
  kommandoText,
  statusText,
  fehlerText,
  laeuft,
  begrenzeSollFrequenz,
  type MesswertKey,
} from './h300'

// Port 4841 = OPC UA ueber WebSocket der APIXON-FORTE (wie im Krauternter-Dashboard)
const endpointUrl = ref('ws://192.168.1.11:4841')
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

function resetWerte() {
  for (const n of MESSWERT_NODES) werte[n.key] = 0
}

function handleLost() {
  if (!connected.value) return
  connected.value = false
  verbindungsText.value = 'Fehler: Verbindung verloren'
  resetWerte()
}

async function connect() {
  verbindungsText.value = 'Verbinde…'
  client = new OPCUAClient({
    securityMode: MessageSecurityMode.None,
    securityPolicy: SecurityPolicy.None,
    endpoint_must_exist: false,
    connectionStrategy: { maxRetry: 0 },
  })

  try {
    await client.connectP(endpointUrl.value)
    client.on('connection_lost', handleLost)
    client.on('close', handleLost)
    session = await client.createSessionP({})
    connected.value = true
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
  } catch (err) {
    console.error('FU-Demo connect failed:', err)
    verbindungsText.value = `Fehler: ${err}`
    connected.value = false
  }
}

async function disconnect() {
  if (client) {
    client.off('connection_lost', handleLost)
    client.off('close', handleLost)
    await client.disconnectP()
  }
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
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.strokeStyle = '#2a3a5e'
  ctx.lineWidth = 1
  for (let i = 1; i < 4; i++) {
    const y = (canvas.height / 4) * i
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke()
  }
  const stromMax = Math.max(1, ...trendStrom.filter((v) => !Number.isNaN(v))) * 1.2
  zeichneLinie(ctx, trendFrequenz, FMAX_HZ, '#4fc3f7')
  zeichneLinie(ctx, trendStrom, stromMax, '#ffb74d')
}

onMounted(() => {
  trendTimer = setInterval(trendSample, 200)
})

onUnmounted(() => {
  clearInterval(trendTimer)
  disconnect()
})
</script>

<style scoped>
* { box-sizing: border-box; }

.app {
  font-family: system-ui, sans-serif;
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem;
  background: #1a1a2e;
  min-height: 100vh;
  color: #e0e0e0;
}

h1 { font-size: 1.3rem; margin: 0 0 0.5rem; color: #fff; }
h2 { font-size: 1rem; margin: 0 0 0.75rem; color: #fff; }

.connection { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.url-input { flex: 1; min-width: 200px; padding: 0.35rem; background: #0f1629; color: #e0e0e0; border: 1px solid #2a3a5e; border-radius: 4px; }
.dot { width: 12px; height: 12px; border-radius: 50%; background: #c62828; }
.dot.on { background: #43a047; }
.status-line { font-size: 0.8rem; color: #999; margin: 0.4rem 0 1rem; }

button {
  padding: 0.45rem 0.9rem;
  border: none;
  border-radius: 4px;
  background: #2a3a5e;
  color: #fff;
  cursor: pointer;
  font-size: 0.9rem;
}
button:disabled { opacity: 0.4; cursor: not-allowed; }
button.start { background: #2e7d32; }
button.stopp { background: #b71c1c; }
button.quitt { background: #f9a825; color: #000; }

section { background: #16213e; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }

.zustand { text-align: center; font-size: 1.2rem; font-weight: 600; border: 2px solid transparent; }
.zustand.laeuft { border-color: #43a047; }
.zustand.stoerung { border-color: #c62828; background: #3b1218; }
.fehler { margin-top: 0.4rem; font-size: 0.95rem; color: #ff8a80; }

.kacheln { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; background: none; padding: 0; }
.kachel { background: #16213e; border-radius: 8px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.2rem; }
.kachel.gross { grid-column: 1 / -1; }
.label { font-size: 0.8rem; color: #999; }
.wert { font-size: 1.6rem; font-variant-numeric: tabular-nums; color: #fff; }
.kachel.gross .wert { font-size: 2.6rem; color: #4fc3f7; }
.wert small { font-size: 0.9rem; color: #999; }
.neben { font-size: 0.85rem; color: #bbb; }

.trend-kopf { display: flex; justify-content: space-between; font-size: 0.8rem; color: #999; margin-bottom: 0.4rem; flex-wrap: wrap; gap: 0.5rem; }
.legende i { display: inline-block; width: 12px; height: 3px; margin: 0 0.3rem 0.2rem 0.6rem; vertical-align: middle; }
.legende i.f { background: #4fc3f7; }
.legende i.a { background: #ffb74d; }
canvas { width: 100%; height: 160px; background: #0f1629; border-radius: 4px; }

.buttons { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.soll { display: flex; gap: 0.5rem; align-items: center; margin-top: 1rem; flex-wrap: wrap; }
.soll input[type='range'] { flex: 1; min-width: 160px; }
.zahl { width: 5.5rem; padding: 0.3rem; background: #0f1629; color: #e0e0e0; border: 1px solid #2a3a5e; border-radius: 4px; }
.hinweis { font-size: 0.8rem; color: #999; margin: 0.5rem 0 0; }
</style>
