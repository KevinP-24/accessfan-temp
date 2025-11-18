// static/js/admin_list.js
// Animación de números
function animateNumbers() {
  const numbers = document.querySelectorAll('.stat-number');
  numbers.forEach(number => {
    const finalNumber = parseInt(number.textContent || '0', 10);
    let current = 0;
    const inc = Math.max(1, Math.floor(finalNumber / 20));
    const timer = setInterval(() => {
      current += inc;
      if (current >= finalNumber) {
        number.textContent = finalNumber;
        clearInterval(timer);
      } else {
        number.textContent = current;
      }
    }, 50);
  });
}

// Hover filas
function bindRowHover() {
  document.querySelectorAll('tbody tr').forEach(row => {
    row.addEventListener('mouseenter', function () {
      this.style.transform = 'translateX(8px) scale(1.01)';
    });
    row.addEventListener('mouseleave', function () {
      this.style.transform = 'translateX(0) scale(1)';
    });
  });
}

// Crear modal si no existe
function ensureModal() {
  if (document.getElementById('videoModal')) return;

  const modal = document.createElement('div');
  modal.id = 'videoModal';
  modal.style.position = 'fixed';
  modal.style.inset = '0';
  modal.style.background = 'rgba(0,0,0,0.6)';
  modal.style.display = 'none';
  modal.style.alignItems = 'center';
  modal.style.justifyContent = 'center';
  modal.style.zIndex = '9999';

  modal.innerHTML = `
    <div style="
      width: min(900px, 95vw);
      background: linear-gradient(145deg, #000000, #1C1C1C);
      border: 1px solid rgba(245, 82, 44, 0.2);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 20px 40px rgba(0,0,0,.4);
      position: relative;">
      <button id="closeModal" style="
        position:absolute;right:12px;top:12px;border:none;border-radius:10px;
        padding:8px 12px;cursor:pointer;font-weight:700;
        background:linear-gradient(135deg,#CCCCCC,#999999);color:#000;">✖</button>

      <div id="modalLoading" style="color:#ccc;text-align:center;margin-bottom:8px;display:none">
        Cargando…
      </div>
      <video id="modalVideo" controls style="width:100%;border-radius:12px;background:#000"></video>
    </div>`;
  document.body.appendChild(modal);

  // Cerrar al click fuera del contenido
  modal.addEventListener('click', (e) => {
    if (e.target.id === 'videoModal') hideModal();
  });
  // Cerrar botón
  document.getElementById('closeModal').addEventListener('click', hideModal);
  // Cerrar con ESC
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideModal();
  });
}

function showModal(url) {
  ensureModal();
  const modal = document.getElementById('videoModal');
  const video = document.getElementById('modalVideo');
  const loading = document.getElementById('modalLoading');

  // Limpieza previa
  video.pause();
  video.removeAttribute('src');
  video.load();

  loading.style.display = 'block';
  video.src = url;

  const onLoaded = () => {
    loading.style.display = 'none';
    video.removeEventListener('loadedmetadata', onLoaded);
  };
  video.addEventListener('loadedmetadata', onLoaded);

  // Reintento único si falla (URL firmada caducó)
  let retried = false;
  video.addEventListener('error', async () => {
    if (retried) return;
    retried = true;
    loading.style.display = 'block';
    try {
      const refreshed = await fetchSignedUrl(video.dataset.id);
      if (refreshed) {
        video.src = refreshed;
        video.load();
      } else {
        loading.style.display = 'none';
      }
    } catch {
      loading.style.display = 'none';
    }
  }, { once: true });

  video.dataset.id = video.dataset.id || ''; // no-op si no hay id
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden'; // bloquear scroll fondo
}

function hideModal() {
  const modal = document.getElementById('videoModal');
  const video = document.getElementById('modalVideo');
  const loading = document.getElementById('modalLoading');
  if (video) {
    video.pause();
    video.removeAttribute('src');
    video.load();
  }
  if (loading) loading.style.display = 'none';
  if (modal) modal.style.display = 'none';
  document.body.style.overflow = ''; // restaurar scroll
}

