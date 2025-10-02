# Usamos una imagen base de Python
FROM python:3.10-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos el archivo de dependencias al contenedor
COPY requirements.txt /app/requirements.txt

# Instalamos las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el código fuente de la aplicación al contenedor
COPY . /app

# Exponemos el puerto 8080, que es el puerto por defecto para Cloud Run
EXPOSE 8080

# Definimos el comando para ejecutar la aplicación con Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "--workers=1", "--threads=8", "--timeout=120", "run:app"]
