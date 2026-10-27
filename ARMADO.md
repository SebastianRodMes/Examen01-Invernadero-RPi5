# Conexiones para invernadero_rpi5.py

Los nombres en `código` son lo que dice impreso en el T-Cobbler rojo.
Cada etiqueta del cobbler está conectada con los huequitos libres de **su misma fila**.
Conectá todo con la Raspberry **apagada**.

## Rieles
| Cobbler | Hacia |
|---|---|
| `3V3` | riel **+** (3.3 V) |
| `GND` | riel **−** |
| `5V0` | solo para el relé (nunca al riel de 3.3 V) |

## Sensores y actuadores
| Componente | Pin del componente | Cobbler |
|---|---|---|
| DHT-11 | VCC / DATA / GND | `3V3` / `GPIO4` / `GND` |
| Sensor de agua (lluvia) | + / S / − | `3V3` / `GPIO27` / `GND` |
| Sensor de suelo | VCC / SIG (o AO/DO) / GND | `3V3` / `GPIO22` / `GND` |
| LDR | una pata a `3V3`, la otra a una fila libre | esa fila → `GPIO5`, y una resistencia de 10k de esa fila a `GND` |
| HC-SR04 | VCC / Trig / Echo / Gnd | `3V3` / `GPIO23` / `GPIO24` / `GND` |
| Relé | VCC / IN / GND | `5V0` / `GPIO17` / `GND` |
| LED RGB | R / G / B (cada una con 220 Ω) | `GPIO13` / `GPIO19` / `GPIO26`; la pata larga a `GND` |

## Ajustes en el código (parte de arriba de invernadero_rpi5.py)
- Si algo no está conectado, ponelo en `False` en `SENSORES_REALES` o `ACTUADORES_REALES` y se simula.
- Si conectaste algo en otro GPIO, cambiá su `PIN_...`.
- Si el suelo dice "mojado" cuando está seco, cambiá `SUELO_MOJADO_ES_1`.
- Si la luz UV se enciende con luz y se apaga a oscuras, cambiá `LUZ_ES_1`.
- Si el LED RGB es de ánodo común (pata larga a 3V3), los colores salen invertidos: avisá.

## Correr en la Raspberry
```
python -m venv --system-site-packages venv
source venv/bin/activate
pip install pymongo adafruit-circuitpython-dht
python invernadero_rpi5.py
```