// Pide URL firmada y muestra modal
function bindPlayButtons() {
  document.querySelectorAll('.btn-play').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-id');
      if (!id) return;
      try {
        const url = await fetchSignedUrl(id);
        if (url) {
          // Guardamos el id en el video para un posible reintento
          ensureModal();
          const video = document.getElementById('modalVideo');
          video.dataset.id = id;
          showModal(url);
        }
      } catch (e) {
        alert('Error al preparar la reproducción. Intenta de nuevo.');
        console.error(e);
      }
    });
  });
}

async function fetchSignedUrl(id) {
  const resp = await fetch(`/admin/videos/${encodeURIComponent(id)}/signed-url?ts=${Date.now()}`, {
    cache: 'no-store'
  });
  if (!resp.ok) throw new Error('No se pudo obtener URL firmada');
  const data = await resp.json();
  return data && data.url ? data.url : null;
}

// ======= REFRESCO EN TIEMPO CASI REAL (polling ligero) =======
// Devuelve los IDs visibles
function getVisibleVideoIds() {
  return Array.from(document.querySelectorAll('tbody tr[data-video-id]'))
    .map(tr => parseInt(tr.getAttribute('data-video-id'), 10))
    .filter(Boolean);
}

// Render helpers para los chips según tu HTML actual
function renderEstadoIA(estado) {
  switch (estado) {
    case 'completado':
      return '<i class="fas fa-check-circle"></i> Completado';
    case 'procesando':
      return '<i class="fas fa-spinner fa-spin"></i> Procesando';
    case 'error':
      return '<i class="fas fa-exclamation-triangle"></i> Error';
    default:
      return '<i class="fas fa-hourglass-half"></i> Pendiente';
  }
}

function renderEstadoAdmin(estado) {
  switch (estado) {
    case 'aceptado':
      return '<i class="fas fa-check-circle"></i> Aceptado';
    case 'rechazado':
      return '<i class="fas fa-times-circle"></i> Rechazado';
    default:
      return '<i class="fas fa-clock"></i> Sin Revisar';
  }
}

// Aplica el estado al DOM con tus clases .estado-ia y .estado-admin
function applyVideoStatus(v) {
  const row = document.querySelector(`tbody tr[data-video-id="${v.id}"]`);
  if (!row) return;

  const iaSpan  = row.querySelector('.estado-ia');
  const admSpan = row.querySelector('.estado-admin');

  if (iaSpan) {
    iaSpan.className = `estado-ia ${v.estado_ia || ''}`;   // mantiene las clases para estilo
    iaSpan.innerHTML = renderEstadoIA(v.estado_ia);
    iaSpan.dataset.estado = v.estado_ia || '';             // opcional para CSS
  }

  if (admSpan) {
    admSpan.className = `estado-admin ${v.estado || ''}`;
    admSpan.innerHTML = renderEstadoAdmin(v.estado);
    admSpan.dataset.estado = v.estado || '';
  }
}

// Llama al endpoint y actualiza
async function pollStatuses() {
  const ids = getVisibleVideoIds();
  if (!ids.length) return;

  try {
    const resp = await fetch(`/admin/videos/status?ids=${encodeURIComponent(ids.join(','))}`, { cache: 'no-store' });
    if (!resp.ok) return;
    const data = await resp.json();
    (data.videos || []).forEach(applyVideoStatus);
  } catch (e) {
    console.warn('Polling error:', e);
  }
}

// Arranca polling y re-enlaza comportamientos si cambian filas
function startRealtimePolling(intervalMs = 15000) {
  pollStatuses();
  setInterval(pollStatuses, intervalMs);

  const tbody = document.querySelector('tbody');
  if (tbody && 'MutationObserver' in window) {
    const mo = new MutationObserver(() => {
      bindRowHover();
      bindPlayButtons();
    });
    mo.observe(tbody, { childList: true });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setTimeout(animateNumbers, 500);
  bindRowHover();
  bindPlayButtons();
  startRealtimePolling();
});

