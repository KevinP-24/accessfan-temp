import os
from vertexai import init
from vertexai.preview.generative_models import GenerativeModel, Part
from app.services.logging_service import audit_logger

PROJECT = os.getenv("VERTEX_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
MODEL_NAME = os.getenv("VERTEX_FOUNDATION_MODEL", "gemini-2.5-flash")

def analizar_video_gemini(gcs_uri: str) -> dict:
    """
    Analiza un video en GCS usando Gemini (modelo multimodal).
    Retorna un dict estructurado compatible con tu pipeline.
    """
    try:
        init(project=PROJECT, location=LOCATION)
        model = GenerativeModel(MODEL_NAME)
        video_part = Part.from_uri(gcs_uri, mime_type="video/mp4")

        prompt = """
        Analiza este video y responde en formato JSON:
        {
          "objetos_detectados": [{"label": "objeto", "confianza": 0.9}],
          "texto_detectado": ["palabra1", "palabra2"],
          "alertas": ["contenido_violento", "arma", "sangre", ...]
        }

        Solo responde el JSON válido, sin texto adicional.
        """

        response = model.generate_content([video_part, prompt])
        texto = response.text.strip()

        import json
        try:
            data = json.loads(texto)
        except json.JSONDecodeError:
            data = {"raw_text": texto}

        return data

    except Exception as e:
        audit_logger.log_error(
            error_type="GEMINI_VIDEO_ANALYSIS_ERROR",
            message=f"Error analizando video con Gemini: {str(e)}"
        )
        return {}
