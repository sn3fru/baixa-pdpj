/**
 * Devedor360 v2 - Minimal global JavaScript
 * A maior parte da logica esta inline nos templates via Alpine.js.
 * Este arquivo contem apenas helpers globais reutilizaveis.
 */

// ============================================================================
// Formatters
// ============================================================================

window.D360 = {
  /**
   * Formata bytes para exibicao humana.
   */
  formatBytes(b) {
    if (b == null) return '-';
    if (b < 1024) return b + ' B';
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1024 / 1024).toFixed(1) + ' MB';
  },

  /**
   * Formata numero como moeda BRL.
   */
  formatBRL(value) {
    if (value == null || value === '' || isNaN(value)) return '-';
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency', currency: 'BRL'
    }).format(parseFloat(value));
  },

  /**
   * Formata data ISO para exibicao local.
   */
  formatDate(iso) {
    if (!iso) return '-';
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('pt-BR');
    } catch { return iso; }
  },

  /**
   * Formata timestamp epoch para hora.
   */
  formatTime(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('pt-BR');
  },

  /**
   * Toast notification simples (usa o container #toast-area se existir).
   */
  toast(message, type = 'info') {
    const area = document.getElementById('toast-area');
    if (!area) {
      console.log(`[${type}] ${message}`);
      return;
    }
    const colors = {
      info: 'bg-blue-900/80 border-blue-700 text-blue-300',
      success: 'bg-emerald-900/80 border-emerald-700 text-emerald-300',
      error: 'bg-red-900/80 border-red-700 text-red-300',
      warn: 'bg-yellow-900/80 border-yellow-700 text-yellow-300',
    };
    const el = document.createElement('div');
    el.className = `px-4 py-2 rounded-lg border text-sm mb-2 transition-opacity duration-300 ${colors[type] || colors.info}`;
    el.textContent = message;
    area.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 4000);
  },

  /**
   * Cria Tabulator com defaults do projeto.
   */
  createTable(container, data, columns, opts = {}) {
    return new Tabulator(container, {
      data: data,
      columns: columns,
      layout: "fitDataFill",
      height: opts.height || "600px",
      pagination: true,
      paginationSize: opts.pageSize || 50,
      movableColumns: true,
      placeholder: "Nenhum dado disponivel",
      ...opts,
    });
  },
};

// ============================================================================
// Pipeline status monitor (todas as paginas)
// ============================================================================

(function() {
  let lastRunning = null;
  let keepAliveInterval = null;

  // Keep-alive: manda ping a cada 20s enquanto pipeline roda
  // Previne Heroku de hibernar o dyno durante a execucao
  function startKeepAlive() {
    if (keepAliveInterval) return;
    keepAliveInterval = setInterval(() => {
      fetch('/api/ping').catch(() => {});
    }, 20000);
  }

  function stopKeepAlive() {
    if (keepAliveInterval) {
      clearInterval(keepAliveInterval);
      keepAliveInterval = null;
    }
  }

  async function checkPipelineStatus() {
    const el = document.getElementById('sidebar-pipeline-status');
    if (!el) return;

    try {
      const res = await fetch('/api/status');
      const status = await res.json();

      if (status.running) {
        startKeepAlive();
        const evtCount = status.events_total || 0;
        const lastEvt = status.last_event;
        const lastMsg = lastEvt && lastEvt.data ? (lastEvt.data.message || lastEvt.event || '') : '';
        el.innerHTML = `
          <a href="/pipeline" class="block">
            <div class="flex items-center gap-2 mb-1">
              <div class="animate-spin h-3 w-3 border border-blue-400 border-t-transparent rounded-full"></div>
              <span class="text-xs font-semibold text-blue-400">Pipeline rodando</span>
            </div>
            <p class="text-xs text-gray-500 truncate">${lastMsg.substring(0, 40)}</p>
            <p class="text-xs text-gray-600">${evtCount} eventos</p>
          </a>`;
        lastRunning = true;
      } else {
        stopKeepAlive();
        if (lastRunning === true) {
          // Pipeline acabou de terminar - mostra botao de download
          const lr = status.last_run;
          const statusColor = lr && lr.status === 'completed' ? 'emerald' : 'red';
          const statusText = lr && lr.status === 'completed' ? 'Concluido!' : 'Erro';
          const downloadBtn = lr && lr.status === 'completed'
            ? `<a href="/api/download-zip" class="mt-2 flex items-center gap-1.5 px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs rounded transition">
                 <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                 Baixar ZIP
               </a>`
            : '';
          el.innerHTML = `
            <div>
              <a href="/pipeline" class="block">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-semibold text-${statusColor}-400">${statusText}</span>
                </div>
                <p class="text-xs text-gray-600">Ver detalhes</p>
              </a>
              ${downloadBtn}
            </div>`;
          // Nao limpa automaticamente - usuario precisa ver o botao
        } else if (lastRunning === null) {
          el.innerHTML = '';
        }
        lastRunning = false;
      }
    } catch(e) {
      // Silencioso
    }
  }

  // Verifica a cada 3s
  checkPipelineStatus();
  setInterval(checkPipelineStatus, 3000);
})();

// ============================================================================
// HTMX config
// ============================================================================

document.body.addEventListener('htmx:configRequest', function(e) {
  e.detail.headers['X-Requested-With'] = 'htmx';
});

// ============================================================================
// Tailwind config (cores customizadas)
// ============================================================================
if (typeof tailwind !== 'undefined') {
  tailwind.config = {
    darkMode: 'class',
    theme: {
      extend: {
        colors: {
          gray: {
            950: '#0a0f1a',
          }
        }
      }
    }
  };
}
