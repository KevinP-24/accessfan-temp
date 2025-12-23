// Función centralizada de validación de formatos de video
function isValidVideoType(file) {
    const validTypes = [
        'video/mp4',        // MP4 - Universal
        'video/quicktime',  // MOV - iPhone por defecto
        'video/avi',        // AVI - Legacy pero común
        'video/x-msvideo',  // AVI alternativo
        'video/webm',       // WebM - Android moderno
        'video/3gpp',       // 3GP - Dispositivos antiguos
        'video/3gpp2'       // 3G2 - Variant de 3GP
    ];
    return validTypes.includes(file.type);
}

// Elementos del DOM
const videoInput = document.getElementById('video');
const fileLabel = document.getElementById('file-label');
const fileInfo = document.getElementById('file-info');
const fileDetails = document.getElementById('file-details');
const preview = document.getElementById('preview');
const uploadForm = document.getElementById('upload-form');
const submitBtn = document.getElementById('submit-btn');
const uploadProgress = document.getElementById('upload-progress');


// Flag para prevenir múltiples envíos
let isSubmitting = false;
let videoDurationSeconds = 0;

// Manejar selección de archivos
videoInput.addEventListener('change', function (event) {
    const file = event.target.files[0];

    if (file) {
        // Validar tamaño (máximo 100MB)
        const maxSize = 100 * 1024 * 1024; // 100MB en bytes
        if (file.size > maxSize) {
            alert('El archivo es demasiado grande. El tamaño máximo permitido es 100MB.');
            resetFileInput();
            return;
        }
        
        // Validar tipo de archivo usando función centralizada
        if (!isValidVideoType(file)) {
            alert('Tipo de archivo no soportado. Formatos permitidos: MP4, MOV, AVI, WebM, 3GP.');
            resetFileInput();
            return;
        }

        // Actualizar la etiqueta del input
        fileLabel.classList.add('has-file');
        fileLabel.innerHTML = `
            <div class="upload-icon">✅</div>
            <span>Video seleccionado correctamente</span>
            <small>Haz clic para cambiar el archivo</small>
        `;

        // Mostrar información del archivo
        const fileSize = (file.size / (1024 * 1024)).toFixed(2);
        fileDetails.textContent = `${file.name} (${fileSize} MB)`;
        fileInfo.style.display = 'block';

        // Mostrar duración del video
        const videoDurationElement = document.getElementById('video-duration');
        const durationValueElement = document.getElementById('duration-value');
        
        if (videoDurationElement && durationValueElement) {
            videoDurationElement.style.display = 'block';
            durationValueElement.textContent = 'Calculando...';
        }

        // Mostrar preview del video
        const videoURL = URL.createObjectURL(file);
        preview.src = videoURL;
        preview.style.display = 'block';

        // Calcular duración cuando el video se carga
        preview.addEventListener('loadedmetadata', function() {
            const duration = preview.duration;
             // guardar para enviarla al backend
            videoDurationSeconds = (duration && !isNaN(duration) && isFinite(duration)) ? duration : 0;
            if (duration && !isNaN(duration) && durationValueElement) {
                const minutes = Math.floor(duration / 60);
                const seconds = Math.floor(duration % 60);
                const formattedDuration = `${minutes}:${seconds.toString().padStart(2, '0')}`;
                durationValueElement.textContent = `${formattedDuration} (${duration.toFixed(1)}s)`;
            } else if (durationValueElement) {
                durationValueElement.textContent = 'No disponible';
            }
        }, { once: true });

        // Manejar error al cargar video
        preview.addEventListener('error', function() {
            videoDurationSeconds = 0;
            const durationValueElementErr = document.getElementById('duration-value');
            if (durationValueElementErr) {
                durationValueElementErr.textContent = 'Error al calcular';
            }
        }, { once: true });

        // Añadir efecto de entrada al video
        setTimeout(() => {
            preview.style.opacity = '1';
            preview.style.transform = 'translateY(0)';
        }, 100);
    } else {
        // Resetear todo si no hay archivo
        resetFileInput();
    }
});

// Función para resetear el input de archivo
function resetFileInput() {
    videoDurationSeconds = 0;
    fileLabel.classList.remove('has-file');
    fileLabel.innerHTML = `
        <div class="upload-icon"><i class="fas fa-video"></i></div>
        <span>Haz clic aquí o arrastra tu video</span>
        <small>Formatos soportados: MP4, MOV, AVI, WebM, 3GP</small>
    `;
    fileInfo.style.display = 'none';
    
    // Ocultar duración
    const videoDurationElement = document.getElementById('video-duration');
    if (videoDurationElement) {
        videoDurationElement.style.display = 'none';
    }
    
    preview.style.display = 'none';
    preview.src = '';
}

// Efectos de drag and drop
fileLabel.addEventListener('dragover', function (e) {
    e.preventDefault();
    const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--primary-color') || '#0e1d90';
    this.style.borderColor = primaryColor;
    this.style.transform = 'scale(1.02)';
});

fileLabel.addEventListener('dragleave', function (e) {
    e.preventDefault();
    const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--primary-color') || '#0e1d90';
    this.style.borderColor = primaryColor;
    this.style.transform = 'scale(1)';
});

