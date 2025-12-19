from app import db
from datetime import datetime
from app.services.core.logging_service import audit_logger

class Usuario(db.Model):
    """
    Modelo de datos para representar un usuario/socio en la base de datos.
    
    Este modelo almacena información de los socios que pertenecen a un club
    y pueden subir videos al sistema.
    """
    
    __tablename__ = 'usuario'
    
    # Identificador único del usuario (clave primaria)
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Relación con club
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=False)
    
    # Información básica del usuario
    nombre = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(50), nullable=False)
    
    # Fechas y estado
    fecha_registro = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    
    # Relación con videos (un usuario tiene muchos videos)
    # La relación ya está definida en el modelo Video con backref

    def __repr__(self):
        """
        Representación en forma de string del objeto Usuario.
        """
        return f'<Usuario {self.nombre}>'