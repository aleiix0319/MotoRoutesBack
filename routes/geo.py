"""Geometria minima, sin PostGIS.

Instalar GeoDjango obligaria a GDAL, que en Windows es un dolor y no compensa
para lo que hacemos: medir una polilinea y filtrar por radio.
"""
import math

EARTH_RADIUS_KM = 6371.0088

# Grados de latitud por kilometro. La longitud depende de la latitud, se
# corrige en bounding_box().
KM_PER_DEGREE_LAT = 110.574


def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia en km entre dos coordenadas, sobre la esfera."""
    lat1, lon1, lat2, lon2 = (
        math.radians(float(v)) for v in (lat1, lon1, lat2, lon2)
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def polyline_length_km(coordinates):
    """Longitud de una polilinea dada como [(lat, lon), ...].

    Es la distancia en linea recta entre puntos consecutivos, no la real por
    carretera: subestima si los puntos estan muy espaciados. Es el mismo
    criterio que usaba el cliente, aplicado igual para todos.
    """
    total = 0.0

    for (lat1, lon1), (lat2, lon2) in zip(coordinates, coordinates[1:]):
        total += haversine_km(lat1, lon1, lat2, lon2)

    return total


def bounding_box(latitude, longitude, radius_km):
    """Caja (min_lat, max_lat, min_lon, max_lon) que envuelve el radio.

    Es un prefiltro barato e indexable: recorta con un BETWEEN en SQL y el
    haversine solo se ejecuta sobre lo que sobrevive.
    """
    latitude = float(latitude)
    longitude = float(longitude)
    radius_km = float(radius_km)

    delta_lat = radius_km / KM_PER_DEGREE_LAT

    # Cerca de los polos un grado de longitud vale muchos menos km.
    cos_lat = math.cos(math.radians(latitude))
    if abs(cos_lat) < 1e-6:
        delta_lon = 180.0
    else:
        delta_lon = radius_km / (KM_PER_DEGREE_LAT * cos_lat)

    return (
        max(latitude - delta_lat, -90.0),
        min(latitude + delta_lat, 90.0),
        max(longitude - abs(delta_lon), -180.0),
        min(longitude + abs(delta_lon), 180.0),
    )
