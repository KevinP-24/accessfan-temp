# En app/models/video.py
import json
from app import db
from datetime import datetime
from app.services.logging_service import audit_logger

class Video(db.Model):
    """
    Modelo de datos para representar un video en la base de datos.
    """
    
    __tablename__ = 'video'
    
    # --- Definición de Columnas ---
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usuario_id = db.Column(db.Integer, nullable=False)
    video_url = db.Column(db.Text, nullable=True)
    gcs_object_name = db.Column(db.String(500), nullable=True)
    nombre_archivo = db.Column(db.String(200), nullable=True)
    duracion = db.Column(db.Float, nullable=False, default=0)
    descripcion = db.Column(db.Text, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='sin-revisar')
    estado_ia = db.Column(db.String(20), nullable=False, default='pendiente')
    razon_rechazo = db.Column(db.String(500), nullable=True)
    contenido_explicito = db.Column(db.String(50), nullable=False, default='No analizado')
    etiquetas = db.Column(db.Text, nullable=True)
    logotipos = db.Column(db.Text, nullable=True)
    puntaje_confianza = db.Column(db.Float, nullable=True, default=0)
    tiempo_procesamiento = db.Column(db.Float, nullable=True, default=0)
    fecha_subida = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_procesamiento = db.Column(db.DateTime, nullable=True)
    objetos_detectados = db.Column(db.Text, nullable=True, comment="Lista JSON de objetos detectados en el video")
    # Campos para detectar texto malicioso
    texto_detectado = db.Column(db.Text, nullable=True, comment="Texto completo extraído del video por Cloud Vision.")
    palabras_problematicas_texto = db.Column(db.Text, nullable=True, comment="Lista de palabras problemáticas encontradas.")
    nivel_problema_texto = db.Column(db.String(20), nullable=True, default='limpio', comment="Clasificación del texto: limpio, sospechoso, problematico, error.")
    frames_texto_analizados = db.Column(db.Integer, nullable=True, default=0, comment="Número de frames analizados para texto.")

    # --- Constantes de Estado ---
    ESTADOS_ADMIN = ['sin-revisar', 'aceptado', 'rechazado']
    ESTADOS_IA = ['pendiente', 'procesando', 'completado', 'error']
    NIVELES_PROBLEMA_TEXTO = ['limpio', 'sospechoso', 'problematico', 'error']

    # --- Métodos de Actualización de Estado ---
    def actualizar_estado_admin(self, nuevo_estado, razon=None, admin_user=None):
        if nuevo_estado not in self.ESTADOS_ADMIN:
            raise ValueError(f"Estado administrativo inválido: {nuevo_estado}")
        
        self.estado = nuevo_estado
        if razon:
            self.razon_rechazo = razon
        elif nuevo_estado == 'aceptado':
            self.razon_rechazo = None
        
        if nuevo_estado in ['aceptado', 'rechazado']:
            self.fecha_procesamiento = datetime.utcnow()
        # (El logging se puede quedar como lo tenías)

    def actualizar_estado_ia(self, nuevo_estado_ia, datos_ia=None):
        """
        Actualiza el estado del análisis de IA y guarda los resultados en la BD.
        """
        if nuevo_estado_ia not in self.ESTADOS_IA:
            raise ValueError(f"Estado de IA inválido: {nuevo_estado_ia}")
        
        self.estado_ia = nuevo_estado_ia
        
        if nuevo_estado_ia == 'completado' and datos_ia:
            # === Campos de Video Intelligence ===
            self.contenido_explicito = datos_ia.get('contenido_explicito', 'No analizado')
            self.etiquetas = datos_ia.get('etiquetas', '')
            self.logotipos = datos_ia.get('logotipos', '')
            self.puntaje_confianza = datos_ia.get('puntaje_confianza', 0.0)
            self.tiempo_procesamiento = datos_ia.get('tiempo_procesamiento', 0.0)

            # === Objetos detectados ===
            objetos = datos_ia.get('objetos_detectados', [])
            try:
                self.objetos_detectados = json.dumps(objetos, ensure_ascii=False)
            except Exception:
                self.objetos_detectados = "[]"

            # --- 🔴 NUEVO: forzar riesgo visual si hay armas ---
            try:
                if any(o.get("es_arma") for o in objetos):
                    self.contenido_explicito = "Riesgo Visual: Arma detectada"
            except Exception:
                pass

            # === Análisis de texto ===
            self.texto_detectado = datos_ia.get('texto_detectado', '')
            self.palabras_problematicas_texto = datos_ia.get('palabras_problematicas', '')
            self.nivel_problema_texto = datos_ia.get('nivel_problema_texto', 'error')
            self.frames_texto_analizados = datos_ia.get('frames_texto_analizados', 0)
            
            # --- Actualizar fecha ---
            self.fecha_procesamiento = datetime.utcnow()
        
        elif nuevo_estado_ia == 'error':
            error_msg = "Error en análisis de IA"
            if datos_ia and 'error_message' in datos_ia:
                error_msg = datos_ia['error_message']
            self.razon_rechazo = error_msg

    # --- Métodos de conveniencia ---
    def marcar_como_aceptado(self, razon=None, admin_user=None):
        self.actualizar_estado_admin('aceptado', razon, admin_user)

    def marcar_como_rechazado(self, razon, admin_user=None):
        if not razon or not razon.strip():
            raise ValueError("Debe proporcionarse una razón para rechazar el video")
        self.actualizar_estado_admin('rechazado', razon, admin_user)


    # --- Métodos de cálculo para la UI ---
    def get_moderation_status(self):
        """
        Devuelve el estado de moderación con texto, color y razón.
        Se calcula dinámicamente según puntaje, armas y contenido explícito.
        """
        try:
            objs = json.loads(self.objetos_detectados) if self.objetos_detectados else []
        except Exception:
            objs = []

        puntaje = float(self.puntaje_confianza or 0)
        nivel_texto = (self.nivel_problema_texto or "").lower()
        ce = (self.contenido_explicito or "").lower()

        tiene_arma = any("arma" in (o.get("label", "").lower()) for o in objs)
        reason = None

        # Procesando / error
        if self.estado_ia == "procesando":
            return {"text": "Procesando...", "color": "info"}
        if self.estado_ia == "error":
            return {"text": "Error en análisis", "color": "secondary"}

        # Amenazante
        if tiene_arma:
            reason = "Arma detectada"
            return {"text": "Amenazante", "color": "danger", "reason": reason}
        if ce in ("explícito", "explicit"):
            reason = "Contenido explícito"
            return {"text": "Amenazante", "color": "danger", "reason": reason}
        if puntaje < 0.4:
            reason = "Puntaje muy bajo"
            return {"text": "Amenazante", "color": "danger", "reason": reason}

        # Riesgoso
        if puntaje < 0.7 or nivel_texto in ("problematico", "sospechoso", "medio"):
            reason = "Riesgo moderado"
            return {"text": "Riesgoso", "color": "warning", "reason": reason}

        # Seguro
        return {"text": "Seguro", "color": "success", "reason": None}


    def get_safety_score(self):
        """
        Calcula un puntaje de seguridad a partir de los factores almacenados.
        Considera IA visual, texto y detección de armas.
        """
        score = (self.puntaje_confianza or 0) * 100

        # Penalización por contenido explícito
        ce = (self.contenido_explicito or "").lower()
        if ce in ["explicit", "explícito"]:
            score -= 40
        elif ce in ["possible", "posible"]:
            score -= 20

        # Penalización por texto
        nivel = (self.nivel_problema_texto or "").lower()
        if nivel == "problematico":
            score -= 30
        elif nivel == "sospechoso":
            score -= 15

        # Penalización por armas detectadas
        try:
            objs = json.loads(self.objetos_detectados) if self.objetos_detectados else []
        except Exception:
            objs = []
        if any("arma de fuego" in o.get("label", "").lower() for o in objs):
            score -= 50
        elif any("arma blanca" in o.get("label", "").lower() for o in objs):
            score -= 30

        final = max(0, round(score))
        color = "success"
        if final < 75:
            color = "warning"
        if final < 50:
            color = "danger"

        return {"score": final, "color": color}

    # --- Métodos de representación y serialización ---
    def to_dict(self):
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'video_url': self.video_url,
            'nombre_archivo': self.nombre_archivo,
            'duracion': self.duracion,
            'descripcion': self.descripcion,
            'estado': self.estado,
            'estado_ia': self.estado_ia,
            'razon_rechazo': self.razon_rechazo,
            'contenido_explicito': self.contenido_explicito,
            'etiquetas': self.etiquetas,
            'logotipos': self.logotipos,
            'objetos_detectados': json.loads(self.objetos_detectados) if self.objetos_detectados else [],
            'puntaje_confianza': self.puntaje_confianza,
            'fecha_subida': self.fecha_subida.isoformat() if self.fecha_subida else None,
            'texto_detectado': self.texto_detectado,
            'palabras_problematicas_texto': self.palabras_problematicas_texto,
            'nivel_problema_texto': self.nivel_problema_texto,
        }

    def __repr__(self):
        return f'<Video {self.id}: {self.nombre_archivo} (Admin: {self.estado}, IA: {self.estado_ia})>'