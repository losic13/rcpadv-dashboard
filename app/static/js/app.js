/* ============================================================
 * 사내 대시보드 클라이언트 스크립트
 *
 * 1) QueryRunner: 쿼리 실행 + DataTables 갱신 + 자동갱신 + 스피너 + CSV
 *    - 모든 페이지(통합 대시보드/개별 페이지)에서 동일하게 재사용
 * 2) LogPanel: 하단 로그 패널 폴링/렌더
 * ============================================================ */

(function () {
  'use strict';

  // ----- 공용 유틸 -----
  function fmtElapsed(ms) {
    if (ms == null) return '';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  }

  function buildQueryString(params) {
    const usp = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') usp.append(k, v);
    });
    const s = usp.toString();
    return s ? `?${s}` : '';
  }

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ============================================================
  // QueryRunner
  // ============================================================
  class QueryRunner {
    /**
     * @param {Object} opts
     * @param {HTMLElement} opts.rootEl - 카드/페이지 루트 (data-role 요소들 탐색 범위)
     * @param {string} opts.source       - "vnand" | "dram" | "es"
     * @param {string} opts.queryId      - 쿼리 ID
     * @param {number} [opts.autoRefreshIntervalMs=10000]
     * @param {Function} [opts.paramsCollector] - () => {param: value, ...}
     * @param {number} [opts.pageLength=25]
     */
    constructor(opts) {
      this.root = opts.rootEl;
      this.source = opts.source;
      this.queryId = opts.queryId;
      this.intervalMs = opts.autoRefreshIntervalMs || 10000;
      this.paramsCollector = opts.paramsCollector || (() => ({}));
      this.pageLength = opts.pageLength || 25;

      this.tableEl = this.root.querySelector('[data-role="table"]');
      this.refreshBtn = this.root.querySelector('[data-role="refresh"]');
      this.autoCheck = this.root.querySelector('[data-role="auto-refresh"]');
      this.spinner = this.root.querySelector('[data-role="spinner"]');
      this.elapsedEl = this.root.querySelector('[data-role="elapsed"]');
      this.errorEl = this.root.querySelector('[data-role="error"]');

      this.dataTable = null;
      this.timer = null;
      this.inFlight = false;

      this._onRefreshClick = () => this.run();
      this._onAutoChange = () => this._applyAutoRefresh();
    }

    init({ runOnLoad = true } = {}) {
      if (this.refreshBtn) this.refreshBtn.addEventListener('click', this._onRefreshClick);
      if (this.autoCheck) {
        this.autoCheck.checked = false; // 항상 OFF 가 기본
        this.autoCheck.addEventListener('change', this._onAutoChange);
      }
      if (runOnLoad) this.run();
    }

    destroy() {
      this._stopTimer();
      if (this.refreshBtn) this.refreshBtn.removeEventListener('click', this._onRefreshClick);
      if (this.autoCheck) this.autoCheck.removeEventListener('change', this._onAutoChange);
      if (this.dataTable) {
        try { this.dataTable.destroy(true); } catch (e) {}
        this.dataTable = null;
      }
      // 빈 테이블로 리셋
      if (this.tableEl) {
        this.tableEl.innerHTML = '<thead><tr><th>(쿼리를 실행하세요)</th></tr></thead><tbody></tbody>';
      }
    }

    _applyAutoRefresh() {
      if (this.autoCheck && this.autoCheck.checked) this._startTimer();
      else this._stopTimer();
    }

    _startTimer() {
      this._stopTimer();
      this.timer = setInterval(() => {
        if (!this.inFlight) this.run();
      }, this.intervalMs);
    }

    _stopTimer() {
      if (this.timer) {
        clearInterval(this.timer);
        this.timer = null;
      }
    }

    _setSpinner(on) {
      if (!this.spinner) return;
      this.spinner.hidden = !on;
    }

    _setError(msg) {
      if (!this.errorEl) return;
      if (msg) {
        this.errorEl.textContent = msg;
        this.errorEl.hidden = false;
      } else {
        this.errorEl.textContent = '';
        this.errorEl.hidden = true;
      }
    }

    async run() {
      if (this.inFlight) return; // 중복 방지
      this.inFlight = true;
      this._setError(null);
      this._setSpinner(true);

      const params = this.paramsCollector() || {};
      const url = `/${this.source}/query/${encodeURIComponent(this.queryId)}${buildQueryString(params)}`;

      const startedAt = performance.now();
      try {
        const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
        if (!res.ok) {
          const text = await res.text().catch(() => '');
          let detail = `HTTP ${res.status}`;
          try {
            const j = JSON.parse(text);
            if (j && j.detail) detail = j.detail;
          } catch (_) { if (text) detail = text; }
          throw new Error(detail);
        }
        const data = await res.json();
        this._renderTable(data);
        const ms = data.elapsed_ms != null ? data.elapsed_ms : Math.round(performance.now() - startedAt);
        if (this.elapsedEl) {
          this.elapsedEl.textContent = `${fmtElapsed(ms)} · ${data.row_count}행`;
        }
      } catch (err) {
        this._setError(`쿼리 실패: ${err.message || err}`);
        if (this.elapsedEl) this.elapsedEl.textContent = '';
      } finally {
        this._setSpinner(false);
        this.inFlight = false;
      }
    }

    _renderTable(data) {
      const columns = (data.columns || []).map(c => ({
        title: c,
        data: c,
        // 객체/배열은 JSON 으로 직렬화하여 표시 (ES 응답 대응)
        render: (val) => {
          if (val == null) return '';
          if (typeof val === 'object') return escapeHtml(JSON.stringify(val));
          return escapeHtml(val);
        },
        defaultContent: '',
      }));

      // 결과가 0행이고 컬럼도 없는 케이스
      if (columns.length === 0) {
        if (this.dataTable) { try { this.dataTable.destroy(true); } catch (_) {} this.dataTable = null; }
        this.tableEl.innerHTML = '<thead><tr><th>(결과 없음)</th></tr></thead><tbody></tbody>';
        return;
      }

      // 같은 컬럼 구성이면 데이터만 갱신, 아니면 재초기화
      const sameColumns = this._sameColumns(columns);
      if (this.dataTable && sameColumns) {
        this.dataTable.clear().rows.add(data.rows || []).draw(false);
        return;
      }

      // 재초기화
      if (this.dataTable) {
        try { this.dataTable.destroy(true); } catch (_) {}
        this.dataTable = null;
      }

      // thead 재구성 (DataTables 가 인식하도록)
      const thead = '<thead><tr>' +
        columns.map(c => `<th>${escapeHtml(c.title)}</th>`).join('') +
        '</tr></thead><tbody></tbody>';
      this.tableEl.innerHTML = thead;

      this.dataTable = $(this.tableEl).DataTable({
        data: data.rows || [],
        columns: columns,
        dom: '<"dt-top"lBf>rt<"dt-bottom"ip>',
        buttons: [
          { extend: 'csvHtml5', text: 'CSV 내보내기', filename: `${this.source}_${this.queryId}` }
        ],
        pageLength: this.pageLength,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, '전체']],
        order: [],
        deferRender: true,
        language: DATATABLES_KO,
      });

      this._cachedColumns = columns.map(c => c.data);
    }

    _sameColumns(columns) {
      const incoming = columns.map(c => c.data);
      if (!this._cachedColumns) return false;
      if (this._cachedColumns.length !== incoming.length) return false;
      for (let i = 0; i < incoming.length; i++) {
        if (this._cachedColumns[i] !== incoming[i]) return false;
      }
      return true;
    }
  }

  // DataTables 한국어 번역 (간단 버전)
  const DATATABLES_KO = {
    emptyTable: '데이터가 없습니다.',
    info: '_TOTAL_ 건 중 _START_ ~ _END_',
    infoEmpty: '0 건',
    infoFiltered: '(전체 _MAX_ 건 중 검색)',
    lengthMenu: '_MENU_ 건씩 보기',
    loadingRecords: '로딩 중...',
    processing: '처리 중...',
    search: '검색:',
    zeroRecords: '검색 결과 없음',
    paginate: { first: '처음', last: '마지막', next: '다음', previous: '이전' },
  };

  // ============================================================
  // LogPanel
  // ============================================================
  const LogPanel = {
    POLL_MS: 5000,
    nextIndex: 0,
    panelEl: null,
    bodyTbody: null,
    countEl: null,

    init() {
      this.panelEl = document.getElementById('log-panel');
      this.bodyTbody = document.getElementById('log-tbody');
      this.countEl = document.getElementById('log-count');
      const toggle = document.getElementById('log-panel-toggle');
      const clearBtn = document.getElementById('log-clear-view');
      if (!this.panelEl || !this.bodyTbody) return;

      toggle.addEventListener('click', (e) => {
        // 화면 지우기 버튼 클릭은 토글 안 함
        if (e.target.closest('#log-clear-view')) return;
        this.panelEl.classList.toggle('collapsed');
      });
      clearBtn.addEventListener('click', () => {
        this.bodyTbody.innerHTML = '';
      });

      this.poll();
      setInterval(() => this.poll(), this.POLL_MS);
    },

    async poll() {
      try {
        const res = await fetch(`/api/logs?since_index=${this.nextIndex}`, {
          headers: { 'Accept': 'application/json' },
          cache: 'no-store',
        });
        if (!res.ok) return;
        const data = await res.json();
        this.nextIndex = data.next_index;
        this.appendLogs(data.logs);
        if (this.countEl) this.countEl.textContent = data.total;
      } catch (_) {
        // 폴링 실패는 무시 (조용히)
      }
    },

    appendLogs(logs) {
      if (!logs || logs.length === 0) return;
      const frag = document.createDocumentFragment();
      logs.forEach(l => {
        const tr = document.createElement('tr');
        tr.className = `log-row level-${escapeHtml(l.level)}`;
        tr.innerHTML =
          `<td class="col-ts">${escapeHtml(l.ts)}</td>` +
          `<td class="col-level">${escapeHtml(l.level)}</td>` +
          `<td class="col-logger">${escapeHtml(l.logger)}</td>` +
          `<td class="col-msg">${escapeHtml(l.message)}</td>`;
        frag.appendChild(tr);
      });
      this.bodyTbody.appendChild(frag);
      // 최근 로그가 보이도록 스크롤
      const body = this.panelEl.querySelector('.log-panel-body');
      if (body) body.scrollTop = body.scrollHeight;
      // 화면 보관량 너무 많아지면 가장 오래된 것 자르기
      const MAX_DOM_ROWS = 1000;
      while (this.bodyTbody.children.length > MAX_DOM_ROWS) {
        this.bodyTbody.removeChild(this.bodyTbody.firstChild);
      }
    },
  };

  // ============================================================
  // Bootstrap
  // ============================================================
  document.addEventListener('DOMContentLoaded', () => {
    LogPanel.init();
  });

  // 외부 노출
  window.QueryRunner = QueryRunner;
})();
