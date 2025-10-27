import os
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, abort
from app.services.gcs_service import subir_a_gcs, _get_bucket, obtener_url_firmada, obtener_url_logo
from app.services.video_duration_service import obtener_duracion_video
from app.services.video_processor import procesar_video_individual
from app.services.logging_service import audit_logger
from app.models.video import Video
from app.models.club import Club
from app import db
from datetime import datetime
import logging
import threading
from app.services import secret_manager_service as secrets



logger = logging.getLogger(__name__)

main = Blueprint("main", __name__)

# -------------------------------
#   PERMITIR IFRAME EN FLASK
# -------------------------------
@main.after_request
def after_request(response):
    # Permitir que tu app sea embebida en iframe
    response.headers.pop('X-Frame-Options', None)
    return response

@main.route('/iframe_admin')
def test_iframe_admin():
    return render_template('iframe_admin.html')

# -------------------------------
#   FUNCIONES DE USUARIO
# -------------------------------
def obtener_usuario_por_defecto():
    """
    Obtiene o crea el usuario por defecto para la demostración.
    En producción, esto se reemplazaría por lógica real de usuarios.
    """
    try:
        # Por ahora, simplemente devolver ID=1 como usuario demo
        # TODO: En el futuro, importar modelo Usuario y crear/buscar usuario real
        logger.info("Usando usuario por defecto ID=1 para demostración")
        return 1
        
    except Exception as e:
        logger.error(f"Error obteniendo usuario por defecto: {e}")
        # En caso de error, usar ID 1 como fallback
        return 1

def obtener_usuario_desde_header():
    """
    Función preparada para obtener usuario desde header X-USER-ID.
    Por ahora devuelve usuario por defecto para demostración.
    """
    x_user_id = request.headers.get("X-USER-ID")
    
    if x_user_id:
        logger.info(f"Header X-USER-ID recibido: {x_user_id} (usando usuario demo por ahora)")
        # TODO: En el futuro, buscar usuario real por este ID/nombre
        # usuario = Usuario.query.filter_by(nombre=x_user_id).first()
        # return usuario.id if usuario else obtener_usuario_por_defecto()
    
    # Por ahora siempre devolver usuario por defecto
    return obtener_usuario_por_defecto()

# -------------------------------
#   FUNCIONES DE CLUB
# -------------------------------
def obtener_club_por_id(club_id):
    """
    Obtiene configuración del club desde la base de datos.
    Convierte el modelo Club a formato compatible con los templates.
    """
    try:
        club = Club.query.filter_by(id=club_id, activo=True).first()
        
        if not club:
            logger.warning(f"Club con ID {club_id} no encontrado o inactivo")
            audit_logger.log_error(
                error_type="CLUB_NOT_FOUND",
                message=f"Club con ID {club_id} no encontrado o inactivo"
            )
            return None
        
        # Convertir a formato que esperan los templates
        config = {
            "id": club.id,
            "nombre": club.nombre,
            "color": club.color_primario,
            "logo": club.logo_url,
            "titulo": f"Subir Video del Socio {club.nombre}"
        }
        
        logger.info(f"Club cargado desde BD: {club.nombre} (ID: {club.id})")
        return config
        
    except Exception as e:
        logger.error(f"Error obteniendo club ID {club_id}: {e}")
        audit_logger.log_error(
            error_type="CLUB_QUERY_ERROR",
            message=f"Error obteniendo club ID {club_id}: {str(e)}"
        )
        return None

