# app/services/text_detection_service.py
import os
import time
import logging
import tempfile
from typing import Dict, List, Optional
from google.cloud import vision
from google.oauth2 import service_account
import cv2
import numpy as np
from app.services.core.logging_service import audit_logger
# snlap
from app.services.moderation import spanlp_service
# Natural Language API
import unicodedata
from functools import lru_cache
from google.cloud import language_v2 as language
from app.services.moderation import badwords_service


PROVIDER = os.getenv("TEXT_MOD_PROVIDER", "language_v2").lower()
ENABLE_MOD = os.getenv("ENABLE_TEXT_MODERATION", "true").lower() in ("1", "true", "yes")
TH_SUS = float(os.getenv("PROFANITY_SUSPECT", "0.25"))
TH_PROB = float(os.getenv("PROFANITY_PROBLEMATIC", "0.60"))
LOCALE = os.getenv("BAD_WORDS_LOCALE", "es-AR")



# Configurar logging
logger = logging.getLogger(__name__)

# Configuración
_GOOGLE_CRED_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
BUCKET_NAME = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "accessfan-video")

# Lista de palabras problemáticas (expandible)
PALABRAS_SOECES = {
    'español': [
        'idiota', 'estúpido', 'imbécil', 'tarado', 'pendejo', 'cabrón',
        'hijo de puta', 'puta', 'puto', 'marica', 'maricón', 'joto',
        'culero', 'ojete', 'chingar', 'joder', 'mierda', 'cagada',
        'huevón', 'güevón', 'baboso', 'mamón', 'cerdo', 'cochino', 'pelotudos','forros', 'cabrones',
        # Agregar más según necesidades
    ],
    'inglés': [
        'idiot', 'stupid', 'moron', 'dumbass', 'asshole', 'bastard',
        'bitch', 'fuck', 'fucking', 'shit', 'damn', 'hell',
        'crap', 'suck', 'sucks', 'gay', 'retard', 'loser',
        'dickhead', 'motherfucker', 'son of a bitch', 'whore',
        # Agregar más según necesidades
    ]
}

_LEET_MAP = str.maketrans({"0":"o","1":"i","3":"e","4":"a","5":"s","7":"t","@":"a","$":"s","!":"i"})

def _normalize(text: str) -> str:
    t = text.lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")  # quita acentos
    t = t.translate(_LEET_MAP)
    out, prev, run = [], "", 0
    for c in t:
        if c == prev: run += 1
        else: run, prev = 0, c
        if run < 2: out.append(c)  # permite hasta 2 repeticiones
    return "".join(out)

@lru_cache(maxsize=8)
def _load_bad_words(locale: str) -> Dict[str, list]:
    base = {
        "es-AR": ["boludo","pelotudo","forro","la concha de tu madre","gato","pajero","puto","puta"],
        "es-ES": ["gilipollas","capullo","hijo de puta","zorra","mierda","cabrón"],
        "en":    ["fuck","fucking","shit","bitch","asshole","dickhead"]
    }
    # fusiona con tus listas existentes para compat
    base.setdefault("es", []).extend(PALABRAS_SOECES.get("español", []))
    base.setdefault("en", []).extend(PALABRAS_SOECES.get("inglés", []))
    return base

def _detectar_palabras_problematicas_normalizado(texto_norm: str, locale: str) -> List[str]:
    found, seen = [], set()
    lex = _load_bad_words(locale)
    buckets = [locale, locale.split("-")[0], "es", "en"]  # prioridad local -> es/en
    for k in buckets:
        for w in lex.get(k, []):
            w_norm = _normalize(w)
            if w_norm in texto_norm and w_norm not in seen:
                found.append(w)
                seen.add(w_norm)
    return found

def _get_vision_client():
    """Crea cliente de Cloud Vision API usando las mismas credenciales que Video AI"""
    try:
        if _GOOGLE_CRED_PATH and os.path.isfile(_GOOGLE_CRED_PATH):
            creds = service_account.Credentials.from_service_account_file(_GOOGLE_CRED_PATH)
            return vision.ImageAnnotatorClient(credentials=creds)
        return vision.ImageAnnotatorClient()  # Application Default Credentials
    except Exception as e:
        audit_logger.log_error(
            error_type="TEXT_DETECTION_CLIENT_ERROR",
            message=f"Error creando cliente de Cloud Vision: {str(e)}"
        )
        raise

_vision_client = None

