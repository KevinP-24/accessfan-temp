from app import db
from datetime import datetime
from app.services.logging_service import audit_logger

class Club(db.Model):
    """
    Modelo de datos para representar un club/organización en la base de datos.
    
    Este modelo almacena información de los clubes deportivos, incluyendo 
    colores de branding, logos y estado de actividad.
    """
    
    __tablename__ = 'club'
    
    # Identificador único del club (clave primaria)
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Información básica del club
    nombre = db.Column(db.String(100), nullable=False)
    color_primario = db.Column(db.String(7), nullable=False, default='#000000')
    logo_url = db.Column(db.String(200), nullable=True)
    
    # Fechas y estado
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    
    # Relación con usuarios (un club tiene muchos usuarios)
    # usuarios = db.relationship('Usuario', backref=db.backref('club', lazy=True), lazy='dynamic')


    def __repr__(self):
        """
        Representación en forma de string del objeto Club.
        
        Devuelve una cadena con el nombre del club.
        """
        return f'<Club {self.nombre}>'
    
    def to_dict(self):
        """
        Convierte el objeto Club a un diccionario (DTO).
        Útil para APIs JSON y serialización.
        """
        return {
            'id': self.id,
            'nombre': self.nombre,
            'color_primario': self.color_primario,
            'logo_url': self.logo_url,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'activo': self.activo,
            'total_usuarios': len(self.usuarios) if self.usuarios else 0
        }
    
    @staticmethod
    def from_dict(data):
        """
        Crea un objeto Club desde un diccionario (DTO).
        Útil para crear clubs desde datos externos o APIs.
        """
        try:
            nuevo_club = Club(
                nombre=data.get('nombre'),
                color_primario=data.get('color_primario', '#000000'),
                logo_url=data.get('logo_url', ''),
                activo=data.get('activo', True)
            )
            
            # Log la creación del club (cuando se guarde en BD)
            audit_logger.log_error(
                error_type="CLUB_CREATION",
                message=f"Club creado desde dict: {data.get('nombre')}",
                details={
                    'nombre': data.get('nombre'),
                    'color_primario': data.get('color_primario', '#000000'),
                    'activo': data.get('activo', True)
                }
            )
            
            return nuevo_club
            
        except Exception as e:
            audit_logger.log_error(
                error_type="CLUB_CREATION_ERROR",
                message=f"Error creando club desde dict: {str(e)}",
                details={'data': data}
            )
            raise
    
    @classmethod
    def get_activos(cls):
        """
        Obtiene todos los clubes activos.
        Método de conveniencia para consultas frecuentes.
        """
        try:
            clubes_activos = cls.query.filter_by(activo=True).all()
            
            # Log consulta exitosa (solo en debug/desarrollo)
            if len(clubes_activos) == 0:
                audit_logger.log_error(
                    error_type="CLUB_QUERY_WARNING",
                    message="No se encontraron clubes activos"
                )
            
            return clubes_activos
            
        except Exception as e:
            audit_logger.log_error(
                error_type="CLUB_QUERY_ERROR",
                message=f"Error consultando clubes activos: {str(e)}"
            )
            raise
    
    def desactivar(self):
        """
        Marca el club como inactivo en lugar de eliminarlo.
        Soft delete para mantener integridad referencial.
        """
        try:
            estado_anterior = self.activo
            self.activo = False
            db.session.commit()
            
            # Log la desactivación
            audit_logger.log_error(
                error_type="CLUB_DEACTIVATION",
                message=f"Club desactivado: {self.nombre}",
                details={
                    'club_id': self.id,
                    'club_nombre': self.nombre,
                    'estado_anterior': estado_anterior,
                    'total_usuarios': len(self.usuarios) if self.usuarios else 0
                }
            )
            
        except Exception as e:
            # Rollback en caso de error
            db.session.rollback()
            
            audit_logger.log_error(
                error_type="CLUB_DEACTIVATION_ERROR",
                message=f"Error desactivando club {self.nombre}: {str(e)}",
                details={
                    'club_id': self.id,
                    'club_nombre': self.nombre
                }
            )
            raise
    
    def activar(self):
        """
        Reactiva un club previamente desactivado.
        """
        try:
            estado_anterior = self.activo
            self.activo = True
            db.session.commit()
            
            # Log la activación
            audit_logger.log_error(
                error_type="CLUB_ACTIVATION",
                message=f"Club reactivado: {self.nombre}",
                details={
                    'club_id': self.id,
                    'club_nombre': self.nombre,
                    'estado_anterior': estado_anterior,
                    'total_usuarios': len(self.usuarios) if self.usuarios else 0
                }
            )
            
        except Exception as e:
            # Rollback en caso de error
            db.session.rollback()
            
            audit_logger.log_error(
                error_type="CLUB_ACTIVATION_ERROR",
                message=f"Error reactivando club {self.nombre}: {str(e)}",
                details={
                    'club_id': self.id,
                    'club_nombre': self.nombre
                }
            )
            raise