# -------------------------------
#   FUNCIONES AUXILIARES
# -------------------------------
def _procesar_video_con_ia_async(video_id):
    """
    Procesa un video con IA de forma asíncrona.
    Se ejecuta en un hilo separado para no bloquear la respuesta HTTP.
    """
    try:
        print(f"🔥 INICIANDO PROCESAMIENTO ASÍNCRONO PARA VIDEO {video_id}")
        from app import create_app
        
        # Crear contexto de aplicación para el hilo
        app = create_app()
        with app.app_context():
            video = Video.query.get(video_id)
            if video:
                print(f"🎬 Video encontrado: {video.nombre_archivo}")
                logger.info(f"🤖 Iniciando procesamiento asíncrono de IA para video {video_id}")
                resultado = procesar_video_individual(video)
                if resultado['exitoso']:
                    print(f"✅ ÉXITO: Video {video_id} procesado con IA")
                    logger.info(f"✅ Video {video_id} procesado exitosamente con IA")
                else:
                    print(f"❌ ERROR: {resultado.get('error')}")
                    logger.error(f"❌ Error procesando video {video_id}: {resultado.get('error')}")
            else:
                print(f"❌ VIDEO {video_id} NO ENCONTRADO")
                logger.error(f"❌ Video {video_id} no encontrado para procesamiento IA")
    except Exception as e:
        print(f"💥 ERROR CRÍTICO: {e}")
        logger.error(f"❌ Error crítico en procesamiento asíncrono de video {video_id}: {e}")

def _procesar_upload_club(club_id, config):
    """Función auxiliar para procesar uploads de clubes dinámicos"""
    video = request.files.get("video")
    descripcion = (request.form.get("descripcion") or "").strip()

    if not video or not video.filename:
        audit_logger.log_error("UPLOAD_ERROR", "No video file provided", user_id=obtener_usuario_desde_header())
        return redirect(url_for("main.upload_dinamico", club_id=club_id, error="no_file"))

    # Usar datos del club desde BD o configuración por defecto
    socio = f"{config.get('nombre', 'AccessFan')} - {request.headers.get('X-USER-ID', 'Socio desconocido')}"
    
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    
    # Generar filename según si hay club_id o no
    if club_id:
        filename = f"uploads/club_{club_id}_{timestamp}_{video.filename}"
    else:
        filename = f"uploads/accessfan_{timestamp}_{video.filename}"

    # Obtener duración del video ANTES de subir a GCS
    try:
        duracion_video = obtener_duracion_video(video)
        logger.info(f"Duración obtenida para {config['nombre']}: {duracion_video} segundos")
    except Exception as e:
        logger.warning(f"Error obteniendo duración del video: {e}")
        audit_logger.log_error("VIDEO_DURATION_ERROR", f"Error obteniendo duración: {str(e)}", user_id=obtener_usuario_desde_header())
        duracion_video = 0.0

    # Subir a GCS y obtener también el tamaño del archivo
    try:
        object_name, url_inicial, file_size_bytes = subir_a_gcs(
            video, 
            filename=filename, 
            socio=socio, 
            descripcion=descripcion
        )
        logger.info(f"Video subido exitosamente para {config['nombre']}: {object_name}, tamaño: {file_size_bytes} bytes")
    except Exception as e:
        logger.error(f"Error subiendo video: {e}")
        audit_logger.log_error("GCS_UPLOAD_ERROR", f"Error subiendo a GCS: {str(e)}", user_id=obtener_usuario_desde_header())
        return redirect(url_for("main.upload_dinamico", club_id=club_id, error="upload_failed"))

    # Guardar en base de datos con campos IA
    try:
        usuario_id = obtener_usuario_desde_header()
        
        nuevo_video = Video(
            usuario_id=usuario_id,
            video_url=url_inicial,
            gcs_object_name=object_name,
            nombre_archivo=video.filename,
            duracion=duracion_video,
            descripcion=descripcion or "Sin descripción proporcionada",
            estado="sin-revisar",
            estado_ia="pendiente",
            contenido_explicito="No analizado"
        )
        
        db.session.add(nuevo_video)
        db.session.commit()
        logger.info(f"Video de {config['nombre']} guardado en BD con ID: {nuevo_video.id}, duración: {duracion_video}s")
        
        audit_logger.log_video_upload(
            video_id=nuevo_video.id,
            user_id=usuario_id,
            filename=video.filename,
            size_bytes=file_size_bytes
        )
        
        import os
        from app.services.video_processor import procesar_video_individual

        logger.info(f"Iniciando procesamiento de IA para video {nuevo_video.id}")

        if os.getenv("K_SERVICE"):  # Estamos en Cloud Run
            logger.info("Cloud Run detectado: procesamiento IA sin threading")
            try:
                resultado = procesar_video_individual(nuevo_video)
                if resultado.get("exitoso"):
                    print(f"ÉXITO: Video {nuevo_video.id} procesado con IA")
                else:
                    print(f"❌ ERROR IA: {resultado.get('error')}")
            except Exception as e:
                logger.error(f"❌ Fallo crítico en procesamiento inline: {e}")
        else:
            # Local: threading asíncrono
            thread = threading.Thread(
                target=_procesar_video_con_ia_async, 
                args=(nuevo_video.id,)
            )
            thread.daemon = True
            thread.start()
        audit_logger.log_ia_analysis(
            video_id=nuevo_video.id,
            estado_ia="procesando",
            resultado={"organizacion": config.get('nombre', 'AccessFan')},
            tiempo_procesamiento=0
        )
        
    except Exception as e:
        logger.error(f"Error guardando video en BD: {e}")
        audit_logger.log_error("DATABASE_ERROR", f"Error guardando en BD: {str(e)}", user_id=obtener_usuario_desde_header())
        db.session.rollback()
        return redirect(url_for("main.upload_dinamico", club_id=club_id, error="database_error"))

    # Redirigir con parámetro de éxito
    return redirect(url_for("main.upload_prueba_hijo", club_id=club_id, success="true"))

