# app/services/video_duration_service.py
import os
import tempfile
import logging
from typing import Optional
from app.services.core.logging_service import audit_logger

logger = logging.getLogger(__name__)

def obtener_duracion_video(file_obj) -> float:
    """
    Obtiene la duración del video en segundos usando moviepy.
    
    Args:
        file_obj: Objeto archivo del video (FileStorage de Flask)
        
    Returns:
        float: Duración en segundos, 0.0 si hay error
    """
    logger.info("✅ === INICIO obtener_duracion_video ===")
    print(f"✅ Tipo de archivo recibido: {type(file_obj)}")
    
    filename = getattr(file_obj, 'filename', 'No disponible')
    print(f"✅ Nombre del archivo: {filename}")
    
    audit_logger.log_error(
        error_type="VIDEO_DURATION_START",
        message=f"Iniciando análisis de duración para archivo: {filename}",
        details={'filename': filename, 'file_type': str(type(file_obj))}
    )
    
    temp_file_path = None
    
    try:
        # Crear archivo temporal
        print("✅ Creando archivo temporal...")
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
            temp_file_path = temp_file.name
            print(f"✅ Archivo temporal creado en: {temp_file_path}")
            
            # Resetear el stream al inicio
            if hasattr(file_obj, 'stream'):
                print("✅ El archivo tiene atributo 'stream'")
                file_obj.stream.seek(0)
                data = file_obj.stream.read()
                print(f"✅ Bytes leídos del stream: {len(data)}")
                temp_file.write(data)
                file_obj.stream.seek(0)  # Resetear para otros usos posteriores
                print("✅ Stream reseteado correctamente")
            else:
                print("✅ El archivo NO tiene atributo 'stream', usando seek directo")
                file_obj.seek(0)
                data = file_obj.read()
                print(f"✅ Bytes leídos directamente: {len(data)}")
                temp_file.write(data)
                file_obj.seek(0)  # Resetear para otros usos posteriores
                print("✅ Archivo reseteado correctamente")
        
        # Verificar que el archivo temporal tiene contenido
        temp_size = os.path.getsize(temp_file_path)
        print(f"✅ Tamaño del archivo temporal: {temp_size} bytes")
        
        if temp_size == 0:
            print("❌ El archivo temporal está vacío!")
            audit_logger.log_error(
                error_type="VIDEO_DURATION_EMPTY_FILE",
                message=f"El archivo temporal está vacío para: {filename}",
                details={'temp_file_path': temp_file_path, 'temp_size': temp_size}
            )
            return 0.0
        
        # Usar moviepy para obtener duración
        try:
            print("✅ Intentando importar MoviePy...")
            from moviepy.editor import VideoFileClip
            print("✅ MoviePy importado correctamente")
            
            print(f"✅ Abriendo video con VideoFileClip: {temp_file_path}")
            with VideoFileClip(temp_file_path) as video_clip:
                duracion = video_clip.duration
                print(f"✅ Duración obtenida de MoviePy: {duracion}")
                
            if duracion is not None:
                resultado = float(duracion)
                print(f"✅ === FIN obtener_duracion_video: {resultado} segundos ===")
                
                # Log duración exitosa
                audit_logger.log_error(
                    error_type="VIDEO_DURATION_SUCCESS",
                    message=f"Duración obtenida exitosamente: {resultado} segundos",
                    details={
                        'filename': filename,
                        'duracion_segundos': resultado,
                        'temp_file_size': temp_size
                    }
                )
                
                return resultado
            else:
                print("⚠️ MoviePy retornó duración None")
                audit_logger.log_error(
                    error_type="VIDEO_DURATION_NULL",
                    message=f"MoviePy retornó duración None para: {filename}",
                    details={'filename': filename, 'temp_file_size': temp_size}
                )
                return 0.0
            
        except ImportError as e:
            print(f"❌ MoviePy no está instalado: {e}")
            audit_logger.log_error(
                error_type="VIDEO_DURATION_MOVIEPY_NOT_INSTALLED",
                message=f"MoviePy no está instalado: {str(e)}",
                details={'filename': filename}
            )
            return 0.0
        except Exception as e:
            print(f"❌ Error usando moviepy para obtener duración: {e}")
            print(f"❌ Tipo de error: {type(e)}")
            audit_logger.log_error(
                error_type="VIDEO_DURATION_MOVIEPY_ERROR",
                message=f"Error usando MoviePy para obtener duración: {str(e)}",
                details={
                    'filename': filename,
                    'error_type': str(type(e)),
                    'temp_file_path': temp_file_path,
                    'temp_file_size': temp_size
                }
            )
            return 0.0
            
    except Exception as e:
        print(f"❌ Error creando archivo temporal para obtener duración: {e}")
        print(f"❌ Tipo de error: {type(e)}")
        audit_logger.log_error(
            error_type="VIDEO_DURATION_TEMP_FILE_ERROR",
            message=f"Error creando archivo temporal para obtener duración: {str(e)}",
            details={
                'filename': filename,
                'error_type': str(type(e)),
                'temp_file_path': temp_file_path
            }
        )
        return 0.0
        
    finally:
        # Limpiar archivo temporal
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                print(f"🗑️ Archivo temporal eliminado: {temp_file_path}")
            except Exception as e:
                print(f"⚠️ No se pudo eliminar archivo temporal {temp_file_path}: {e}")
                audit_logger.log_error(
                    error_type="VIDEO_DURATION_CLEANUP_ERROR",
                    message=f"No se pudo eliminar archivo temporal: {str(e)}",
                    details={'temp_file_path': temp_file_path, 'filename': filename}
                )
        
        print("🎬 === FIN obtener_duracion_video ===")