# Usa una imagen base con Python
FROM python:3.10-slim

# Instala dependencias del sistema necesarias para wkhtmltopdf y PDF rendering
RUN apt-get update && apt-get install -y \
    wkhtmltopdf \
    libxrender1 \
    libxext6 \
    libfontconfig1 \
    libjpeg62-turbo \
    libpng-dev \
    && apt-get clean

# Establece el directorio de trabajo
WORKDIR /app

# Copia los archivos de tu proyecto
COPY . /app

# Instala las dependencias de Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expone el puerto que usará Gunicorn
EXPOSE 5000

# Comando para iniciar la app con Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]