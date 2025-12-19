# app/models/badword.py
from app import db
from datetime import datetime
from app.services.core.logging_service import audit_logger

class BadWord(db.Model):
    """
    Modelo de datos para representar palabras problemáticas en la BD.
    Usado para detección de texto ofensivo (soez, violento, sexual).
    """

    __tablename__ = "badword"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Palabra en su forma original o normalizada
    palabra = db.Column(db.String(100), nullable=False)

    # Categoría de la palabra: soez, violenta, sexual
    categoria = db.Column(
        db.Enum("soez", "violenta", "sexual", name="categoria_badword"),
        nullable=False,
        default="soez"
    )

    # Idioma principal: español (es) o inglés (en)
    idioma = db.Column(
        db.Enum("es", "en", name="idioma_badword"),
        nullable=False,
        default="es"
    )

    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Fuente de la palabra: manual, migracion_inicial, etc.
    fuente = db.Column(db.String(50), nullable=False, default="manual")

    # Restricción única para evitar duplicados
    __table_args__ = (
        db.UniqueConstraint("palabra", "categoria", "idioma", name="uq_palabra_categoria_idioma"),
    )

    def __repr__(self):
        return f"<BadWord {self.palabra} ({self.idioma}, {self.categoria})>"

    def to_dict(self):
        """Convierte el objeto a diccionario (útil para APIs)."""
        return {
            "id": self.id,
            "palabra": self.palabra,
            "categoria": self.categoria,
            "idioma": self.idioma,
            "activo": self.activo,
            "fuente": self.fuente,
            "fecha_creacion": self.fecha_creacion.isoformat() if self.fecha_creacion else None
        }

    @staticmethod
    def from_dict(data):
        """Crea un objeto BadWord desde un diccionario."""
        try:
            nueva = BadWord(
                palabra=data.get("palabra"),
                categoria=data.get("categoria", "soez"),
                idioma=data.get("idioma", "es"),
                activo=data.get("activo", True),
                fuente=data.get("fuente", "manual")
            )
            audit_logger.log_error(
                error_type="BADWORD_CREATION",
                message=f"BadWord creada: {nueva.palabra}",
                details=nueva.to_dict()
            )
            return nueva
        except Exception as e:
            audit_logger.log_error(
                error_type="BADWORD_CREATION_ERROR",
                message=f"Error creando BadWord: {str(e)}",
                details={"data": data}
            )
            raise
