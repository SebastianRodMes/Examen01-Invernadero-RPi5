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