# -------------------------------
#   RUTAS PRINCIPALES
# -------------------------------
@main.get("/")
def home():
    """Redirige al listado de videos admin"""
    return redirect(url_for("main.listado_videos"))

# -------------------------------
#   RUTA DINÁMICA (PARA IFRAME)
# -------------------------------
@main.get("/upload")
def upload_dinamico():
    """Formulario de subida dinámico basado en club_id de la BD"""
    
    club_id = request.args.get('club_id')
    
    # Configuración por defecto de AccessFan
    config_default = {
        "id": None,
        "nombre": "AccessFan",
        "color": "#F5522C",
        "logo": "logo-b.png",
        "titulo": "Subir Video - AccessFan Platform"
    }
    
    config = config_default  # valor por defecto inicial

    if club_id:
        try:
            club_id_int = int(club_id)
            config_db = obtener_club_por_id(club_id_int)
            if config_db:
                config = config_db
            else:
                logger.warning(f"Club {club_id_int} no encontrado, usando configuración por defecto pero manteniendo club_id={club_id}")
        except ValueError:
            logger.warning(f"club_id inválido: {club_id}, usando configuración por defecto")
            # aquí no sobreescribimos club_id, lo dejamos como vino
    else:
        logger.info("Acceso a /upload sin club_id, usando configuración por defecto AccessFan")
        club_id = None
    
    # Obtener logo
    try:
        logo_url = obtener_url_logo(config["logo"]) if config["logo"] else None
    except Exception as e:
        logger.warning(f"Error obteniendo logo: {e}")
        logo_url = None
    
    upload_success = request.args.get('success') == 'true'
    
    # Log acceso
    audit_logger.log_error(
        error_type="UPLOAD_FORM_ACCESS",
        message=f"Acceso a formulario de upload para {config['nombre']}",
        details={'club_id': club_id, 'club_nombre': config['nombre'], 'es_default': (config == config_default)}
    )
    
    return render_template(
        "upload.html", 
        logo_url=logo_url,
        team_name=config["nombre"],
        team_color=config["color"],
        team_title=config["titulo"],
        club_id=club_id,
        upload_success=upload_success
    )

