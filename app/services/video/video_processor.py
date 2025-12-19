# app/services/video_processor.py
import logging
import os
from typing import List, Optional
from app import db
from app.models.video import Video
from app.services.gcp.video_ai_service import analizar_video_completo
from app.services.core.logging_service import audit_logger

# Configurar logging
logger = logging.getLogger(__name__)

# Configuración desde variables de entorno
BUCKET_NAME = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "accessfan-video")
PROCESAMIENTO_HABILITADO = os.getenv("ENABLE_AI_PROCESSING", "true").lower() == "true"

def procesar_videos_pendientes(limite: int = 5) -> dict:
    """
    Procesa videos que están pendientes de análisis de IA.
    
    Args:
        limite (int): Número máximo de videos a procesar en esta ejecución
        
    Returns:
        dict: Estadísticas del procesamiento
    """
    if not PROCESAMIENTO_HABILITADO:
        logger.warning("❌ Procesamiento de IA deshabilitado en configuración")
        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_DISABLED",
            message="Procesamiento de IA deshabilitado en configuración"
        )
        return {"error": "Procesamiento deshabilitado"}
    
    logger.info(f"🔍 Buscando videos pendientes de análisis IA (límite: {limite})")
    audit_logger.log_error(
        error_type="VIDEO_PROCESSOR_BATCH_START",
        message=f"Iniciando procesamiento por lotes (límite: {limite})",
        details={'limite': limite}
    )
    
    # Buscar videos pendientes
    videos_pendientes = Video.obtener_por_estado_ia('pendiente')[:limite]
    
    if not videos_pendientes:
        logger.info("✅ No hay videos pendientes de análisis")
        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_NO_PENDING",
            message="No hay videos pendientes de análisis"
        )
        return {
            "procesados": 0,
            "exitosos": 0,
            "errores": 0,
            "mensaje": "No hay videos pendientes"
        }
    
    logger.info(f"Encontrados {len(videos_pendientes)} videos pendientes")
    audit_logger.log_error(
        error_type="VIDEO_PROCESSOR_FOUND_PENDING",
        message=f"Encontrados {len(videos_pendientes)} videos pendientes",
        details={'videos_encontrados': len(videos_pendientes)}
    )
    
    # Estadísticas de procesamiento
    stats = {
        "procesados": 0,
        "exitosos": 0,
        "errores": 0,
        "videos_procesados": []
    }
    
    for video in videos_pendientes:
        try:
            resultado = procesar_video_individual(video)
            stats["procesados"] += 1
            
            if resultado["exitoso"]:
                stats["exitosos"] += 1
                stats["videos_procesados"].append({
                    "id": video.id,
                    "nombre": video.nombre_archivo,
                    "estado": "completado",
                    "tiempo": resultado.get("tiempo", 0)
                })
            else:
                stats["errores"] += 1
                stats["videos_procesados"].append({
                    "id": video.id,
                    "nombre": video.nombre_archivo,
                    "estado": "error",
                    "error": resultado.get("error", "Error desconocido")
                })
                
        except Exception as e:
            logger.error(f"❌ Error procesando video {video.id}: {e}")
            audit_logger.log_error(
                error_type="VIDEO_PROCESSOR_INDIVIDUAL_ERROR",
                message=f"Error procesando video {video.id}: {str(e)}",
                video_id=video.id,
                details={'nombre_archivo': video.nombre_archivo}
            )
            stats["procesados"] += 1
            stats["errores"] += 1
            stats["videos_procesados"].append({
                "id": video.id,
                "nombre": video.nombre_archivo,
                "estado": "error",
                "error": str(e)
            })
    
    logger.info(f"Procesamiento completado: {stats['exitosos']} exitosos, {stats['errores']} errores")
    audit_logger.log_error(
        error_type="VIDEO_PROCESSOR_BATCH_COMPLETE",
        message=f"Procesamiento por lotes completado: {stats['exitosos']} exitosos, {stats['errores']} errores",
        details=stats
    )
    
    return stats

