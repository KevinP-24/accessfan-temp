import os
import json
from google.cloud import secretmanager
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied, NotFound
from google.oauth2 import service_account
import logging
from app.services.logging_service import audit_logger

logger = logging.getLogger(__name__)

def _get_client():
    """
    Crea el cliente de Secret Manager con las credenciales apropiadas.
    En producción (Cloud Run, Compute Engine, etc.) usa Application Default Credentials.
    En local, usa el archivo de credenciales si está definido.
    """
    google_cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    try:
        if google_cred_path and os.path.isfile(google_cred_path):
            logger.info("Usando credenciales desde archivo de servicio")
            credentials = service_account.Credentials.from_service_account_file(google_cred_path)
            return secretmanager.SecretManagerServiceClient(credentials=credentials)
        else:
            logger.info("Usando Application Default Credentials")
            return secretmanager.SecretManagerServiceClient()
    except Exception as e:
        logger.error(f"Error inicializando cliente de Secret Manager: {e}")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_CLIENT_ERROR",
            message=f"Error inicializando cliente de Secret Manager: {str(e)}"
        )
        raise

def obtener_token_secreto():
    """
    Obtiene el token principal desde Google Cloud Secret Manager.
    Usa la nueva configuración del proyecto del cliente.
    """
    try:
        client = _get_client()
        
        # Usar el nuevo proyecto del cliente
        project_id = os.getenv('GCP_PROJECT_ID', 'learned-grammar-468317-r1')
        
        if not project_id:
            logger.error("GCP_PROJECT_ID no está definido en las variables de entorno")
            audit_logger.log_error(
                error_type="SECRET_MANAGER_CONFIG_ERROR",
                message="GCP_PROJECT_ID no está definido en las variables de entorno"
            )
            return None

        # Usar el nuevo nombre del secreto
        nombre_secreto = os.getenv("SECRET_NAME", "access-secret")
        secret_name = f"projects/{project_id}/secrets/{nombre_secreto}/versions/latest"
        
        logger.debug(f"Accediendo al secreto: {secret_name}")
        
        response = client.access_secret_version(request={"name": secret_name})
        secret_string = response.payload.data.decode("UTF-8").strip()
        
        if not secret_string:
            logger.warning(f"El secreto {nombre_secreto} está vacío")
            audit_logger.log_error(
                error_type="SECRET_MANAGER_EMPTY_SECRET",
                message=f"El secreto {nombre_secreto} está vacío"
            )
            return None
        
        # Intentar parsear como JSON primero
        try:
            token_json = json.loads(secret_string)
            # Buscar el token en diferentes claves posibles
            if isinstance(token_json, dict):
                # Intentar claves comunes
                for key in ['token', 'value', 'api_token', 'auth_token', 'access_token']:
                    if key in token_json:
                        logger.info(f"Token encontrado en clave '{key}'")
                        return token_json[key]
                
                # Si no encuentra claves conocidas, tomar el primer valor
                if token_json:
                    first_key = list(token_json.keys())[0]
                    first_value = token_json[first_key]
                    logger.info(f"Usando primer valor del JSON (clave: '{first_key}')")
                    return first_value
            
            logger.warning(f"El JSON del secreto no tiene el formato esperado: {type(token_json)}")
            audit_logger.log_error(
                error_type="SECRET_MANAGER_FORMAT_ERROR",
                message=f"El JSON del secreto no tiene el formato esperado: {type(token_json)}"
            )
            return None
            
        except json.JSONDecodeError:
            # Si no es JSON, asumir que es un string simple
            logger.debug("El secreto no es JSON, usando como string simple")
            return secret_string
            
    except NotFound:
        logger.error(f"Secreto no encontrado: {nombre_secreto} en proyecto {project_id}")
        logger.error("Verifica que el secreto exista y que tengas permisos")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_NOT_FOUND",
            message=f"Secreto no encontrado: {nombre_secreto} en proyecto {project_id}"
        )
        return None
    except PermissionDenied:
        logger.error(f"Permisos insuficientes para acceder al secreto: {nombre_secreto}")
        logger.error("Verifica que el service account tenga rol 'Secret Manager Secret Accessor'")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_PERMISSION_DENIED",
            message=f"Permisos insuficientes para acceder al secreto: {nombre_secreto}"
        )
        return None
    except GoogleAPICallError as e:
        logger.error(f"Error de API accediendo al secreto: {e}")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_API_ERROR",
            message=f"Error de API accediendo al secreto: {str(e)}"
        )
        return None
    except Exception as e:
        logger.error(f"Error inesperado al obtener el token: {e}")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_UNEXPECTED_ERROR",
            message=f"Error inesperado al obtener el token: {str(e)}"
        )
        return None