fileLabel.addEventListener('drop', function (e) {
    e.preventDefault();
    const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--primary-color') || '#0e1d90';
    this.style.borderColor = primaryColor;
    this.style.transform = 'scale(1)';

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        const file = files[0];
        // Usar la misma validación centralizada
        if (isValidVideoType(file)) {
            videoInput.files = files;
            videoInput.dispatchEvent(new Event('change'));
        } else {
            alert('Tipo de archivo no soportado. Formatos permitidos: MP4, MOV, AVI, WebM, 3GP.');
        }
    }
});

// Función para mostrar la barra de progreso
function showUploadProgress() {
    if (uploadProgress) {
        uploadProgress.style.display = 'block';
        
        // Añadir animación de entrada
        setTimeout(() => {
            uploadProgress.style.opacity = '1';
        }, 10);
    }
}

// Función para ocultar la barra de progreso (para casos de error)
function hideUploadProgress() {
    if (uploadProgress) {
        uploadProgress.style.opacity = '0';
        setTimeout(() => {
            uploadProgress.style.display = 'none';
        }, 300);
    }
    
    // Rehabilitar el botón
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<span>Subir Video</span>';
    isSubmitting = false;
}

function getVideoDurationSeconds(file) {
  return new Promise((resolve) => {
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      const d = Number(v.duration);
      URL.revokeObjectURL(v.src);
      resolve(Number.isFinite(d) ? d : 0);
    };
    v.onerror = () => resolve(0);
    v.src = URL.createObjectURL(file);
  });
}


// Helpers para subida directa a GCS con URL firmada
async function pedirUrlFirmada(file) {
  const descripcionInput = document.getElementById('desc');
  const clubIdInput = document.getElementById('club_id_field');

  const payload = {
    nombre_archivo: file.name,
    content_type: file.type || 'video/mp4',
    descripcion: descripcionInput ? descripcionInput.value : '',
    club_id: clubIdInput ? clubIdInput.value : null,
    duracion: videoDurationSeconds
  };

  const res = await fetch('/api/upload-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) throw new Error('No se pudo obtener URL firmada de subida');
  return res.json();
}

function subirDirectoGCS(uploadUrl, file, onProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('PUT', uploadUrl, true);
        xhr.setRequestHeader('Content-Type', file.type || 'video/mp4');

        xhr.upload.onprogress = function (e) {
            if (e.lengthComputable && typeof onProgress === 'function') {
                const percent = Math.round((e.loaded / e.total) * 100);
                onProgress(percent);
            }
        };

        xhr.onload = function () {
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve();
            } else {
                reject(new Error('Error HTTP ' + xhr.status));
            }
        };

        xhr.onerror = function () {
            reject(new Error('Fallo de red durante la subida'));
        };

        xhr.send(file);
    });
}

// Interceptar el submit del formulario (un solo listener centralizado)
function handleSubmit(e) {
    e.preventDefault(); // Prevenir envío normal para decidir ruta

    if (isSubmitting) {
        return;
    }
    isSubmitting = true;

    // Validar que hay un archivo seleccionado
    if (!videoInput.files || !videoInput.files[0]) {
        alert('Por favor, selecciona un video antes de continuar.');
        isSubmitting = false;
        return;
    }

    const file = videoInput.files[0];

    // Mostrar barra de progreso
    showUploadProgress();

    // Deshabilitar el botón
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span>Subiendo...</span>';
    (async () => {
        try {
            if (!videoDurationSeconds || videoDurationSeconds <= 0) {
                videoDurationSeconds = await getVideoDurationSeconds(file);
            }
            // 1) Pedir URL firmada + registro en BD
            const { upload_url } = await pedirUrlFirmada(file);

            // 2) Subir directo a GCS con progreso
            await subirDirectoGCS(upload_url, file, (percent) => {
                const bar = document.querySelector('#upload-progress .progress-bar');
                const label = document.querySelector('#upload-progress .progress-label');
                if (bar) bar.style.width = percent + '%';
                if (label) label.textContent = percent + '%';
            });

            // 3) Redirigir a la misma pantalla de éxito que ya usas
            window.location.href = '/upload_prueba?success=true';
        } catch (err) {
            console.error('Error en subida directa:', err);
            alert('Ocurrió un error subiendo el video. Intenta de nuevo.');
            hideUploadProgress();
        }
    })();
}

uploadForm.addEventListener('submit', handleSubmit);

// Estilos iniciales para el video preview
if (preview) {
    preview.style.opacity = '0';
    preview.style.transform = 'translateY(20px)';
    preview.style.transition = 'all 0.3s ease';
}

// Manejar el mensaje de éxito (si existe)
const successMessage = document.getElementById('success-message');
if (successMessage) {
    // Auto-ocultar el mensaje después de 5 segundos
    setTimeout(() => {
        successMessage.style.opacity = '0';
        successMessage.style.transform = 'translateY(-20px)';
        setTimeout(() => {
            successMessage.style.display = 'none';
        }, 300);
    }, 5000);
}

console.log('Upload.js cargado correctamente');
