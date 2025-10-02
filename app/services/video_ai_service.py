# app/services/video_ai_service.py (ACTUALIZADO CON TRADUCCIÓN)
import os
import time
import logging
from typing import Dict, List, Optional
from google.cloud import videointelligence_v1 as vi
from google.oauth2 import service_account
from app.services.logging_service import audit_logger
from app.services.translation_service import traducir_etiquetas, traducir_contenido_explicito, traducir_logos
from app.services.text_detection_service import analizar_texto_en_video

# Configurar logging
logger = logging.getLogger(__name__)

_GOOGLE_CRED_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

def _get_client():
    try:
        if _GOOGLE_CRED_PATH and os.path.isfile(_GOOGLE_CRED_PATH):
            creds = service_account.Credentials.from_service_account_file(_GOOGLE_CRED_PATH)
            return vi.VideoIntelligenceServiceClient(credentials=creds)
        return vi.VideoIntelligenceServiceClient()  # Application Default Credentials
    except Exception as e:
        audit_logger.log_error(
            error_type="VIDEO_AI_CLIENT_ERROR",
            message=f"Error creando cliente de Video Intelligence: {str(e)}"
        )
        raise

_video_client = None

def _client():
    global _video_client
    if _video_client is None:
        _video_client = _get_client()
    return _video_client

def analizar_video_completo(gcs_uri: str, timeout_sec: int = 600) -> Dict:
    """
    Analiza un video en GCS y retorna datos formateados para el modelo Video.
    Incluye etiquetas, contenido explícito, logotipos, objetos detectados y texto.
    """
    start_time = time.time()
    
    try:
        logger.info(f"Iniciando análisis de video para: {gcs_uri}")
        
        # --- Features habilitadas ---
        features = [
            vi.Feature.LABEL_DETECTION,
            vi.Feature.EXPLICIT_CONTENT_DETECTION,
            vi.Feature.LOGO_RECOGNITION,
            vi.Feature.OBJECT_TRACKING, 
            vi.Feature.SHOT_CHANGE_DETECTION,
        ]
        video_context = vi.VideoContext(
            label_detection_config=vi.LabelDetectionConfig(
                label_detection_mode=vi.LabelDetectionMode.SHOT_AND_FRAME_MODE
            )
        )

        operation = _client().annotate_video(
            request={"input_uri": gcs_uri, "features": features, "video_context": video_context}
        )
        result = operation.result(timeout=timeout_sec)
        annotation_result = result.annotation_results[0]
        
        # --- Procesamiento ---
        etiquetas_en = _procesar_etiquetas(annotation_result)
        contenido_explicito_en = _procesar_contenido_explicito(annotation_result)
        logotipos_obj_en = _procesar_logotipos(annotation_result) 
        logotipos_en = ', '.join([item['logo'] for item in logotipos_obj_en])
        objetos_detectados = _procesar_objetos(annotation_result)  # 👈 nuevo
        
        objetos_detectados = _procesar_objetos(annotation_result)
        logger.info(f"[VI] Objetos detectados totales: {len(objetos_detectados)}")

        # --- Traducción ---
        logger.info("Traduciendo resultados del análisis de IA...")
        try:
            etiquetas_es = traducir_etiquetas(etiquetas_en, 'es')
            contenido_explicito_es = traducir_contenido_explicito(contenido_explicito_en, 'es')
            logotipos_es = traducir_logos(logotipos_en, 'es')
        except Exception as e:
            logger.warning(f"Error en traducción, usando textos originales: {str(e)}")
            etiquetas_es = etiquetas_en
            contenido_explicito_es = contenido_explicito_en
            logotipos_es = logotipos_en

        # --- Detección de texto ---
        logger.info("Analizando texto en frames del video...")
        try:
            resultados_texto = analizar_texto_en_video(gcs_uri, video_id=None)
        except Exception as e:
            logger.warning(f"Error en detección de texto: {str(e)}")
            resultados_texto = { 
                'texto_detectado': '', 
                'palabras_problematicas': '', 
                'nivel_problema': 'error', 
                'frames_analizados': 0 
            }

        # --- Construcción de resultados finales ---
        tiempo_total = time.time() - start_time
        datos_procesados = {
            'etiquetas': etiquetas_es,
            'contenido_explicito': contenido_explicito_es,
            'logotipos': logotipos_es,
            'objetos_detectados': objetos_detectados,  # 👈 agregado
            'puntaje_confianza': _calcular_puntaje_confianza(annotation_result),
            'tiempo_procesamiento': round(tiempo_total, 2),
            'texto_detectado': resultados_texto['texto_detectado'],
            'palabras_problematicas': resultados_texto['palabras_problematicas'], 
            'nivel_problema_texto': resultados_texto['nivel_problema'],
            'frames_texto_analizados': resultados_texto['frames_analizados'],
            # originales
            'etiquetas_original': etiquetas_en,
            'contenido_explicito_original': contenido_explicito_en,
            'logotipos_original': logotipos_en
        }
        
        logger.info(f"Análisis completado en {tiempo_total:.2f} segundos")
        return datos_procesados
        
    except Exception as e:
        logger.error(f"Error fatal en analizar_video_completo: {e}")
        raise

