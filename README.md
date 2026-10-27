# Examen 01 – Invernadero de tomate con Raspberry Pi 5

Universidad Técnica Nacional, Sede del Pacífico · ITIEL-11 · Profesor Jorge Ruiz (york)

Integrantes: Erick Murillo, Ana Paula Zúñiga, Dylan Benavides, Sebastián Rodríguez

Control de un invernadero de tomate con una Raspberry Pi 5: captación de agua lluvia,
nivel del contenedor, riego automático según la humedad del suelo, luz UV con un LED RGB
y registro de las lecturas en MongoDB.

## Contenido

| Archivo | Descripción |
|---|---|
| `invernadero_rpi5.py` | Programa completo en Python (un solo archivo) |
| `ARMADO.md` | Conexiones de cada sensor al T-Cobbler |
| `esquematico/` | Esquemático (KiCad para importar en EasyEDA Pro, e imagen SVG) |

## Ejecución en la Raspberry Pi 5

```bash
python -m venv --system-site-packages venv
source venv/bin/activate
pip install pymongo adafruit-circuitpython-dht
export MONGO_URI="mongodb://usuario:clave@IP:27017/?authSource=admin"
python invernadero_rpi5.py
```

Para probar sin hardware: `python invernadero_rpi5.py --simular`

Los sensores que no estén conectados se marcan como `False` en `SENSORES_REALES`
(al inicio del archivo) y se simulan. Cada registro en MongoDB indica qué valores fueron simulados.

## Código completo (invernadero_rpi5.py)

