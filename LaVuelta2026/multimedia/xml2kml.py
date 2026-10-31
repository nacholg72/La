#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from xml.sax.saxutils import escape


@dataclass
class Punto:
    """Punto geográfico de la etapa."""
    nombre: str
    longitud: float
    latitud: float
    altitud: float
    distancia_km: float = 0.0     # kilómetros desde la salida
    descripcion: str = ""


# ---------------------------------------------------------------------------
# Lectura del XML con XPath
# ---------------------------------------------------------------------------
class EtapaXml:
    """Lee etapaEsquema.xml y extrae la información con expresiones XPath."""

    PREFIJO = "u"   # prefijo que se usa en las expresiones XPath

    def __init__(self, ruta):
        self.ruta = ruta
        self.raiz = None
        self.ns = {}
        
    def cargar(self):
        """Construye en memoria el árbol DOM y detecta el espacio de nombres."""
        arbol = ET.parse(self.ruta)
        self.raiz = arbol.getroot()
        if not self.raiz.tag.startswith("{"):
            raise ValueError("el elemento raíz no tiene espacio de nombres "
                             "(se esperaba http://www.uniovi.es)")
        uri = self.raiz.tag[1:self.raiz.tag.index("}")]
        self.ns = {self.PREFIJO: uri}

    # ----- utilidades XPath ---------------------------------------------
    def _elemento(self, xpath, contexto=None):
        """Devuelve el primer elemento que cumple la expresión XPath."""
        base = self.raiz if contexto is None else contexto
        elemento = base.find(xpath, self.ns)
        if elemento is None:
            raise ValueError("no se encuentra '%s' en el XML" % xpath)
        return elemento

    def _texto(self, xpath, contexto=None):
        """Devuelve el texto (sin espacios sobrantes) del elemento XPath."""
        return (self._elemento(xpath, contexto).text or "").strip()

    def _numero(self, xpath, contexto=None):
        """Devuelve el contenido numérico (float) del elemento XPath."""
        texto = self._texto(xpath, contexto)
        try:
            return float(texto)
        except ValueError:
            raise ValueError("'%s' no es un número válido en '%s'" % (texto, xpath))

   
    def nombre(self):
        return self._texto("u:nombre")

    def lugar_salida(self):
        return self._texto("u:lugarSalida")

    def lugar_llegada(self):
        return self._texto("u:lugarLlegada")

   
    def _distancia_km(self, contexto):
        """Lee u:distancia y la convierte a kilómetros según su atributo unidad."""
        elemento = self._elemento("u:distancia", contexto)
        valor = self._numero("u:distancia", contexto)
        return valor / 1000.0 if elemento.get("unidad") == "m" else valor

    def _punto(self, contexto, nombre, descripcion=""):
        """Construye un Punto leyendo longitud, latitud y altitud del contexto."""
        return Punto(
            nombre=nombre,
            longitud=self._numero("u:longitud", contexto),
            latitud=self._numero("u:latitud", contexto),
            altitud=self._numero("u:altitud", contexto),
            descripcion=descripcion,
        )

    def salida(self):
        contexto = self._elemento("u:coordenadasSalida")
        return self._punto(contexto, "Salida: " + self.lugar_salida())

    def meta(self):
        contexto = self._elemento("u:coordenadasMeta")
        punto = self._punto(contexto, "Meta: " + self.lugar_llegada())
        punto.distancia_km = self._numero("u:longitud")      # longitud de la etapa (km)
        return punto

    def hitos(self, tipo):
        """Hitos de un tipo (puertoMontana, sprintIntermedio, sprintBonificado)."""
        resultado = []
        for hito in self.raiz.findall('.//u:hito[@tipo="%s"]' % tipo, self.ns):
            descripcion = "Altitud: %s m" % self._texto("u:altitud", hito)
            categoria = hito.find("u:categoria", self.ns)
            if categoria is not None and (categoria.text or "").strip():
                descripcion = categoria.text.strip() + ". " + descripcion
            punto = self._punto(hito, self._texto("u:nombreHito", hito), descripcion)
            punto.distancia_km = self._distancia_km(hito)
            resultado.append(punto)
        return resultado

    def puntos_anonimos(self):
        """Puntos anónimos de la etapa, ordenados por distancia."""
        resultado = []
        for numero, elemento in enumerate(self.raiz.findall(".//u:puntosAnonimos/u:punto", self.ns), 1):
            nombre = elemento.get("nombre") or "Punto %d" % numero
            punto = self._punto(elemento, nombre)
            punto.distancia_km = self._distancia_km(elemento)
            punto.descripcion = "Punto anónimo a %.1f km de la salida" % punto.distancia_km
            resultado.append(punto)
        return sorted(resultado, key=lambda p: p.distancia_km)


