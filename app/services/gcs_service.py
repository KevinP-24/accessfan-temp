import os
import mimetypes
from datetime import timedelta, datetime
from google.cloud import storage
from google.oauth2 import service_account
import json
from app.services.logging_service import audit_logger
import logging
logger = logging.getLogger(__name__)

# Lee config desde variables de entorno (centralizado en .env)
BUCKET_NAME = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "accessfan-video")
GOOGLE_CRED_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # opcional en local

def _get_storage_client():
    """
    Crea el cliente de GCS. Si hay ruta de credenciales (local), la usa.
    En Cloud Run, bastan las credenciales por defecto de la Service Account.
    """
    try:
        if GOOGLE_CRED_PATH and os.path.isfile(GOOGLE_CRED_PATH):
            creds = service_account.Credentials.from_service_account_file(GOOGLE_CRED_PATH)
            return storage.Client(credentials=creds)
        return storage.Client()  # Usar credenciales predeterminadas en Cloud Run
    except Exception as e:
        audit_logger.log_error(
            error_type="GCS_CLIENT_ERROR",
            message=f"Error creando cliente de GCS: {str(e)}"
        )
        raise

def _get_bucket():
    if not BUCKET_NAME:
        audit_logger.log_error(
            error_type="GCS_CONFIG_ERROR",
            message="Falta configurar GOOGLE_CLOUD_STORAGE_BUCKET"
        )
        raise RuntimeError("Falta configurar GOOGLE_CLOUD_STORAGE_BUCKET")
    
    try:
        client = _get_storage_client()
        return client.bucket(BUCKET_NAME)
    except Exception as e:
        audit_logger.log_error(
            error_type="GCS_BUCKET_ERROR",
            message=f"Error accediendo al bucket {BUCKET_NAME}: {str(e)}"
        )
        raise

def _guess_content_type(name: str) -> str:
    """
    Adivina el tipo de contenido (Content-Type) del archivo.
    """
    return mimetypes.guess_type(name)[0] or "application/octet-stream"

def obtener_url_logo(nombre_archivo="esc-csir.png"):
    """
    Obtiene la URL del logo desde la carpeta assets/, con fallbacks si no se puede firmar.
    """
    try:
        bucket = _get_bucket()
        blob = bucket.blob(f"assets/{nombre_archivo}")

        # Verificar existencia
        try:
            if not blob.exists():
                audit_logger.log_error(
                    error_type="LOGO_NOT_FOUND",
                    message=f"El logo {nombre_archivo} no existe en assets/"
                )
                try:
                    blob.reload()
                    if not blob.exists():
                        return None
                except:
                    return None
        except Exception as e:
            audit_logger.log_error(
                error_type="LOGO_EXISTS_CHECK_WARNING",
                message=f"No se pudo verificar existencia de logo: {str(e)}"
            )

        # Si público
        if (os.environ.get("GCS_PUBLIC", "false")).lower() == "true":
            try:
                blob.make_public()
            except Exception as e:
                audit_logger.log_error(
                    error_type="LOGO_PUBLIC_WARNING",
                    message=f"No se pudo hacer público el logo: {str(e)}"
                )
            return blob.public_url

        # Intentar firmar
        try:
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=24),
                method="GET"
            )
        except Exception as e:
            # Fallbacks
            audit_logger.log_error(
                error_type="LOGO_SIGNED_URL_FALLBACK",
                message="Fallo firmar URL de logo, usando fallback",
                details={'error': str(e), 'logo': nombre_archivo}
            )
            try:
                return blob.public_url
            except Exception:
                return f"gs://{BUCKET_NAME}/assets/{nombre_archivo}"

    except Exception as e:
        audit_logger.log_error(
            error_type="LOGO_ACCESS_ERROR",
            message=f"Error al obtener URL del logo {nombre_archivo}: {str(e)}"
        )
        return None

