# app/services/translation_service.py
import os
import logging
from typing import List, Dict, Optional
from google.cloud import translate_v2 as translate
from google.oauth2 import service_account
from app.services.logging_service import audit_logger

# Configurar logging
logger = logging.getLogger(__name__)

# Configuración desde variables de entorno
_GOOGLE_CRED_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
TRADUCCION_HABILITADA = os.getenv("ENABLE_TRANSLATION", "true").lower() == "true"

def _get_translate_client():
    """
    Crea el cliente de Google Translate.
    """
    try:
        if _GOOGLE_CRED_PATH and os.path.isfile(_GOOGLE_CRED_PATH):
            creds = service_account.Credentials.from_service_account_file(_GOOGLE_CRED_PATH)
            return translate.Client(credentials=creds)
        return translate.Client()  # Application Default Credentials
    except Exception as e:
        audit_logger.log_error(
            error_type="TRANSLATE_CLIENT_ERROR",
            message=f"Error creando cliente de Google Translate: {str(e)}"
        )
        raise

_translate_client = None

def _client():
    """Obtiene el cliente de traducción (singleton)"""
    global _translate_client
    if _translate_client is None:
        _translate_client = _get_translate_client()
    return _translate_client

def traducir_etiquetas(etiquetas_texto: str, idioma_destino: str = 'es') -> str:
    """
    Traduce un string de etiquetas separadas por comas del inglés al idioma especificado.
    
    Args:
        etiquetas_texto (str): Etiquetas separadas por comas en inglés
        idioma_destino (str): Código de idioma destino (por defecto 'es' para español)
    
    Returns:
        str: Etiquetas traducidas separadas por comas
    """
    if not TRADUCCION_HABILITADA:
        logger.info("Traducción deshabilitada, devolviendo etiquetas originales")
        return etiquetas_texto
    
    if not etiquetas_texto or not etiquetas_texto.strip():
        return etiquetas_texto
    
    try:
        # Separar etiquetas y limpiar espacios
        etiquetas_lista = [etiqueta.strip() for etiqueta in etiquetas_texto.split(',') if etiqueta.strip()]
        
        if not etiquetas_lista:
            return etiquetas_texto
        
        logger.info(f"Traduciendo {len(etiquetas_lista)} etiquetas del inglés al {idioma_destino}")
        
        # Traducir cada etiqueta individualmente para mejor precisión
        etiquetas_traducidas = []
        
        for etiqueta in etiquetas_lista:
            try:
                # Detectar idioma primero
                detection = _client().detect_language(etiqueta)
                idioma_detectado = detection['language']
                
                # Solo traducir si está en inglés
                if idioma_detectado == 'en':
                    resultado = _client().translate(
                        etiqueta,
                        source_language='en',
                        target_language=idioma_destino
                    )
                    etiqueta_traducida = resultado['translatedText'].lower()
                    etiquetas_traducidas.append(etiqueta_traducida)
                    logger.debug(f"'{etiqueta}' -> '{etiqueta_traducida}'")
                else:
                    # Si no está en inglés, mantener original
                    etiquetas_traducidas.append(etiqueta.lower())
                    logger.debug(f"'{etiqueta}' mantenida (idioma: {idioma_detectado})")
                    
            except Exception as e:
                # Si falla la traducción de una etiqueta, mantener la original
                logger.warning(f"Error traduciendo '{etiqueta}': {str(e)}")
                etiquetas_traducidas.append(etiqueta.lower())
        
        resultado_final = ', '.join(etiquetas_traducidas)
        
        # Log de traducción exitosa
        audit_logger.log_error(
            error_type="TRANSLATION_SUCCESS",
            message=f"Etiquetas traducidas exitosamente: {len(etiquetas_lista)} items",
            details={
                'idioma_destino': idioma_destino,
                'etiquetas_originales': len(etiquetas_lista),
                'etiquetas_finales': len(etiquetas_traducidas)
            }
        )
        
        return resultado_final
        
    except Exception as e:
        logger.error(f"Error general traduciendo etiquetas: {str(e)}")
        audit_logger.log_error(
            error_type="TRANSLATION_ERROR",
            message=f"Error traduciendo etiquetas: {str(e)}",
            details={'etiquetas_originales': etiquetas_texto}
        )
        # En caso de error, devolver etiquetas originales
        return etiquetas_texto

