from app.models.video import Video
from app import db
from app.services.video.video_processor import procesar_video_individual
import logging

logger = logging.getLogger(__name__)

def procesar_videos_pendientes_batch(limite=3):
    """
    Procesa videos en estado_ia = 'pendiente'
    """
    videos = Video.query.filter_by(estado_ia="pendiente") \
                        .order_by(Video.fecha_subida.asc()) \
                        .limit(limite).all()

    if not videos:
        return {"procesados": 0, "sin_pendientes": True}

    procesados = 0

    for video in videos:
        try:
            resultado = procesar_video_individual(video)

            if resultado.get("exitoso"):
                video.estado_ia = "completado"
            else:
                video.estado_ia = "error"

            db.session.commit()
            procesados += 1

        except Exception as e:
            logger.error(f"Error procesando video {video.id}: {e}")
            video.estado_ia = "error"
            db.session.commit()

    return {"procesados": procesados, "sin_pendientes": False}
