"""
Genera el esquemático del invernadero (Raspberry Pi 5) en dos formatos:
  - invernadero.kicad_sch : para importar en EasyEDA Pro (File > Import > KiCad)
  - esquematico.svg       : imagen del mismo diagrama

Las conexiones se hacen con etiquetas de red (net labels): dos pines con la
misma etiqueta están conectados. Los pines coinciden con invernadero/config.py.
"""
import json
import uuid
import zipfile
from pathlib import Path

G = 2.54  # Grilla estándar (0.1 pulgadas)
SALIDA = Path(__file__).parent


# ---------------------------------------------------------------
# Símbolos
# ---------------------------------------------------------------
class Simbolo:
    """Caja rectangular con pines a la izquierda y/o a la derecha."""

    def __init__(self, nombre, izquierda, derecha=(), ancho=15.24, mostrar_numeros=True):
        self.nombre = nombre
        self.izquierda = list(izquierda)   # [(numero, nombre), ...]
        self.derecha = list(derecha)
        self.ancho = ancho
        self.mostrar_numeros = mostrar_numeros
        filas = max(len(self.izquierda), len(self.derecha))
        self.arriba = ((filas - 1) // 2 + (filas - 1) % 2) * G

    def pines(self):
        """Devuelve (numero, nombre, x, y, angulo) en coordenadas del símbolo (y hacia arriba)."""
        x = self.ancho / 2 + G
        for i, (num, nom) in enumerate(self.izquierda):
            yield num, nom, -x, self.arriba - i * G, 0
        for i, (num, nom) in enumerate(self.derecha):
            yield num, nom, x, self.arriba - i * G, 180

    def caja(self):
        filas = max(len(self.izquierda), len(self.derecha))
        return (-self.ancho / 2, self.arriba + G, self.ancho / 2, self.arriba - filas * G)


class Pasivo(Simbolo):
    """Componente de dos pines horizontal (resistencia, LDR)."""

    def __init__(self, nombre):
        super().__init__(nombre, [("1", "1")], [("2", "2")], ancho=5.08, mostrar_numeros=False)

    def pines(self):
        yield "1", "1", -5.08, 0, 0
        yield "2", "2", 5.08, 0, 180

    def caja(self):
        return (-2.54, 1.016, 2.54, -1.016)


RPI_PINES = {
    1: "3V3", 2: "5V", 3: "GPIO2/SDA", 4: "5V", 5: "GPIO3/SCL", 6: "GND",
    7: "GPIO4", 8: "GPIO14/TXD", 9: "GND", 10: "GPIO15/RXD", 11: "GPIO17",
    12: "GPIO18", 13: "GPIO27", 14: "GND", 15: "GPIO22", 16: "GPIO23",
    17: "3V3", 18: "GPIO24", 19: "GPIO10/MOSI", 20: "GND", 21: "GPIO9/MISO",
    22: "GPIO25", 23: "GPIO11/SCLK", 24: "GPIO8/CE0", 25: "GND", 26: "GPIO7/CE1",
    27: "ID_SD", 28: "ID_SC", 29: "GPIO5", 30: "GND", 31: "GPIO6", 32: "GPIO12",
    33: "GPIO13", 34: "GND", 35: "GPIO19", 36: "GPIO16", 37: "GPIO26",
    38: "GPIO20", 39: "GND", 40: "GPIO21",
}

SIMBOLOS = {
    "RPI5": Simbolo(
        "RPI5",
        [(str(n), RPI_PINES[n]) for n in range(1, 41, 2)],
        [(str(n), RPI_PINES[n]) for n in range(2, 41, 2)],
        ancho=35.56),
    "MCP3008": Simbolo(
        "MCP3008",
        [(str(n), f"CH{n - 1}") for n in range(1, 9)],
        [("16", "VDD"), ("15", "VREF"), ("14", "AGND"), ("13", "CLK"),
         ("12", "DOUT"), ("11", "DIN"), ("10", "CS/SHDN"), ("9", "DGND")],
        ancho=22.86),
    "DHT11": Simbolo("DHT11", [("1", "VCC"), ("2", "DATA"), ("3", "GND")]),
    "TMP36": Simbolo("TMP36", [("1", "+VS"), ("2", "VOUT"), ("3", "GND")]),
    "LLUVIA": Simbolo("LLUVIA", [("1", "S"), ("2", "+"), ("3", "-")]),
    "FC28": Simbolo("FC28", [("1", "VCC"), ("2", "GND"), ("3", "DO"), ("4", "AO")]),
    "HCSR04": Simbolo("HCSR04", [("1", "VCC"), ("2", "TRIG"), ("3", "ECHO"), ("4", "GND")]),
    "RELE": Simbolo("RELE", [("1", "VCC"), ("2", "GND"), ("3", "IN")],
                    [("4", "COM"), ("5", "NO"), ("6", "NC")], ancho=17.78),
    "LED_RGB": Simbolo("LED_RGB", [("1", "R"), ("3", "G"), ("4", "B"), ("2", "K")]),
    "BOMBA": Simbolo("BOMBA", [("1", "L"), ("2", "N")], ancho=12.7),
    "AC": Simbolo("AC", [("1", "L"), ("2", "N")], ancho=12.7),
    "R": Pasivo("R"),
    "LDR": Pasivo("LDR"),
}


# ---------------------------------------------------------------
# Componentes: (referencia, símbolo, valor, x, y, {pin: red})
# ---------------------------------------------------------------
COMPONENTES = [
    ("U1", "RPI5", "Raspberry Pi 5 (GPIO 40 pines)", 95.25, 116.84, {
        "1": "3V3", "2": "5V", "6": "GND", "7": "DHT_DATA", "11": "RELE_IN",
        "16": "HC_TRIG", "18": "ECHO_3V3", "19": "SPI_MOSI", "21": "SPI_MISO",
        "23": "SPI_SCLK", "24": "SPI_CE0", "33": "LED_R", "35": "LED_G",
        "37": "LED_B", "39": "GND",
    }),
    ("U2", "MCP3008", "MCP3008 (ADC SPI)", 205.74, 66.04, {
        "1": "LDR_OUT", "2": "LLUVIA_OUT", "3": "SUELO_OUT", "4": "TMP36_OUT",
        "9": "GND", "10": "SPI_CE0", "11": "SPI_MOSI", "12": "SPI_MISO",
        "13": "SPI_SCLK", "14": "GND", "15": "3V3", "16": "3V3",
    }),
    ("U3", "DHT11", "DHT-11 Temp/Hum", 314.96, 35.56,
     {"1": "3V3", "2": "DHT_DATA", "3": "GND"}),
    ("U4", "TMP36", "TMP36 Temp", 314.96, 58.42,
     {"1": "3V3", "2": "TMP36_OUT", "3": "GND"}),
    ("U5", "LLUVIA", "Sensor agua S8050 (lluvia)", 314.96, 81.28,
     {"1": "LLUVIA_OUT", "2": "3V3", "3": "GND"}),
    ("U6", "FC28", "FC-28 Humedad suelo", 314.96, 106.68,
     {"1": "3V3", "2": "GND", "4": "SUELO_OUT"}),
    ("U7", "HCSR04", "HC-SR04 Nivel tanque", 314.96, 139.7,
     {"1": "5V", "2": "HC_TRIG", "3": "ECHO_5V", "4": "GND"}),
    ("R1", "R", "10k", 375.92, 35.56, {"1": "DHT_DATA", "2": "3V3"}),
    ("LDR1", "LDR", "LDR", 195.58, 109.22, {"1": "3V3", "2": "LDR_OUT"}),
    ("R2", "R", "10k", 195.58, 121.92, {"1": "LDR_OUT", "2": "GND"}),
    ("R3", "R", "1k", 375.92, 137.16, {"1": "ECHO_5V", "2": "ECHO_3V3"}),
    ("R4", "R", "2k", 375.92, 149.86, {"1": "ECHO_3V3", "2": "GND"}),
    ("K1", "RELE", "Modulo rele 5V (SRD-05VDC)", 205.74, 175.26, {
        "1": "5V", "2": "GND", "3": "RELE_IN", "4": "AC_L", "5": "BOMBA_L",
    }),
    ("M1", "BOMBA", "Bomba de riego 110V", 287.02, 175.26, {"1": "BOMBA_L", "2": "AC_N"}),
    ("J1", "AC", "Toma 110V AC", 287.02, 198.12, {"1": "AC_L", "2": "AC_N"}),
    ("R5", "R", "220", 195.58, 228.6, {"1": "LED_R", "2": "LED_R_A"}),
    ("R6", "R", "220", 195.58, 241.3, {"1": "LED_G", "2": "LED_G_A"}),
    ("R7", "R", "220", 195.58, 254.0, {"1": "LED_B", "2": "LED_B_A"}),
    ("D1", "LED_RGB", "LED RGB catodo comun (luz UV)", 279.4, 241.3, {
        "1": "LED_R_A", "3": "LED_G_A", "4": "LED_B_A", "2": "GND",
    }),
]

TITULO = "Examen 01 - Invernadero de tomate con Raspberry Pi 5"
NOTAS = [
    "Conexiones por etiqueta de red: los pines con el mismo nombre estan conectados.",
    "MCP3008 por SPI0 (raspi-config > SPI). Sensores analogicos alimentados a 3.3 V.",
    "ECHO del HC-SR04 sale a 5 V: divisor R3 (1k) / R4 (2k) lo baja a 3.3 V.",
    "Rele activo en LOW (GPIO17). El contacto NO enciende la bomba de 110 V.",
    "LED RGB en violeta (R + B) = luz UV cuando hay poca luz (LDR).",
]


# ---------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------
def uid():
    return str(uuid.uuid4())


def pines_absolutos(simbolo, x, y):
    """Posición de cada pin en la hoja (en KiCad el eje y de la hoja va hacia abajo)."""
    for num, nom, px, py, ang in simbolo.pines():
        yield num, nom, round(x + px, 2), round(y - py, 2), ang


def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------
# KiCad
# ---------------------------------------------------------------
def efectos(tam=1.27, oculto=False, justificar=None):
    j = f" (justify {justificar})" if justificar else ""
    h = " hide" if oculto else ""
    return f"(effects (font (size {tam} {tam})){j}{h})"


def kicad_simbolo_lib(s):
    x1, y1, x2, y2 = s.caja()
    lineas = [
        f'    (symbol "inv:{s.nombre}" (pin_names (offset 1.016){"" if s.mostrar_numeros else " hide"})'
        f'{"" if s.mostrar_numeros else " (pin_numbers hide)"} (in_bom yes) (on_board yes)',
        f'      (property "Reference" "U" (at 0 {fmt(y1 + 1.27)} 0) {efectos()})',
        f'      (property "Value" "{s.nombre}" (at 0 {fmt(y2 - 1.27)} 0) {efectos()})',
        f'      (property "Footprint" "" (at 0 0 0) {efectos(oculto=True)})',
        f'      (property "Datasheet" "" (at 0 0 0) {efectos(oculto=True)})',
        f'      (symbol "{s.nombre}_0_1"',
        f'        (rectangle (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)})'
        f' (stroke (width 0.254) (type default)) (fill (type background)))',
        "      )",
        f'      (symbol "{s.nombre}_1_1"',
    ]
    for num, nom, px, py, ang in s.pines():
        lineas.append(
            f'        (pin passive line (at {fmt(px)} {fmt(py)} {ang}) (length 2.54)'
            f' (name "{nom}" {efectos()}) (number "{num}" {efectos()}))')
    lineas += ["      )", "    )"]
    return "\n".join(lineas)


def kicad_sch():
    raiz = uid()
    partes = [
        "(kicad_sch (version 20230121) (generator eeschema)",
        f"  (uuid {raiz})",
        '  (paper "A3")',
        f'  (title_block (title "{TITULO}") (date "2026-10-26") (rev "1")'
        ' (company "Universidad Tecnica Nacional - ITIEL-11"))',
        "  (lib_symbols",
    ]
    partes += [kicad_simbolo_lib(s) for s in SIMBOLOS.values()]
    partes.append("  )")

    for ref, nombre, valor, x, y, redes in COMPONENTES:
        s = SIMBOLOS[nombre]
        _, y1, _, y2 = s.caja()
        partes.append(
            f'  (symbol (lib_id "inv:{nombre}") (at {fmt(x)} {fmt(y)} 0) (unit 1)'
            f" (in_bom yes) (on_board yes) (dnp no) (uuid {uid()})")
        partes.append(f'    (property "Reference" "{ref}" (at {fmt(x)} {fmt(y - y1 - 1.27)} 0) {efectos()})')
        partes.append(f'    (property "Value" "{valor}" (at {fmt(x)} {fmt(y - y2 + 1.27)} 0) {efectos()})')
        partes.append(f'    (property "Footprint" "" (at {fmt(x)} {fmt(y)} 0) {efectos(oculto=True)})')
        partes.append(f'    (property "Datasheet" "" (at {fmt(x)} {fmt(y)} 0) {efectos(oculto=True)})')
        for num, *_ in s.pines():
            partes.append(f'    (pin "{num}" (uuid {uid()}))')
        partes.append(
            f'    (instances (project "invernadero" (path "/{raiz}" (reference "{ref}") (unit 1))))')
        partes.append("  )")

        for num, _, px, py, ang in pines_absolutos(s, x, y):
            red = redes.get(num)
            if red is None:
                partes.append(f"  (no_connect (at {fmt(px)} {fmt(py)}) (uuid {uid()}))")
                continue
            # Pin a la izquierda: etiqueta hacia la izquierda; a la derecha: hacia la derecha
            angulo, just = (180, "right bottom") if ang == 0 else (0, "left bottom")
            partes.append(
                f'  (label "{red}" (at {fmt(px)} {fmt(py)} {angulo}) (fields_autoplaced)'
                f" {efectos(justificar=just)} (uuid {uid()}))")

    partes.append(f'  (text "{TITULO}" (at 20.32 17.78 0) {efectos(3, justificar="left bottom")} (uuid {uid()}))')
    for i, nota in enumerate(NOTAS):
        partes.append(
            f'  (text "{nota}" (at 20.32 {fmt(220.98 + i * 5.08)} 0)'
            f' {efectos(1.8, justificar="left bottom")} (uuid {uid()}))')

    partes.append('  (sheet_instances (path "/" (page "1")))')
    partes.append(")")
    return "\n".join(partes) + "\n"


# ---------------------------------------------------------------
# SVG
# ---------------------------------------------------------------
def svg():
    e = 4  # píxeles por mm
    ancho, alto = 420 * e, 297 * e
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
        f'viewBox="0 0 {ancho} {alto}" font-family="Consolas, monospace">',
        f'<rect width="{ancho}" height="{alto}" fill="#fffdf6"/>',
        f'<rect x="{5 * e}" y="{5 * e}" width="{410 * e}" height="{287 * e}" fill="none" stroke="#a00000" stroke-width="2"/>',
        f'<text x="{20.32 * e}" y="{17.78 * e}" font-size="{4.5 * e}" font-weight="bold" fill="#222">{TITULO}</text>',
    ]
    colores = {"3V3": "#d40000", "5V": "#d46a00", "GND": "#333333"}
    for ref, nombre, valor, x, y, redes in COMPONENTES:
        s = SIMBOLOS[nombre]
        x1, y1, x2, y2 = s.caja()
        out.append(
            f'<rect x="{(x + x1) * e}" y="{(y - y1) * e}" width="{(x2 - x1) * e}" height="{(y1 - y2) * e}" '
            f'fill="#fff6c8" stroke="#8a0000" stroke-width="2"/>')
        out.append(f'<text x="{x * e}" y="{(y - y1 - 1.6) * e}" font-size="{2 * e}" text-anchor="middle" '
                   f'font-weight="bold" fill="#00008a">{ref}</text>')
        out.append(f'<text x="{x * e}" y="{(y - y2 + 3.4) * e}" font-size="{1.7 * e}" text-anchor="middle" '
                   f'fill="#00008a">{valor}</text>')
        for num, nom, px, py, ang in pines_absolutos(s, x, y):
            hacia = 1 if ang == 0 else -1
            out.append(f'<line x1="{px * e}" y1="{py * e}" x2="{(px + hacia * G) * e}" y2="{py * e}" '
                       f'stroke="#8a0000" stroke-width="2"/>')
            if s.mostrar_numeros:
                anc = "end" if ang == 0 else "start"
                out.append(f'<text x="{(px + hacia * (G + 1)) * e}" y="{(py + 0.5) * e}" font-size="{1.4 * e}" '
                           f'text-anchor="{"start" if ang == 0 else "end"}" fill="#333">{nom}</text>')
                out.append(f'<text x="{(px + hacia * 1.9) * e}" y="{(py - 0.4) * e}" font-size="{1.1 * e}" '
                           f'text-anchor="middle" fill="#888">{num}</text>')
            red = redes.get(num)
            if red is None:
                out.append(f'<text x="{px * e}" y="{(py + 0.6) * e}" font-size="{2 * e}" text-anchor="middle" '
                           f'fill="#0000cc">×</text>')
                continue
            color = colores.get(red, "#007a00")
            anc = "end" if ang == 0 else "start"
            dx = -0.8 if ang == 0 else 0.8
            out.append(f'<circle cx="{px * e}" cy="{py * e}" r="3" fill="{color}"/>')
            out.append(f'<text x="{(px + dx) * e}" y="{(py - 0.5) * e}" font-size="{1.6 * e}" '
                       f'text-anchor="{anc}" font-weight="bold" fill="{color}">{red}</text>')
    for i, nota in enumerate(NOTAS):
        out.append(f'<text x="{20.32 * e}" y="{(220.98 + i * 5.08) * e}" font-size="{2 * e}" fill="#222">• {nota}</text>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    (SALIDA / "invernadero.kicad_sch").write_text(kicad_sch(), encoding="utf-8")
    proyecto = {"meta": {"filename": "invernadero.kicad_pro", "version": 1}}
    (SALIDA / "invernadero.kicad_pro").write_text(json.dumps(proyecto, indent=2), encoding="utf-8")
    with zipfile.ZipFile(SALIDA / "invernadero_kicad.zip", "w") as z:
        z.write(SALIDA / "invernadero.kicad_pro", "invernadero/invernadero.kicad_pro")
        z.write(SALIDA / "invernadero.kicad_sch", "invernadero/invernadero.kicad_sch")
    (SALIDA / "esquematico.svg").write_text(svg(), encoding="utf-8")
    print("Generados: invernadero.kicad_sch, invernadero.kicad_pro, invernadero_kicad.zip, esquematico.svg")


if __name__ == "__main__":
    main()