# ---------------------------------------------------------------------------
# Escritura del KML (generación de código)
# ---------------------------------------------------------------------------
class Kml:
    """Genera el texto de un archivo KML: prólogo, estilos, puntos, línea y epílogo."""

    ICONO = "http://maps.google.com/mapfiles/kml/paddle/%s-circle.png"
    ESTILOS = {          # id de estilo -> código del icono de Google
        "rojo": "red",
        "verde": "grn",
        "azul": "blu",
        "amarillo": "ylw",
    }
    COLOR_LINEA = "ffff00ff"   # formato KML aabbggrr (magenta, para no confundirse con los puntos)

    def __init__(self):
        self._lineas = []
        self._nivel = 0

    def _escribir(self, texto):
        self._lineas.append("  " * self._nivel + texto)

    def _abrir(self, etiqueta):
        self._escribir("<%s>" % etiqueta)
        self._nivel += 1

    def _cerrar(self, etiqueta):
        self._nivel -= 1
        self._escribir("</%s>" % etiqueta)

    @staticmethod
    def _coordenadas(punto):
        return "%.6f,%.6f,%.1f" % (punto.longitud, punto.latitud, punto.altitud)

    # ----- prólogo ------------------------------------------------------
    def prologo(self, nombre, descripcion=""):
        self._escribir('<?xml version="1.0" encoding="UTF-8"?>')
        self._escribir('<kml xmlns="http://www.opengis.net/kml/2.2">')
        self._nivel += 1
        self._abrir("Document")
        self._escribir("<name>%s</name>" % escape(nombre))
        if descripcion:
            self._escribir("<description>%s</description>" % escape(descripcion))
        self._estilos()

    def _estilos(self):
        for identificador, codigo in self.ESTILOS.items():
            self._abrir('Style id="%s"' % identificador)
            self._abrir("IconStyle")
            self._escribir("<scale>1.1</scale>")
            self._escribir("<Icon><href>%s</href></Icon>" % (self.ICONO % codigo))
            self._cerrar("IconStyle")
            self._cerrar("Style")
        self._abrir('Style id="recorrido"')
        self._abrir("LineStyle")
        self._escribir("<color>%s</color>" % self.COLOR_LINEA)
        self._escribir("<width>4</width>")
        self._cerrar("LineStyle")
        self._cerrar("Style")

    # ----- carpetas, puntos y línea --------------------------------------
    def abrir_carpeta(self, nombre):
        self._abrir("Folder")
        self._escribir("<name>%s</name>" % escape(nombre))

    def cerrar_carpeta(self):
        self._cerrar("Folder")

    def punto(self, punto, estilo):
        """Escribe una marca (Placemark) puntual con el estilo indicado."""
        self._abrir("Placemark")
        self._escribir("<name>%s</name>" % escape(punto.nombre))
        if punto.descripcion:
            self._escribir("<description>%s</description>" % escape(punto.descripcion))
        self._escribir("<styleUrl>#%s</styleUrl>" % estilo)
        self._abrir("Point")
        self._escribir("<altitudeMode>clampToGround</altitudeMode>")
        self._escribir("<coordinates>%s</coordinates>" % self._coordenadas(punto))
        self._cerrar("Point")
        self._cerrar("Placemark")

    def linea(self, nombre, puntos):
        """Escribe una línea (LineString) que une los puntos en el orden dado."""
        self._abrir("Placemark")
        self._escribir("<name>%s</name>" % escape(nombre))
        self._escribir("<styleUrl>#recorrido</styleUrl>")
        self._abrir("LineString")
        self._escribir("<tessellate>1</tessellate>")
        self._escribir("<altitudeMode>clampToGround</altitudeMode>")
        self._abrir("coordinates")
        for punto in puntos:
            self._escribir(self._coordenadas(punto))
        self._cerrar("coordinates")
        self._cerrar("LineString")
        self._cerrar("Placemark")

   
    def epilogo(self):
        self._cerrar("Document")
        self._cerrar("kml")

    def guardar(self, ruta):
        with open(ruta, "w", encoding="utf-8", newline="\n") as archivo:
            archivo.write("\n".join(self._lineas) + "\n")