def subir_a_gcs(file_obj, filename, socio=None, descripcion=None):
    """
    Sube un archivo a GCS con solo la fecha como metadata.
    Retorna: (object_name, url, file_size)

    Robustecida: si no se puede firmar URL, hace fallback a public_url o gs://.
    """
    try:
        logger.info(f"[UPLOAD] Iniciando subida de archivo: {filename}")

        bucket = _get_bucket()
        blob = bucket.blob(filename)

        # Determinar el tipo de contenido
        content_type = getattr(file_obj, "content_type", None) or _guess_content_type(filename)
        logger.info(f"[UPLOAD] Content-Type detectado para '{filename}': {content_type}")

        # Asegura que el puntero del stream esté al inicio si existe
        stream = getattr(file_obj, "stream", file_obj)
        try:
            if hasattr(stream, "seek"):
                stream.seek(0)
                logger.debug(f"[UPLOAD] Stream reseteado al inicio para '{filename}'")
        except Exception as e:
            logger.warning(f"[UPLOAD] No se pudo resetear stream para '{filename}': {e}")

        # Tamaño del archivo antes de subir (best effort)
        file_size = 0
        if hasattr(file_obj, 'content_length') and file_obj.content_length:
            file_size = file_obj.content_length
            logger.info(f"[UPLOAD] Tamaño detectado desde content_length: {file_size} bytes")
        elif hasattr(stream, 'seek') and hasattr(stream, 'tell'):
            try:
                current_pos = stream.tell()
                stream.seek(0, 2)
                file_size = stream.tell()
                stream.seek(0)
                logger.info(f"[UPLOAD] Tamaño calculado manualmente: {file_size} bytes")
            except Exception as e:
                logger.warning(f"[UPLOAD] No se pudo calcular tamaño de '{filename}': {e}")
                audit_logger.log_error(
                    error_type="GCS_SIZE_CALC_WARNING",
                    message=f"No se pudo calcular el tamaño del archivo: {str(e)}"
                )

        # 1) Subir archivo
        try:
            logger.info(f"[UPLOAD] Subiendo '{filename}' al bucket {BUCKET_NAME} ...")
            blob.upload_from_file(stream, content_type=content_type)
            logger.info(f"[UPLOAD] Subida completada para '{filename}'")
        except Exception as e:
            logger.error(f"[UPLOAD] Error subiendo '{filename}': {e}", exc_info=True)
            audit_logger.log_error(
                error_type="GCS_UPLOAD_ERROR",
                message=f"No se pudo subir el archivo {filename}: {str(e)}"
            )
            raise

        # 2) Metadata mínima (solo fecha)
        fecha_actual = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            meta = {"fecha": fecha_actual}
            blob.metadata = meta
            blob.patch()
            logger.info(f"[UPLOAD] Metadata guardada en blob '{filename}': {meta}")
        except Exception as e:
            logger.warning(f"[UPLOAD] No se pudo guardar metadata en '{filename}': {e}")
            audit_logger.log_error(
                error_type="GCS_METADATA_WARNING",
                message=f"No se pudo guardar metadata en {filename}: {str(e)}"
            )

        # Log exitoso en auditoría
        audit_logger.log_error(
            error_type="GCS_UPLOAD_SUCCESS",
            message=f"Archivo subido exitosamente: {filename}",
            details={
                'filename': filename,
                'content_type': content_type,
                'file_size': file_size,
                'socio': socio,
                'bucket': BUCKET_NAME
            }
        )

        # 3) Política de URLs:
        gcs_public = (os.environ.get("GCS_PUBLIC", "false")).lower() == "true"
        if gcs_public:
            try:
                blob.make_public()
                logger.info(f"[UPLOAD] Blob '{filename}' hecho público. URL: {blob.public_url}")
                return blob.name, blob.public_url, file_size
            except Exception as e:
                logger.warning(f"[UPLOAD] No se pudo hacer público '{filename}': {e}")
                audit_logger.log_error(
                    error_type="GCS_PUBLIC_WARNING",
                    message=f"No se pudo hacer público el objeto: {str(e)}"
                )
                # sigue al intento de signed_url

        # b) Intentar firmar (preferido en entornos privados)
        try:
            signed_url = blob.generate_signed_url(
                expiration=timedelta(hours=24),
                method="GET"
            )
            logger.info(f"[UPLOAD] URL firmada generada para '{filename}': {signed_url}")
            return blob.name, signed_url, file_size
        except Exception as e:
            logger.error(f"[UPLOAD] Error generando signed_url para '{filename}': {e}", exc_info=True)
            audit_logger.log_error(
                error_type="GCS_SIGNED_URL_FALLBACK",
                message="Fallo firmar URL, usando fallback",
                details={'error': str(e), 'object': filename}
            )
            # Fallback 1: public_url
            try:
                public_url = blob.public_url
                if public_url:
                    logger.info(f"[UPLOAD] Usando public_url fallback para '{filename}': {public_url}")
                    return blob.name, public_url, file_size
            except Exception as e:
                logger.warning(f"[UPLOAD] Error obteniendo public_url fallback: {e}")
            # Fallback 2: gs://
            fallback = f"gs://{BUCKET_NAME}/{filename}"
            logger.warning(f"[UPLOAD] Usando gs:// fallback para '{filename}': {fallback}")
            return blob.name, fallback, file_size

    except Exception as e:
        logger.critical(f"[UPLOAD] Error fatal subiendo '{filename}': {e}", exc_info=True)
        audit_logger.log_error(
            error_type="GCS_UPLOAD_FATAL_ERROR",
            message=f"Error fatal subiendo archivo {filename}: {str(e)}"
        )
        raise