def _procesar_etiquetas(annotation_result) -> str:
    """
    Procesa las etiquetas detectadas y las convierte en string separado por comas.
    Filtra por confianza mínima y elimina duplicados.
    *** NOTA: Devuelve etiquetas en INGLÉS (se traducen después) ***
    """
    try:
        etiquetas = []
        confianza_minima = 0.4  # Solo etiquetas con 50% o más de confianza
        
        # Procesar etiquetas de segmentos
        for label in annotation_result.segment_label_annotations:
            for segment in label.segments:
                if segment.confidence >= confianza_minima:
                    etiqueta = label.entity.description.lower()
                    if etiqueta not in etiquetas:
                        etiquetas.append(etiqueta)
        
        # Procesar etiquetas de frames individuales 
        for label in annotation_result.frame_label_annotations:
            for frame in label.frames:
                if frame.confidence >= confianza_minima:
                    etiqueta = label.entity.description.lower()
                    if etiqueta not in etiquetas:
                        etiquetas.append(etiqueta)
        
        # Limitar a máximo 20 etiquetas más relevantes
        etiquetas_ordenadas = sorted(etiquetas)[:20]
        
        logger.debug(f"Etiquetas procesadas (EN): {etiquetas_ordenadas}")
        return ', '.join(etiquetas_ordenadas) if etiquetas_ordenadas else ''
        
    except Exception as e:
        audit_logger.log_error(
            error_type="VIDEO_AI_LABELS_ERROR",
            message=f"Error procesando etiquetas: {str(e)}"
        )
        return ''

def _procesar_contenido_explicito(annotation_result) -> str:
    """
    Analiza los frames para detectar contenido explícito.
    *** VERSIÓN MEJORADA: Usa la puntuación MÁXIMA en lugar del promedio para ser más sensible. ***
    """
    try:
        if not hasattr(annotation_result, 'explicit_annotation') or not annotation_result.explicit_annotation:
            return 'Not analyzed'
        
        niveles_pornografia = [1] # Empezar con 1 (MUY IMPROBABLE) para evitar errores con listas vacías
        
        for frame in annotation_result.explicit_annotation.frames:
            porn_level = _likelihood_to_number(frame.pornography_likelihood)
            niveles_pornografia.append(porn_level)
        
        # --- CAMBIO CLAVE: Usamos el valor MÁXIMO, no el promedio ---
        max_porn = max(niveles_pornografia)
        
        # Determinar resultado final basado en la PEOR puntuación encontrada
        if max_porn >= 5:    # Si cualquier frame es VERY_LIKELY
            resultado = 'Explicit'
        elif max_porn >= 4:  # Si cualquier frame es LIKELY
            resultado = 'Explicit'
        elif max_porn >= 3:  # Si cualquier frame es POSSIBLE
            resultado = 'Possible' # Este es el que debería activarse con contenido sugestivo
        else:                # Si ningún frame superó el nivel 'POSSIBLE'
            resultado = 'Safe'
        
        logger.debug(f"Contenido explícito (EN) - Puntuación Máxima: {max_porn} -> {resultado}")
        
        # El log de auditoría se mantiene igual
        if resultado in ['Explicit', 'Possible']:
            audit_logger.log_error(
                error_type="VIDEO_AI_EXPLICIT_CONTENT",
                message=f"Contenido explícito detectado: {resultado}",
                details={'max_porn_level': max_porn, 'frames_analizados': len(niveles_pornografia) - 1}
            )
        
        return resultado
        
    except Exception as e:
        audit_logger.log_error(
            error_type="VIDEO_AI_EXPLICIT_ERROR",
            message=f"Error procesando contenido explícito: {str(e)}"
        )
        return 'Not analyzed'