def _client():
    global _vision_client
    if _vision_client is None:
        _vision_client = _get_vision_client()
    return _vision_client

def _fusionar_palabras(lista_local, lista_spanlp, lista_badwords):
    """
    Une resultados de lista manual, spanlp y badwords_service evitando duplicados.
    Retorna solo la palabra limpia (sin etiquetas ni sufijos).
    """
    fusion = {}

    def limpiar_tag(w: str) -> str:
        return (
            w.replace("(es)", "")
            .replace("(en)", "")
            .replace("(global)", "")
            .replace("[lista]", "")
            .replace("[spanlp]", "")
            .replace("[badwords]", "")
            .strip()
        )

    def agregar(words: List[str]):
        for w in words:
            wn = _normalize(limpiar_tag(w))
            if wn not in fusion:   # evita duplicados
                fusion[wn] = limpiar_tag(w)

    agregar(lista_local)
    agregar(lista_spanlp)
    agregar(lista_badwords)

    return list(fusion.values())

def analizar_texto_en_video(gcs_uri: str, video_id: int = None) -> Dict:
    """
    Analiza texto en frames (OCR) + modera con Language v2 (moderate_text)
    y combina con lista local, spanlp y badwords_service.
    """
    start_time = time.time()

    try:
        logger.info(f"Iniciando detección de texto para video: {gcs_uri}")
        audit_logger.log_error(
            error_type="TEXT_DETECTION_START",
            message="Iniciando detección de texto en video",
            video_id=video_id,
            details={"gcs_uri": gcs_uri}
        )

        # ---------- OCR ----------
        frames_analizados = 0
        todo_el_texto: List[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, "temp_video.mp4")

            if not _descargar_video_desde_gcs(gcs_uri, video_path):
                raise Exception("No se pudo descargar el video desde GCS")

            frames_textos = _extraer_y_analizar_frames(video_path, max_frames=10)
            frames_analizados = len(frames_textos)

            for fragmento in frames_textos:
                if fragmento:
                    todo_el_texto.append(fragmento)

        texto_completo = " ".join(todo_el_texto).strip()
        texto_norm = texto_completo.lower() if texto_completo else ""

        # ---------- Lista local + spanlp + badwords ----------
        palabras_encontradas: List[str] = []
        nivel_lista = "limpio"
        if texto_norm:
            # 1) Detectar con lista manual
            palabras_locales = _detectar_palabras_problematicas(texto_norm)

            # 2) Detectar con spanlp
            palabras_spanlp = spanlp_service.detectar_palabras(texto_completo)

            # 3) Detectar con badwords_service
            bw_result = badwords_service.detect_badwords(texto_completo)
            palabras_badwords = bw_result.get("found", [])


            # 4) Unir todas las fuentes
            palabras_encontradas = _fusionar_palabras(
                palabras_locales, palabras_spanlp, palabras_badwords
            )

            # 5) Calcular nivel
            nivel_lista = _calcular_nivel_problema(palabras_encontradas)

        # ---------- Language v2: moderate_text ----------
        nivel_api = "limpio"
        score_api = 0.0
        detalle_api: Dict = {}
        top_cat = "profanity"

        if os.getenv("ENABLE_MOD", "false").lower() in ("true", "1") and texto_completo:
            try:
                res = _moderate_text_language_v2(texto_completo)
                cats = {k.lower(): float(v) for k, v in res.get("raw", {}).items()}
                nivel_api, top_cat, score_api, detalle_api = _nivel_api_desde_categorias(cats)
            except Exception as me:
                logger.warning(f"Moderation provider error: {me}")
                nivel_api = "error"

        # ---------- Fusión niveles ----------
        def _combinar_niveles(n1, n2):
            rank = {"limpio": 0, "sospechoso": 1, "problematico": 2, "error": -1}
            return max([n1, n2], key=lambda n: rank.get(n, -1))

        nivel_problema = _combinar_niveles(nivel_lista, nivel_api)

        # Log de moderación
        audit_logger.log_error(
            error_type="TEXT_MODERATION_RESULT",
            message=f"nivel={nivel_problema}, top={top_cat}:{round(score_api, 3)}",
            video_id=video_id,
            details={
                "api_level": nivel_api,
                "lista_level": nivel_lista,
                "scores": detalle_api
            }
        )

        tiempo_procesamiento = time.time() - start_time

        # ---------- Resultado ----------
        resultado = {
            "texto_detectado": "; ".join(todo_el_texto) if todo_el_texto else "",
            "frames_analizados": frames_analizados,
            "palabras_problematicas": ", ".join(palabras_encontradas) if palabras_encontradas else "",
            "nivel_problema": nivel_problema,
            "nivel_problema_lista": nivel_lista,
            "nivel_problema_api": nivel_api,
            "profanity_score_api": round(score_api, 3),
            "moderation_details": detalle_api,
            "tiempo_procesamiento": round(tiempo_procesamiento, 2),
            "texto_encontrado": bool(todo_el_texto),
        }

        logger.info(f"Detección de texto completada en {tiempo_procesamiento:.2f}s")
        logger.info(f"Frames analizados: {frames_analizados}")
        logger.info(f"Texto encontrado: {len(todo_el_texto)} fragmentos")
        logger.info(
            f"Nivel (final): {nivel_problema} | API={nivel_api}({score_api:.3f} {top_cat}) | Lista={nivel_lista}"
        )

        return resultado

    except Exception as e:
        tiempo_procesamiento = time.time() - start_time
        logger.error(f"Error en detección de texto: {str(e)}")
        audit_logger.log_error(
            error_type="TEXT_DETECTION_ERROR",
            message=f"Error en detección de texto: {str(e)}",
            video_id=video_id,
            details={"gcs_uri": gcs_uri, "tiempo_procesamiento": tiempo_procesamiento}
        )
        return {
            "texto_detectado": "",
            "frames_analizados": 0,
            "palabras_problematicas": "",
            "nivel_problema": "error",
            "nivel_problema_lista": "error",
            "nivel_problema_api": "error",
            "profanity_score_api": 0.0,
            "moderation_details": {},
            "tiempo_procesamiento": round(tiempo_procesamiento, 2),
            "texto_encontrado": False,
            "error": str(e),
        }

