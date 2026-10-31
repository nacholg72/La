#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
@dataclass
class PuntoPerfil:
    """Un punto del perfil: distancia desde la salida y altitud."""
    nombre: str
    km: float
    altitud: float
    tipo: str            # salida | meta | puerto | sprint | anonimo
    detalle: str = ""    # por ejemplo la categoría de un puerto


# ---------------------------------------------------------------------------
# Lectura del XML con XPath
# ---------------------------------------------------------------------------
class EtapaXml:
    """Lee etapaEsquema.xml y extrae los datos del perfil con expresiones XPath."""

    PREFIJO = "u"

    def __init__(self, ruta):
        self.ruta = ruta
        self.raiz = None
        self.ns = {}

    def cargar(self):
        """Construye en memoria el árbol DOM y detecta el espacio de nombres."""
        self.raiz = ET.parse(self.ruta).getroot()
        self.ns = {self.PREFIJO: self.raiz.tag[1:self.raiz.tag.index("}")]}

    # ----- utilidades XPath ---------------------------------------------
    def _elemento(self, xpath, contexto=None):
        base = self.raiz if contexto is None else contexto
        elemento = base.find(xpath, self.ns)
        if elemento is None:
            raise ValueError("no se encuentra '%s' en el XML" % xpath)
        return elemento

    def _texto(self, xpath, contexto=None):
        return (self._elemento(xpath, contexto).text or "").strip()

    def _numero(self, xpath, contexto=None):
        texto = self._texto(xpath, contexto)
        try:
            return float(texto)
        except ValueError:
            raise ValueError("'%s' no es un número válido en '%s'" % (texto, xpath))

    def _distancia_km(self, contexto):
        """Lee u:distancia y la convierte a kilómetros según su atributo unidad."""
        valor = self._numero("u:distancia", contexto)
        unidad = self._elemento("u:distancia", contexto).get("unidad")
        return valor / 1000.0 if unidad == "m" else valor

    # ----- datos generales ----------------------------------------------
    def nombre(self):
        return self._texto("u:nombre")

    def numero_etapa(self):
        return self._texto("u:numeroEtapa")

    def fecha(self):
        return self._texto("u:fecha")

    def longitud_km(self):
        """Longitud de la etapa (hijo directo u:longitud de la raíz)."""
        return self._numero("u:longitud")

    def desnivel_m(self):
        return self._numero("u:desnivel")

    # ----- puntos del perfil ---------------------------------------------
    def _extremo(self, xpath_coordenadas, prefijo, lugar, tipo, km):
        contexto = self._elemento(xpath_coordenadas)
        return PuntoPerfil("%s: %s" % (prefijo, lugar), km,
                           self._numero("u:altitud", contexto), tipo)

    def perfil(self):
        """Devuelve todos los puntos del perfil ordenados por distancia."""
        puntos = [
            self._extremo("u:coordenadasSalida", "Salida", self._texto("u:lugarSalida"), "salida", 0.0),
            self._extremo("u:coordenadasMeta", "Meta", self._texto("u:lugarLlegada"), "meta", self.longitud_km()),
        ]
        tipos = {"puertoMontana": "puerto", "sprintIntermedio": "sprint", "sprintBonificado": "sprint"}
        for hito in self.raiz.findall(".//u:hitos/u:hito", self.ns):
            categoria = hito.find("u:categoria", self.ns)
            puntos.append(PuntoPerfil(
                nombre=self._texto("u:nombreHito", hito),
                km=self._distancia_km(hito),
                altitud=self._numero("u:altitud", hito),
                tipo=tipos.get(hito.get("tipo"), "sprint"),
                detalle=(categoria.text or "").strip() if categoria is not None else "",
            ))
        for numero, punto in enumerate(self.raiz.findall(".//u:puntosAnonimos/u:punto", self.ns), 1):
            puntos.append(PuntoPerfil(
                nombre=punto.get("nombre") or "Punto %d" % numero,
                km=self._distancia_km(punto),
                altitud=self._numero("u:altitud", punto),
                tipo="anonimo",
            ))
        return sorted(puntos, key=lambda p: p.km)