def _procesar_logotipos(annotation_result) -> List[Dict]:
    """
    Extrae los logos detectados, su confianza y los devuelve como una lista de diccionarios.
    *** NOTA: Devuelve nombres en idioma original (generalmente inglés) ***
    """
    try:
        # 1. UMBRAL CONFIGURABLE Y MÁS SENSIBLE
        # Lee la variable de entorno o usa 0.15 (15%) por defecto.
        confianza_minima = float(os.getenv("LOGO_CONFIDENCE_THRESHOLD", "0.15"))
        
        logos_encontrados = {}
        
        for logo_annotation in annotation_result.logo_recognition_annotations:
            logo_name = logo_annotation.entity.description
            
            # 2. LÓGICA DE CONFIANZA SIMPLIFICADA
            # Usamos la confianza principal de cada "track" o seguimiento del logo
            for track in logo_annotation.tracks:
                if track.confidence >= confianza_minima:
                    # Guardamos la confianza más alta encontrada para un mismo logo
                    if logo_name not in logos_encontrados or track.confidence > logos_encontrados[logo_name]:
                        logos_encontrados[logo_name] = track.confidence
        
        # 3. DEVOLVER RESULTADOS MÁS RICOS
        # Convertir el diccionario a una lista de diccionarios formateados
        logos_formateados = [
            {'logo': name, 'confianza': round(conf, 2)} 
            for name, conf in logos_encontrados.items()
        ]
        
        logger.debug(f"Logos detectados (nombre y confianza): {logos_formateados}")
        
        if logos_formateados:
            audit_logger.log_error(
                error_type="VIDEO_AI_LOGOS_DETECTED",
                message=f"Logos detectados en video: {[item['logo'] for item in logos_formateados]}",
                details={'logos': logos_formateados, 'total_logos': len(logos_formateados)}
            )
        
        return logos_formateados
        
    except Exception as e:
        audit_logger.log_error(
            error_type="VIDEO_AI_LOGOS_ERROR",
            message=f"Error procesando logos: {str(e)}"
        )
        return []

def _calcular_puntaje_confianza(annotation_result, objetos_detectados=None) -> float:
    """
    Calcula un puntaje general de confianza basado en todos los análisis.
    - Promedio de confianzas de etiquetas, frames y logos
    - Penalización si se detectan armas (en objetos o en etiquetas)
    Retorna valor entre 0.0 y 1.0
    """
    try:
        confianzas = []

        # Confianza de etiquetas (segmentos)
        for label in annotation_result.segment_label_annotations:
            for segment in label.segments:
                confianzas.append(segment.confidence)

        # Confianza de etiquetas (frames individuales)
        for label in annotation_result.frame_label_annotations:
            for frame in label.frames:
                confianzas.append(frame.confidence)

        # Confianza de logos
        for logo_annotation in annotation_result.logo_recognition_annotations:
            for track in logo_annotation.tracks:
                for timestamped_object in track.timestamped_objects:
                    for attribute in timestamped_object.attributes:
                        if attribute.name == "logo_confidence":
                            confianzas.append(attribute.confidence)

        # === Puntaje base ===
        puntaje_base = sum(confianzas) / len(confianzas) if confianzas else 0.0

        # === Ajustes de riesgo visual ===
        penalty = 0.0

        # --- 1. Revisar objetos detectados ---
        if objetos_detectados:
            for obj in objetos_detectados:
                if obj.get("label") == "arma de fuego":
                    penalty = max(penalty, 0.5)  # -50%
                    logger.warning(f"[CONF] Penalización: Arma de fuego detectada en objetos -> -50%")
                elif obj.get("label") == "arma blanca":
                    penalty = max(penalty, 0.3)  # -30%
                    logger.warning(f"[CONF] Penalización: Arma blanca detectada en objetos -> -30%")

        # --- 2. Revisar etiquetas (por si no hubo objetos trackeados) ---
        ARMAS_BLANCA_KEYWORDS = {
            "knife","blade","dagger","machete","sword","cutlass",
            "cutter","razor","scissors","shears","cutlery","utensil",
            "kitchen knife","pocket knife","switchblade","box cutter",
            "x-acto","scalpel","screwdriver","shank","shiv"
        }
        ARMAS_FUEGO_KEYWORDS = {
            "gun","pistol","rifle","firearm","shotgun",
            "revolver","machine gun","handgun","weapon"
        }

        for label in annotation_result.segment_label_annotations:
            l = label.entity.description.lower().strip()
            if l in ARMAS_FUEGO_KEYWORDS:
                penalty = max(penalty, 0.5)
                logger.warning(f"[CONF] Penalización: Arma de fuego detectada en etiquetas ('{l}') -> -50%")
            elif l in ARMAS_BLANCA_KEYWORDS:
                penalty = max(penalty, 0.3)
                logger.warning(f"[CONF] Penalización: Arma blanca detectada en etiquetas ('{l}') -> -30%")

        # === Puntaje final ajustado ===
        puntaje_final = max(0.0, puntaje_base * (1 - penalty))

        logger.info(f"[CONF] Puntaje base={puntaje_base:.3f} | Penalización={penalty*100:.0f}% | Final={puntaje_final:.3f}")
        return round(puntaje_final, 3)

    except Exception as e:
        audit_logger.log_error(
            error_type="VIDEO_AI_CONFIDENCE_ERROR",
            message=f"Error calculando puntaje de confianza: {str(e)}"
        )
        return 0.0