```python
"""
Invernadero de tomate - Raspberry Pi 5
Curso ITIEL-11 - Examen 01

Controla un invernadero de tomate:
  - Captación de agua lluvia (sensor de agua usado como sensor de lluvia)
  - Nivel del contenedor de agua (sensor ultrasónico HC-SR04)
  - Riego automático según la humedad del suelo (relé de la bomba)
  - Luz UV con un LED RGB en violeta cuando baja la luz (LDR)
  - Temperatura y humedad ambiente (DHT-11)
  - Registro de todas las lecturas en MongoDB con el dispositivo y la fecha

Uso:
    python invernadero_rpi5.py                 # con los sensores conectados
    python invernadero_rpi5.py --simular       # sin hardware (para probar en la laptop)
    python invernadero_rpi5.py --ciclos 10     # termina después de 10 lecturas
    python invernadero_rpi5.py --detectar      # muestra en qué GPIO está cada sensor

Instalación en la Raspberry Pi 5:
    python -m venv --system-site-packages venv
    source venv/bin/activate
    pip install pymongo adafruit-circuitpython-dht
"""
import argparse
import json
import os
import random
import time
from datetime import datetime

import pymongo

# ===============================================================
# CONFIGURACIÓN
# Los pines usan numeración BCM: es el número que dice el T-Cobbler
# (por ejemplo "GPIO17" -> 17).
# ===============================================================
DISPOSITIVO = "rpi5-invernadero-01"
INTERVALO_SEG = 5               # El DHT-11 necesita al menos 2 s entre lecturas

# True = el sensor está conectado; False = se simula
SENSORES_REALES = {
    "dht11": True,              # Temperatura y humedad ambiente
    "lluvia": True,             # Sensor de agua (lluvia)
    "suelo": True,              # Sensor de humedad de suelo
    "luz": True,                # LDR
    "nivel": True,              # HC-SR04
}
ACTUADORES_REALES = {
    "rele": True,               # Relé de la bomba de riego
    "led_uv": True,             # LED RGB
}

PIN_DHT = 4                     # DHT-11 DATA
PIN_LLUVIA = 27                 # Sensor de agua, pin S
PIN_SUELO = 22                  # Sensor de suelo, pin de señal (SIG / AO / DO)
PIN_LDR = 5                     # Punto medio del divisor LDR + resistencia
PIN_TRIG = 23                   # HC-SR04 Trig
PIN_ECHO = 24                   # HC-SR04 Echo (a 3.3 V o con divisor de voltaje)
PIN_RELE = 17                   # Relé IN
PIN_LED_R = 13                  # LED RGB rojo
PIN_LED_G = 19                  # LED RGB verde
PIN_LED_B = 26                  # LED RGB azul

# La Pi no tiene entradas analógicas: suelo, lluvia y luz se leen como 0 o 1.
# Si un sensor da justo al revés, cambiar su valor aquí.
SUELO_MOJADO_ES_1 = True        # Sensor con pin SIG: mojado = 1. Si es el pin DO de un FC-28, poner False
LUZ_ES_1 = True                 # LDR arriba (a 3V3) y resistencia abajo (a GND): con luz = 1
LUZ_MODO = "digital"            # "digital" (LDR + resistencia) o "rc" (LDR + capacitor de 1 uF)

# Contenedor de agua lluvia
ALTURA_TANQUE_CM = 30.0         # Distancia del sensor ultrasónico al fondo (prototipo)
CAPACIDAD_TANQUE_L = 480
CANTIDAD_TANQUES = 10
NIVEL_MIN_RIEGO_PCT = 10        # Con menos agua no se riega

# Condiciones del tomate en invernadero
TEMP_MIN_C = 18
TEMP_MAX_C = 30
HUM_AMB_MIN = 60
HUM_AMB_MAX = 80
SUELO_SECO_PCT = 40             # Por debajo se enciende el riego
SUELO_HUMEDO_PCT = 70           # Desde aquí se apaga el riego
LUZ_BAJA_PCT = 30               # Por debajo se enciende la luz UV

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://admin:CAMBIAR@127.0.0.1:27017/?authMechanism=DEFAULT&authSource=admin",
)
MONGO_DB = "Invernadero"
MONGO_COLECCION = "Lecturas"


# ===============================================================
# SENSORES
# Cada sensor devuelve un diccionario con sus valores en leer().
# ===============================================================
class Sensor:
    """Clase base de todos los sensores."""

    def __init__(self, nombre):
        self.nombre = nombre

    def leer(self):
        raise NotImplementedError


class SensorDHT11(Sensor):
    """Temperatura y humedad ambiente."""

    def __init__(self, pin):
        super().__init__("DHT-11")
        import adafruit_dht
        import board
        self.dht = adafruit_dht.DHT11(getattr(board, f"D{pin}"))

    def leer(self):
        # El DHT-11 falla seguido, por eso se intenta varias veces
        for _ in range(3):
            try:
                temperatura = self.dht.temperature
                humedad = self.dht.humidity
                if temperatura is not None and humedad is not None:
                    return {"temperatura": float(temperatura),
                            "humedad_ambiente": float(humedad)}
            except RuntimeError:
                pass
            time.sleep(2)
        return {"temperatura": None, "humedad_ambiente": None}


class SensorDigital(Sensor):
    """Sensor leído como 0 o 1 en un GPIO (la Pi no lee voltajes analógicos)."""

    def __init__(self, nombre, pin, activo_es_1=True):
        super().__init__(nombre)
        from gpiozero import DigitalInputDevice
        self.entrada = DigitalInputDevice(pin, pull_up=False)
        self.activo_es_1 = activo_es_1

    def activo(self):
        return bool(self.entrada.value) == self.activo_es_1


class SensorLluvia(SensorDigital):
    """Sensor de agua usado solo para detectar lluvia: mojado = está lloviendo."""

    def __init__(self, pin):
        super().__init__("Lluvia", pin)

    def leer(self):
        return {"lloviendo": self.activo()}


class SensorHumedadSuelo(SensorDigital):
    """Humedad de suelo: mojado = 100 %, seco = 0 %."""

    def __init__(self, pin, mojado_es_1):
        super().__init__("Suelo", pin, mojado_es_1)

    def leer(self):
        return {"humedad_suelo": 100.0 if self.activo() else 0.0}


class SensorLuz(SensorDigital):
    """LDR con resistencia en divisor de voltaje: hay luz = 100 %, oscuro = 0 %."""

    def __init__(self, pin, luz_es_1):
        super().__init__("LDR", pin, luz_es_1)

    def leer(self):
        return {"luz": 100.0 if self.activo() else 0.0}


class SensorLuzRC(Sensor):
    """LDR + capacitor de 1 uF: mide cuánto tarda en cargarse (más luz = más rápido)."""

    def __init__(self, pin):
        super().__init__("LDR")
        from gpiozero import LightSensor
        self.ldr = LightSensor(pin, charge_time_limit=0.1)

    def leer(self):
        return {"luz": round(self.ldr.value * 100, 1)}


class SensorNivelAgua(Sensor):
    """
    HC-SR04 colocado en la tapa del contenedor. Mide la distancia hasta el agua:
    entre menos distancia, más lleno está.
    """

    def __init__(self, pin_trig, pin_echo):
        super().__init__("HC-SR04")
        from gpiozero import DistanceSensor
        self.ultrasonico = DistanceSensor(echo=pin_echo, trigger=pin_trig,
                                          max_distance=ALTURA_TANQUE_CM / 100 * 2)

    def leer(self):
        distancia_cm = self.ultrasonico.distance * 100
        return calcular_nivel(ALTURA_TANQUE_CM - distancia_cm)


def calcular_nivel(nivel_cm):
    """Convierte la altura del agua en porcentaje y litros."""
    nivel_cm = max(0.0, min(nivel_cm, ALTURA_TANQUE_CM))
    porcentaje = nivel_cm / ALTURA_TANQUE_CM * 100
    litros = CAPACIDAD_TANQUE_L * porcentaje / 100
    return {
        "nivel_agua_cm": round(nivel_cm, 1),
        "nivel_agua_pct": round(porcentaje, 1),
        "litros_tanque": round(litros, 1),
        # Se asume que los 10 contenedores están conectados y tienen el mismo nivel
        "litros_total": round(litros * CANTIDAD_TANQUES, 1),
    }


def crear_sensor_real(nombre):
    if nombre == "dht11":
        return SensorDHT11(PIN_DHT)
    if nombre == "lluvia":
        return SensorLluvia(PIN_LLUVIA)
    if nombre == "suelo":
        return SensorHumedadSuelo(PIN_SUELO, SUELO_MOJADO_ES_1)
    if nombre == "luz":
        return SensorLuzRC(PIN_LDR) if LUZ_MODO == "rc" else SensorLuz(PIN_LDR, LUZ_ES_1)
    if nombre == "nivel":
        return SensorNivelAgua(PIN_TRIG, PIN_ECHO)
    raise ValueError(f"Sensor desconocido: {nombre}")


# ===============================================================
# SIMULACIÓN
# Reemplaza a los sensores que no están conectados. La lluvia llena
# el tanque y el riego gasta agua y humedece la tierra.
# ===============================================================
class Simulador:
    def __init__(self):
        self.temperatura = 25.0
        self.humedad_ambiente = 70.0
        self.luz = 60.0
        self.humedad_suelo = 45.0
        self.litros_tanque = CAPACIDAD_TANQUE_L * 0.5
        self.lloviendo = False
        # True cuando la lluvia la mide el sensor real y no se inventa aquí
        self.lluvia_real = False

    def avanzar(self, riego_activo, lloviendo_medido=None):
        """Calcula el estado del siguiente ciclo."""
        if self.lluvia_real and lloviendo_medido is not None:
            self.lloviendo = lloviendo_medido
        elif self.lloviendo:
            self.lloviendo = random.random() > 0.25
        else:
            self.lloviendo = random.random() < 0.10

        self.temperatura = limitar(self.temperatura + random.uniform(-0.8, 0.8), 12, 38)
        self.humedad_ambiente = limitar(self.humedad_ambiente + random.uniform(-3, 3)
                                        + (3 if self.lloviendo else 0), 35, 98)
        self.luz = limitar(self.luz + random.uniform(-10, 10)
                           - (8 if self.lloviendo else 0), 0, 100)

        if self.lloviendo:
            self.litros_tanque += 30
        if riego_activo:
            self.litros_tanque -= 20
            self.humedad_suelo += 7
        else:
            self.humedad_suelo -= 3
        self.litros_tanque = limitar(self.litros_tanque, 0, CAPACIDAD_TANQUE_L)
        self.humedad_suelo = limitar(self.humedad_suelo, 0, 100)

    def estado(self):
        datos = {
            "temperatura": round(self.temperatura, 1),
            "humedad_ambiente": round(self.humedad_ambiente, 1),
            "luz": round(self.luz, 1),
            "humedad_suelo": round(self.humedad_suelo, 1),
            "lloviendo": self.lloviendo,
        }
        datos.update(calcular_nivel(self.litros_tanque / CAPACIDAD_TANQUE_L * ALTURA_TANQUE_CM))
        return datos


class SensorSimulado(Sensor):
    """Sensor falso que toma sus valores del simulador."""

    CAMPOS = {
        "dht11": ("DHT-11", ["temperatura", "humedad_ambiente"]),
        "lluvia": ("Lluvia", ["lloviendo"]),
        "suelo": ("Suelo", ["humedad_suelo"]),
        "luz": ("LDR", ["luz"]),
        "nivel": ("HC-SR04", ["nivel_agua_cm", "nivel_agua_pct", "litros_tanque", "litros_total"]),
    }

    def __init__(self, tipo, simulador):
        nombre, self.campos = self.CAMPOS[tipo]
        super().__init__(nombre)
        self.simulador = simulador

    def leer(self):
        estado = self.simulador.estado()
        return {campo: estado[campo] for campo in self.campos}


def limitar(valor, minimo, maximo):
    return max(minimo, min(valor, maximo))


# ===============================================================
# ACTUADORES
# ===============================================================
class Actuador:
    """Clase base: algo que se puede encender y apagar."""

    def __init__(self, nombre):
        self.nombre = nombre
        self.encendido = False

    def encender(self):
        if not self.encendido:
            self.encendido = True
            self._aplicar()
            print(f"  >> {self.nombre}: ENCENDIDO")

    def apagar(self):
        if self.encendido:
            self.encendido = False
            self._aplicar()
            print(f"  >> {self.nombre}: APAGADO")

    def _aplicar(self):
        raise NotImplementedError


class Rele(Actuador):
    """Módulo de relé. Igual que en Arduino, se activa con LOW (active_high=False)."""

    def __init__(self, nombre, pin, simular=False):
        super().__init__(nombre)
        self.dispositivo = None
        if not simular:
            from gpiozero import OutputDevice
            self.dispositivo = OutputDevice(pin, active_high=False, initial_value=False)

    def _aplicar(self):
        if self.dispositivo:
            if self.encendido:
                self.dispositivo.on()
            else:
                self.dispositivo.off()


class LedUV(Actuador):
    """LED RGB en violeta (rojo + azul) para simular luz ultravioleta."""

    VIOLETA = (0.6, 0.0, 1.0)
    APAGADO = (0.0, 0.0, 0.0)

    def __init__(self, nombre, pin_r, pin_g, pin_b, simular=False):
        super().__init__(nombre)
        self.dispositivo = None
        if not simular:
            from gpiozero import RGBLED
            self.dispositivo = RGBLED(red=pin_r, green=pin_g, blue=pin_b)

    def _aplicar(self):
        if self.dispositivo:
            self.dispositivo.color = self.VIOLETA if self.encendido else self.APAGADO


# ===============================================================
# BASE DE DATOS
# Si MongoDB no responde, la lectura se guarda en respaldo.jsonl.
# ===============================================================
class BaseDatos:
    def __init__(self, uri, nombre_bd, coleccion, archivo_respaldo="respaldo.jsonl"):
        self.cliente = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000)
        self.coleccion = self.cliente[nombre_bd][coleccion]
        self.archivo_respaldo = archivo_respaldo

    def probar_conexion(self):
        try:
            self.cliente.admin.command("ping")
            print("Conectado a MongoDB")
        except pymongo.errors.PyMongoError as error:
            print(f"No se pudo conectar a MongoDB: {error}")

    def guardar(self, documento):
        try:
            # insert_one le agrega _id al documento, por eso se envía una copia
            self.coleccion.insert_one(dict(documento))
            return True
        except pymongo.errors.PyMongoError:
            with open(self.archivo_respaldo, "a", encoding="utf-8") as archivo:
                archivo.write(json.dumps(documento, default=str) + "\n")
            return False

    def cerrar(self):
        self.cliente.close()


# ===============================================================
# INVERNADERO
# En cada ciclo lee los sensores, decide captación, riego y luz UV,
# revisa las alertas y guarda todo en MongoDB.
# ===============================================================
class Invernadero:
    def __init__(self, sensores, rele_riego, led_uv, base_datos, simulador, simulados):
        self.sensores = sensores
        self.rele_riego = rele_riego
        self.led_uv = led_uv
        self.base_datos = base_datos
        self.simulador = simulador
        # Nombres de los sensores/actuadores simulados (se guarda en Mongo)
        self.simulados = simulados

    def leer_sensores(self):
        lectura = {}
        for sensor in self.sensores:
            try:
                lectura.update(sensor.leer())
            except Exception as error:
                print(f"  ! Error leyendo {sensor.nombre}: {error}")
        return lectura

    def captacion_lluvia(self, lectura):
        lloviendo = lectura.get("lloviendo", False)
        tanque_lleno = lectura.get("nivel_agua_pct", 0) >= 100
        return {
            "lloviendo": lloviendo,
            "captando": lloviendo and not tanque_lleno,
            "tanque_lleno": tanque_lleno,
        }

    def distribucion_agua(self, lectura):
        suelo = lectura.get("humedad_suelo")
        hay_agua = lectura.get("nivel_agua_pct", 0) > NIVEL_MIN_RIEGO_PCT

        if suelo is None or not hay_agua:
            self.rele_riego.apagar()
        elif suelo < SUELO_SECO_PCT:
            self.rele_riego.encender()
        elif suelo >= SUELO_HUMEDO_PCT:
            self.rele_riego.apagar()
        # Entre los dos umbrales se queda como estaba, así la bomba no se
        # prende y apaga a cada rato

        return {"activo": self.rele_riego.encendido, "hay_agua": hay_agua}

    def control_luz(self, lectura):
        luz = lectura.get("luz")
        if luz is not None and luz < LUZ_BAJA_PCT:
            self.led_uv.encender()
        else:
            self.led_uv.apagar()
        return {"activa": self.led_uv.encendido}

    def revisar_alertas(self, lectura, riego):
        alertas = []
        temperatura = lectura.get("temperatura")
        humedad = lectura.get("humedad_ambiente")

        if temperatura is None:
            alertas.append("Sin lectura de temperatura")
        elif temperatura < TEMP_MIN_C:
            alertas.append("Temperatura baja para el tomate")
        elif temperatura > TEMP_MAX_C:
            alertas.append("Temperatura alta para el tomate")

        if humedad is None:
            alertas.append("Sin lectura de humedad ambiente")
        elif humedad < HUM_AMB_MIN:
            alertas.append("Humedad ambiente baja")
        elif humedad > HUM_AMB_MAX:
            alertas.append("Humedad ambiente alta (riesgo de hongos)")

        if not riego["hay_agua"]:
            alertas.append("Tanque casi vacío, riego bloqueado")
        return alertas

    def ciclo(self):
        fecha = datetime.now()
        print(f"\n[{fecha:%Y-%m-%d %H:%M:%S}] {DISPOSITIVO}")

        lectura = self.leer_sensores()
        captacion = self.captacion_lluvia(lectura)
        riego = self.distribucion_agua(lectura)
        luz_uv = self.control_luz(lectura)
        alertas = self.revisar_alertas(lectura, riego)

        documento = {
            "dispositivo": DISPOSITIVO,
            "fecha": fecha,
            "variables": {
                "temperatura": lectura.get("temperatura"),
                "humedad_ambiente": lectura.get("humedad_ambiente"),
                "luz": lectura.get("luz"),
                "humedad_suelo": lectura.get("humedad_suelo"),
                "nivel_agua_cm": lectura.get("nivel_agua_cm"),
                "nivel_agua_pct": lectura.get("nivel_agua_pct"),
                "litros_tanque": lectura.get("litros_tanque"),
                "litros_total": lectura.get("litros_total"),
            },
            "tareas": {
                "captacion_lluvia": captacion,
                "riego": riego,
                "luz_uv": luz_uv,
            },
            "alertas": alertas,
            "simulados": self.simulados,
        }
        guardado = self.base_datos.guardar(documento)
        self.mostrar(documento, guardado)

        # El simulador calcula el siguiente estado según el riego y la lluvia actuales
        self.simulador.avanzar(self.rele_riego.encendido, lectura.get("lloviendo"))
        return documento

    def mostrar(self, doc, guardado):
        v = doc["variables"]
        t = doc["tareas"]
        print(f"  Temp: {v['temperatura']} °C | Hum: {v['humedad_ambiente']} % | "
              f"Luz: {v['luz']} % | Suelo: {v['humedad_suelo']} %")
        print(f"  Tanque: {v['nivel_agua_pct']} % ({v['litros_tanque']} L, "
              f"total {v['litros_total']} L)")
        print(f"  Lluvia: {'sí' if t['captacion_lluvia']['lloviendo'] else 'no'} | "
              f"Riego: {'ON' if t['riego']['activo'] else 'OFF'} | "
              f"Luz UV: {'ON' if t['luz_uv']['activa'] else 'OFF'}")
        for alerta in doc["alertas"]:
            print(f"  ! {alerta}")
        if doc["simulados"]:
            print(f"  (simulado: {', '.join(doc['simulados'])})")
        print(f"  MongoDB: {'guardado' if guardado else 'sin conexión, guardado en respaldo'}")

    def apagar_todo(self):
        self.rele_riego.apagar()
        self.led_uv.apagar()


def crear_invernadero(simular):
    """Crea cada sensor real o simulado según SENSORES_REALES."""
    reales = {nombre: real and not simular for nombre, real in SENSORES_REALES.items()}
    simulados = [nombre for nombre, real in reales.items() if not real]

    simulador = Simulador()
    simulador.lluvia_real = reales["lluvia"]

    sensores = []
    for nombre, real in reales.items():
        sensores.append(crear_sensor_real(nombre) if real else SensorSimulado(nombre, simulador))

    rele_real = ACTUADORES_REALES["rele"] and not simular
    led_real = ACTUADORES_REALES["led_uv"] and not simular
    simulados += [n for n, real in (("rele", rele_real), ("led_uv", led_real)) if not real]

    rele = Rele("Bomba de riego", PIN_RELE, simular=not rele_real)
    led = LedUV("Luz UV", PIN_LED_R, PIN_LED_G, PIN_LED_B, simular=not led_real)
    base_datos = BaseDatos(MONGO_URI, MONGO_DB, MONGO_COLECCION)
    return Invernadero(sensores, rele, led, base_datos, simulador, simulados)


# ===============================================================
# DETECTOR DE PINES
# Ayuda a saber qué sensor quedó en qué GPIO: busca el DHT-11 y
# después avisa cada vez que una entrada cambia (al mojar el sensor
# de agua o el de suelo, o al tapar el LDR).
# ===============================================================
PINES_A_REVISAR = [4, 5, 16, 20, 21, 22, 27]


def detectar_pines():
    pin_dht = None
    print("Buscando el DHT-11...")
    import adafruit_dht
    import board
    for pin in PINES_A_REVISAR:
        dht = adafruit_dht.DHT11(getattr(board, f"D{pin}"))
        for _ in range(3):
            try:
                if dht.temperature is not None:
                    pin_dht = pin
                    break
            except RuntimeError:
                time.sleep(2)
        dht.exit()
        if pin_dht is not None:
            print(f"  DHT-11 encontrado en GPIO{pin_dht}  ->  PIN_DHT = {pin_dht}")
            break
    if pin_dht is None:
        print("  No se encontró el DHT-11 en ninguno de los pines revisados")

    from gpiozero import DigitalInputDevice
    entradas = {p: DigitalInputDevice(p, pull_up=False) for p in PINES_A_REVISAR if p != pin_dht}
    anterior = {p: e.value for p, e in entradas.items()}
    print("\nEstado inicial: " + ", ".join(f"GPIO{p}={v}" for p, v in anterior.items()))
    print("Ahora mojá el sensor de agua, después el de suelo, y tapá el LDR con la mano.")
    print("Cada cambio aparece aquí. Ctrl+C para terminar.\n")
    try:
        while True:
            for pin, entrada in entradas.items():
                if entrada.value != anterior[pin]:
                    anterior[pin] = entrada.value
                    print(f"  {datetime.now():%H:%M:%S}  GPIO{pin} cambió a {entrada.value}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDetector terminado")


def main():
    parser = argparse.ArgumentParser(description="Control del invernadero de tomate")
    parser.add_argument("--simular", action="store_true", help="correr sin hardware")
    parser.add_argument("--ciclos", type=int, default=0, help="cantidad de lecturas (0 = infinito)")
    parser.add_argument("--intervalo", type=float, default=INTERVALO_SEG)
    parser.add_argument("--detectar", action="store_true", help="identificar en qué GPIO está cada sensor")
    args = parser.parse_args()

    if args.detectar:
        detectar_pines()
        return

    print(f"Iniciando {DISPOSITIVO} ({'SIMULACIÓN' if args.simular else 'Raspberry Pi 5'})")
    invernadero = crear_invernadero(args.simular)
    invernadero.base_datos.probar_conexion()

    ciclo = 0
    try:
        while args.ciclos == 0 or ciclo < args.ciclos:
            invernadero.ciclo()
            ciclo += 1
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("\nDeteniendo el invernadero...")
    finally:
        invernadero.apagar_todo()
        invernadero.base_datos.cerrar()


if __name__ == "__main__":
    main()
```
