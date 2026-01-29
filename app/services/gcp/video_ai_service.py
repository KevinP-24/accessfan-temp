# app/services/video_ai_service.py (ACTUALIZADO CON TRADUCCIÓN)
import os
import time
import logging
from typing import Dict, List, Optional
from google.cloud import videointelligence_v1 as vi
from google.oauth2 import service_account
from app.services.core.logging_service import audit_logger
from app.services.i18n.translation_service import traducir_etiquetas, traducir_contenido_explicito, traducir_logos
from app.services.moderation.text_detection_service import analizar_texto_en_video

# Configurar logging
logger = logging.getLogger(__name__)

_GOOGLE_CRED_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
USE_VERTEX_AI = os.getenv("USE_VERTEX_AI", "false").lower() in ("true", "1", "yes")

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

class TransientQuotaError(Exception):
    """Error transitorio (cuota / rate limit) para forzar retry vía Cloud Tasks."""
    pass

_video_client = None

def _client():
    global _video_client
    if _video_client is None:
        _video_client = _get_client()
    return _video_client

def analizar_video_completo(gcs_uri: str, timeout_sec: int = 600) -> Dict:
    """
    Analiza un video en GCS unificando Gemini (Vertex AI) y Video Intelligence.
    Retorna un dict consolidado con:
      - etiquetas, objetos, logos, texto, alertas visuales
      - puntaje_confianza, estado_visual, estado_texto, veredicto_ia
    """
    start_time = time.time()
    logger.info(f"[AI] Iniciando análisis combinado para: {gcs_uri}")

    use_vertex = os.getenv("USE_VERTEX_AI", "false").lower() in ("true", "1", "yes")

    # === BLOQUE 1: Inicialización de variables ===
    gemini_resultado = {}
    objetos_gemini: List[Dict] = []
    texto_gemini: str = ""
    alertas_gemini: List[str] = []
    evidencia_gemini: List[Dict] = []

    alertas_visual: List[str] = []
    alertas_set = set()  # SIEMPRE definido (evita NameError cuando use_vertex=false)

    # === BLOQUE 2: Análisis con Gemini (Vertex AI) ===
    if use_vertex:
        try:
            from app.services.gcp.vertex_ai_video_service import analizar_video_gemini
            import json, re
            logger.info("[GEMINI] Ejecutando análisis Vertex AI...")
            gemini_resultado = analizar_video_gemini(gcs_uri)
            raw = gemini_resultado.get("raw_text", "")
            if raw:
                clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
                try:
                    gemini_resultado = json.loads(clean)
                except Exception:
                    logger.warning("[GEMINI] No se pudo parsear JSON limpio; se usará el dict original si trae campos.")

            objetos_gemini = gemini_resultado.get("objetos_detectados", []) or []
            evidencia_gemini = gemini_resultado.get("evidencia", []) or []

            texto_val = gemini_resultado.get("texto_detectado", [])
            if isinstance(texto_val, list):
                texto_gemini = ", ".join([str(x) for x in texto_val if str(x).strip()])
            else:
                texto_gemini = str(texto_val or "").strip()

            alertas_gemini = gemini_resultado.get("alertas", []) or []

            # Normalizar alertas Gemini (SIN conducta_obscena: todo va a gesto_obsceno)
            for a in alertas_gemini:
                x = str(a).strip().lower().replace(" ", "_")
                if x in ("arma", "arma_de_fuego", "pistola", "gun", "firearm", "weapon_firearm"):
                    alertas_set.add("arma_fuego")
                elif x in ("arma_blanca", "cuchillo", "knife", "blade", "navaja", "machete", "weapon_knife"):
                    alertas_set.add("arma_blanca")
                elif x in ("gesto_obsceno", "dedo_medio", "middle_finger", "fuck_you"):
                    alertas_set.add("gesto_obsceno")
                elif x in ("violencia", "sangre", "blood", "violence", "fight", "aggression"):
                    alertas_set.add("violencia")
                elif x in ("amenaza", "threat", "intimidacion", "intimidation", "neck_cut", "slit_throat"):
                    alertas_set.add("amenaza")

            # Normalizar evidencia Gemini (SIN conducta_obscena: todo va a gesto_obsceno)
            for ev in evidencia_gemini:
                try:
                    t = str(ev.get("tipo", "")).strip().lower().replace(" ", "_")
                    if t in ("arma", "arma_de_fuego", "pistola", "gun", "firearm"):
                        ev["tipo"] = "arma_fuego"
                    elif t in ("arma_blanca", "cuchillo", "knife", "blade", "navaja", "machete"):
                        ev["tipo"] = "arma_blanca"
                    elif t in ("gesto_obsceno", "dedo_medio", "middle_finger", "fuck_you"):
                        ev["tipo"] = "gesto_obsceno"
                    elif t in ("conducta_obscena", "genital_grab", "sexual_gesture"):
                        ev["tipo"] = "gesto_obsceno"
                    elif t in ("violencia", "blood", "fight", "aggression"):
                        ev["tipo"] = "violencia"
                    elif t in ("amenaza", "threat", "intimidation", "neck_cut", "slit_throat"):
                        ev["tipo"] = "amenaza"
                except Exception:
                    continue

                hay_cuchillo = any(
                    any(k in str(o.get("notas", "")).lower() for k in ("cuchillo", "knife", "blade", "cubierto", "cutlery", "utensil", "table knife", "butter knife", "steak knife"))
                    for o in (objetos_gemini or [])
                ) or any(
                    any(k in str(ev.get("descripcion", "")).lower() for k in ("cuchillo", "knife", "blade", "cubierto", "cutlery", "utensil", "table knife", "cuello", "degoll", "corte", "slit", "throat", "neck"))
                    for ev in (evidencia_gemini or [])
                )

                if hay_cuchillo:
                    alertas_set.add("arma_blanca")

            logger.info(
                f"[GEMINI] {len(objetos_gemini)} objetos | alertas={sorted(alertas_set)} | evidencia={len(evidencia_gemini)}"
            )

        except Exception as e:
            logger.warning(f"[GEMINI] Error: {e}. Continuando con Video Intelligence.")
            gemini_resultado = {}
            objetos_gemini = []
            texto_gemini = ""
            evidencia_gemini = []
            alertas_set = set()

    # === BLOQUE 3: Análisis con Video Intelligence ===
    try:
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

        etiquetas_en = _procesar_etiquetas(annotation_result)
        contenido_explicito_en = _procesar_contenido_explicito(annotation_result)
        logotipos_obj_en = _procesar_logotipos(annotation_result)
        logotipos_en = ", ".join([item["logo"] for item in logotipos_obj_en])
        objetos_detectados_vi = _procesar_objetos(annotation_result)
        logger.info(f"[VI] Objetos detectados: {len(objetos_detectados_vi)}")

    except Exception as e:
        msg = str(e)

        # Clasificar cuota/rate-limit como transitorio (para retry)
        if (
            "429" in msg
            or "RATE_LIMIT_EXCEEDED" in msg
            or "RESOURCE_EXHAUSTED" in msg
            or "Quota exceeded" in msg
            or "quota" in msg.lower()
        ):
            logger.error(f"[VI] Quota/rate-limit (transitorio): {e}")
            raise TransientQuotaError(msg) from e
        
        logger.error(f"[VI] Error analizando video con Video Intelligence: {e}")
        raise

    # === BLOQUE 4: Fusionar Gemini + VideoIntelligence ===
    objetos_detectados = objetos_detectados_vi or []
    if objetos_gemini:
        objetos_detectados.extend(objetos_gemini)

    # Inyectar "objetos" sintéticos desde alertas Gemini (SIN conducta obscena)
    if "gesto_obsceno" in alertas_set:
        conf = 0.35
        for ev in (evidencia_gemini or []):
            if str(ev.get("tipo","")).lower() == "gesto_obsceno":
                try:
                    conf = float(ev.get("confianza", conf) or conf)
                except Exception:
                    pass
        objetos_detectados.append({
            "label": "gesto obsceno",
            "label_original": "gemini",
            "es_arma": False,
            "tipo_arma": "",
            "confianza": round(conf, 2)
        })

    if "amenaza" in alertas_set:
        objetos_detectados.append({
            "label": "amenaza",
            "label_original": "gemini",
            "es_arma": False,
            "tipo_arma": "",
            "confianza": 0.9
        })

    if "arma_blanca" in alertas_set:
        objetos_detectados.append({
        "label": "arma blanca",
        "label_original": "gemini",
        "es_arma": True,
        "tipo_arma": "blanca",
        "confianza": 0.9
    })


    if "violencia" in alertas_set:
        objetos_detectados.append({
        "label": "violencia",
        "label_original": "gemini",
        "es_arma": False,
        "tipo_arma": "",
        "confianza": 0.9
    })
        

    # Alertas visuales desde objetos (VI/Gemini) por keywords
    for obj in objetos_detectados:
        label = str(obj.get("label", "")).lower()
        if any(k in label for k in ("arma", "cuchillo", "pistola", "knife", "blade", "cutlery", "utensil", "kitchen knife")):
            alertas_visual.append(label)

    # Alertas normalizadas de Gemini con prioridad
    for a in alertas_set:
        if a not in alertas_visual:
            alertas_visual.append(a)

    logger.info(f"[MERGE] Total objetos fusionados={len(objetos_detectados)} | alertas_visual={alertas_visual}")

    # === BLOQUE 5: Traducciones ===
    try:
        etiquetas_es = traducir_etiquetas(etiquetas_en, "es")
        contenido_explicito_es = traducir_contenido_explicito(contenido_explicito_en, "es")
        logotipos_es = traducir_logos(logotipos_en, "es")
    except Exception as e:
        logger.warning(f"[TRAD] Error traduciendo: {e}")
        etiquetas_es, contenido_explicito_es, logotipos_es = etiquetas_en, contenido_explicito_en, logotipos_en

    # === BLOQUE 6: OCR / texto en video ===
    try:
        resultados_texto = analizar_texto_en_video(gcs_uri, video_id=None)
    except Exception as e:
        logger.warning(f"[OCR] Error en detección de texto: {e}")
        resultados_texto = {
            "texto_detectado": "",
            "palabras_problematicas": "",
            "nivel_problema": "error",
            "frames_analizados": 0,
        }

    texto_final = resultados_texto.get("texto_detectado", "") or ""
    if texto_gemini:
        texto_final = f"{texto_final}, {texto_gemini}".strip(", ")

    palabras_problematicas = resultados_texto.get("palabras_problematicas", "") or ""
    nivel_problema = resultados_texto.get("nivel_problema", "bajo") or "bajo"

    # === BLOQUE 7: Calcular puntaje de seguridad ===
    from app.services.gcp.video_ai_service import _calcular_puntaje_confianza
    puntaje = _calcular_puntaje_confianza(annotation_result, objetos_detectados, alertas_visual)

    if alertas_visual:
        puntaje = max(0.0, puntaje * 0.7)
        logger.warning(f"[CONF] Penalización adicional por alertas visuales: {alertas_visual}")

    # === BLOQUE 8: Estados y veredicto IA (solo lo necesario) ===
    estado_visual, estado_texto, veredicto_ia = "Seguro", "Limpio", "Seguro"

    # Hard rule por evidencia de amenaza “corte al cuello”
    hard_rule = None
    for ev in (evidencia_gemini or []):
        ev_tipo = str(ev.get("tipo", "")).strip().lower()
        ev_desc = str(ev.get("descripcion", "")).lower()
        ev_conf = float(ev.get("confianza", 0.0) or 0.0)
        if ev_tipo == "amenaza" and any(k in ev_desc for k in ("cuello", "degoll", "corte", "slit", "throat", "neck")) and ev_conf >= 0.35:
            hard_rule = ("THREAT_NECK_CUT", ev_conf, ev_desc)
            estado_visual, veredicto_ia = "Amenazante", "Amenazante"
            break

    # Fallback por alertas
    if not hard_rule:
        if "arma_fuego" in alertas_set or "amenaza" in alertas_set:
            estado_visual, veredicto_ia = "Amenazante", "Amenazante"
        elif {"arma_blanca", "violencia", "gesto_obsceno"} & alertas_set:
            estado_visual, veredicto_ia = "Riesgoso", "Riesgoso"
        elif puntaje < 0.6 or alertas_visual:
            estado_visual, veredicto_ia = "Riesgoso", "Riesgoso"

    # Estado texto
    if nivel_problema in ("alto", "error"):
        estado_texto = "Crítico"
    elif nivel_problema == "medio":
        estado_texto = "Advertencia"

    # Mezcla texto->veredicto
    if estado_texto in ("Crítico", "Advertencia") and veredicto_ia != "Amenazante":
        veredicto_ia = "Riesgoso"
        if estado_visual == "Seguro":
            estado_visual = "Riesgoso"

    if "arma" in palabras_problematicas.lower():
        veredicto_ia = "Amenazante"
        estado_visual = "Amenazante"

    # === BLOQUE 9: Construcción de respuesta final ===
    tiempo_total = time.time() - start_time

    datos_procesados = {
        "etiquetas": etiquetas_es,
        "contenido_explicito": contenido_explicito_es,
        "logotipos": logotipos_es,
        "objetos_detectados": objetos_detectados,
        "alertas_visual": list(set(alertas_visual)),
        "puntaje_confianza": round(puntaje, 3),
        "estado_visual": estado_visual,
        "estado_texto": estado_texto,
        "veredicto_ia": veredicto_ia,
        "tiempo_procesamiento": round(tiempo_total, 2),
        "texto_detectado": texto_final,
        "palabras_problematicas": palabras_problematicas,
        "nivel_problema_texto": nivel_problema,
        "frames_texto_analizados": resultados_texto.get("frames_analizados", 0),
        "fuente_analisis": "Gemini + VideoIntelligence" if use_vertex else "VideoIntelligence",
        "alertas_gemini_normalizadas": sorted(list(alertas_set)),
        "evidencia_gemini": evidencia_gemini,
        "etiquetas_original": etiquetas_en,
        "contenido_explicito_original": contenido_explicito_en,
        "logotipos_original": logotipos_en,
    }

    logger.info(
        f"[PIPELINE] Finalizado en {tiempo_total:.2f}s | Visual={estado_visual} | Texto={estado_texto} "
        f"| Veredicto={veredicto_ia} | Puntaje={puntaje:.2f}"
    )
    return datos_procesados

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