def obtener_url_firmada(filename, horas=1, method="GET"):
    """
    Genera una URL firmada v4 para el objeto 'filename' válido por 'horas' horas.
    """
    try:
        logger.info(f"[SIGNED_URL] Solicitud de URL firmada para '{filename}' "
                    f"(horas={horas}, method={method})")

        bucket = _get_bucket()
        blob = bucket.blob(filename)

        # Verificar existencia del blob antes de firmar
        if not blob.exists():
            logger.error(f"[SIGNED_URL] El objeto '{filename}' no existe en el bucket '{BUCKET_NAME}'")
        else:
            blob.reload()
            logger.info(f"[SIGNED_URL] Objeto '{filename}' encontrado. "
                        f"Content-Type={blob.content_type}, Metadata={blob.metadata}")

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=horas),
            method=method,
        )

        logger.info(f"[SIGNED_URL] URL firmada generada para '{filename}': {signed_url}")

        return signed_url

    except Exception as e:
        logger.error(f"[SIGNED_URL] Error generando URL firmada para '{filename}': {e}", exc_info=True)
        audit_logger.log_error(
            error_type="GCS_SIGNED_URL_ERROR",
            message=f"Error generando URL firmada para {filename}: {str(e)}"
        )
        raise

def _rehydrate_from_gcs(videos_list, id_counter, prefix="uploads/"):
    """
    Recupera los archivos desde GCS y los agrega a la lista videos_list.
    """
    try:
        logger.info(f"[REHYDRATE] Iniciando rehidratación de videos desde bucket '{BUCKET_NAME}', prefijo='{prefix}'")

        client = _get_storage_client()
        bucket = _get_bucket()

        blobs = bucket.list_blobs(prefix=prefix)
        count = 0

        for blob in blobs:
            count += 1
            logger.info(f"[REHYDRATE] Procesando blob {count}: '{blob.name}' "
                        f"(Content-Type={blob.content_type}, Size={blob.size})")

            # Determinar URL (public o firmada)
            url = blob.public_url
            if not url:
                try:
                    url = blob.generate_signed_url(expiration=timedelta(hours=24), method="GET")
                    logger.info(f"[REHYDRATE] Signed URL generada para '{blob.name}': {url}")
                except Exception as e:
                    logger.error(f"[REHYDRATE] No se pudo generar signed_url para '{blob.name}': {e}", exc_info=True)
                    url = None

            video = {
                "id": next(id_counter),
                "url": url,
                "socio": blob.metadata.get("socio", "Socio desconocido") if blob.metadata else "Socio desconocido",
                "fecha_subida": blob.metadata.get("fecha_subida", "Fecha desconocida") if blob.metadata else "Fecha desconocida",
                "descripcion": blob.metadata.get("descripcion", "Sin descripción proporcionada") if blob.metadata else "Sin descripción proporcionada",
                "estado": blob.metadata.get("estado", "sin-revisar") if blob.metadata else "sin-revisar",
                "duracion": "-",  # Duración no calculada aquí
                "explicito": "No",  # Placeholder hasta análisis IA
                "etiquetas": blob.metadata.get("etiquetas", "") if blob.metadata else "",
                "logotipos": blob.metadata.get("logotipos", "") if blob.metadata else "",
                "nombre_original": blob.metadata.get("nombre_original", "") if blob.metadata else "",
                "gcs_object": blob.name,
            }

            videos_list.append(video)
            logger.debug(f"[REHYDRATE] Video agregado: {video}")

        logger.info(f"[REHYDRATE] Total blobs procesados: {count}")

    except Exception as e:
        logger.error(f"[REHYDRATE] Error recuperando archivos desde GCS: {e}", exc_info=True)
        audit_logger.log_error(
            error_type="GCS_REHYDRATE_ERROR",
            message=f"Error recuperando archivos desde GCS: {str(e)}"
        )
        raise