@main.post("/upload")
def upload_video_dinamico():
    """Procesar subida de video dinámico"""
    
    club_id = request.form.get('club_id') or request.args.get('club_id')
    
    config_default = {
        "id": None,
        "nombre": "AccessFan",
        "color": "#F5522C",
        "logo": None,
        "titulo": "Subir Video - AccessFan Platform"
    }
    
    if not club_id:
        config = config_default
        logger.info("Upload sin club_id, usando configuración por defecto AccessFan")
        return _procesar_upload_club(None, config)
    else:
        try:
            club_id_int = int(club_id)
            config = obtener_club_por_id(club_id_int)
            
            if not config:
                logger.warning(f"Club {club_id_int} no encontrado, usando configuración por defecto")
                config = config_default
                # ⚠️ Pasar club_id aunque se use config_default
                return _procesar_upload_club(club_id_int, config)
            
            return _procesar_upload_club(club_id_int, config)
            
        except ValueError:
            logger.warning(f"club_id inválido: {club_id}, usando configuración por defecto")
            config = config_default
            return _procesar_upload_club(club_id, config)
# -------------------------------
#   RUTAS ADMIN 
# -------------------------------
@main.get("/admin/videos")
def listado_videos():
    """Listado de videos - Con logging estructurado de accesos admin"""
    admin_user = obtener_usuario_desde_header()
    
    # LOGGING ESTRUCTURADO: Registrar acceso admin
    audit_logger.log_admin_action(
        action='view_list',
        video_id=None,
        admin_user=admin_user,
        details={'endpoint': '/admin/videos'}
    )
    
    try:
        videos = Video.query.order_by(Video.fecha_subida.desc()).all()
        
        # Log básico para debugging (solo si hay problemas)
        logger.info(f"Admin listado: {len(videos)} videos cargados")
        
        # LOGGING ESTRUCTURADO: Registrar estadísticas de acceso
        stats = {
            'total_videos': len(videos),
            'sin_revisar': len([v for v in videos if v.estado == 'sin-revisar']),
            'aceptados': len([v for v in videos if v.estado == 'aceptado']),
            'rechazados': len([v for v in videos if v.estado == 'rechazado']),
            'ia_pendiente': len([v for v in videos if v.estado_ia == 'pendiente']),
            'ia_completado': len([v for v in videos if v.estado_ia == 'completado'])
        }
        
        audit_logger.log_admin_action(
            action='list_stats',
            video_id=None,
            admin_user=admin_user,
            details=stats
        )
        
        return render_template("admin_list.html", videos=videos)
        
    except Exception as e:
        # LOGGING ESTRUCTURADO: Error accediendo a listado
        audit_logger.log_error(
            error_type="ADMIN_LIST_ERROR",
            message=f"Error cargando listado de videos: {str(e)}",
            user_id=admin_user
        )
        
        # Log detallado solo para debugging interno
        logger.error(f"Error en listado admin: {str(e)}")
        
        return render_template("admin_list.html", videos=[])

@main.get("/admin/videos/<int:video_id>")
def ver_detalle_video(video_id: int):
    """Ver detalle de video - Con logging estructurado básico"""
    admin_user = obtener_usuario_desde_header()
    
    try:
        video = Video.query.get(video_id)
        
        if not video:
            audit_logger.log_admin_action(
                action='view_detail_not_found',
                video_id=video_id,
                admin_user=admin_user
            )
            return jsonify({"error": "Video not found"}), 404

        # LOGGING ESTRUCTURADO: Registrar acceso a detalle
        audit_logger.log_admin_action(
            action='view_detail',
            video_id=video_id,
            admin_user=admin_user,
            video_owner=video.usuario_id,
            details={'video_filename': video.nombre_archivo, 'video_estado': video.estado}
        )

        return render_template("admin_detalle.html", video=video, signed_url=None)
        
    except Exception as e:
        audit_logger.log_error(
            error_type="ADMIN_DETAIL_ERROR",
            message=f"Error accediendo detalle video {video_id}: {str(e)}",
            video_id=video_id,
            user_id=admin_user
        )
        return jsonify({"error": "Database error", "details": str(e)}), 500

