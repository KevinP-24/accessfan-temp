import os
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, abort
from app.services.gcp.gcs_service import subir_a_gcs, _get_bucket, obtener_url_firmada, obtener_url_firmada_upload
from app.services.video.video_duration_service import obtener_duracion_video
from app.services.video.video_processor import procesar_video_individual
from app.services.video.video_batch_worker import procesar_videos_pendientes_batch
from app.services.core.logging_service import audit_logger
from app.models.video import Video
from app.models.club import Club
from app import db
from datetime import datetime
import logging
from app.services.gcp import secret_manager_service as secrets
import math
from datetime import datetime
import uuid

#Cantidad de videos que se cargan
ADMIN_VIDEOS_PAGE_SIZE = int(os.getenv("ADMIN_VIDEOS_PAGE_SIZE", 100))


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
def _procesar_upload_club(club_id, config):
    video = request.files.get("video")
    descripcion = (request.form.get("descripcion") or "").strip()
    if not video:
        return redirect(url_for("main.upload_dinamico", club_id=club_id, error="no_file"))
    socio = f"{config.get('nombre','AccessFan')} - {request.headers.get('X-USER-ID','Socio desconocido')}"
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    filename = f"uploads/club_{club_id}_{timestamp}_{video.filename}" if club_id \
               else f"uploads/accessfan_{timestamp}_{video.filename}"
    try:
        duracion_video = obtener_duracion_video(video)
    except:
        duracion_video = 0.0
    object_name, url_inicial, file_size_bytes = subir_a_gcs(video, filename, socio, descripcion)
    nuevo_video = Video(
        usuario_id=obtener_usuario_desde_header(),
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
    return redirect(url_for("main.upload_hijo", club_id=club_id, success="true"))

@main.post("/events/gcs")
def events_gcs_trigger():
    """
    Worker disparado por Eventarc cuando un objeto se finalize en GCS.
    """
    try:
        stats = procesar_videos_pendientes_batch(limite=3)
        logger.info(f"[EVENTARC] Resultado batch: {stats}")
        return ("", 204)
    except Exception as e:
        logger.error(f"[EVENTARC] Error: {e}")
        return ("", 500)

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
    """
    Listado de videos - Con logging estructurado de accesos admin + paginación
    y con token disponible para el front (igual que en upload).
    """
    # === Obtener token desde Secret Manager (sin bloquear por él) ===
    token_real = None
    try:
        token_real = secrets.obtener_token_secreto()
        if not token_real:
            logger.warning("No se obtuvo token_real en /admin/videos (se continúa sin abortar).")
    except Exception as e:
        logger.error(f"Error obteniendo token_real en /admin/videos: {e}")

    admin_user = obtener_usuario_desde_header()
    audit_logger.log_admin_action(
        action='view_list',
        video_id=None,
        admin_user=admin_user,
        details={'endpoint': '/admin/videos'}
    )

    try:
        page = request.args.get("page", 1, type=int)
        if page < 1:
            page = 1

        per_page = ADMIN_VIDEOS_PAGE_SIZE
        base_query = Video.query.order_by(Video.fecha_subida.desc())

        total_videos = base_query.count()
        videos = (
            base_query
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        import math
        total_pages = max(1, math.ceil(total_videos / per_page))
        has_next = page < total_pages
        has_prev = page > 1

        logger.info(
            f"Admin listado: page={page}, per_page={per_page}, "
            f"total_videos={total_videos}, page_items={len(videos)}"
        )

        stats = {
            'total_videos': total_videos,
            'pagina_actual': page,
            'total_paginas': total_pages,
            'items_en_pagina': len(videos),
        }
        audit_logger.log_admin_action(
            action='list_stats',
            video_id=None,
            admin_user=admin_user,
            details=stats
        )

        return render_template(
            "admin_list.html",
            videos=videos,
            page=page,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
            auth_token=token_real,  # ← igual que en upload_padre
        )

    except Exception as e:
        audit_logger.log_error(
            error_type="ADMIN_LIST_ERROR",
            message=f"Error cargando listado de videos: {str(e)}",
            user_id=admin_user
        )
        logger.error(f"Error en listado admin: {str(e)}")
        return render_template(
            "admin_list.html",
            videos=[],
            page=1,
            total_pages=1,
            has_prev=False,
            has_next=False,
            auth_token=token_real,  # también lo pasamos en el caso de error
        )

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
# ========= RUTAS DE PRUEBA PARA IFRAME DINÁMICO ==============
# =============================================================
@main.route('/equipo1')
def upload_padre():
    #Obtiene el token de Secret Manager.
    token_real = secrets.obtener_token_secreto()

    if not token_real:
        logger.error("Fallo crítico al obtener el token de Secret Manager. La página no cargará.")
        abort(503, description="No se pudo obtener la credencial de autenticación.")

    # 3. Si el token existe, carga la página y se lo pasa.
    return render_template('iframe_upload.html', auth_token=token_real)

@main.get("/upload_prueba")
def upload_hijo():
    """
    Renderiza la plantilla genérica del iframe que esperará los datos.
    """
    upload_success = request.args.get("success") == "true"
    error = request.args.get("error")  # opcional, si quieres mostrar errores en el futuro

    return render_template(
        "upload.html",
        upload_success=upload_success,
        error=error
    )
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


#========================================
@main.post("/api/upload-url")
def api_upload_url():
    try:
        data = request.get_json(force=True) or {}

        nombre_archivo = data.get("nombre_archivo") or "video.mp4"
        content_type   = data.get("content_type")   or "video/mp4"
        descripcion    = (data.get("descripcion") or "").strip()
        club_id        = data.get("club_id")

        # Usuario desde header
        usuario_id = obtener_usuario_desde_header()

        # Construir object_name (mismo patrón que ya tienes)
        base, ext = os.path.splitext(nombre_archivo)
        if not ext:
            ext = ".mp4"

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        safe_base = base.replace(" ", "_")[:40] or "video"
        object_name = (
            f"uploads/club_{club_id}_{timestamp}_{safe_base}{ext}"
            if club_id
            else f"uploads/{timestamp}_{safe_base}{ext}"
        )

        # 1) URL firmada de SUBIDA (PUT)
        info_upload = obtener_url_firmada_upload(
            object_name=object_name,
            content_type=content_type,
            minutos=60
        )

        # 2) URL firmada de LECTURA (GET) para preview
        try:
            info_get = obtener_url_firmada(object_name, horas=24)
            video_url = info_get.get("url", "")
        except Exception as e:
            audit_logger.log_error(
                error_type="SIGNED_URL_GET_ERROR",
                message=f"No se pudo generar URL GET para preview: {e}",
                video_id=None,
                user_id=usuario_id,
            )
            video_url = ""

        # 3) Crear registro en BD (SIN club_id en el modelo)
        nuevo_video = Video(
            usuario_id=usuario_id,
            video_url=video_url,          # ← ahora queda llena
            gcs_object_name=object_name,
            nombre_archivo=nombre_archivo,
            duracion=0.0,                 # la IA o el servicio de duración lo actualizarán
            descripcion=descripcion or "Sin descripción proporcionada",
            estado="sin-revisar",
            estado_ia="pendiente",
            contenido_explicito="No analizado"
        )

        db.session.add(nuevo_video)
        db.session.commit()

        audit_logger.log_event(
            event_type="API_UPLOAD_URL",
            message="URL firmada de subida generada",
            video_id=nuevo_video.id,
            details={
                "gcs_object_name": object_name,
                "bucket": info_upload["bucket"],
                "mode": info_upload["mode"],
                "content_type": content_type,
            }
        )

        return jsonify({
            "upload_url": info_upload["url"],
            "object_name": object_name,
            "video_id": nuevo_video.id
        }), 200

    except Exception as e:
        db.session.rollback()
        audit_logger.log_error(
            error_type="API_UPLOAD_URL_ERROR",
            message=f"Error generando URL firmada: {str(e)}"
        )
        return jsonify({"error": "upload_url_error"}), 500