# Escritura del SVG
class Svg:
    """Genera el texto de un archivo SVG: cabecera, elementos gráficos y cierre."""

    def __init__(self, ancho, alto):
        self.ancho = ancho
        self.alto = alto
        self._lineas = []

    @staticmethod
    def _atributos(atributos):
        """Convierte {'stroke_width': 2} en ' stroke-width="2"'."""
        return "".join(" %s=%s" % (clave.replace("_", "-"), quoteattr(str(valor)))
                       for clave, valor in atributos.items())

    def _escribir(self, texto):
        self._lineas.append("  " + texto)

    @staticmethod
    def _coord(numero):
        return ("%.1f" % numero).rstrip("0").rstrip(".")

    # ----- cabecera y cierre --------------------------------------------
    def prologo(self, titulo, descripcion=""):
        self._lineas.append('<?xml version="1.0" encoding="UTF-8"?>')
        self._lineas.append(
            '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="%d" height="%d" '
            'viewBox="0 0 %d %d" font-family="Arial, Helvetica, sans-serif">'
            % (self.ancho, self.alto, self.ancho, self.alto))
        self._escribir("<title>%s</title>" % escape(titulo))
        if descripcion:
            self._escribir("<desc>%s</desc>" % escape(descripcion))

    def degradado(self, identificador, color_arriba, color_abajo):
        self._escribir("<defs>")
        self._escribir('  <linearGradient id="%s" x1="0" y1="0" x2="0" y2="1">' % identificador)
        self._escribir('    <stop offset="0" stop-color="%s"/>' % color_arriba)
        self._escribir('    <stop offset="1" stop-color="%s"/>' % color_abajo)
        self._escribir("  </linearGradient>")
        self._escribir("</defs>")

    def epilogo(self):
        self._lineas.append("</svg>")

    # ----- elementos gráficos -------------------------------------------
    def rectangulo(self, x, y, ancho, alto, **atributos):
        self._escribir('<rect x="%s" y="%s" width="%s" height="%s"%s/>'
                       % (self._coord(x), self._coord(y), self._coord(ancho),
                          self._coord(alto), self._atributos(atributos)))

    def linea(self, x1, y1, x2, y2, **atributos):
        self._escribir('<line x1="%s" y1="%s" x2="%s" y2="%s"%s/>'
                       % (self._coord(x1), self._coord(y1), self._coord(x2),
                          self._coord(y2), self._atributos(atributos)))

    def circulo(self, cx, cy, radio, **atributos):
        self._escribir('<circle cx="%s" cy="%s" r="%s"%s/>'
                       % (self._coord(cx), self._coord(cy), self._coord(radio),
                          self._atributos(atributos)))

    def _lista_puntos(self, puntos):
        return " ".join("%s,%s" % (self._coord(x), self._coord(y)) for x, y in puntos)

    def polilinea(self, puntos, **atributos):
        self._escribir('<polyline points="%s"%s/>' % (self._lista_puntos(puntos), self._atributos(atributos)))

    def poligono(self, puntos, **atributos):
        """Polilínea cerrada (efecto suelo) que se puede rellenar."""
        self._escribir('<polygon points="%s"%s/>' % (self._lista_puntos(puntos), self._atributos(atributos)))

    def texto(self, x, y, contenido, giro=None, **atributos):
        """Escribe un texto; con 'giro' (grados) alrededor de (x, y), p. ej. -90 para vertical."""
        if giro is not None:
            atributos["transform"] = "rotate(%s %s %s)" % (giro, self._coord(x), self._coord(y))
        self._escribir('<text x="%s" y="%s"%s>%s</text>'
                       % (self._coord(x), self._coord(y), self._atributos(atributos), escape(contenido)))

    # ----- volcado a archivo --------------------------------------------
    def guardar(self, ruta):
        with open(ruta, "w", encoding="utf-8", newline="\n") as archivo:
            archivo.write("\n".join(self._lineas) + "\n")


