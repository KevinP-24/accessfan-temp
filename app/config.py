import os
from dotenv import load_dotenv
import logging

# Configurar logger
logger = logging.getLogger(__name__)

# Cargar las variables del archivo .env
load_dotenv()

class Config:
    """Clase de configuración para la aplicación Flask."""
    
    logger.info("=== INICIANDO CONFIGURACIÓN DE BASE DE DATOS ===")
    
    # Cargar la clave secreta de Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'my_default_secret_key')

    # Configuración base de datos
    DB_NAME = os.environ.get('DB_NAME', 'video')
    DB_USER = os.environ.get('DB_USER', 'tivit')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    
    # DETECCIÓN DE ENTORNO: Cloud Run vs Local
    IS_CLOUD_RUN = bool(os.getenv('K_SERVICE'))  # K_SERVICE solo existe en Cloud Run
    
    if IS_CLOUD_RUN:
        # ========================================
        # CONFIGURACIÓN PARA CLOUD RUN + CLOUD SQL
        # ========================================
        logger.info("🚀 ENTORNO DETECTADO: Cloud Run")
        
        INSTANCE_CONNECTION_NAME = os.environ.get('INSTANCE_CONNECTION_NAME')
        if not INSTANCE_CONNECTION_NAME:
            logger.error("❌ FALTA INSTANCE_CONNECTION_NAME en variables de entorno")
            raise ValueError("INSTANCE_CONNECTION_NAME es requerido para Cloud Run")
        
        logger.info(f"🔧 INSTANCE_CONNECTION_NAME: {INSTANCE_CONNECTION_NAME}")
        logger.info(f"🔧 DB_NAME: {DB_NAME}")
        logger.info(f"🔧 DB_USER: {DB_USER}")
        logger.info(f"🔧 DB_PASSWORD: {'***CONFIGURADO***' if DB_PASSWORD else '❌ VACÍO'}")
        
        # URI para Cloud SQL usando Unix Socket y UTC
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@/{DB_NAME}"
            f"?unix_socket=/cloudsql/{INSTANCE_CONNECTION_NAME}"
        )

        logger.info(f"🔗 CONEXIÓN CLOUD SQL: /cloudsql/{INSTANCE_CONNECTION_NAME}")
        
    else:
        # ========================================
        # CONFIGURACIÓN PARA DESARROLLO LOCAL
        # ========================================
        logger.info("🏠 ENTORNO DETECTADO: Desarrollo Local")
        
        DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
        DB_PORT = os.environ.get('DB_PORT', '3307')
        
        logger.info(f"🔧 DB_HOST: {DB_HOST}")
        logger.info(f"🔧 DB_PORT: {DB_PORT}")
        logger.info(f"🔧 DB_NAME: {DB_NAME}")
        logger.info(f"🔧 DB_USER: {DB_USER}")
        logger.info(f"🔧 DB_PASSWORD: {'***CONFIGURADO***' if DB_PASSWORD else '❌ VACÍO'}")
        
        # URI para desarrollo local con UTC
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
            "?connect_timeout=10&autocommit=true"
        )
        
        logger.info(f"🔗 CONEXIÓN LOCAL: {DB_HOST}:{DB_PORT}")
    
    # Configuración común
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ✅ Siempre en UTC
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"init_command": "SET time_zone = 'UTC'"}
    }
    
    logger.info(f"🔐 URI GENERADA: mysql+{'pymysql' if IS_CLOUD_RUN else 'mysqlconnector'}://{DB_USER}:***@{'unix_socket' if IS_CLOUD_RUN else f'{DB_HOST}:{DB_PORT}' if not IS_CLOUD_RUN else 'N/A'}")
    logger.info("=== FIN CONFIGURACIÓN DE BASE DE DATOS ===")
    
    # Google Cloud Storage 
    GOOGLE_CLOUD_STORAGE_BUCKET = os.environ.get('GOOGLE_CLOUD_STORAGE_BUCKET', 'default-bucket-name')
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'path_to_your_credentials.json')

    # Límite de tamaño de archivo de subida
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 104857600))  # 100 MB