def _descargar_video_desde_gcs(gcs_uri: str, local_path: str) -> bool:
    """Descarga video desde GCS a archivo local temporal"""
    try:
        from google.cloud import storage
        
        # Extraer bucket y object name de la URI
        uri_parts = gcs_uri.replace('gs://', '').split('/', 1)
        bucket_name = uri_parts[0]
        object_name = uri_parts[1]
        
        # Descargar archivo
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.download_to_filename(local_path)
        
        logger.debug(f"Video descargado: {local_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error descargando video desde GCS: {str(e)}")
        return False

def _extraer_y_analizar_frames(video_path: str, max_frames: int = 10) -> List[str]:
    """Extrae frames del video y analiza texto en cada uno"""
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception("No se pudo abrir el video")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        
        # Calcular intervalos para extraer frames representativos
        if total_frames <= max_frames:
            frame_indices = list(range(0, total_frames, max(1, total_frames // max_frames)))
        else:
            frame_indices = list(range(0, total_frames, total_frames // max_frames))[:max_frames]
        
        frames_textos = []
        
        for frame_idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            
            if ret:
                texto = _analizar_texto_en_frame(frame)
                if texto:
                    frames_textos.append(texto)
                    logger.debug(f"Frame {frame_idx}: {texto[:100]}...")
        
        cap.release()
        logger.info(f"Analizados {len(frame_indices)} frames, texto en {len(frames_textos)}")
        
        return frames_textos
        
    except Exception as e:
        logger.error(f"Error extrayendo frames: {str(e)}")
        return []

def _analizar_texto_en_frame(frame) -> str:
    """Analiza texto en un frame específico usando Cloud Vision API"""
    try:
        # Convertir frame a bytes
        _, buffer = cv2.imencode('.jpg', frame)
        image_bytes = buffer.tobytes()
        
        # Crear objeto Image para Vision API
        image = vision.Image(content=image_bytes)
        
        # Detectar texto
        response = _client().text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"Error en Vision API: {response.error.message}")
        
        # Extraer texto detectado
        texts = response.text_annotations
        if texts:
            return texts[0].description.strip()
        
        return ""
        
    except Exception as e:
        logger.debug(f"Error analizando frame: {str(e)}")
        return ""

def _detectar_palabras_problematicas(texto: str) -> List[str]:
    """Busca palabras problemáticas en el texto detectado"""
    palabras_encontradas = []
    texto_limpio = texto.lower().strip()
    
    # Buscar en español
    for palabra in PALABRAS_SOECES['español']:
        if palabra in texto_limpio:
            palabras_encontradas.append(f"{palabra} (es)")
    
    # Buscar en inglés
    for palabra in PALABRAS_SOECES['inglés']:
        if palabra in texto_limpio:
            palabras_encontradas.append(f"{palabra} (en)")
    
    return palabras_encontradas

def _calcular_nivel_problema(palabras_encontradas: List[str]) -> str:
    """Calcula el nivel de problema basado en palabras encontradas"""
    num_palabras = len(palabras_encontradas)
    
    if num_palabras == 0:
        return 'limpio'
    elif num_palabras <= 2:
        return 'sospechoso'
    else:
        return 'problematico'

# --- Helpers de moderación avanzada ---

# Umbrales (Valores ajustables)
TH_SUS = 0.3
TH_PROB = 0.6

# Categorías relevantes y sus umbrales
RELEVANT_CATS = {
    "profanity":              (TH_SUS, TH_PROB),
    "violent":                (TH_SUS, TH_PROB),
    "sexual":                 (TH_SUS, TH_PROB),
    "death, harm & tragedy":  (TH_SUS, TH_PROB),
}

def _nivel_por_score_cat(cat: str, score: float) -> str:
    sus, prob = RELEVANT_CATS.get(cat, (TH_SUS, TH_PROB))
    if score >= prob:
        return "problematico"
    if score >= sus:
        return "sospechoso"
    return "limpio"

def _nivel_api_desde_categorias(cats: dict):
    """
    cats viene como { "profanity": 0.xx, "violent": 0.yy, ... } en minúsculas.
    Devuelve: (nivel_api, categoria_top, score_top, selected_scores)
    """
    # nos quedamos solo con las relevantes
    selected = {k: float(cats.get(k, 0.0)) for k in RELEVANT_CATS.keys()}
    # nivel por categoría
    niveles = {k: _nivel_por_score_cat(k, v) for k, v in selected.items()}
    # severidad: limpio < sospechoso < problematico
    rank = {"limpio": 0, "sospechoso": 1, "problematico": 2}
    nivel_api = max(niveles.values(), key=lambda n: rank[n])
    top_cat, top_score = max(selected.items(), key=lambda kv: kv[1]) if selected else ("profanity", 0.0)
    return nivel_api, top_cat, top_score, selected

def agregar_palabras_soeces(nuevas_palabras: Dict[str, List[str]]):
    """Permite agregar nuevas palabras problemáticas dinámicamente"""
    global PALABRAS_SOECES
    
    for idioma, palabras in nuevas_palabras.items():
        if idioma not in PALABRAS_SOECES:
            PALABRAS_SOECES[idioma] = []
        PALABRAS_SOECES[idioma].extend(palabras)
    
    logger.info(f"Agregadas nuevas palabras soeces: {nuevas_palabras}")

def probar_conexion_vision_api() -> bool:
    """Prueba la conexión con Cloud Vision API"""
    try:
        client = _client()
        
        # Probar con imagen de prueba
        image = vision.Image()
        image.source.image_uri = "gs://cloud-samples-data/vision/text/screen.jpg"
        
        response = client.text_detection(image=image)
        
        if response.text_annotations:
            logger.info("✅ Conexión con Cloud Vision API exitosa")
            return True
        else:
            logger.warning("⚠️ Cloud Vision API responde pero no detectó texto")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error conectando con Cloud Vision API: {e}")
        audit_logger.log_error(
            error_type="TEXT_DETECTION_CONNECTION_ERROR",
            message=f"Error conectando con Cloud Vision API: {str(e)}"
        )
        return False

def _moderate_text_language_v2(texto: str) -> dict:
    """
    Stub de moderación de texto con Google Language v2 (moderate_text).
    Aquí deberías llamar a la API real. Por ahora simula respuesta.
    """
    try:
        from google.cloud import language_v2

        client = language_v2.LanguageServiceClient()
        response = client.moderate_text(
            model="moderation-text-v1.0",
            prompt=texto
        )
        raw_scores = {cat.name.lower(): cat.score for cat in response.moderation_categories}
        return {"raw": raw_scores}

    except Exception as e:
        logger.warning(f"Error llamando a Language v2 moderate_text: {e}")
        return {"raw": {}}

def _nivel_por_score(score: float) -> str:
    if score >= TH_PROB: return "problematico"
    if score >= TH_SUS:  return "sospechoso"
    return "limpio"

def _combinar_niveles(n1: str, n2: str) -> str:
    orden = {"limpio":0,"sospechoso":1,"problematico":2,"error":-1}
    return n1 if orden[n1] >= orden[n2] else n2
