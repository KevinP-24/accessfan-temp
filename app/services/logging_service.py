import logging
import json
from datetime import datetime

class StructuredLogger:
    """
    Logger estructurado para auditoría y monitoreo.
    Funciona automáticamente con Cloud Logging en Cloud Run.
    """
    
    def __init__(self):
        # Usar el logger estándar de Python - Cloud Run lo envía automáticamente a Cloud Logging
        self.logger = logging.getLogger('accessfan-audit')
        self.logger.setLevel(logging.INFO)
    
    def log_admin_action(self, action, video_id, admin_user=None, video_owner=None, details=None):
        """
        Registra acciones administrativas importantes.
        
        Args:
            action (str): 'accept' o 'reject'
            video_id (int): ID del video
            admin_user (int): ID del usuario admin que realizó la acción
            video_owner (int): ID del usuario propietario del video
            details (dict): Información adicional
        """
        log_data = {
            'event_type': 'ADMIN_ACTION',
            'action': action,
            'video_id': video_id,
            'admin_user': admin_user,
            'video_owner': video_owner,
            'timestamp': datetime.utcnow().isoformat(),
            'details': details or {}
        }
        
        # Log estructurado en formato JSON
        self.logger.info(f"AUDIT: {json.dumps(log_data)}")
    
    def log_video_upload(self, video_id, user_id, filename, size_bytes=0):
        """
        Registra subidas de videos.
        
        Args:
            video_id (int): ID del video creado
            user_id (int): ID del usuario que subió
            filename (str): Nombre del archivo
            size_bytes (int): Tamaño del archivo en bytes
        """
        log_data = {
            'event_type': 'VIDEO_UPLOAD',
            'video_id': video_id,
            'user_id': user_id,
            'filename': filename,
            'size_mb': round(size_bytes / (1024*1024), 2) if size_bytes else 0,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        self.logger.info(f"UPLOAD: {json.dumps(log_data)}")
    
    def log_ia_analysis(self, video_id, estado_ia, resultado=None, tiempo_procesamiento=0):
        """
        Registra resultados del análisis de IA.
        
        Args:
            video_id (int): ID del video analizado
            estado_ia (str): 'completado', 'error', etc.
            resultado (dict): Resultados del análisis
            tiempo_procesamiento (float): Tiempo en segundos
        """
        log_data = {
            'event_type': 'IA_ANALYSIS',
            'video_id': video_id,
            'estado_ia': estado_ia,
            'tiempo_procesamiento': tiempo_procesamiento,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if resultado:
            log_data['resultado'] = resultado
        
        self.logger.info(f"IA_ANALYSIS: {json.dumps(log_data)}")
    
    def log_error(self, error_type, message, video_id=None, user_id=None, details=None):
        """
        Registra errores del sistema.
        
        Args:
            error_type (str): Tipo de error
            message (str): Mensaje descriptivo
            video_id (int, optional): ID del video relacionado
            user_id (int, optional): ID del usuario relacionado
            details (dict, optional): Información adicional
        """
        log_data = {
            'event_type': 'SYSTEM_ERROR',
            'error_type': error_type,
            'message': message,
            'video_id': video_id,
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Agregar details si se proporciona
        if details:
            log_data['details'] = details
        
        self.logger.error(f"ERROR: {json.dumps(log_data)}")

# Instancia global para usar en toda la aplicación
audit_logger = StructuredLogger()