# ---------------------------------------------------------------------------
# Proceso completo
# ---------------------------------------------------------------------------
class Xml2Kml:
    """Convierte etapaEsquema.xml en etapa.kml."""

    MAX_ANONIMOS = 30                       # límite de puntos anónimos del enunciado
    TIPOS_SPRINT = ("sprintIntermedio", "sprintBonificado")

    def __init__(self, ruta_xml="etapaEsquema.xml", ruta_kml="etapa.kml"):
        self.ruta_xml = ruta_xml
        self.ruta_kml = ruta_kml
        self.etapa = EtapaXml(ruta_xml)
        self.kml = Kml()

    def _reducir(self, puntos):
        """Si hay más puntos que MAX_ANONIMOS, se eligen repartidos por todo el recorrido."""
        if len(puntos) <= self.MAX_ANONIMOS:
            return puntos
        indices = sorted({round(i * (len(puntos) - 1) / (self.MAX_ANONIMOS - 1))
                          for i in range(self.MAX_ANONIMOS)})
        return [puntos[i] for i in indices]

    def construir(self):
        """Lee el XML y escribe en memoria todo el contenido del KML."""
        self.etapa.cargar()
        salida = self.etapa.salida()
        meta = self.etapa.meta()
        puertos = self.etapa.hitos("puertoMontana")
        sprints = []
        for tipo in self.TIPOS_SPRINT:
            sprints += self.etapa.hitos(tipo)
        anonimos = self._reducir(self.etapa.puntos_anonimos())

        self.kml.prologo(self.etapa.nombre(),
                         "Planimetría de la etapa (generada desde %s)" % self.ruta_xml)

        self.kml.abrir_carpeta("Salida y meta")
        self.kml.punto(salida, "rojo")
        self.kml.punto(meta, "rojo")
        self.kml.cerrar_carpeta()

        self.kml.abrir_carpeta("Puertos de montaña")
        for punto in puertos:
            self.kml.punto(punto, "verde")
        self.kml.cerrar_carpeta()

        self.kml.abrir_carpeta("Sprints")
        for punto in sprints:
            self.kml.punto(punto, "azul")
        self.kml.cerrar_carpeta()

        self.kml.abrir_carpeta("Puntos anónimos")
        for punto in anonimos:
            self.kml.punto(punto, "amarillo")
        self.kml.cerrar_carpeta()

        # La distancia de cada punto se mide desde la salida, así que ordenándolos
        # por distancia se obtiene el recorrido: salida -> intermedios -> meta.
        intermedios = sorted(puertos + sprints + anonimos, key=lambda p: p.distancia_km)
        self.kml.abrir_carpeta("Recorrido")
        self.kml.linea("Recorrido de la etapa", [salida] + intermedios + [meta])
        self.kml.cerrar_carpeta()

        self.kml.epilogo()
        return len(puertos), len(sprints), len(anonimos)

    def ejecutar(self):
        """Genera el archivo KML y resumen por pantalla."""
        puertos, sprints, anonimos = self.construir()
        self.kml.guardar(self.ruta_kml)
        print("Archivo '%s' generado a partir de '%s'." % (self.ruta_kml, self.ruta_xml))
        print("  Salida y meta : 2 puntos (rojo)")
        print("  Puertos       : %d (verde)" % puertos)
        print("  Sprints       : %d (azul)" % sprints)
        print("  Anónimos      : %d (amarillo)" % anonimos)

    @staticmethod
    def main(argumentos=None):
        """Punto de entrada: interpreta la línea de comandos y ejecuta el proceso."""
        argumentos = sys.argv[1:] if argumentos is None else argumentos
        if len(argumentos) > 2:
            print("Uso: python xml2kml.py [etapaEsquema.xml] [etapa.kml]")
            return 2
        try:
            Xml2Kml(*argumentos).ejecutar()
        except FileNotFoundError as error:
            print("Error: no se encuentra el archivo '%s'." % error.filename)
            return 1
        except ET.ParseError as error:
            print("Error: el XML no está bien formado (%s)." % error)
            return 1
        except ValueError as error:
            print("Error en los datos: %s." % error)
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(Xml2Kml.main())