# ---------------------------------------------------------------------------
# Dibujo del perfil
# ---------------------------------------------------------------------------
class Altimetria:
    """Convierte el perfil de la etapa en un dibujo SVG."""

    ANCHO, ALTO = 1200, 680
    IZQ, DER, ARRIBA, ABAJO = 80, 40, 80, 200          # márgenes del área de dibujo
    COLORES = {"salida": "#e53935", "meta": "#e53935", "puerto": "#2e9e44",
               "sprint": "#1e6fe0", "anonimo": "#f5c518"}
    AZUL_OSCURO = "#1f4e79"

    def __init__(self, ruta_xml="etapaEsquema.xml", ruta_svg="altimetria.svg"):
        self.ruta_xml = ruta_xml
        self.ruta_svg = ruta_svg
        self.etapa = EtapaXml(ruta_xml)
        self.svg = Svg(self.ANCHO, self.ALTO)
        self.km_max = 0.0
        self.alt_max = 0.0
        self.puntos = []

    # ----- escalas ------------------------------------------------------
    @staticmethod
    def _paso(maximo, divisiones, pasos_validos):
        """Elige un paso 'redondo' para que haya aproximadamente 'divisiones' marcas."""
        for paso in pasos_validos:
            if maximo / paso <= divisiones:
                return paso
        return pasos_validos[-1]

    def _x(self, km):
        return self.IZQ + km / self.km_max * (self.ANCHO - self.IZQ - self.DER)

    def _y(self, altitud):
        return self.ALTO - self.ABAJO - altitud / self.alt_max * (self.ALTO - self.ARRIBA - self.ABAJO)

    # ----- partes del dibujo ----------------------------------------------
    def _titulo(self):
        etapa = self.etapa
        self.svg.texto(self.IZQ, 34, etapa.nombre(), font_size=22, font_weight="bold", fill=self.AZUL_OSCURO)
        subtitulo = "Etapa %s  ·  %s  ·  %s km  ·  %s m de desnivel positivo" % (
            etapa.numero_etapa(), etapa.fecha(), self._formato(etapa.longitud_km()),
            self._formato(etapa.desnivel_m()))
        self.svg.texto(self.IZQ, 58, subtitulo, font_size=14, fill="#555555")

    def _leyenda(self):
        elementos = [("Salida / meta", "salida"), ("Puerto de montaña", "puerto"),
                     ("Sprint", "sprint"), ("Punto anónimo", "anonimo")]
        x = self.IZQ
        for texto, tipo in elementos:
            self.svg.circulo(x + 6, self.ALTO - 20, 6, fill=self.COLORES[tipo], stroke="#333333", stroke_width=1)
            self.svg.texto(x + 18, self.ALTO - 16, texto, font_size=12, fill="#333333")
            x += 40 + len(texto) * 6.5

    def _rejilla(self):
        svg = self.svg
        base = self._y(0)
        derecha = self.ANCHO - self.DER
        paso_alt = self._paso(self.alt_max, 8, [100, 200, 250, 500, 1000])
        for valor in range(0, int(self.alt_max) + 1, paso_alt):
            y = self._y(valor)
            svg.linea(self.IZQ, y, derecha, y, stroke="#dddddd", stroke_width=1)
            svg.linea(self.IZQ - 5, y, self.IZQ, y, stroke="#333333", stroke_width=1)
            svg.texto(self.IZQ - 9, y + 4, str(valor), text_anchor="end", font_size=12, fill="#333333")
        paso_km = self._paso(self.km_max, 12, [5, 10, 20, 25, 50])
        for valor in range(0, int(self.km_max) + 1, paso_km):
            x = self._x(valor)
            svg.linea(x, self.ARRIBA, x, base, stroke="#eeeeee", stroke_width=1)
            svg.linea(x, base, x, base + 5, stroke="#333333", stroke_width=1)
            svg.texto(x, base + 20, str(valor), text_anchor="middle", font_size=12, fill="#333333")
        # ejes y rótulos
        svg.linea(self.IZQ, self.ARRIBA, self.IZQ, base, stroke="#333333", stroke_width=1.5)
        svg.linea(self.IZQ, base, derecha, base, stroke="#333333", stroke_width=1.5)
        svg.texto((self.IZQ + derecha) / 2, self.ALTO - 52, "Distancia desde la salida (km)",
                  text_anchor="middle", font_size=13, fill="#333333")
        svg.texto(22, (self.ARRIBA + base) / 2, "Altitud (m)", giro=-90,
                  text_anchor="middle", font_size=13, fill="#333333")

    def _perfil(self):
        """Polilínea del perfil cerrada contra el suelo y rellena con un degradado."""
        vertices = [(self._x(p.km), self._y(p.altitud)) for p in self.puntos]
        suelo = self._y(0)
        cerrado = [(vertices[0][0], suelo)] + vertices + [(vertices[-1][0], suelo)]
        self.svg.poligono(cerrado, fill="url(#relleno)", stroke="none")
        self.svg.polilinea(vertices, fill="none", stroke=self.AZUL_OSCURO, stroke_width=2.5,
                           stroke_linejoin="round")

    def _marcas(self):
        """Líneas de caída, círculos de colores y etiquetas verticales de los puntos."""
        suelo = self._y(0)
        for p in self.puntos:
            x, y = self._x(p.km), self._y(p.altitud)
            self.svg.linea(x, y, x, suelo + (30 if p.tipo == "anonimo" else 0), stroke="#888888",
                           stroke_width=1, stroke_dasharray="3,3")
        for p in self.puntos:       # los círculos se dibujan después para quedar encima
            x, y = self._x(p.km), self._y(p.altitud)
            radio = 4 if p.tipo == "anonimo" else 6.5
            self.svg.circulo(x, y, radio, fill=self.COLORES[p.tipo], stroke="#333333", stroke_width=1)
        for p in self.puntos:
            self._etiqueta(p)

    def _etiqueta(self, p):
        """Texto vertical: sobre el punto si cabe; si no, debajo."""
        x, y = self._x(p.km), self._y(p.altitud)
        if p.tipo == "anonimo":
            # los pueblos se rotulan en vertical, debajo del eje de distancias
            self.svg.texto(x - 4, self._y(0) + 36, p.nombre, giro=90, font_size=11, fill="#1f3b57")
            return
        texto = p.nombre
        if p.detalle:
            texto += " · " + p.detalle.replace("categoría", "cat.")
        largo = len(texto) * 6.9
        desplazamiento = 14 if x - self.IZQ < 10 else 4      # no pisar el eje vertical
        if y - 14 - largo >= self.ARRIBA - 10:
            self.svg.texto(x + desplazamiento, y - 14, texto, giro=-90, font_size=12,
                           font_weight="bold", fill="#222222")
        else:
            self.svg.texto(x + desplazamiento, y + 16, texto, giro=-90, text_anchor="end", font_size=12,
                           font_weight="bold", fill="#222222")

    @staticmethod
    def _formato(numero):
        return ("%d" % numero) if float(numero).is_integer() else ("%.1f" % numero)

    # ----- proceso completo ---------------------------------------------
    def construir(self):
        self.etapa.cargar()
        self.puntos = self.etapa.perfil()
        if len(self.puntos) < 2:
            raise ValueError("hacen falta al menos 2 puntos para dibujar el perfil")
        self.km_max = max(self.etapa.longitud_km(), self.puntos[-1].km)
        maximo = max(p.altitud for p in self.puntos)
        self.alt_max = math.ceil(maximo * 1.05 / 250.0) * 250      # margen superior, múltiplo de 250 m

        self.svg.prologo("Altimetría - " + self.etapa.nombre(),
                         "Perfil altimétrico generado desde %s" % self.ruta_xml)
        self.svg.degradado("relleno", "#9fc9e8", "#e8f2fa")
        self.svg.rectangulo(0, 0, self.ANCHO, self.ALTO, fill="#ffffff")
        self._titulo()
        self._leyenda()
        self._rejilla()
        self._perfil()
        self._marcas()
        self.svg.epilogo()

    def ejecutar(self):
        self.construir()
        self.svg.guardar(self.ruta_svg)
        print("Archivo '%s' generado a partir de '%s'." % (self.ruta_svg, self.ruta_xml))
        print("  Puntos del perfil: %d  |  longitud: %s km  |  altitud máxima: %s m"
              % (len(self.puntos), self._formato(self.km_max),
                 self._formato(max(p.altitud for p in self.puntos))))

    @staticmethod
    def main(argumentos=None):
        argumentos = sys.argv[1:] if argumentos is None else argumentos
        if len(argumentos) > 2:
            print("Uso: python xml2altimetria.py [etapaEsquema.xml] [altimetria.svg]")
            return 2
        try:
            Altimetria(*argumentos).ejecutar()
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
    sys.exit(Altimetria.main())