def _likelihood_to_number(likelihood) -> int:
    """
    Convierte likelihood enum a número para cálculos.
    """
    likelihood_map = {
        vi.Likelihood.VERY_UNLIKELY: 1,
        vi.Likelihood.UNLIKELY: 2,
        vi.Likelihood.POSSIBLE: 3,
        vi.Likelihood.LIKELY: 4,
        vi.Likelihood.VERY_LIKELY: 5
    }
    return likelihood_map.get(likelihood, 1)

def _procesar_objetos(annotation_result) -> List[Dict]:
    """
    Procesa OBJECT_TRACKING con:
    - Umbrales configurables
    - Duración por track
    - Ejemplos de timestamps
    - Allow/Deny list por ENV
    - Top-K por duración
    - Normalización de armas blancas y de fuego
    """
    try:
        objetos = []
        # Umbrales globales
        conf_global = float(os.getenv("OBJECT_CONFIDENCE_THRESHOLD", "0.25"))
        min_frames = int(os.getenv("OBJECT_MIN_FRAMES", "3"))
        top_k = int(os.getenv("OBJECT_TOPK", "20"))
        # Allow/Deny
        allow = {s.strip().lower() for s in os.getenv("OBJECT_LABEL_ALLOWLIST", "").split(",") if s.strip()}
        deny  = {s.strip().lower() for s in os.getenv("OBJECT_LABEL_DENYLIST", "").split(",") if s.strip()}

        # --- Listados de posibles armas ---
        ARMAS_BLANCA_KEYWORDS = {
            "knife","blade","dagger","machete","sword","cutlass",
            "cutter","razor","scissors","shears","cutlery","utensil",
            "kitchen knife","pocket knife","switchblade","box cutter",
            "x-acto","scalpel","screwdriver","shank","shiv"
        }
        ARMAS_FUEGO_KEYWORDS = {
            "gun","pistol","rifle","firearm","shotgun",
            "revolver","machine gun","handgun","weapon"
        }

        def conf_por_label(label: str) -> float:
            key = f"OBJECT_CONF_THRESH_{label.replace(' ', '_')}".upper()
            try:
                return float(os.getenv(key, str(conf_global)))
            except:
                return conf_global

        raw_objs = getattr(annotation_result, "object_annotations", [])
        logger.info(f"[OBJ] Objetos crudos: {len(raw_objs)}")

        def permitido(label: str) -> bool:
            if allow and label not in allow: return False
            if label in deny: return False
            return True

        # Compactador de intervalos
        def compactar_intervalos(intervalos, gap=0.5):
            if not intervalos: return []
            intervalos = sorted(intervalos, key=lambda x: x[0])
            res = [list(intervalos[0])]
            for s,e in intervalos[1:]:
                if s - res[-1][1] <= gap:
                    res[-1][1] = max(res[-1][1], e)
                else:
                    res.append([s,e])
            return [tuple(x) for x in res]

        for idx, obj in enumerate(raw_objs, 1):
            raw_label = obj.entity.description.lower().strip()
            if not permitido(raw_label):
                continue

            thr = conf_por_label(raw_label)
            conf = float(getattr(obj, "confidence", 0.0))
            if conf < thr:
                logger.debug(f"[OBJ] '{raw_label}' descartado por confianza {conf:.2f} < {thr:.2f}")
                continue

            # Duración y frames
            seg = getattr(obj, "segment", None)
            inicio = _duration_to_seconds(getattr(seg, "start_time_offset", None))
            fin    = _duration_to_seconds(getattr(seg, "end_time_offset", None))
            frames = getattr(obj, "frames", []) or getattr(obj, "timestamps", [])
            total_frames = len(frames)
            if total_frames < min_frames:
                continue

            # Ejemplos de offsets (máx 5)
            ejemplos = []
            for f in frames[:5]:
                to = getattr(f, "time_offset", None)
                ejemplos.append(_duration_to_seconds(to))

            # Intervalos
            winsize = float(os.getenv("OBJECT_FRAME_WINDOW_S", "0.20"))
            intervalos_raw = []
            for f in frames:
                t = _duration_to_seconds(getattr(f, "time_offset", None))
                if t > 0:
                    intervalos_raw.append((max(0.0, t - winsize/2), t + winsize/2))
            intervalos = compactar_intervalos(intervalos_raw, gap=0.5)

            dur_total = sum(max(0.0, e - s) for s, e in intervalos)

            # --- Normalización de armas ---
            label_norm = raw_label
            es_arma = False
            tipo_arma = ""

            if raw_label in ARMAS_BLANCA_KEYWORDS:
                label_norm = "arma blanca"
                es_arma = True
                tipo_arma = "blanca"
                logger.warning(f"[OBJ][ARMA BLANCA] '{raw_label}' detectado -> normalizado a '{label_norm}'")

            elif raw_label in ARMAS_FUEGO_KEYWORDS:
                label_norm = "arma de fuego"
                es_arma = True
                tipo_arma = "fuego"
                logger.warning(f"[OBJ][ARMA DE FUEGO] '{raw_label}' detectado -> normalizado a '{label_norm}'")

            objetos.append({
                "label": label_norm,
                "label_original": raw_label,
                "es_arma": es_arma,
                "tipo_arma": tipo_arma,
                "confianza": round(conf, 2),
                "frames_detectados": total_frames,
                "segmento_inicio": inicio,
                "segmento_fin": fin,
                "duracion_seg": round(dur_total, 2),
                "intervalos": [(round(s,2), round(e,2)) for s,e in intervalos[:10]],
                "ejemplo_offsets": ejemplos,
            })

        # Ordenar por duración y confianza
        objetos.sort(key=lambda x: (x["duracion_seg"], x["confianza"]), reverse=True)
        if top_k > 0 and len(objetos) > top_k:
            objetos = objetos[:top_k]

        logger.info(f"[OBJ] Objetos filtrados finales: {len(objetos)}")
        if objetos:
            logger.debug(f"[OBJ] Ejemplos: {objetos[:3]}")
        return objetos

    except Exception as e:
        logger.exception(f"[OBJ] Error procesando objetos: {e}")
        audit_logger.log_error(
            error_type="VIDEO_AI_OBJECTS_ERROR",
            message=f"Error procesando objetos: {str(e)}"
        )
        return []

