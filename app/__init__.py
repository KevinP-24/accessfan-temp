from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from app.config import Config
from app.services.logging_service import audit_logger

# Crear la instancia de SQLAlchemy
db = SQLAlchemy()

def create_app():
    """Función para crear y configurar la instancia de la aplicación Flask."""
    try:
        app = Flask(__name__)

        # Cargar la configuración desde la clase Config
        app.config.from_object(Config)

        # Log inicialización de la aplicación
        audit_logger.log_error(
            error_type="APP_INITIALIZATION_START",
            message="Iniciando configuración de la aplicación Flask",
            details={
                'database_uri': app.config.get('SQLALCHEMY_DATABASE_URI', '').split('@')[-1] if app.config.get('SQLALCHEMY_DATABASE_URI') else 'No configurada',
                'secret_key_configured': bool(app.config.get('SECRET_KEY')),
                'gcs_bucket': app.config.get('GOOGLE_CLOUD_STORAGE_BUCKET', 'No configurado')
            }
        )

        # Inicializar la base de datos con la app
        db.init_app(app)

        # Importar el Blueprint 'main' desde el archivo correspondiente
        from app.routes.main import main

        # Registrar el Blueprint 'main'
        app.register_blueprint(main)

        # Importar modelos para que SQLAlchemy los reconozca
        from app.models.video import Video

        # Crear las tablas si no existen (solo en desarrollo)
        with app.app_context():
            try:
                db.create_all()
                audit_logger.log_error(
                    error_type="APP_DATABASE_TABLES_CREATED",
                    message="Tablas de base de datos creadas/verificadas exitosamente"
                )
            except Exception as e:
                print(f"Error creando tablas: {e}")
                audit_logger.log_error(
                    error_type="APP_DATABASE_ERROR",
                    message=f"Error creando tablas de base de datos: {str(e)}"
                )

        # Log inicialización exitosa
        audit_logger.log_error(
            error_type="APP_INITIALIZATION_SUCCESS",
            message="Aplicación Flask inicializada exitosamente"
        )
    
        return app

    except Exception as e:
        # Log error crítico de inicialización
        audit_logger.log_error(
            error_type="APP_INITIALIZATION_CRITICAL_ERROR",
            message=f"Error crítico inicializando aplicación Flask: {str(e)}"
        )
        raise