def obtener_todos_los_videos(prefix="uploads/"):
    """
    Obtiene todos los videos del bucket de GCS y los retorna como lista.
    
    Returns:
        list: Lista de diccionarios con información de cada video (solo fecha)
    """
    videos_list = []
    id_counter = iter(range(1, 10000))  # Generador de IDs
    
    try:
        _rehydrate_from_gcs(videos_list, id_counter, prefix)
        
        audit_logger.log_error(
            error_type="GCS_VIDEO_LIST_SUCCESS",
            message=f"Se recuperaron {len(videos_list)} videos del bucket",
            details={'video_count': len(videos_list), 'prefix': prefix}
        )
        
        return videos_list
        
    except Exception as e:
        audit_logger.log_error(
            error_type="GCS_VIDEO_LIST_ERROR",
            message=f"Error al recuperar videos del bucket: {str(e)}"
        )
        return []

def obtener_video_por_nombre(nombre_archivo):
    """
    Obtiene un video específico por su nombre de archivo en GCS.
    
    Args:
        nombre_archivo (str): Nombre del archivo en GCS (ej: "uploads/video1.mp4")
    
    Returns:
        dict or None: Información del video (solo fecha) o None si no se encuentra
    """
    try:
        logger.info(f"[GET_VIDEO] Buscando video '{nombre_archivo}' en bucket '{BUCKET_NAME}'")

        bucket = _get_bucket()
        blob = bucket.blob(nombre_archivo)

        if not blob.exists():
            logger.error(f"[GET_VIDEO] El archivo '{nombre_archivo}' NO existe en el bucket '{BUCKET_NAME}'")
            audit_logger.log_error(
                error_type="GCS_VIDEO_NOT_FOUND",
                message=f"El archivo {nombre_archivo} no existe en el bucket"
            )
            return None

        # Recargar metadata del blob
        blob.reload()
        logger.info(f"[GET_VIDEO] Blob '{nombre_archivo}' encontrado. "
                    f"Content-Type={blob.content_type}, Metadata={blob.metadata}")

        # Intentar usar public_url primero, si no, firmar
        url = blob.public_url
        if not url:
            logger.info(f"[GET_VIDEO] public_url vacío para '{nombre_archivo}', generando signed_url…")
            url = blob.generate_signed_url(expiration=timedelta(hours=24), method="GET")

        logger.info(f"[GET_VIDEO] URL obtenida para '{nombre_archivo}': {url}")

        video = {
            "id": 1,  # En este caso usamos ID fijo ya que es un video específico
            "url": url,
            "fecha": blob.metadata.get("fecha", datetime.utcnow().strftime("%Y-%m-%d")) if blob.metadata else datetime.utcnow().strftime("%Y-%m-%d"),
            "gcs_object": blob.name,
        }

        return video

    except Exception as e:
        logger.error(f"[GET_VIDEO] Error al obtener '{nombre_archivo}': {e}", exc_info=True)
        audit_logger.log_error(
            error_type="GCS_GET_VIDEO_ERROR",
            message=f"Error al obtener el video {nombre_archivo}: {str(e)}"
        )
        return None

def obtener_videos_por_fecha(fecha=None, prefix="uploads/"):
    """
    Obtiene videos filtrados por fecha.
    
    Args:
        fecha (str, optional): Filtrar por fecha en formato YYYY-MM-DD
        prefix (str): Prefijo para buscar en GCS
    
    Returns:
        list: Lista de videos que cumplen el filtro de fecha
    """
    try:
        todos_los_videos = obtener_todos_los_videos(prefix)
        
        if fecha is None:
            return todos_los_videos
        
        videos_filtrados = []
        for video in todos_los_videos:
            if video.get("fecha") == fecha:
                videos_filtrados.append(video)
        
        audit_logger.log_error(
            error_type="GCS_VIDEO_FILTER_SUCCESS",
            message=f"Se encontraron {len(videos_filtrados)} videos para la fecha {fecha}",
            details={'fecha': fecha, 'total_encontrados': len(videos_filtrados)}
        )
        
        return videos_filtrados
        
    except Exception as e:
        audit_logger.log_error(
            error_type="GCS_VIDEO_FILTER_ERROR",
            message=f"Error filtrando videos por fecha {fecha}: {str(e)}"
        )
        return []