def obtener_secreto_generico(nombre_secreto, es_json=False, project_id_override=None):
    """
    Obtiene cualquier secreto desde Google Cloud Secret Manager.
    
    Args:
        nombre_secreto (str): Nombre del secreto.
        es_json (bool): Si el secreto está en formato JSON.
        project_id_override (str, optional): ID del proyecto específico.
        
    Returns:
        dict|str|None: El contenido del secreto o None si hay error.
    """
    try:
        client = _get_client()
        
        # Usar el proyecto del cliente por defecto
        project_id = project_id_override or os.getenv('GCP_PROJECT_ID', 'learned-grammar-468317-r1')
        
        if not project_id:
            logger.error("GCP_PROJECT_ID no está definido")
            audit_logger.log_error(
                error_type="SECRET_MANAGER_CONFIG_ERROR",
                message="GCP_PROJECT_ID no está definido"
            )
            return None

        secret_name = f"projects/{project_id}/secrets/{nombre_secreto}/versions/latest"
        logger.debug(f"Accediendo al secreto: {secret_name}")
        
        response = client.access_secret_version(request={"name": secret_name})
        
        secret_string = response.payload.data.decode("UTF-8")
        
        if not secret_string.strip():
            logger.warning(f"El secreto {nombre_secreto} está vacío")
            audit_logger.log_error(
                error_type="SECRET_MANAGER_EMPTY_SECRET",
                message=f"El secreto {nombre_secreto} está vacío"
            )
            return None
        
        if es_json:
            try:
                return json.loads(secret_string)
            except json.JSONDecodeError as e:
                logger.error(f"Error decodificando JSON del secreto {nombre_secreto}: {e}")
                audit_logger.log_error(
                    error_type="SECRET_MANAGER_JSON_ERROR",
                    message=f"Error decodificando JSON del secreto {nombre_secreto}: {str(e)}"
                )
                return None
        else:
            return secret_string.strip()

    except NotFound:
        logger.error(f"Secreto no encontrado: {nombre_secreto} en proyecto {project_id}")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_NOT_FOUND",
            message=f"Secreto no encontrado: {nombre_secreto} en proyecto {project_id}"
        )
        return None
    except PermissionDenied:
        logger.error(f"Permisos insuficientes para acceder al secreto: {nombre_secreto}")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_PERMISSION_DENIED",
            message=f"Permisos insuficientes para acceder al secreto: {nombre_secreto}"
        )
        return None
    except GoogleAPICallError as e:
        logger.error(f"Error de API accediendo al secreto {nombre_secreto}: {e}")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_API_ERROR",
            message=f"Error de API accediendo al secreto {nombre_secreto}: {str(e)}"
        )
        return None
    except Exception as e:
        logger.error(f"Error inesperado obteniendo el secreto {nombre_secreto}: {e}")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_UNEXPECTED_ERROR",
            message=f"Error inesperado obteniendo el secreto {nombre_secreto}: {str(e)}"
        )
        return None