def traducir_logos(logos_texto: str, idioma_destino: str = 'es') -> str:
    """
    Traduce nombres de logos/marcas (opcional, ya que muchas marcas mantienen su nombre original).
    
    Args:
        logos_texto (str): Logos separados por comas
        idioma_destino (str): Código de idioma destino
    
    Returns:
        str: Logos traducidos (si aplica) separados por comas
    """
    if not TRADUCCION_HABILITADA:
        return logos_texto
    
    if not logos_texto or not logos_texto.strip():
        return logos_texto
    
    try:
        # Para logos/marcas, generalmente no se traducen porque son nombres propios
        # Pero podemos limpiar y normalizar el formato
        logos_lista = [logo.strip() for logo in logos_texto.split(',') if logo.strip()]
        
        # Normalizar formato pero mantener nombres originales
        logos_normalizados = []
        for logo in logos_lista:
            # Mantener nombres de marcas como están, solo normalizar formato
            logo_normalizado = logo.title()  # Primera letra mayúscula
            logos_normalizados.append(logo_normalizado)
        
        return ', '.join(logos_normalizados)
        
    except Exception as e:
        logger.error(f"Error procesando logos: {str(e)}")
        return logos_texto

def traducir_contenido_explicito(contenido_en: str, idioma_destino: str = 'es') -> str:
    """
    Traduce el estado de contenido explícito del inglés al español.
    
    Args:
        contenido_en (str): Estado en inglés (ej: 'Safe', 'Explicit', 'Possible')
        idioma_destino (str): Código de idioma destino
    
    Returns:
        str: Estado traducido
    """
    if not TRADUCCION_HABILITADA:
        return contenido_en
    
    # Mapeo directo para términos comunes de contenido explícito
    traducciones_explicito = {
        'Safe': 'Seguro',
        'Explicit': 'Explícito', 
        'Possible': 'Posible',
        'Likely': 'Probable',
        'Very Likely': 'Muy Probable',
        'Unlikely': 'Improbable',
        'Very Unlikely': 'Muy Improbable',
        'Unknown': 'Desconocido',
        'No analizado': 'No analizado',
        'Dudoso': 'Dudoso'
    }
    
    # Buscar traducción directa primero
    if contenido_en in traducciones_explicito:
        return traducciones_explicito[contenido_en]
    
    # Si no hay mapeo directo, usar la API
    try:
        if contenido_en and contenido_en.strip():
            resultado = _client().translate(
                contenido_en,
                source_language='en',
                target_language=idioma_destino
            )
            return resultado['translatedText']
        return contenido_en
        
    except Exception as e:
        logger.warning(f"Error traduciendo contenido explícito '{contenido_en}': {str(e)}")
        return contenido_en

def probar_conexion_translate() -> bool:
    """
    Función de utilidad para probar la conexión con Google Translate API.
    
    Returns:
        bool: True si la conexión es exitosa, False en caso contrario.
    """
    try:
        logger.info("🔤 Probando conexión con Google Translate...")
        
        # Hacer una traducción simple de prueba
        resultado = _client().translate(
            'hello world',
            source_language='en',
            target_language='es'
        )
        
        if resultado and 'translatedText' in resultado:
            traduccion = resultado['translatedText']
            logger.info(f"✅ Translate API funcional: 'hello world' -> '{traduccion}'")
            
            audit_logger.log_error(
                error_type="TRANSLATE_TEST_SUCCESS",
                message="Conexión con Google Translate API exitosa",
                details={'test_translation': traduccion}
            )
            return True
        else:
            logger.warning("⚠️ Respuesta inesperada de Translate API")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error probando conexión con Translate API: {e}")
        audit_logger.log_error(
            error_type="TRANSLATE_TEST_ERROR",
            message=f"Error probando conexión con Google Translate API: {str(e)}"
        )
        return False

def obtener_idiomas_soportados() -> List[Dict]:
    """
    Obtiene la lista de idiomas soportados por Google Translate.
    
    Returns:
        List[Dict]: Lista de idiomas con códigos y nombres
    """
    try:
        idiomas = _client().get_languages(target_language='es')
        
        # Filtrar idiomas más comunes para la interfaz
        idiomas_principales = []
        codigos_principales = ['es', 'en', 'pt', 'fr', 'it', 'de', 'ca', 'eu']
        
        for idioma in idiomas:
            if idioma['language'] in codigos_principales:
                idiomas_principales.append({
                    'codigo': idioma['language'],
                    'nombre': idioma['name']
                })
        
        return sorted(idiomas_principales, key=lambda x: x['nombre'])
        
    except Exception as e:
        logger.error(f"Error obteniendo idiomas soportados: {str(e)}")
        # Devolver lista básica como fallback
        return [
            {'codigo': 'es', 'nombre': 'Español'},
            {'codigo': 'en', 'nombre': 'Inglés'},
            {'codigo': 'pt', 'nombre': 'Portugués'},
            {'codigo': 'fr', 'nombre': 'Francés'}
        ]