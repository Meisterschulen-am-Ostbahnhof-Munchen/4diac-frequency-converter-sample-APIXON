"""Lese-Test DELIXI H300 ueber das Waveshare-Gateway - schreibt NICHTS.

Probiert zwei Varianten:
  rtu  - rohe Modbus-RTU-Frames (mit CRC) durch den TCP-Tunnel
         (Gateway im Transparent-Modus, Werksdefault Port 4196)
  tcp  - Modbus-TCP-Frames (MBAP) (Gateway im Modus "Modbus TCP<->RTU", Port 502)

Aufruf: python tools/h300_modbus_test.py [host] [port] [slave] [rtu|tcp|beide]
"""
import socket
import struct
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.200"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 4196
SLAVE = int(sys.argv[3]) if len(sys.argv) > 3 else 1
MODE = sys.argv[4] if len(sys.argv) > 4 else "beide"

FEHLER = {1: "Illegal Function", 2: "Illegal Data Address", 3: "Illegal Data Value", 4: "Slave Device Failure"}


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


def recv_all(sock: socket.socket, timeout: float) -> bytes:
    sock.settimeout(timeout)
    buf = b""
    ende = time.time() + timeout
    while time.time() < ende:
        try:
            chunk = sock.recv(256)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        sock.settimeout(0.15)  # nach dem ersten Byte nur noch kurz auf den Rest warten
    return buf


def lese_rtu(sock, start: int, anzahl: int):
    pdu = struct.pack(">BBHH", SLAVE, 0x03, start, anzahl)
    frame = pdu + crc16(pdu)
    sock.sendall(frame)
    antwort = recv_all(sock, 1.5)
    print(f"  TX {frame.hex(' ')}\n  RX {antwort.hex(' ') or '(nichts)'}")
    if len(antwort) >= 5 and antwort[1] & 0x80:
        return f"Exception {antwort[2]} ({FEHLER.get(antwort[2], '?')})"
    if len(antwort) < 5 + 2 * anzahl:
        return None
    if crc16(antwort[:-2]) != antwort[-2:]:
        return "CRC falsch"
    return list(struct.unpack(f">{anzahl}H", antwort[3:3 + 2 * anzahl]))


def lese_tcp(sock, start: int, anzahl: int, tid: int):
    frame = struct.pack(">HHHBBHH", tid, 0, 6, SLAVE, 0x03, start, anzahl)
    sock.sendall(frame)
    antwort = recv_all(sock, 1.5)
    print(f"  TX {frame.hex(' ')}\n  RX {antwort.hex(' ') or '(nichts)'}")
    if len(antwort) >= 9 and antwort[7] & 0x80:
        return f"Exception {antwort[8]} ({FEHLER.get(antwort[8], '?')})"
    if len(antwort) < 9 + 2 * anzahl:
        return None
    return list(struct.unpack(f">{anzahl}H", antwort[9:9 + 2 * anzahl]))


def auswerten(mess, status):
    if isinstance(mess, list) and len(mess) == 5:
        print(f"  Ist-Frequenz      {mess[0] / 100:.2f} Hz")
        print(f"  Soll-Frequenz     {mess[1] / 100:.2f} Hz")
        print(f"  Strom             {mess[2] / 100:.2f} A")
        print(f"  Ausgangsspannung  {mess[3]} V")
        print(f"  Zwischenkreis     {mess[4] / 10:.1f} V")
    if isinstance(status, list) and len(status) == 2:
        text = {1: "laeuft vorwaerts", 2: "laeuft rueckwaerts", 3: "gestoppt"}.get(status[0], "?")
        print(f"  Status 9332H      {status[0]} ({text})")
        print(f"  Fehlercode 9333H  {status[1]}")


def test(mode: str) -> bool:
    print(f"\n=== {mode.upper()} -> {HOST}:{PORT}, Slave {SLAVE} ===")
    with socket.create_connection((HOST, PORT), timeout=3) as sock:
        recv_all(sock, 0.3)  # evtl. Restmuell im Tunnel verwerfen
        if mode == "rtu":
            mess = lese_rtu(sock, 0x9000, 5)
            status = lese_rtu(sock, 0x9332, 2)
        else:
            mess = lese_tcp(sock, 0x9000, 5, 1)
            status = lese_tcp(sock, 0x9332, 2, 2)
    print(f"  9000H..9004H: {mess}\n  9332H..9333H: {status}")
    auswerten(mess, status)
    return isinstance(mess, list) or isinstance(status, list)


if __name__ == "__main__":
    modi = ["rtu", "tcp"] if MODE == "beide" else [MODE]
    ok = False
    for m in modi:
        try:
            ok = test(m) or ok
        except OSError as e:
            print(f"  Verbindungsfehler: {e}")
    print("\nERGEBNIS:", "Umrichter antwortet" if ok else "keine gueltige Antwort")
    sys.exit(0 if ok else 1)