def validar_token(token_recibido):
    """
    Valida un token contra el almacenado en Secret Manager.
    
    Args:
        token_recibido (str): Token a validar
        
    Returns:
        bool: True si el token es válido, False en caso contrario
    """
    if not token_recibido or not token_recibido.strip():
        logger.warning("Token recibido está vacío")
        audit_logger.log_error(
            error_type="AUTH_TOKEN_EMPTY",
            message="Token recibido está vacío"
        )
        return False
    
    # Verificar si la autenticación está habilitada
    if os.getenv('ENABLE_AUTH', 'true').lower() not in ('true', '1', 'yes'):
        logger.info("Autenticación deshabilitada - permitiendo acceso")
        audit_logger.log_error(
            error_type="AUTH_DISABLED",
            message="Autenticación deshabilitada - permitiendo acceso"
        )
        return True
    
    token_valido = obtener_token_secreto()
    if not token_valido:
        logger.error("No se pudo obtener el token válido desde Secret Manager")
        audit_logger.log_error(
            error_type="AUTH_TOKEN_FETCH_ERROR",
            message="No se pudo obtener el token válido desde Secret Manager"
        )
        return False
    
    is_valid = token_recibido.strip() == token_valido.strip()
    
    if not is_valid:
        logger.warning("Token inválido recibido")
        audit_logger.log_error(
            error_type="AUTH_TOKEN_INVALID",
            message="Token inválido recibido"
        )
    else:
        logger.info("Token validado correctamente")
        audit_logger.log_error(
            error_type="AUTH_TOKEN_VALID",
            message="Token validado correctamente"
        )
    
    return is_valid

def obtener_credenciales_gcp():
    """
    Obtiene las credenciales de GCP desde Secret Manager si están almacenadas allí.
    Útil para cuando las credenciales se guardan como secreto en lugar de archivo.
    
    Returns:
        dict|None: Las credenciales en formato JSON o None si no se encuentran.
    """
    return obtener_secreto_generico("gcp-credentials", es_json=True)

def obtener_config_database():
    """
    Obtiene la configuración de base de datos desde Secret Manager.
    
    Returns:
        dict|None: Configuración de DB o None si no se encuentra.
    """
    return obtener_secreto_generico("database-config", es_json=True)

def cargar_variables_desde_secret():
    """
    Carga todas las variables del secreto principal (JSON) al entorno (os.environ).
    Usa SECRET_NAME y GCP_PROJECT_ID ya configurados.
    """
    try:
        nombre_secreto = os.getenv("SECRET_NAME", "access-secret")
        data = obtener_secreto_generico(nombre_secreto, es_json=True)

        if not data:
            logger.warning(f"No se pudo cargar configuración desde el secreto '{nombre_secreto}'")
            return False

        for key, value in data.items():
            # No pisamos SECRET_NAME ni GCP_PROJECT_ID
            if key in ("SECRET_NAME", "GCP_PROJECT_ID"):
                continue
            os.environ[key] = str(value)

        logger.info(f"Variables cargadas desde Secret Manager: {len(data)} claves")
        return True

    except Exception as e:
        logger.error(f"Error cargando variables desde Secret Manager: {e}")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_ENV_LOAD_ERROR",
            message=f"Error cargando variables desde Secret Manager: {str(e)}"
        )
        return False

def test_secret_manager_connection():
    """
    Función de utilidad para probar la conexión con Secret Manager.
    
    Returns:
        bool: True si la conexión es exitosa, False en caso contrario.
    """
    try:
        logger.info("🔐 Probando conexión con Secret Manager...")
        
        # Mostrar configuración
        project_id = os.getenv('GCP_PROJECT_ID')
        secret_name = os.getenv('SECRET_NAME')
        logger.info(f"📋 Proyecto: {project_id}")
        logger.info(f"🔑 Secreto: {secret_name}")
        
        token = obtener_token_secreto()
        if token:
            token_preview = f"{token[:8]}...{token[-8:]}" if len(token) > 16 else "***"
            logger.info(f"✅ Token obtenido: {token_preview}")
            logger.info("✅ Conexión con Secret Manager exitosa")
            audit_logger.log_error(
                error_type="SECRET_MANAGER_TEST_SUCCESS",
                message="Conexión con Secret Manager exitosa",
                details={'project_id': project_id, 'secret_name': secret_name}
            )
            return True
        else:
            logger.warning("❌ No se pudo obtener el token")
            audit_logger.log_error(
                error_type="SECRET_MANAGER_TEST_FAILED",
                message="No se pudo obtener el token en test de conexión"
            )
            return False
    except Exception as e:
        logger.error(f"❌ Error probando conexión con Secret Manager: {e}")
        audit_logger.log_error(
            error_type="SECRET_MANAGER_TEST_ERROR",
            message=f"Error probando conexión con Secret Manager: {str(e)}"
        )
        return False