def procesar_video_individual(video: Video) -> dict:
    """
    Procesa un video individual con IA y guarda los resultados en la base de datos.
    Conserva la clasificación visual real (explícito / posible / seguro) y agrega la fuente de IA.
    """
    logger.info(f"Procesando video ID {video.id}: {video.nombre_archivo}")
    audit_logger.log_error(
        error_type="VIDEO_PROCESSOR_INDIVIDUAL_START",
        message=f"Iniciando procesamiento individual de video {video.id}",
        video_id=video.id,
        user_id=video.usuario_id,
        details={'nombre_archivo': video.nombre_archivo}
    )

    try:
        # --- Validación ---
        if not video.gcs_object_name:
            audit_logger.log_error(
                error_type="VIDEO_PROCESSOR_MISSING_GCS",
                message=f"Video {video.id} no tiene gcs_object_name",
                video_id=video.id,
                user_id=video.usuario_id
            )
            raise ValueError("Video no tiene gcs_object_name")

        # --- Construcción de URI GCS ---
        gcs_uri = f"gs://{BUCKET_NAME}/{video.gcs_object_name}"
        logger.debug(f"URI GCS: {gcs_uri}")

        # --- Marcar video como procesando ---
        video.actualizar_estado_ia('procesando')
        db.session.commit()
        logger.info(f"Video {video.id} marcado como 'procesando'")

        # --- Análisis IA ---
        logger.info(f"Iniciando análisis de IA para video {video.id}")
        datos_ia = analizar_video_completo(gcs_uri, timeout_sec=600)

        # ✅ Asegurar que se conserva la clasificación visual real
        if datos_ia.get("contenido_explicito") in (None, "", "No analizado"):
            datos_ia["contenido_explicito"] = datos_ia.get("contenido_explicito_original", "No analizado")

        # ✅ Registrar fuente del análisis sin sobrescribir el campo real
        datos_ia["fuente_analisis"] = "Gemini + VideoIntelligence"

        # --- Guardar en BD ---
        video.actualizar_estado_ia('completado', datos_ia)
        db.session.commit()

        # --- Logs ---
        logger.info(f"✅ Video {video.id} procesado exitosamente")
        logger.info(f"   - Etiquetas: {len(datos_ia['etiquetas'].split(',')) if datos_ia.get('etiquetas') else 0}")
        logger.info(f"   - Contenido explícito: {datos_ia.get('contenido_explicito')}")
        logger.info(f"   - Fuente IA: {datos_ia.get('fuente_analisis')}")
        logger.info(f"   - Confianza: {datos_ia.get('puntaje_confianza')}")
        logger.info(f"   - Tiempo: {datos_ia.get('tiempo_procesamiento')}s")

        # --- Auditar éxito ---
        audit_logger.log_ia_analysis(
            video_id=video.id,
            estado_ia='completado',
            resultado=datos_ia,
            tiempo_procesamiento=datos_ia.get('tiempo_procesamiento', 0)
        )

        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_INDIVIDUAL_SUCCESS",
            message=f"Video {video.id} procesado exitosamente",
            video_id=video.id,
            user_id=video.usuario_id,
            details={
                'nombre_archivo': video.nombre_archivo,
                'tiempo_procesamiento': datos_ia.get('tiempo_procesamiento', 0),
                'contenido_explicito': datos_ia.get('contenido_explicito'),
                'fuente_analisis': datos_ia.get('fuente_analisis'),
                'etiquetas_count': len(datos_ia['etiquetas'].split(',')) if datos_ia.get('etiquetas') else 0,
                'puntaje_confianza': datos_ia.get('puntaje_confianza', 0)
            }
        )

        return {
            "exitoso": True,
            "tiempo": datos_ia.get('tiempo_procesamiento', 0),
            "datos": datos_ia
        }

    except Exception as e:
        logger.error(f"❌ Error procesando video {video.id}: {e}")

        audit_logger.log_ia_analysis(
            video_id=video.id,
            estado_ia='error',
            resultado={'error_message': str(e)},
            tiempo_procesamiento=0
        )

        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_INDIVIDUAL_ERROR",
            message=f"Error procesando video {video.id}: {str(e)}",
            video_id=video.id,
            user_id=video.usuario_id,
            details={'nombre_archivo': video.nombre_archivo}
        )

        try:
            video.actualizar_estado_ia('error')
            video.razon_rechazo = f"Error análisis IA: {str(e)}"
            db.session.commit()
        except Exception as db_error:
            logger.error(f"Error adicional actualizando BD: {db_error}")
            audit_logger.log_error(
                error_type="VIDEO_PROCESSOR_DB_ERROR",
                message=f"Error adicional actualizando BD para video {video.id}: {str(db_error)}",
                video_id=video.id
            )
            db.session.rollback()

        return {"exitoso": False, "error": str(e)}