@main.get("/admin/videos/<int:video_id>/signed-url")
def signed_url_for_video(video_id: int):
    """Obtener URL firmada para video - Con logging estructurado básico"""
    admin_user = obtener_usuario_desde_header()
    
    video = Video.query.get(video_id)
    if not video:
        audit_logger.log_admin_action(
            action='signed_url_not_found',
            video_id=video_id,
            admin_user=admin_user
        )
        return jsonify({"error": "Video not found"}), 404

    if not video.gcs_object_name:
        return jsonify({"url": video.video_url, "mode": "DIRECT"}), 200
    
    try:
        info = obtener_url_firmada(video.gcs_object_name, horas=2)

        # LOGGING ESTRUCTURADO
        audit_logger.log_admin_action(
            action='generate_signed_url',
            video_id=video_id,
            admin_user=admin_user,
            details={'gcs_object': video.gcs_object_name, 'mode': info.get("mode")}
        )
        
        return jsonify(info), 200  # ya incluye {"url":..., "mode":...}
        
    except Exception as e:
        audit_logger.log_error(
            error_type="SIGNED_URL_ERROR",
            message=f"Error generando URL firmada para video {video_id}: {str(e)}",
            video_id=video_id,
            user_id=admin_user
        )
        return jsonify({"error": "Could not generate signed URL", "details": str(e)}), 500

# -------------------------------
#   RUTAS MODIFICAR ESTADO VIDEO
# -------------------------------

@main.post("/admin/videos/<int:video_id>/revisar")
def marcar_como_revisado(video_id: int):
    """Marcar video como aceptado - Con logging estructurado"""
    admin_user = obtener_usuario_desde_header()
    
    video = Video.query.get(video_id)
    if not video:
        audit_logger.log_admin_action(
            action='accept_not_found',
            video_id=video_id,
            admin_user=admin_user
        )
        
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({"error": "Video not found"}), 404
        return redirect(url_for('main.listado_videos'))
    
    try:
        # Usar el nuevo método del modelo
        video.marcar_como_aceptado()
        db.session.commit()
        
        # LOGGING ESTRUCTURADO: Registrar acción de aceptación
        audit_logger.log_admin_action(
            action='accept',
            video_id=video_id,
            admin_user=admin_user,
            video_owner=video.usuario_id,
            details={
                'video_filename': video.nombre_archivo,
                'previous_estado': 'sin-revisar',
                'new_estado': 'aceptado'
            }
        )

        # Actualizar metadata en GCS también
        if video.gcs_object_name:
            try:
                bucket = _get_bucket()
                blob = bucket.blob(video.gcs_object_name)
                meta = blob.metadata or {}
                meta["estado"] = "aceptado"
                blob.metadata = meta
                blob.patch()
            except Exception as e:
                audit_logger.log_error(
                    error_type="GCS_METADATA_ERROR",
                    message=f"Error actualizando metadata GCS: {str(e)}",
                    video_id=video_id,
                    user_id=admin_user
                )

        # Si es petición AJAX, devolver JSON
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({
                "message": "Video marked as accepted",
                "video_id": video_id,
                "estado": video.estado
            }), 200
        
        return redirect(url_for('main.ver_detalle_video', video_id=video_id))
        
    except ValueError as ve:
        audit_logger.log_error(
            error_type="VALIDATION_ERROR",
            message=f"Error validación al aceptar video: {str(ve)}",
            video_id=video_id,
            user_id=admin_user
        )
        db.session.rollback()
        
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({"error": "Validation error", "details": str(ve)}), 400
        return redirect(url_for('main.listado_videos'))
        
    except Exception as e:
        audit_logger.log_error(
            error_type="DATABASE_ERROR",
            message=f"Error aceptando video: {str(e)}",
            video_id=video_id,
            user_id=admin_user
        )
        db.session.rollback()
        
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({"error": "Database error", "details": str(e)}), 500
        return redirect(url_for('main.listado_videos'))

