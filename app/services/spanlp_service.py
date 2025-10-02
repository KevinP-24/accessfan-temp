# app/services/spanlp_service.py
"""
Wrapper robusto de detección de palabrotas/violencia usando spanlp.

Características:
- Detector global (todos los países).
- Detector por país (country="ar", "mx", "es", etc.) con fallback al global.
- Si se indica 'country', se ejecuta país + global y se combinan resultados.
- Sin seeds manuales: este módulo depende 100% del dataset de spanlp.

API:
    detectar_palabras(texto: str, country: Optional[str] = None) -> List[str]
    detectar_palabras_struct(texto: str, country: Optional[str] = None) -> List[Dict[str, Any]]

Ejemplos:
    detectar_palabras("Hijos de puta de mierda")
    -> ['puta (global) [spanlp]', 'mierda (global) [spanlp]']

    detectar_palabras("Hijos de puta de mierda", country="ar")
    -> ['puta (ar) [spanlp]', 'mierda (ar) [spanlp]']  # si país lo detecta; si no, caerá en (global)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# --- Import de spanlp con tolerancia ---
try:
    from spanlp.palabrota import Palabrota  # type: ignore
    SPANLP_AVAILABLE: bool = True
except Exception:
    Palabrota = None  # type: ignore[assignment]
    SPANLP_AVAILABLE = False
    logger.warning("spanlp no está disponible. El wrapper funcionará en modo inactivo.")

# --- Cache de detectores (global y por país) ---
_palabrota_global: Optional[Any] = None
_palabrota_by_country: Dict[str, Any] = {}

# --- Regex de tokenización unicode (palabras) ---
_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


def _normalize_country(country: Optional[str]) -> Optional[str]:
    """
    Normaliza un identificador de país a un código de 2 letras (ej. 'AR', 'es-AR' -> 'ar').
    Si no puede normalizar, devuelve None.
    """
    if not country:
        return None
    code = re.sub(r"[^A-Za-z]", "", country).lower()
    if len(code) >= 2:
        return code[-2:]
    return None


def _get_detector_global() -> Optional[Any]:
    """
    Devuelve/cacha el detector global (todos los países).
    """
    global _palabrota_global
    if not SPANLP_AVAILABLE or Palabrota is None:
        return None
    if _palabrota_global is None:
        try:
            _palabrota_global = Palabrota()
            logger.info("Inicializado Palabrota global (dataset de todos los países).")
        except Exception as e:
            logger.error("No se pudo inicializar Palabrota global: %s", e)
            _palabrota_global = None
    return _palabrota_global


def _get_detector_country(country: str) -> Optional[Any]:
    """
    Devuelve/cacha el detector para un país. Si falla, retorna None.
    """
    if not SPANLP_AVAILABLE or Palabrota is None:
        return None
    c = country.lower()
    if c in _palabrota_by_country:
        return _palabrota_by_country[c]
    try:
        detector = Palabrota(country=c)
        _palabrota_by_country[c] = detector
        logger.info("Inicializado Palabrota para país=%s", c)
        return detector
    except Exception as e:
        logger.warning("No se pudo inicializar Palabrota para país=%s: %s", c, e)
        return None


def _detect_with(detector: Any, texto: str) -> Set[str]:
    """
    Ejecuta contains_palabrota token a token y devuelve un set de palabras (lowercase).
    Maneja errores internos del detector de forma segura.
    """
    found: Set[str] = set()
    if not detector or not texto:
        return found
    try:
        tokens = _WORD_RE.findall(texto)
        for t in tokens:
            try:
                if detector.contains_palabrota(t):
                    found.add(t.lower())
            except Exception:
                # Si falla en un token, continuamos con los demás
                continue
    except Exception as e:
        logger.debug("Error tokenizando o detectando con spanlp: %s", e, exc_info=True)
    return found


def detectar_palabras_struct(texto: str, country: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Devuelve lista de dicts con detecciones:
        {'word': str, 'country': Optional[str], 'source': 'spanlp'}

    Comportamiento:
    - Sin 'country': usa solo el detector global.
    - Con 'country': usa detector del país + global y combina (prefiere país cuando ambos detectan).
    - Fallback: si el detector del país no está disponible, usa solo global.
    """
    out: List[Dict[str, Any]] = []
    if not texto or not SPANLP_AVAILABLE or Palabrota is None:
        return out

    # Preparar detectores
    normalized_country = _normalize_country(country)
    det_global = _get_detector_global()
    det_country = _get_detector_country(normalized_country) if normalized_country else None

    # Detectar
    words_global = _detect_with(det_global, texto) if det_global else set()
    words_country = _detect_with(det_country, texto) if det_country else set()

    # Fusionar: preferir origen por país si está
    # Mapear palabra -> etiqueta de país ('ar', etc.) o 'global'
    origin_for_word: Dict[str, Optional[str]] = {}
    for w in words_global:
        origin_for_word[w] = None  # None => global
    for w in words_country:
        origin_for_word[w] = normalized_country  # sobrescribe si también estaba en global

    # Construir salida estructurada
    for w, origin in origin_for_word.items():
        out.append(
            {
                "word": w,
                "country": origin,  # None => global
                "source": "spanlp",
            }
        )

    return out


def detectar_palabras(texto: str, country: Optional[str] = None) -> List[str]:
    """
    Devuelve lista de strings legibles, con anotación de origen:
        "palabra (ar) [spanlp]"  o  "palabra (global) [spanlp]"
    """
    structs = detectar_palabras_struct(texto, country)
    result: List[str] = []
    for s in structs:
        word = s.get("word", "")
        tag = s.get("country") or "global"
        result.append(f"{word} ({tag}) [spanlp]")
    return result


__all__ = ["detectar_palabras", "detectar_palabras_struct"]