# Función original mantenida para compatibilidad
def analizar_video(gcs_uri: str, timeout_sec: int = 600):
    """
    Función original - mantener para compatibilidad hacia atrás.
    Retorna el annotation_result crudo.
    """
    try:
        features = [
            vi.Feature.LABEL_DETECTION,
            vi.Feature.EXPLICIT_CONTENT_DETECTION,
            vi.Feature.LOGO_RECOGNITION,
            vi.Feature.OBJECT_TRACKING,
            vi.Feature.SHOT_CHANGE_DETECTION,
        ]
        op = _client().annotate_video(request={
            "input_uri": gcs_uri,
            "features": features
        })
        result = op.result(timeout=timeout_sec)
        return result.annotation_results[0]
        
    except Exception as e:
        audit_logger.log_error(
            error_type="VIDEO_AI_LEGACY_ERROR",
            message=f"Error en función legacy analizar_video: {str(e)}",
            details={'gcs_uri': gcs_uri}
        )
        raise

def probar_conexion_api() -> bool:
    """
    Función de utilidad para probar la conexión con Video Intelligence API.
    """
    try:
        client = _client()
        logger.info("✅ Conexión con Video Intelligence API exitosa")
        audit_logger.log_error(
            error_type="VIDEO_AI_CONNECTION_TEST_SUCCESS",
            message="Conexión con Video Intelligence API exitosa"
        )
        return True
    except Exception as e:
        logger.error(f"❌ Error conectando con Video Intelligence API: {e}")
        audit_logger.log_error(
            error_type="VIDEO_AI_CONNECTION_TEST_FAILED",
            message=f"Error conectando con Video Intelligence API: {str(e)}"
        )
        return False

def _duration_to_seconds(duracion) -> float:
    """
    Convierte un Duration (protobuf) o un timedelta a segundos.
    """
    if not duracion:
        return 0.0
    try:
        # Caso protobuf Duration
        if hasattr(duracion, "seconds") and hasattr(duracion, "nanos"):
            return duracion.seconds + duracion.nanos / 1e9
        # Caso timedelta
        if hasattr(duracion, "total_seconds"):
            return duracion.total_seconds()
    except Exception as e:
        logger.warning(f"[OBJ] No se pudo convertir duración: {duracion} ({e})")
    return 0.0