@main.post("/admin/videos/<int:video_id>/aceptar")
def aceptar_video(video_id: int):
    """Marcar video como aceptado"""
    admin_user = obtener_usuario_desde_header()
    
    try:
        video = Video.query.get(video_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404

        # Actualizar estado a aceptado
        video.estado = "aceptado"
        video.fecha_procesamiento = datetime.utcnow()
        video.razon_rechazo = None  # Limpiar razón de rechazo si existía
        
        db.session.commit()
        logger.info(f"Video {video_id} marcado como aceptado por admin {admin_user}")

        # Redirigir de vuelta al detalle del video
        return redirect(url_for('main.ver_detalle_video', video_id=video_id))
        
    except Exception as e:
        logger.error(f"Error aceptando video {video_id}: {e}")
        db.session.rollback()
        return jsonify({"error": "Database error", "details": str(e)}), 500

@main.post("/admin/videos/<int:video_id>/rechazar")
def rechazar_video(video_id: int):
    """Rechazar video"""
    admin_user = obtener_usuario_desde_header()
    
    try:
        video = Video.query.get(video_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404

        # Actualizar estado a rechazado
        video.estado = "rechazado"
        video.fecha_procesamiento = datetime.utcnow()
        # razon_rechazo queda vacío por ahora
        
        db.session.commit()
        logger.info(f"Video {video_id} rechazado por admin {admin_user}")

        # Redirigir de vuelta al detalle del video
        return redirect(url_for('main.ver_detalle_video', video_id=video_id))
        
    except Exception as e:
        logger.error(f"Error rechazando video {video_id}: {e}")
        db.session.rollback()
        return jsonify({"error": "Database error", "details": str(e)}), 500

# -------------------------------
#   RUTAS DE DEBUG/UTILIDAD
# -------------------------------
@main.get("/health")
def health_check():
    """Health check endpoint - CAMBIO: contar videos desde base de datos"""
    try:
        video_count = Video.query.count()
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "videos_count": video_count
        }), 200
    except Exception as e:
        logger.error(f"Error en health check: {e}")
        return jsonify({
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }), 500

# =============================================================
# ========= RUTA PARA STATUS DEL SPINER DE LOS VIDEOS =========
# =============================================================
@main.get("/admin/videos/status")
def estados_videos():
    ids = request.args.get('ids', '')
    if not ids.strip():
        return jsonify({"error": "ids required"}), 400
    try:
        id_list = [int(x) for x in ids.split(',') if x.strip().isdigit()]
        if not id_list:
            return jsonify({"error": "empty ids"}), 400

        videos = Video.query.filter(Video.id.in_(id_list)).all()

        def pack(v):
            # Campos ligeros para refrescar la UI
            safety = v.get_safety_score()
            mod = v.get_moderation_status()
            return {
                "id": v.id,
                "estado": v.estado,
                "estado_ia": v.estado_ia,
                "contenido_explicito": v.contenido_explicito,
                "nivel_problema_texto": v.nivel_problema_texto,
                "puntaje_confianza": v.puntaje_confianza,
                "safety_score": safety["score"],
                "safety_color": safety["color"],
                "moderation_text": mod["text"],
                "moderation_color": mod["color"],
                "fecha_procesamiento": v.fecha_procesamiento.isoformat() if v.fecha_procesamiento else None,
            }

        return jsonify({"videos": [pack(v) for v in videos]}), 200
    except Exception as e:
        audit_logger.log_error(
            error_type="ADMIN_STATUS_ENDPOINT_ERROR",
            message=f"Error obteniendo estados: {str(e)}"
        )
        return jsonify({"error": "server"}), 500

# =============================================================
# ========= RUTAS DE PRUEBA PARA IFRAME DINÁMICO =========
# =============================================================
@main.route('/equipo1')
def prueba_final_padre():
    #Obtiene el token de Secret Manager.
    token_real = secrets.obtener_token_secreto()

    if not token_real:
        logger.error("Fallo crítico al obtener el token de Secret Manager. La página no cargará.")
        abort(503, description="No se pudo obtener la credencial de autenticación.")

    # 3. Si el token existe, carga la página y se lo pasa.
    return render_template('iframe_prueba.html', auth_token=token_real)

@main.get("/upload_prueba")
def upload_prueba_hijo():
    """
    Renderiza la plantilla genérica del iframe que esperará los datos.
    """
    upload_success = request.args.get("success") == "true"
    error = request.args.get("error")  # opcional, si quieres mostrar errores en el futuro

    return render_template(
        "upload_prueba.html",
        upload_success=upload_success,
        error=error
    )
