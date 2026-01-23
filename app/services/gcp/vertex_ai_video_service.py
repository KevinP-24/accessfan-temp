import os
import json
import re
from vertexai import init
from vertexai.preview.generative_models import GenerativeModel, Part
from app.services.core.logging_service import audit_logger

PROJECT = os.getenv("VERTEX_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
MODEL_NAME = os.getenv("VERTEX_FOUNDATION_MODEL", "gemini-2.5-flash")

# --- helper: extraer JSON aunque venga con basura ---
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

def _extract_json(text: str) -> dict:
    if not text:
        return {}
    t = text.strip()

    # Quitar fences si vienen
    t = re.sub(r"```(?:json)?", "", t, flags=re.IGNORECASE).strip()

    # 1) Intento directo
    try:
        return json.loads(t)
    except Exception:
        pass

    # 2) Buscar el primer bloque {...}
    m = _JSON_RE.search(t)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    return {"raw_text": text}

def analizar_video_gemini(gcs_uri: str) -> dict:
    """
    Analiza un video en GCS usando Gemini (modelo multimodal).
    Retorna un dict estructurado compatible con tu pipeline.
    """
    try:
        init(project=PROJECT, location=LOCATION)
        model = GenerativeModel(MODEL_NAME)
        video_part = Part.from_uri(gcs_uri, mime_type="video/mp4")

        prompt = """
        Eres un analista de moderación de video para un entorno corporativo. Detecta SOLO hallazgos VISIBLES y clasifícalos con evidencia.

        OBJETIVOS (prioridad):
        1) ARMAS (incluye objetos usados como arma)
        2) GESTOS OBSCENOS (no verbales)  -> TODO gesto obsceno se reporta igual
        3) VIOLENCIA / AMENAZA / INTIMIDACIÓN (incluye gestos simbólicos)
        4) CONTEXTO DE RIESGO (solo si es visible)

        ========================
        1) ARMAS (incluye objetos usados como arma)
        - Arma blanca: cuchillo, navaja, machete, puñal, cuchilla, daga, etc.
        - REGLA FUERTE: si un cuchillo de cocina o un cuchillo de cubiertos/utensilio se usa para amenazar, intimidar o simular agresión, clasifícalo como "arma blanca".
        - Arma de fuego: pistola, revólver, rifle, escopeta, subfusil, etc.
        - Partes/munición: cargador, bala visible (si es evidente).

        ========================
        2) GESTOS OBSCENOS (no verbales)
        - Cualquier gesto obsceno visible (incluye dedo medio, tocar/agarrar genitales por encima o debajo de la ropa, gestos sexuales explícitos, u otros gestos ofensivos inequívocos)
        DEBE clasificarse SIEMPRE como "gesto obsceno".
        - IMPORTANTE: NO confundir con ajustes casuales de ropa o movimientos ambiguos.
        - REGLA DE INTENCIÓN: si el gesto es deliberado, repetido o dirigido (a cámara / rival / público), aumenta la confianza.
        Si es ambiguo, baja confianza (<0.5) o no lo marques.

        ========================
        3) VIOLENCIA / AMENAZA / INTIMIDACIÓN (acciones y gestos)
        - Violencia: peleas, agresiones, golpes visibles, empujones, forcejeo.
        - Amenaza/intimidación: mostrar un arma para intimidar, apuntar, postura amenazante evidente.
        - SEÑALES EXPLÍCITAS de amenaza con arma blanca o gestos simbólicos:
        a) Simular ataque al cuello con cuchillo (incluye cubierto) o acercarlo al cuello como intimidación
        b) Gesto claro de “corte” en el cuello (con mano/dedo o con objeto) como señal de amenaza
        - REGLA FUERTE: el gesto manda más que el objeto. Si hay gesto de degollamiento/corte al cuello => marca "amenaza" aunque el objeto sea cotidiano.

        ========================
        4) CONTEXTO DE RIESGO (solo visible)
        - Encapuchados con actitud amenazante, acoso/intimidación evidente.
        - No asumas intención si no se ve claramente.

        ========================
        SALIDA OBLIGATORIA
        DEVUELVE EXCLUSIVAMENTE un JSON VÁLIDO (sin Markdown, sin texto extra). Debe cumplir EXACTAMENTE este esquema:

        {
        "objetos_detectados": [
            {
            "label": "arma blanca|arma de fuego|gesto obsceno|violencia|amenaza",
            "confianza": 0.0,
            "es_arma": false,
            "tipo_arma": "blanca|fuego|",
            "es_gesto_obsceno": false,
            "notas": "string"
            }
        ],
        "alertas": [
            "arma_blanca|arma_fuego|gesto_obsceno|violencia|amenaza"
        ],
        "evidencia": [
            {
            "tipo": "arma_blanca|arma_fuego|gesto_obsceno|violencia|amenaza",
            "fuente": "gemini",
            "confianza": 0.0,
            "t0": null,
            "t1": null,
            "descripcion": "string breve"
            }
        ],
        "texto_detectado": [],
        "resumen": "string"
        }

        ========================
        REGLAS IMPORTANTES (cumplimiento estricto)
        - Responde SOLO el JSON. Nada más.
        - No inventes: si no hay evidencia visual clara, NO lo marques.
        - En caso dudoso: confianza < 0.5 o excluye el hallazgo.
        - Máximo 15 elementos en "objetos_detectados".
        - "alertas" solo puede contener valores del catálogo permitido.
        - Siempre que agregues una alerta en "alertas", agrega al menos 1 item en "objetos_detectados" o "evidencia" que la justifique.
        - "t0" y "t1" en segundos si puedes inferirlos; si no, null.

        ========================
        MAPEO DE ACCIONES A SALIDAS (obligatorio)

        A) Arma blanca (incluye cubierto usado para amenazar)
        - Si ves cuchillo/navaja/machete/puñal/cuchillo de cubiertos usado de forma amenazante:
        - objetos_detectados += {
            "label":"arma blanca",
            "confianza": X,
            "es_arma": true,
            "tipo_arma":"blanca",
            "es_gesto_obsceno": false,
            "notas":"objeto usado para intimidar/amenazar"
            }
        - alertas incluye "arma_blanca"
        - evidencia incluye tipo="arma_blanca"

        B) Amenaza (gesto de corte al cuello / degollamiento)
        - Si ves gesto claro de “corte” en el cuello (mano/dedo/objeto) o simulación de ataque al cuello:
        - objetos_detectados += {
            "label":"amenaza",
            "confianza": X,
            "es_arma": false,
            "tipo_arma":"",
            "es_gesto_obsceno": false,
            "notas":"gesto/acción de amenaza (corte al cuello)"
            }
        - alertas incluye "amenaza"
        - evidencia incluye tipo="amenaza"
        - si hay cuchillo/cubierto visible, también agrega "arma_blanca" (A)

        C) Arma de fuego
        - Si ves pistola/rifle/revólver/escopeta:
        - objetos_detectados += { "label":"arma de fuego", "confianza": X, "es_arma": true, "tipo_arma":"fuego", "es_gesto_obsceno": false, "notas":"arma de fuego visible" }
        - alertas incluye "arma_fuego"
        - evidencia tipo="arma_fuego"

        D) Gesto obsceno (cualquier tipo)
        - Si ves CUALQUIER gesto obsceno (incluye dedo medio, tocar/agarrar genitales, gestos sexuales explícitos, u otros ofensivos inequívocos):
        - objetos_detectados += { "label":"gesto obsceno", "confianza": X, "es_arma": false, "tipo_arma":"", "es_gesto_obsceno": true, "notas":"gesto obsceno visible" }
        - alertas incluye "gesto_obsceno"
        - evidencia tipo="gesto_obsceno"

        E) Violencia
        - Si ves pelea/agresión visible:
        - objetos_detectados += { "label":"violencia", "confianza": X, "es_arma": false, "tipo_arma":"", "es_gesto_obsceno": false, "notas":"violencia/agresión visible" }
        - alertas incluye "violencia"
        - evidencia tipo="violencia"

        ========================
        SI NO HAY HALLAZGOS
        Si no detectas nada relevante, responde:
        - "objetos_detectados": []
        - "alertas": []
        - "evidencia": []
        - "texto_detectado": []
        - "resumen": "sin hallazgos"
        """


        response = model.generate_content([video_part, prompt])
        texto = (response.text or "").strip()

        data = _extract_json(texto)

        # Normalización defensiva (para que el pipeline no se rompa)
        if not isinstance(data, dict):
            data = {"raw_text": texto}

        data.setdefault("objetos_detectados", [])
        data.setdefault("alertas", [])
        data.setdefault("texto_detectado", [])
        data.setdefault("resumen", "")

        # Forzar tipos
        if not isinstance(data["objetos_detectados"], list):
            data["objetos_detectados"] = []
        if not isinstance(data["alertas"], list):
            data["alertas"] = []

        return data

    except Exception as e:
        audit_logger.log_error(
            error_type="GEMINI_VIDEO_ANALYSIS_ERROR",
            message=f"Error analizando video con Gemini: {str(e)}"
        )
        return {}