def _calcular_puntaje_confianza(annotation_result, objetos_detectados: List[Dict] = None, alertas_visual: List[str] = None) -> float:
    """
    Calcula un puntaje general de seguridad visual.
    - Promedia confianzas de etiquetas, frames y logos.
    - Aplica penalizaciones según detecciones reales de IA (objetos o alertas visuales).
    Retorna valor entre 0.0 y 1.0
    """
    try:
        confianzas = []

        # === 1. Confianza base (Video Intelligence) ===
        for label in annotation_result.segment_label_annotations:
            for segment in label.segments:
                confianzas.append(segment.confidence)
        for label in annotation_result.frame_label_annotations:
            for frame in label.frames:
                confianzas.append(frame.confidence)
        for logo_annotation in annotation_result.logo_recognition_annotations:
            for track in logo_annotation.tracks:
                for timestamped_object in track.timestamped_objects:
                    for attribute in timestamped_object.attributes:
                        if attribute.name == "logo_confidence":
                            confianzas.append(attribute.confidence)

        puntaje_base = sum(confianzas) / len(confianzas) if confianzas else 0.75  # valor por defecto medio
        penalty = 0.0

        # === 2. Penalizaciones dinámicas ===
        # 2.1 Objetos detectados (de Gemini o Video Intelligence)
        if objetos_detectados:
            for obj in objetos_detectados:
                label = str(obj.get("label", "")).lower()
                if "arma de fuego" in label or "pistola" in label or "revolver" in label:
                    penalty = max(penalty, 0.5)  # -50%
                    logger.warning(f"[CONF] Penalización por detección de arma de fuego: '{label}'")
                elif "arma blanca" in label or "cuchillo" in label or "navaja" in label:
                    penalty = max(penalty, 0.3)  # -30%
                    logger.warning(f"[CONF] Penalización por detección de arma blanca: '{label}'")
                elif "arma" in label:
                    penalty = max(penalty, 0.25)
                    logger.warning(f"[CONF] Penalización general por objeto tipo arma: '{label}'")

        # 2.2 Alertas visuales explícitas del análisis de Gemini
        if alertas_visual:
            for alerta in alertas_visual:
                alerta_lower = alerta.lower()
                if "arma" in alerta_lower:
                    penalty = max(penalty, 0.4)
                    logger.warning(f"[CONF] Penalización por alerta visual de IA: '{alerta_lower}'")
                elif "sangre" in alerta_lower or "violencia" in alerta_lower:
                    penalty = max(penalty, 0.35)
                elif "amenaza" in alerta_lower:
                    penalty = max(penalty, 0.3)

        # === 3. Puntaje final ===
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
            "x-acto","scalpel","screwdriver","shank","shiv","table knife", "butter knife", "steak knife", "tableware", "kitchen utensil"
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
