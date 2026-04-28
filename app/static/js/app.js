/* ============================================================
 * Recipe Advisor Site Reliability Dashboard 클라이언트 스크립트
 *
 * 1) QueryRunner: 쿼리 실행 + DataTables 갱신 + 자동갱신 + 스피너 + CSV
 *    - 모든 페이지(통합 대시보드/개별 페이지)에서 동일하게 재사용
 *    - 탭 전환으로 인한 race condition 방어 처리 포함
 *    - race 발생 시 사용자에게 명시적으로 표시 (배지 + 토스트)
 * 2) LogPanel: 하단 로그 패널 폴링/렌더
 * 3) Toast: race / 알림용 우측 상단 토스트
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

  // 자동 실행 안내 placeholder (탭 전환 시 잠깐 보였다가 결과로 교체됨)
  const PLACEHOLDER_HTML =
    '<thead><tr><th class="placeholder-cell">⏳ 쿼리를 자동 실행 중입니다...</th></tr></thead><tbody></tbody>';

  // ============================================================
  // Toast — 우측 상단 알림 (race 상태 등)
  // ============================================================
  const Toast = {
    containerId: 'toast-container',
    _ensureContainer() {
      let el = document.getElementById(this.containerId);
      if (!el) {
        el = document.createElement('div');
        el.id = this.containerId;
        el.className = 'toast-container';
        document.body.appendChild(el);
      }
      return el;
    },
    show(message, opts = {}) {
      const { level = 'info', durationMs = 3000, icon } = opts;
      const container = this._ensureContainer();
      const t = document.createElement('div');
      t.className = `toast toast-${level}`;
      const iconHtml = icon
        ? `<span class="toast-icon" aria-hidden="true">${escapeHtml(icon)}</span>`
        : '';
      t.innerHTML =
        iconHtml +
        `<span class="toast-msg">${escapeHtml(message)}</span>` +
        `<button type="button" class="toast-close" aria-label="닫기">×</button>`;
      const closeBtn = t.querySelector('.toast-close');
      const removeFn = () => {
        t.classList.add('toast-leaving');
        setTimeout(() => { if (t.parentNode) t.parentNode.removeChild(t); }, 220);
      };
      closeBtn.addEventListener('click', removeFn);
      container.appendChild(t);
      // mount 애니메이션
      requestAnimationFrame(() => t.classList.add('toast-shown'));
      if (durationMs > 0) setTimeout(removeFn, durationMs);
    },
  };

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
     * @param {boolean} [opts.showRaceToast=true] - race 발생 시 토스트 표시 여부
     */
    constructor(opts) {
      this.root = opts.rootEl;
      this.source = opts.source;
      this.queryId = opts.queryId;
      this.intervalMs = opts.autoRefreshIntervalMs || 10000;
      this.paramsCollector = opts.paramsCollector || (() => ({}));
      this.pageLength = opts.pageLength || 25;
      this.showRaceToast = opts.showRaceToast !== false;

      this.tableEl = this.root.querySelector('[data-role="table"]');
      this.tableWrapEl = this.tableEl ? this.tableEl.parentElement : null;
      this.refreshBtn = this.root.querySelector('[data-role="refresh"]');
      this.autoCheck = this.root.querySelector('[data-role="auto-refresh"]');
      this.spinner = this.root.querySelector('[data-role="spinner"]');
      this.elapsedEl = this.root.querySelector('[data-role="elapsed"]');
      this.errorEl = this.root.querySelector('[data-role="error"]');
      this.statusBadgeEl = this.root.querySelector('[data-role="status-badge"]');
      this.cancelCountEl = this.root.querySelector('[data-role="cancel-count"]');
      this.cancelCountNumEl = this.cancelCountEl
        ? this.cancelCountEl.querySelector('.cancel-count-num')
        : null;

      this.dataTable = null;
      this.timer = null;
      this.inFlight = false;
      this._destroyed = false;
      this._runToken = 0;          // 매 run() 호출마다 증가; 이전 run의 응답 무시 판별용
      this._abortCtrl = null;       // 현재 in-flight fetch 의 AbortController
      this._cancelledCount = 0;     // 사용자에게 표시되는 누적 race 횟수
      this._supersedeTimer = null;  // "이전 요청 취소됨" 배지 자동 해제 타이머

      this._onRefreshClick = () => this.run();
      this._onAutoChange = () => this._applyAutoRefresh();
    }

    init({ runOnLoad = true } = {}) {
      if (this._destroyed) return;
      if (this.refreshBtn) this.refreshBtn.addEventListener('click', this._onRefreshClick);
      if (this.autoCheck) {
        this.autoCheck.checked = false; // 항상 OFF 가 기본
        this.autoCheck.addEventListener('change', this._onAutoChange);
      }
      // 초기 placeholder
      if (this.tableEl) this.tableEl.innerHTML = PLACEHOLDER_HTML;
      this._setStatusBadge('idle');
      if (runOnLoad) this.run();
    }

    destroy() {
      if (this._destroyed) return;
      this._destroyed = true;

      // 1) 자동갱신 타이머 정지
      this._stopTimer();
      if (this._supersedeTimer) { clearTimeout(this._supersedeTimer); this._supersedeTimer = null; }

      // 2) in-flight fetch 가 있으면 취소(응답 도착 후 _renderTable 호출 차단)
      if (this._abortCtrl) {
        try { this._abortCtrl.abort(); } catch (_) {}
        this._abortCtrl = null;
      }

      // 3) 이벤트 리스너 해제
      if (this.refreshBtn) this.refreshBtn.removeEventListener('click', this._onRefreshClick);
      if (this.autoCheck) this.autoCheck.removeEventListener('change', this._onAutoChange);

      // 4) DataTables 인스턴스 제거 — destroy(false) 로 <table> 노드 자체는 보존
      if (this.dataTable) {
        try { this.dataTable.destroy(false); } catch (_) {}
        this.dataTable = null;
      }

      // 5) 빈 placeholder 로 리셋 (요소가 살아있을 때만)
      if (this.tableEl && this.tableEl.isConnected) {
        try { this.tableEl.innerHTML = PLACEHOLDER_HTML; } catch (_) {}
      }

      // 6) 상태 영역 초기화
      if (this.elapsedEl) this.elapsedEl.textContent = '';
      if (this.errorEl) { this.errorEl.textContent = ''; this.errorEl.hidden = true; }
      if (this.spinner) this.spinner.hidden = true;
      this._setLoadingDim(false);
      this._setStatusBadge('idle');
    }

    _applyAutoRefresh() {
      if (this._destroyed) return;
      if (this.autoCheck && this.autoCheck.checked) this._startTimer();
      else this._stopTimer();
    }

    _startTimer() {
      this._stopTimer();
      this.timer = setInterval(() => {
        if (this._destroyed) return;
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

    /**
     * 상태 배지 표시.
     *   state: 'idle' | 'loading' | 'superseded' | 'error' | 'ok'
     *   text:  배지에 표시할 텍스트 (생략 시 기본 텍스트)
     */
    _setStatusBadge(state, text) {
      const el = this.statusBadgeEl;
      if (!el) return;
      const labels = {
        idle:        '',
        loading:     '실행 중',
        superseded:  '이전 요청 취소 · 재실행',
        error:       '실패',
        ok:          '완료',
      };
      const label = (text != null) ? text : labels[state];
      el.dataset.state = state;
      el.textContent = label || '';
      el.hidden = !label;
    }

    _setLoadingDim(on) {
      if (this.tableWrapEl) {
        this.tableWrapEl.classList.toggle('is-loading', !!on);
      }
      if (this.tableEl) {
        this.tableEl.classList.toggle('is-loading', !!on);
      }
    }

    _bumpCancelCount() {
      this._cancelledCount += 1;
      if (this.cancelCountEl) {
        if (this.cancelCountNumEl) {
          this.cancelCountNumEl.textContent = String(this._cancelledCount);
        } else {
          this.cancelCountEl.textContent = String(this._cancelledCount);
        }
        this.cancelCountEl.hidden = false;
        // 펄스 효과 잠깐 부여
        this.cancelCountEl.classList.remove('pulse');
        // 강제 reflow 로 애니메이션 재시작
        // eslint-disable-next-line no-unused-expressions
        this.cancelCountEl.offsetWidth;
        this.cancelCountEl.classList.add('pulse');
      }
    }

    async run() {
      if (this._destroyed) return;

      // 새 실행 시작 — 이전 in-flight 가 있으면 취소
      const hadInFlight = this.inFlight && !!this._abortCtrl;
      if (hadInFlight) {
        try { this._abortCtrl.abort(); } catch (_) {}
        this._bumpCancelCount();
        // 사용자에게 즉시 알림: 배지 + 토스트
        this._setStatusBadge('superseded');
        if (this._supersedeTimer) clearTimeout(this._supersedeTimer);
        this._supersedeTimer = setTimeout(() => {
          // 진행중이면 다시 loading 으로 표시 (run 메서드가 그 사이 setStatus 했을 수도)
          if (!this._destroyed && this.inFlight) this._setStatusBadge('loading');
          else if (!this._destroyed) this._setStatusBadge('idle');
          this._supersedeTimer = null;
        }, 1500);
        if (this.showRaceToast) {
          Toast.show(
            `이전 ${this.source.toUpperCase()} 쿼리(${this.queryId})를 취소하고 새 쿼리로 다시 실행합니다.`,
            { level: 'warn', icon: '⚠', durationMs: 2800 }
          );
        }
      }

      const token = ++this._runToken;
      const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
      this._abortCtrl = ctrl;

      this.inFlight = true;
      this._setError(null);
      this._setSpinner(true);
      this._setLoadingDim(true);
      // race 직후 superseded 표시 중이면 잠깐 유지, 아니면 loading 표시
      if (!hadInFlight) this._setStatusBadge('loading');

      const params = this.paramsCollector() || {};
      const url = `/${this.source}/query/${encodeURIComponent(this.queryId)}${buildQueryString(params)}`;

      const startedAt = performance.now();
      try {
        const res = await fetch(url, {
          headers: { 'Accept': 'application/json' },
          signal: ctrl ? ctrl.signal : undefined,
        });

        // 도중에 destroy 또는 새 run 이 들어왔다면 결과 폐기
        if (this._destroyed || token !== this._runToken) return;

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

        // 응답 본문 파싱 후 한 번 더 체크
        if (this._destroyed || token !== this._runToken) return;

        this._renderTable(data);
        const ms = data.elapsed_ms != null ? data.elapsed_ms : Math.round(performance.now() - startedAt);
        if (this.elapsedEl) {
          this.elapsedEl.textContent = `${fmtElapsed(ms)} · ${data.row_count}행`;
        }
        this._setStatusBadge('ok');
        // ok 배지는 1.6초 후 idle 로 자동 전환 (조용한 상태)
        setTimeout(() => {
          if (!this._destroyed && this._runToken === token && !this.inFlight) {
            this._setStatusBadge('idle');
          }
        }, 1600);
      } catch (err) {
        // AbortError 는 의도적 취소이므로 무시 (race 발생; 새 run 이 이미 동작 중)
        if (err && (err.name === 'AbortError' || err.code === 20)) return;
        if (this._destroyed || token !== this._runToken) return;
        this._setError(`쿼리 실패: ${err.message || err}`);
        if (this.elapsedEl) this.elapsedEl.textContent = '';
        this._setStatusBadge('error');
      } finally {
        if (token === this._runToken) {
          this.inFlight = false;
          this._abortCtrl = null;
          if (!this._destroyed) {
            this._setSpinner(false);
            this._setLoadingDim(false);
          }
        }
      }
    }

    _renderTable(data) {
      // 안전장치: destroy 됐거나 테이블 요소가 사라졌다면 그리지 않는다
      if (this._destroyed) return;
      if (!this.tableEl || !this.tableEl.isConnected) return;

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
        if (this.dataTable) { try { this.dataTable.destroy(false); } catch (_) {} this.dataTable = null; }
        if (this.tableEl && this.tableEl.isConnected) {
          this.tableEl.innerHTML = '<thead><tr><th class="placeholder-cell">결과 없음</th></tr></thead><tbody></tbody>';
        }
        this._cachedColumns = null;
        return;
      }

      // 같은 컬럼 구성이면 데이터만 갱신, 아니면 재초기화
      const sameColumns = this._sameColumns(columns);
      if (this.dataTable && sameColumns) {
        try {
          this.dataTable.clear().rows.add(data.rows || []).draw(false);
        } catch (_) {
          // DataTables 가 죽었으면 재초기화 경로로
          this.dataTable = null;
        }
        if (this.dataTable) return;
      }

      // 재초기화
      if (this.dataTable) {
        try { this.dataTable.destroy(false); } catch (_) {}
        this.dataTable = null;
      }

      // tableEl 재확인 (DataTables.destroy 로 노드가 detach 됐을 가능성)
      if (!this.tableEl || !this.tableEl.isConnected) return;

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

  // ============================================================
  // ChartCard — 통합 대시보드 전용 카드
  //   - source(vnand|dram) 의 query_id 결과를 fetch
  //   - PRODUCT(LAM/TEL/AMAT) 별로 분리된 차트 그룹 렌더링
  //   - 각 PRODUCT 마다 REGULAR / COMPLETE 두 개 막대 차트(상하 분리, 옵션 c)
  //   - X축: TKIN_TIME(YYYY-MM-DD)
  //   - QueryRunner 와 동일한 race-UI 패턴(_runToken, AbortController, 토스트, 배지)
  // ============================================================
  class ChartCard {
    /**
     * @param {Object} opts
     * @param {HTMLElement} opts.rootEl
     * @param {string} opts.source       - "vnand" | "dram"
     * @param {string} opts.queryId      - 보통 "recent_parsing_results"
     * @param {string[]} opts.products   - ["LAM", "TEL"] 등
     * @param {number} [opts.autoRefreshIntervalMs=10000]
     * @param {boolean} [opts.showRaceToast=true]
     */
    constructor(opts) {
      this.root = opts.rootEl;
      this.source = opts.source;
      this.queryId = opts.queryId;
      this.products = Array.isArray(opts.products) ? opts.products : [];
      this.intervalMs = opts.autoRefreshIntervalMs || 10000;
      this.showRaceToast = opts.showRaceToast !== false;

      this.refreshBtn = this.root.querySelector('[data-role="refresh"]');
      this.autoCheck = this.root.querySelector('[data-role="auto-refresh"]');
      this.spinner = this.root.querySelector('[data-role="spinner"]');
      this.elapsedEl = this.root.querySelector('[data-role="elapsed"]');
      this.errorEl = this.root.querySelector('[data-role="error"]');
      this.statusBadgeEl = this.root.querySelector('[data-role="status-badge"]');
      this.cancelCountEl = this.root.querySelector('[data-role="cancel-count"]');
      this.cancelCountNumEl = this.cancelCountEl
        ? this.cancelCountEl.querySelector('.cancel-count-num')
        : null;
      this.productGroupsEl = this.root.querySelector('[data-role="product-groups"]');

      // PRODUCT -> { regular: Chart, complete: Chart, regularStat, completeStat, groupEl }
      this._charts = {};
      this._initProductSlots();

      this.timer = null;
      this.inFlight = false;
      this._destroyed = false;
      this._runToken = 0;
      this._abortCtrl = null;
      this._cancelledCount = 0;
      this._supersedeTimer = null;

      this._onRefreshClick = () => this.run();
      this._onAutoChange = () => this._applyAutoRefresh();
    }

    _initProductSlots() {
      this.products.forEach(p => {
        const groupEl = this.productGroupsEl
          ? this.productGroupsEl.querySelector(`.product-group[data-product="${p}"]`)
          : null;
        if (!groupEl) return;
        this._charts[p] = {
          groupEl,
          regularCanvas: groupEl.querySelector('[data-role="chart-regular"]'),
          completeCanvas: groupEl.querySelector('[data-role="chart-complete"]'),
          regularStatEl: groupEl.querySelector('[data-role="stat-regular"]'),
          completeStatEl: groupEl.querySelector('[data-role="stat-complete"]'),
          regularChart: null,
          completeChart: null,
        };
      });
    }

    init({ runOnLoad = true } = {}) {
      if (this._destroyed) return;
      if (this.refreshBtn) this.refreshBtn.addEventListener('click', this._onRefreshClick);
      if (this.autoCheck) {
        this.autoCheck.checked = false;
        this.autoCheck.addEventListener('change', this._onAutoChange);
      }
      this._setStatusBadge('idle');
      if (runOnLoad) this.run();
    }

    destroy() {
      if (this._destroyed) return;
      this._destroyed = true;
      this._stopTimer();
      if (this._supersedeTimer) { clearTimeout(this._supersedeTimer); this._supersedeTimer = null; }
      if (this._abortCtrl) {
        try { this._abortCtrl.abort(); } catch (_) {}
        this._abortCtrl = null;
      }
      if (this.refreshBtn) this.refreshBtn.removeEventListener('click', this._onRefreshClick);
      if (this.autoCheck) this.autoCheck.removeEventListener('change', this._onAutoChange);
      Object.values(this._charts).forEach(slot => {
        if (slot.regularChart) { try { slot.regularChart.destroy(); } catch (_) {} slot.regularChart = null; }
        if (slot.completeChart) { try { slot.completeChart.destroy(); } catch (_) {} slot.completeChart = null; }
      });
      if (this.elapsedEl) this.elapsedEl.textContent = '';
      if (this.errorEl) { this.errorEl.textContent = ''; this.errorEl.hidden = true; }
      if (this.spinner) this.spinner.hidden = true;
      this._setLoadingDim(false);
      this._setStatusBadge('idle');
    }

    _applyAutoRefresh() {
      if (this._destroyed) return;
      if (this.autoCheck && this.autoCheck.checked) this._startTimer();
      else this._stopTimer();
    }

    _startTimer() {
      this._stopTimer();
      this.timer = setInterval(() => {
        if (this._destroyed) return;
        if (!this.inFlight) this.run();
      }, this.intervalMs);
    }

    _stopTimer() {
      if (this.timer) { clearInterval(this.timer); this.timer = null; }
    }

    _setSpinner(on) { if (this.spinner) this.spinner.hidden = !on; }

    _setError(msg) {
      if (!this.errorEl) return;
      if (msg) { this.errorEl.textContent = msg; this.errorEl.hidden = false; }
      else { this.errorEl.textContent = ''; this.errorEl.hidden = true; }
    }

    _setStatusBadge(state, text) {
      const el = this.statusBadgeEl;
      if (!el) return;
      const labels = {
        idle: '', loading: '실행 중',
        superseded: '이전 요청 취소 · 재실행',
        error: '실패', ok: '완료',
      };
      const label = (text != null) ? text : labels[state];
      el.dataset.state = state;
      el.textContent = label || '';
      el.hidden = !label;
    }

    _setLoadingDim(on) {
      if (this.productGroupsEl) {
        this.productGroupsEl.classList.toggle('is-loading', !!on);
      }
    }

    _bumpCancelCount() {
      this._cancelledCount += 1;
      if (this.cancelCountEl) {
        if (this.cancelCountNumEl) this.cancelCountNumEl.textContent = String(this._cancelledCount);
        else this.cancelCountEl.textContent = String(this._cancelledCount);
        this.cancelCountEl.hidden = false;
        this.cancelCountEl.classList.remove('pulse');
        // eslint-disable-next-line no-unused-expressions
        this.cancelCountEl.offsetWidth;
        this.cancelCountEl.classList.add('pulse');
      }
    }

    async run() {
      if (this._destroyed) return;

      const hadInFlight = this.inFlight && !!this._abortCtrl;
      if (hadInFlight) {
        try { this._abortCtrl.abort(); } catch (_) {}
        this._bumpCancelCount();
        this._setStatusBadge('superseded');
        if (this._supersedeTimer) clearTimeout(this._supersedeTimer);
        this._supersedeTimer = setTimeout(() => {
          if (!this._destroyed && this.inFlight) this._setStatusBadge('loading');
          else if (!this._destroyed) this._setStatusBadge('idle');
          this._supersedeTimer = null;
        }, 1500);
        if (this.showRaceToast) {
          Toast.show(
            `이전 ${this.source.toUpperCase()} 차트(${this.queryId})를 취소하고 다시 불러옵니다.`,
            { level: 'warn', icon: '⚠', durationMs: 2800 }
          );
        }
      }

      const token = ++this._runToken;
      const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
      this._abortCtrl = ctrl;

      this.inFlight = true;
      this._setError(null);
      this._setSpinner(true);
      this._setLoadingDim(true);
      if (!hadInFlight) this._setStatusBadge('loading');

      const url = `/${this.source}/query/${encodeURIComponent(this.queryId)}`;
      const startedAt = performance.now();
      try {
        const res = await fetch(url, {
          headers: { 'Accept': 'application/json' },
          signal: ctrl ? ctrl.signal : undefined,
        });
        if (this._destroyed || token !== this._runToken) return;

        if (!res.ok) {
          const text = await res.text().catch(() => '');
          let detail = `HTTP ${res.status}`;
          try { const j = JSON.parse(text); if (j && j.detail) detail = j.detail; }
          catch (_) { if (text) detail = text; }
          throw new Error(detail);
        }
        const data = await res.json();
        if (this._destroyed || token !== this._runToken) return;

        this._renderCharts(data);
        const ms = data.elapsed_ms != null ? data.elapsed_ms : Math.round(performance.now() - startedAt);
        if (this.elapsedEl) {
          this.elapsedEl.textContent = `${fmtElapsed(ms)} · ${data.row_count}행`;
        }
        this._setStatusBadge('ok');
        setTimeout(() => {
          if (!this._destroyed && this._runToken === token && !this.inFlight) {
            this._setStatusBadge('idle');
          }
        }, 1600);
      } catch (err) {
        if (err && (err.name === 'AbortError' || err.code === 20)) return;
        if (this._destroyed || token !== this._runToken) return;
        this._setError(`차트 로드 실패: ${err.message || err}`);
        if (this.elapsedEl) this.elapsedEl.textContent = '';
        this._setStatusBadge('error');
      } finally {
        if (token === this._runToken) {
          this.inFlight = false;
          this._abortCtrl = null;
          if (!this._destroyed) {
            this._setSpinner(false);
            this._setLoadingDim(false);
          }
        }
      }
    }

    /**
     * 행을 PRODUCT 별로 그룹핑.
     * data.columns 안에서 PRODUCT/TKIN_TIME/REGULAR/COMPLETE 컬럼을
     * 대소문자 무시하고 찾는다.
     */
    _groupByProduct(data) {
      const cols = data.columns || [];
      const rows = data.rows || [];
      const findCol = (name) => {
        const target = name.toLowerCase();
        return cols.find(c => String(c).toLowerCase() === target) || null;
      };
      const cProduct = findCol('PRODUCT');
      const cTkin = findCol('TKIN_TIME') || findCol('TKIN-TIME');
      const cRegular = findCol('REGULAR');
      const cComplete = findCol('COMPLETE');

      // PRODUCT -> Map<dateStr, {regular, complete}>
      const groups = {};
      this.products.forEach(p => { groups[p] = new Map(); });

      rows.forEach(r => {
        const product = cProduct ? String(r[cProduct] ?? '').toUpperCase() : '';
        if (!groups[product]) return; // 우리가 보여줄 PRODUCT 가 아니면 무시
        const dateRaw = cTkin ? r[cTkin] : null;
        const dateStr = this._toDateStr(dateRaw);
        if (!dateStr) return;
        const reg = cRegular ? Number(r[cRegular]) || 0 : 0;
        const cpl = cComplete ? Number(r[cComplete]) || 0 : 0;
        const m = groups[product];
        const prev = m.get(dateStr) || { regular: 0, complete: 0 };
        prev.regular += reg;
        prev.complete += cpl;
        m.set(dateStr, prev);
      });

      // 각 PRODUCT 안의 dateMap 을 날짜 오름차순 배열로 변환
      const out = {};
      Object.entries(groups).forEach(([p, m]) => {
        const dates = Array.from(m.keys()).sort();
        out[p] = {
          dates,
          regular: dates.map(d => m.get(d).regular),
          complete: dates.map(d => m.get(d).complete),
        };
      });
      return out;
    }

    _toDateStr(val) {
      if (val == null) return null;
      if (typeof val === 'string') {
        // 이미 'YYYY-MM-DD' 형태이거나 ISO 문자열
        const m = val.match(/^(\d{4}-\d{2}-\d{2})/);
        if (m) return m[1];
        const d = new Date(val);
        if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
        return null;
      }
      if (val instanceof Date) {
        if (isNaN(val.getTime())) return null;
        return val.toISOString().slice(0, 10);
      }
      // 숫자(epoch ms)
      if (typeof val === 'number') {
        const d = new Date(val);
        if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
      }
      return null;
    }

    _renderCharts(data) {
      if (this._destroyed) return;
      if (typeof Chart === 'undefined') {
        this._setError('Chart.js 라이브러리가 로드되지 않았습니다.');
        return;
      }
      const grouped = this._groupByProduct(data);

      this.products.forEach(p => {
        const slot = this._charts[p];
        if (!slot) return;
        const g = grouped[p] || { dates: [], regular: [], complete: [] };
        const sumReg = g.regular.reduce((a, b) => a + b, 0);
        const sumCpl = g.complete.reduce((a, b) => a + b, 0);
        if (slot.regularStatEl) slot.regularStatEl.textContent = `합계 ${this._fmtNum(sumReg)}`;
        if (slot.completeStatEl) slot.completeStatEl.textContent = `합계 ${this._fmtNum(sumCpl)}`;

        this._upsertChart(slot, 'regularChart', slot.regularCanvas, {
          labels: g.dates,
          values: g.regular,
          color: this._colorFor(p, 'regular'),
          label: `${p} REGULAR`,
        });
        this._upsertChart(slot, 'completeChart', slot.completeCanvas, {
          labels: g.dates,
          values: g.complete,
          color: this._colorFor(p, 'complete'),
          label: `${p} COMPLETE`,
        });
      });
    }

    _fmtNum(n) {
      if (n == null) return '0';
      try { return Number(n).toLocaleString('ko-KR'); } catch (_) { return String(n); }
    }

    _colorFor(product, kind) {
      // PRODUCT 별 톤 + REGULAR/COMPLETE 의 명도 차이
      const palette = {
        LAM:  { regular: '#6366f1', complete: '#a78bfa' },
        TEL:  { regular: '#0ea5e9', complete: '#67e8f9' },
        AMAT: { regular: '#10b981', complete: '#6ee7b7' },
      };
      const fallback = { regular: '#64748b', complete: '#cbd5e1' };
      return (palette[product] || fallback)[kind] || fallback.regular;
    }

    _upsertChart(slot, key, canvas, payload) {
      if (!canvas || !canvas.isConnected) return;
      const cfg = {
        type: 'bar',
        data: {
          labels: payload.labels,
          datasets: [{
            label: payload.label,
            data: payload.values,
            backgroundColor: payload.color,
            borderColor: payload.color,
            borderWidth: 0,
            borderRadius: 4,
            maxBarThickness: 28,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 250 },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: 'rgba(15,23,42,0.92)',
              titleColor: '#f8fafc',
              bodyColor: '#e2e8f0',
              padding: 8,
              cornerRadius: 6,
              callbacks: {
                label: (ctx) => `${payload.label}: ${this._fmtNum(ctx.parsed.y)}`,
              },
            },
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { color: '#64748b', font: { size: 11 }, maxRotation: 0, autoSkip: true },
            },
            y: {
              beginAtZero: true,
              grid: { color: 'rgba(148,163,184,0.18)' },
              ticks: {
                color: '#64748b', font: { size: 11 },
                callback: (v) => this._fmtNum(v),
              },
            },
          },
        },
      };

      if (slot[key]) {
        try {
          slot[key].data.labels = cfg.data.labels;
          slot[key].data.datasets[0].data = cfg.data.datasets[0].data;
          slot[key].data.datasets[0].backgroundColor = cfg.data.datasets[0].backgroundColor;
          slot[key].data.datasets[0].borderColor = cfg.data.datasets[0].borderColor;
          slot[key].data.datasets[0].label = cfg.data.datasets[0].label;
          slot[key].update('none');
          return;
        } catch (_) {
          try { slot[key].destroy(); } catch (_) {}
          slot[key] = null;
        }
      }
      try {
        slot[key] = new Chart(canvas.getContext('2d'), cfg);
      } catch (e) {
        // Chart 생성 실패 시 다음 run 에서 재시도
        slot[key] = null;
      }
    }
  }

  // 외부 노출
  window.QueryRunner = QueryRunner;
  window.ChartCard = ChartCard;
  window.Toast = Toast;
})();
