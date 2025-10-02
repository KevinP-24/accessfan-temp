// static/js/admin_detalle.js
document.addEventListener('DOMContentLoaded', () => {
  // Animaciones progresivas
  const elements = document.querySelectorAll('.slide-in');
  elements.forEach((el, index) => {
    el.style.animationDelay = `${index * 0.2}s`;
  });

  // Efecto hover para tarjetas
  document.querySelectorAll('.info-card, .analysis-item').forEach(card => {
    card.addEventListener('mouseenter', function () {
      this.style.transform = 'translateY(-5px) scale(1.02)';
      this.style.boxShadow = '0 10px 25px rgba(245, 82, 44, 0.2)';
    });
    card.addEventListener('mouseleave', function () {
      this.style.transform = 'translateY(0) scale(1)';
      this.style.boxShadow = 'none';
    });
  });

  // Mejorar controles del video + refrescar URL firmada si expira
  const video = document.getElementById('player');
  if (video) {
    const videoId = video.dataset.videoId;
    let retrying = false;

    video.addEventListener('loadedmetadata', () => {
      console.log('Video cargado correctamente');
      video.style.background = '';
    });

    function showErrorOverlay(msg = 'Error al cargar el video') {
      video.style.background = 'linear-gradient(45deg, #1C1C1C, #333)';
      video.setAttribute('title', msg);
    }

    async function refreshSignedUrl() {
      if (!videoId) return false;
      try {
        const resp = await fetch(`/admin/videos/${videoId}/signed-url`, { cache: 'no-store' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (data && data.url) {
          const wasPaused = video.paused;
          video.src = data.url;
          video.load();
          if (!wasPaused) {
            try { await video.play(); } catch(_) {}
          }
          return true;
        }
      } catch (err) {
        console.error('No se pudo obtener URL firmada:', err);
      }
      return false;
    }

    video.addEventListener('error', async () => {
      if (!retrying) {
        retrying = true;
        const ok = await refreshSignedUrl();
        if (!ok) showErrorOverlay();
        setTimeout(() => { retrying = false; }, 5000);
      } else {
        showErrorOverlay();
      }
    });
  }

  // === FUNCIONALIDAD DINÁMICA DE BOTONES ===
  
  const btnAccept = document.getElementById('btn-accept');
  const btnReject = document.getElementById('btn-reject');
  const adminStatus = document.getElementById('admin-status');
  const actionButtons = document.querySelector('.action-buttons');

// En static/js/admin_detalle.js

function updateButtonsState(activeAction) {
    const currentDate = new Date().toLocaleString('es-ES', { timeZone: 'America/Bogota', hour12: false }).replace(',', '');
    const statusSection = document.getElementById('admin-actions'); // Obtenemos el contenedor principal

    // Limpiar mensajes y estados de botones anteriores
    const existingMessages = statusSection.querySelectorAll('.action-message');
    existingMessages.forEach(msg => msg.remove());
    btnAccept.className = 'btn btn-accept';
    btnReject.className = 'btn btn-reject';
    btnAccept.innerHTML = '<i class="fas fa-check-circle"></i> Marcar como aceptado';
    btnReject.innerHTML = '<i class="fas fa-times-circle"></i> Rechazar video';

    const message = document.createElement('div');

    if (activeAction === 'aceptado') {
        btnAccept.classList.add('active');
        btnReject.classList.add('inactive');
        
        message.className = 'action-message accepted';
        message.innerHTML = `Aceptado el ${currentDate}`; // Sin emoji
        statusSection.appendChild(message); // Se añade al contenedor principal, debajo de los botones
        
        if (adminStatus) {
            adminStatus.innerHTML = '<span class="status-badge status-accepted">Aceptado</span>';
        }

    } else if (activeAction === 'rechazado') {
        btnReject.classList.add('active');

        message.className = 'action-message rejected';
        message.innerHTML = `Rechazado el ${currentDate}`; // Sin emoji
        statusSection.appendChild(message); // Se añade al contenedor principal, debajo de los botones
        
        if (adminStatus) {
            adminStatus.innerHTML = '<span class="status-badge status-rejected">Rechazado</span>';
        }
    } else {
        // Estado 'sin-revisar'
        message.className = 'action-message pending';
        message.innerHTML = 'Este video está pendiente de tu revisión';
        statusSection.appendChild(message); // Se añade al contenedor principal, debajo de los botones
    }
}

  // Función para mostrar notificaciones
  function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
      <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-triangle'}"></i>
      <span>${message}</span>
    `;
    
    Object.assign(notification.style, {
      position: 'fixed',
      top: '20px',
      right: '20px',
      background: type === 'success' ? '#4CAF50' : '#f44336',
      color: 'white',
      padding: '15px 20px',
      borderRadius: '8px',
      boxShadow: '0 4px 15px rgba(0,0,0,0.3)',
      zIndex: '10000',
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
      fontSize: '14px',
      minWidth: '300px'
    });
    
    document.body.appendChild(notification);
    
    notification.style.transform = 'translateX(100%)';
    notification.style.transition = 'transform 0.3s ease';
    setTimeout(() => {
      notification.style.transform = 'translateX(0)';
    }, 10);
    
    setTimeout(() => {
      notification.style.transform = 'translateX(100%)';
      setTimeout(() => {
        if (notification.parentNode) {
          notification.parentNode.removeChild(notification);
        }
      }, 300);
    }, 5000);
  }

  // Función para deshabilitar botones durante carga
  function setButtonsLoading(loading = true) {
    [btnAccept, btnReject].forEach(btn => {
      if (btn) {
        btn.disabled = loading;
        if (loading) {
          btn.style.opacity = '0.6';
          btn.style.cursor = 'not-allowed';
          const icon = btn.querySelector('i');
          if (icon) icon.className = 'fas fa-spinner fa-spin';
        }
      }
    });
  }

  // Función para restaurar botones después de loading
  function restoreButtonsAfterLoading() {
    [btnAccept, btnReject].forEach(btn => {
      if (btn) {
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
      }
    });
  }

  // Manejador para botón Aceptar
  if (btnAccept) {
    btnAccept.addEventListener('click', async () => {
      if (confirm('¿Estás seguro de que quieres aceptar este video?')) {
        setButtonsLoading(true);
        
        try {
          const response = await fetch(`/admin/videos/${videoId}/aceptar`, {
            method: 'POST'
          });
          
          if (response.redirected) {
            window.location.reload();
          } else if (response.ok) {
            showNotification('Video aceptado exitosamente', 'success');
            restoreButtonsAfterLoading();
            updateButtonsState('aceptado');
          } else {
            const errorData = await response.json();
            showNotification(`Error: ${errorData.error || 'No se pudo aceptar el video'}`, 'error');
            restoreButtonsAfterLoading();
          }
        } catch (error) {
          console.error('Error al aceptar video:', error);
          showNotification('Error de conexión. Intenta nuevamente.', 'error');
          restoreButtonsAfterLoading();
        }
      }
    });
  }

  // Manejador para botón Rechazar
  if (btnReject) {
    btnReject.addEventListener('click', async () => {
      if (confirm('¿Estás seguro de que quieres rechazar este video?')) {
        setButtonsLoading(true);
        
        try {
          const response = await fetch(`/admin/videos/${videoId}/rechazar`, {
            method: 'POST'
          });
          
          if (response.redirected) {
            window.location.reload();
          } else if (response.ok) {
            showNotification('Video rechazado exitosamente', 'success');
            restoreButtonsAfterLoading();
            updateButtonsState('rechazado');
          } else {
            const errorData = await response.json();
            showNotification(`Error: ${errorData.error || 'No se pudo rechazar el video'}`, 'error');
            restoreButtonsAfterLoading();
          }
        } catch (error) {
          console.error('Error al rechazar video:', error);
          showNotification('Error de conexión. Intenta nuevamente.', 'error');
          restoreButtonsAfterLoading();
        }
      }
    });
  }

  // Inicializar estado basado en el estado actual del video
  const currentEstado = typeof window.currentEstado !== 'undefined' ? window.currentEstado : null;
  if (currentEstado === 'aceptado') {
    updateButtonsState('aceptado');
  } else if (currentEstado === 'rechazado') {
    updateButtonsState('rechazado');
  }
});