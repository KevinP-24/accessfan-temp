import os
from app import create_app

# Crear la aplicación Flask
app = create_app()

if __name__ == "__main__":
    # Cloud Run proporciona el puerto a través de la variable de entorno PORT
    port = int(os.environ.get('PORT', 8080))
    
    # En producción (Cloud Run), desactivar debug
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(
        debug=debug_mode, 
        host='0.0.0.0', 
        port=port
    )