def reprocesar_video(video_id: int) -> dict:
    """
    Fuerza el reprocesamiento de un video específico.
    
    Args:
        video_id (int): ID del video a reprocesar
        
    Returns:
        dict: Resultado del reprocesamiento
    """
    logger.info(f"Reprocesando video ID: {video_id}")
    audit_logger.log_error(
        error_type="VIDEO_PROCESSOR_REPROCESS_START",
        message=f"Iniciando reprocesamiento de video {video_id}",
        video_id=video_id
    )
    
    video = Video.query.get(video_id)
    if not video:
        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_REPROCESS_NOT_FOUND",
            message=f"Video {video_id} no encontrado para reprocesamiento",
            video_id=video_id
        )
        return {"exitoso": False, "error": "Video no encontrado"}
    
    # Resetear estado IA a pendiente
    video.estado_ia = 'pendiente'
    video.fecha_procesamiento = None
    video.etiquetas = None
    video.logotipos = None
    video.contenido_explicito = 'No analizado'
    video.puntaje_confianza = 0.0
    video.tiempo_procesamiento = 0.0
    
    try:
        db.session.commit()
        logger.info(f"Video {video_id} reseteado para reprocesamiento")
        
        # Procesar inmediatamente
        return procesar_video_individual(video)
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error reseteando video para reprocesamiento: {e}")
        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_REPROCESS_ERROR",
            message=f"Error reseteando video {video_id} para reprocesamiento: {str(e)}",
            video_id=video_id
        )
        return {"exitoso": False, "error": str(e)}

def obtener_estadisticas_procesamiento() -> dict:
    """
    Obtiene estadísticas generales del procesamiento de IA.
    
    Returns:
        dict: Estadísticas de videos por estado IA
    """
    try:
        stats = {
            "pendientes": Video.query.filter_by(estado_ia='pendiente').count(),
            "procesando": Video.query.filter_by(estado_ia='procesando').count(),
            "completados": Video.query.filter_by(estado_ia='completado').count(),
            "errores": Video.query.filter_by(estado_ia='error').count(),
            "total": Video.query.count()
        }
        
        # Calcular porcentajes
        total = stats["total"]
        if total > 0:
            stats["porcentaje_completado"] = round((stats["completados"] / total) * 100, 1)
            stats["porcentaje_error"] = round((stats["errores"] / total) * 100, 1)
        else:
            stats["porcentaje_completado"] = 0
            stats["porcentaje_error"] = 0
        
        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_STATS_GENERATED",
            message="Estadísticas de procesamiento generadas",
            details=stats
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_STATS_ERROR",
            message=f"Error obteniendo estadísticas de procesamiento: {str(e)}"
        )
        return {"error": str(e)}

def limpiar_videos_colgados() -> dict:
    """
    Encuentra y resetea videos que quedaron en estado 'procesando' por mucho tiempo.
    Útil para limpiar procesos que fallaron sin actualizar el estado.
    
    Returns:
        dict: Resultado de la limpieza
    """
    from datetime import datetime, timedelta
    
    # Buscar videos en 'procesando' por más de 2 horas
    tiempo_limite = datetime.utcnow() - timedelta(hours=2)
    
    try:
        videos_colgados = Video.query.filter(
            Video.estado_ia == 'procesando',
            Video.fecha_subida < tiempo_limite  # Usar fecha_subida como referencia
        ).all()
        
        if not videos_colgados:
            logger.info("No hay videos colgados en procesamiento")
            audit_logger.log_error(
                error_type="VIDEO_PROCESSOR_CLEANUP_NONE",
                message="No hay videos colgados en procesamiento"
            )
            return {"limpiados": 0, "mensaje": "No hay videos colgados"}
        
        # Resetear videos colgados
        for video in videos_colgados:
            video.estado_ia = 'pendiente'
            video.razon_rechazo = "Reiniciado - proceso anterior incompleto"
        
        db.session.commit()
        
        logger.info(f"Se limpiaron {len(videos_colgados)} videos colgados")
        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_CLEANUP_SUCCESS",
            message=f"Se limpiaron {len(videos_colgados)} videos colgados",
            details={
                'videos_limpiados': len(videos_colgados),
                'video_ids': [v.id for v in videos_colgados]
            }
        )
        
        return {
            "limpiados": len(videos_colgados),
            "videos": [v.id for v in videos_colgados]
        }
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error limpiando videos colgados: {e}")
        audit_logger.log_error(
            error_type="VIDEO_PROCESSOR_CLEANUP_ERROR",
            message=f"Error limpiando videos colgados: {str(e)}"
        )
        return {"error": str(e)}