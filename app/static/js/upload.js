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
            if (durationValueElement) {
                durationValueElement.textContent = 'Error al calcular';
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

// Interceptar el submit del formulario
uploadForm.addEventListener('submit', function(e) {
    e.preventDefault(); // Prevenir envío normal
    
    // Validar que hay un archivo seleccionado
    if (!videoInput.files || !videoInput.files[0]) {
        alert('Por favor, selecciona un video antes de continuar.');
        return;
    }
    
    // Mostrar barra de progreso
    showUploadProgress();
    
    // Deshabilitar el botón
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span>Subiendo...</span>';
    
    // Enviar el formulario después de un breve delay para mostrar la UI
    setTimeout(() => {
        uploadForm.submit();
    }, 100);
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
}

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

// Prevenir múltiples envíos
let isSubmitting = false;
uploadForm.addEventListener('submit', function(e) {
    if (isSubmitting) {
        e.preventDefault();
        return;
    }
    isSubmitting = true;
});

console.log('Upload.js cargado correctamente');