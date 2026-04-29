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
        // 상단: [info 우측 정렬]
        // 하단: [length + CSV + 검색] 한 줄 + [페이지네이션]
        dom: '<"dt-top"<"dt-top-right"i>>rt<"dt-bottom"<"dt-tools"lBf><"dt-bottom-right"p>>',
        buttons: [
          {
            extend: 'csvHtml5',
            text: 'CSV 내보내기',
            titleAttr: 'CSV 파일로 내보내기',
            filename: `${this.source}_${this.queryId}`,
          }
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
    info: '_START_–_END_ / 총 _TOTAL_건',
    infoEmpty: '0건',
    infoFiltered: '(전체 _MAX_건 중 검색)',
    lengthMenu: '_MENU_건씩',
    loadingRecords: '로딩 중...',
    processing: '처리 중...',
    search: '',
    searchPlaceholder: '검색...',
    zeroRecords: '검색 결과 없음',
    paginate: { first: '처음', last: '마지막', next: '›', previous: '‹' },
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
  //   - 카드 내부 구조: metric(REGULAR/COMPLETE) 별로 한 개 차트씩, 상하 분리
  //   - 각 차트에는 PRODUCT 별 막대(서로 다른 색)와
  //     PRODUCT 별 이동평균선(마지막 데이터 제외) Line series 가 함께 표시됨
  //   - X축: TKIN_TIME(YYYY-MM-DD)
  //   - QueryRunner 와 동일한 race-UI 패턴(_runToken, AbortController, 토스트, 배지)
  // ============================================================
  const MOVING_AVG_WINDOW = 4; // 이동평균 윈도(최근 N일)

  class ChartCard {
    /**
     * @param {Object} opts
     * @param {HTMLElement} opts.rootEl
     * @param {string} opts.source       - "vnand" | "dram"
     * @param {string} opts.queryId      - 보통 "recent_parsing_results"
     * @param {string[]} opts.products   - ["LAM", "TEL"] 등 (series 로 그려짐)
     * @param {number} [opts.autoRefreshIntervalMs=10000]
     * @param {boolean} [opts.showRaceToast=true]
     * @param {number}  [opts.movingAvgWindow=7] - 이동평균 윈도 크기
     */
    constructor(opts) {
      this.root = opts.rootEl;
      this.source = opts.source;
      this.queryId = opts.queryId;
      this.products = Array.isArray(opts.products) ? opts.products : [];
      this.intervalMs = opts.autoRefreshIntervalMs || 10000;
      this.showRaceToast = opts.showRaceToast !== false;
      this.movingAvgWindow = opts.movingAvgWindow || MOVING_AVG_WINDOW;

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

      // 새 레이아웃: metric-sections 단위
      this.metricSectionsEl = this.root.querySelector('[data-role="metric-sections"]');

      // metric -> { canvas, statEl, legendEl, chart }
      this._charts = {
        regular:  { canvas: null, statEl: null, legendEl: null, chart: null },
        complete: { canvas: null, statEl: null, legendEl: null, chart: null },
      };
      this._initMetricSlots();

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

    _initMetricSlots() {
      const root = this.metricSectionsEl || this.root;
      const findIn = (sel) => root ? root.querySelector(sel) : null;
      this._charts.regular.canvas   = findIn('[data-role="chart-regular"]');
      this._charts.regular.statEl   = findIn('[data-role="stat-regular"]');
      this._charts.regular.legendEl = findIn('[data-role="legend-regular"]');
      this._charts.complete.canvas   = findIn('[data-role="chart-complete"]');
      this._charts.complete.statEl   = findIn('[data-role="stat-complete"]');
      this._charts.complete.legendEl = findIn('[data-role="legend-complete"]');
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
        if (slot && slot.chart) {
          try { slot.chart.destroy(); } catch (_) {}
          slot.chart = null;
        }
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
      if (this.metricSectionsEl) {
        this.metricSectionsEl.classList.toggle('is-loading', !!on);
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
        const prev = m.get(dateStr) || { regularRaw: 0, complete: 0 };
        prev.regularRaw += reg;
        prev.complete += cpl;
        m.set(dateStr, prev);
      });

      // 각 PRODUCT 안의 dateMap 을 날짜 오름차순 배열로 변환.
      // 여기서는 원본 REGULAR / COMPLETE 값을 그대로 노출하고,
      // 표시용 합산(REGULAR + COMPLETE)은 _renderCharts 에서 처리한다.
      const out = {};
      Object.entries(groups).forEach(([p, m]) => {
        const dates = Array.from(m.keys()).sort();
        out[p] = {
          dates,
          regular: dates.map(d => m.get(d).regularRaw || 0),
          complete: dates.map(d => m.get(d).complete || 0),
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

      // 차트 1개당 X축은 모든 PRODUCT 의 합집합 일자 — 정렬된 union
      const labelSet = new Set();
      this.products.forEach(p => {
        const g = grouped[p];
        if (!g) return;
        g.dates.forEach(d => labelSet.add(d));
      });
      const labels = Array.from(labelSet).sort();

      // 각 metric 에 대해 PRODUCT 별 series 만들기
      // - regular 차트: REGULAR + COMPLETE 합산값을 사용 ("초벌파싱 파일 수")
      // - complete 차트: COMPLETE 만 사용                ("본 파싱 파일 수")
      ['regular', 'complete'].forEach(metric => {
        const slot = this._charts[metric];
        if (!slot) return;

        // PRODUCT -> {dates -> value} lookup 으로 변환 후 union 라벨에 맞춰 채움
        const series = this.products.map(p => {
          const g = grouped[p] || { dates: [], regular: [], complete: [] };
          const lookup = new Map();
          g.dates.forEach((d, i) => {
            // 'regular' 메트릭은 "초벌파싱 파일 수" = REGULAR + COMPLETE 합산
            // 'complete' 메트릭은 "본 파싱 파일 수" = COMPLETE 만
            const v = (metric === 'regular')
              ? (Number(g.regular[i]) || 0) + (Number(g.complete[i]) || 0)
              : (Number(g.complete[i]) || 0);
            lookup.set(d, v);
          });
          const values = labels.map(d => lookup.has(d) ? lookup.get(d) : null);
          return {
            product: p,
            values,
            color: this._colorFor(p, metric),
            maColor: this._maColorFor(p, metric),
          };
        });

        // Series 별 일평균 (마지막 데이터 제외) — 차트 헤더 통계
        //   · 마지막 인덱스 값은 제외
        //   · null 은 제외하고 유효 일자 수로만 평균
        //   · 유효 일자 0 이면 — 으로 표시
        const dailyAvgByProduct = series.map(s => {
          const head = s.values.slice(0, Math.max(0, s.values.length - 1));
          const valid = head.filter(v => v != null);
          const avg = valid.length > 0
            ? valid.reduce((a, b) => a + (Number(b) || 0), 0) / valid.length
            : null;
          return { product: s.product, avg };
        });
        if (slot.statEl) {
          // 사용자 요청: 일평균은 정수만 표기 (소수점 버림이 아닌 반올림 — Math.round).
          // 예: 12.4 → 12, 12.6 → 13, null → "—"
          const fmtAvg = (v) => v == null ? '—' : this._fmtNum(Math.round(v));
          // 가독성 향상: "PRODUCT 값" 묶음을 별도 칩으로 wrap 하여 줄바꿈/정렬을 쉽게.
          // 텍스트 노드 직접 조립 — DOM 구조 단순화 및 XSS 회피.
          slot.statEl.innerHTML = '';
          const lead = document.createElement('span');
          lead.className = 'metric-section-stat-lead';
          lead.textContent = '일평균(마지막 제외)';
          slot.statEl.appendChild(lead);
          dailyAvgByProduct.forEach(d => {
            const chip = document.createElement('span');
            chip.className = 'metric-section-stat-chip';
            const name = document.createElement('span');
            name.className = 'metric-section-stat-product';
            name.textContent = String(d.product);
            const val  = document.createElement('span');
            val.className  = 'metric-section-stat-value';
            val.textContent = fmtAvg(d.avg);
            chip.appendChild(name);
            chip.appendChild(val);
            slot.statEl.appendChild(chip);
          });
        }

        // 범례 — 막대 색 + 이동평균선 표시
        if (slot.legendEl) {
          slot.legendEl.innerHTML = series.map(s => (
            `<span class="legend-item">` +
              `<span class="legend-bar" style="background:${s.color}"></span>` +
              `<span class="legend-name">${escapeHtml(s.product)}</span>` +
              `<span class="legend-ma" title="이동평균선 (${this.movingAvgWindow}일, 마지막 데이터 제외)" style="color:${s.maColor}">~MA${this.movingAvgWindow}</span>` +
            `</span>`
          )).join('');
        }

        this._upsertMetricChart(slot, labels, series, metric);
      });
    }

    /**
     * 마지막 데이터를 제외한 이동평균선 계산.
     * - 입력: values (number|null)[] (length = labels.length)
     * - 마지막 인덱스 값은 제외하고 그 앞까지의 시리즈로 이동평균을 계산.
     * - 마지막 인덱스에는 null 을 채워서 라인이 그려지지 않게 한다.
     * - window 내에 null 이 있으면 null 값을 무시하고 존재하는 값들의 평균을 사용.
     *   유효 값이 없으면 null.
     */
    _movingAverageExcludingLast(values, windowSize) {
      const n = values.length;
      const out = new Array(n).fill(null);
      if (n <= 1) return out;
      const last = n - 1;
      for (let i = 0; i < last; i++) {
        const start = Math.max(0, i - windowSize + 1);
        let sum = 0, cnt = 0;
        for (let j = start; j <= i; j++) {
          const v = values[j];
          if (v != null && !isNaN(v)) { sum += Number(v); cnt += 1; }
        }
        out[i] = cnt > 0 ? sum / cnt : null;
      }
      // out[last] 는 null 로 유지 — 마지막 데이터는 이동평균선에서 제외
      return out;
    }

    _fmtNum(n) {
      if (n == null) return '0';
      try {
        const num = Number(n);
        if (!Number.isFinite(num)) return '0';
        if (Math.abs(num - Math.round(num)) < 1e-9) {
          return Math.round(num).toLocaleString('ko-KR');
        }
        return num.toLocaleString('ko-KR', { maximumFractionDigits: 2 });
      } catch (_) { return String(n); }
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

    _maColorFor(product, kind) {
      // 이동평균선은 막대와 같은 색 계열을 쓰되 막대보다 한 단계 연하게.
      // (이전 톤보다는 약간 진하게 — 막대와 라인이 명확히 구별되면서 연관성도 보이도록)
      const palette = {
        LAM:  { regular: '#818cf8', complete: '#c4b5fd' },
        TEL:  { regular: '#38bdf8', complete: '#a5f3fc' },
        AMAT: { regular: '#34d399', complete: '#86efac' },
      };
      const fallback = { regular: '#94a3b8', complete: '#cbd5e1' };
      return (palette[product] || fallback)[kind] || fallback.regular;
    }

    /**
     * REGULAR 또는 COMPLETE 한 차트를 upsert.
     * datasets:
     *   - PRODUCT 마다 type:'bar' 1개
     *   - PRODUCT 마다 type:'line' 1개 (이동평균, 마지막 데이터 제외)
     */
    _upsertMetricChart(slot, labels, series, metric) {
      const canvas = slot.canvas;
      if (!canvas || !canvas.isConnected) return;

      const datasets = [];
      // 막대 series 먼저
      series.forEach(s => {
        datasets.push({
          type: 'bar',
          label: s.product,
          data: s.values,
          backgroundColor: s.color,
          borderColor: s.color,
          borderWidth: 0,
          borderRadius: 4,
          maxBarThickness: 22,
          order: 2,
          stack: undefined, // 그룹형(나란히)
          _kind: 'bar',
          _product: s.product,
        });
      });
      // 이동평균 line series
      series.forEach(s => {
        const ma = this._movingAverageExcludingLast(s.values, this.movingAvgWindow);
        datasets.push({
          type: 'line',
          label: `${s.product} MA${this.movingAvgWindow}`,
          data: ma,
          borderColor: s.maColor,
          backgroundColor: s.maColor,
          borderWidth: 2,
          borderDash: [6, 4],
          tension: 0.3,
          pointRadius: 0,
          pointHoverRadius: 4,
          spanGaps: true,
          fill: false,
          order: 1, // 막대 위에 그려짐
          _kind: 'ma',
          _product: s.product,
        });
      });

      const fmt = (v) => this._fmtNum(v);
      const cfg = {
        type: 'bar',
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 250 },
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: false }, // 자체 범례 사용
            tooltip: {
              backgroundColor: 'rgba(15,23,42,0.92)',
              titleColor: '#f8fafc',
              bodyColor: '#e2e8f0',
              padding: 8,
              cornerRadius: 6,
              callbacks: {
                label: (ctx) => {
                  const ds = ctx.dataset || {};
                  const v = ctx.parsed != null ? ctx.parsed.y : null;
                  if (v == null) return null; // 표시 안 함
                  const tag = ds._kind === 'ma' ? `MA${this.movingAvgWindow}` : '';
                  const name = ds._product || ds.label || '';
                  return `${name}${tag ? ' ' + tag : ''}: ${fmt(v)}`;
                },
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
                callback: (v) => fmt(v),
              },
            },
          },
        },
      };

      // upsert: 동일 차트 인스턴스 재사용 (datasets 길이/구조가 같으면 update 만)
      if (slot.chart) {
        try {
          slot.chart.data.labels = labels;
          // datasets 의 갯수/순서가 같다고 가정 (PRODUCT 가 변하지 않음)
          if (slot.chart.data.datasets.length === datasets.length) {
            datasets.forEach((d, i) => {
              const cur = slot.chart.data.datasets[i];
              cur.type = d.type;
              cur.label = d.label;
              cur.data = d.data;
              cur.backgroundColor = d.backgroundColor;
              cur.borderColor = d.borderColor;
              cur.borderWidth = d.borderWidth;
              cur.borderDash = d.borderDash;
              cur.tension = d.tension;
              cur.pointRadius = d.pointRadius;
              cur.pointHoverRadius = d.pointHoverRadius;
              cur.spanGaps = d.spanGaps;
              cur.fill = d.fill;
              cur.borderRadius = d.borderRadius;
              cur.maxBarThickness = d.maxBarThickness;
              cur.order = d.order;
              cur._kind = d._kind;
              cur._product = d._product;
            });
          } else {
            slot.chart.data.datasets = datasets;
          }
          slot.chart.update('none');
          return;
        } catch (_) {
          try { slot.chart.destroy(); } catch (_) {}
          slot.chart = null;
        }
      }
      try {
        slot.chart = new Chart(canvas.getContext('2d'), cfg);
      } catch (e) {
        slot.chart = null;
      }
    }
  }

  // ============================================================
  // CountCard
  //   - 통합 대시보드의 "카운트 카드" 전용 컨트롤러.
  //   - 임의 쿼리(GET /{source}/query/{queryId}) 의 응답 row_count 를
  //     큰 숫자로 표시한다.
  //   - QueryRunner / ChartCard 와 동일한 race-UI 패턴 사용
  //     (in-flight abort + supersede 배지 + 누적 취소 카운터).
  // ============================================================
  class CountCard {
    /**
     * @param {Object} opts
     * @param {HTMLElement} opts.rootEl
     * @param {string} opts.source                       - "vnand" | "dram" | "es"
     * @param {string} opts.queryId
     * @param {number} [opts.autoRefreshIntervalMs=10000]
     * @param {boolean} [opts.showRaceToast=true]
     */
    constructor(opts) {
      this.root = opts.rootEl;
      this.source = opts.source;
      this.queryId = opts.queryId;
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
      this.displayEl = this.root.querySelector('[data-role="count-display"]');
      this.valueEl = this.root.querySelector('[data-role="count-value"]');

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
      // hover 핸들러 해제 (LoginTodayCard 만 있고 CountCard 에는 없음 — 안전 조건)
      if (Array.isArray(this._hoverHandlers)) {
        this._hoverHandlers.forEach(({ el, show, hide }) => {
          if (!el) return;
          el.removeEventListener('mouseenter', show);
          el.removeEventListener('mouseleave', hide);
          el.removeEventListener('focusin',    show);
          el.removeEventListener('focusout',   hide);
        });
        this._hoverHandlers = [];
      }
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
      if (this.displayEl) this.displayEl.classList.toggle('is-loading', !!on);
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

    _fmtNum(n) {
      if (n == null) return '—';
      try { return Number(n).toLocaleString('ko-KR'); }
      catch (_) { return String(n); }
    }

    _setValue(n) {
      if (!this.valueEl) return;
      this.valueEl.textContent = this._fmtNum(n);
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
            `이전 ${this.source.toUpperCase()} 카운트(${this.queryId})를 취소하고 다시 불러옵니다.`,
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
          let detail = `HTTP ${res.status}`;
          try {
            const j = await res.json();
            if (j && j.detail) detail = j.detail;
          } catch (_) {}
          throw new Error(detail);
        }
        const data = await res.json();
        if (this._destroyed || token !== this._runToken) return;

        // row_count 우선, 없으면 rows.length 폴백
        const count = (typeof data.row_count === 'number')
          ? data.row_count
          : (Array.isArray(data.rows) ? data.rows.length : null);
        this._setValue(count);

        const elapsed = (typeof data.elapsed_ms === 'number')
          ? data.elapsed_ms
          : Math.round(performance.now() - startedAt);
        if (this.elapsedEl) this.elapsedEl.textContent = fmtElapsed(elapsed);
        this._setStatusBadge('ok');
      } catch (err) {
        if (err && (err.name === 'AbortError' || err.code === 20)) return; // 취소된 건 무시
        if (this._destroyed || token !== this._runToken) return;
        this._setError(err && err.message ? err.message : String(err));
        this._setStatusBadge('error');
      } finally {
        if (token === this._runToken) {
          this.inFlight = false;
          this._abortCtrl = null;
          this._setSpinner(false);
          this._setLoadingDim(false);
        }
      }
    }
  }

  // ============================================================
  // LoginTodayCard
  //   - 통합 대시보드의 "오늘 접속자수" 카드 전용 컨트롤러.
  //   - 한 카드 안에 [전체 / 고객] 두 컬럼을 동시에 표시한다.
  //   - GET /login-history/today 한 번 호출 → 응답에서
  //       data.all.distinct      → 좌측 큰 숫자 (전체 접속자)
  //       data.all.total         → 좌측 보조 숫자 (전체 총 로그인)
  //       data.customer.distinct → 우측 큰 숫자 (고객 접속자)
  //       data.customer.total    → 우측 보조 숫자 (고객 총 로그인)
  //     양쪽 컬럼을 같은 응답에서 동시에 채운다.
  //   - CountCard 와 동일한 race-UI 패턴(in-flight abort, supersede 배지,
  //     누적 취소 카운터)을 재활용하기 위해 같은 형태로 구현한다.
  //   - "오늘" 의 카운트는 빠르게 변하지 않으므로 자동 갱신 기본 1분.
  // ============================================================
  class LoginTodayCard {
    /**
     * @param {Object} opts
     * @param {HTMLElement} opts.rootEl
     * @param {number} [opts.autoRefreshIntervalMs=60000]
     * @param {boolean} [opts.showRaceToast=false]   - 한 페이지에 여러 카드가
     *        동시에 갱신되면서 같은 토스트가 두 번 뜨는 것을 막기 위해 기본 false.
     */
    constructor(opts) {
      this.root = opts.rootEl;
      this.intervalMs = opts.autoRefreshIntervalMs || 60000;
      this.showRaceToast = !!opts.showRaceToast;

      this.refreshBtn       = this.root.querySelector('[data-role="refresh"]');
      this.autoCheck        = this.root.querySelector('[data-role="auto-refresh"]');
      this.spinner          = this.root.querySelector('[data-role="spinner"]');
      this.elapsedEl        = this.root.querySelector('[data-role="elapsed"]');
      this.errorEl          = this.root.querySelector('[data-role="error"]');
      this.statusBadgeEl    = this.root.querySelector('[data-role="status-badge"]');
      this.cancelCountEl    = this.root.querySelector('[data-role="cancel-count"]');
      this.cancelCountNumEl = this.cancelCountEl
        ? this.cancelCountEl.querySelector('.cancel-count-num')
        : null;

      // 두 컬럼(scope) 별 DOM 참조를 dict 로 보관.
      // usersTip / usersList / topnEl 은 hover 시 보여줄 "접속자 ID Top N"
      // tooltip 의 DOM. (이전 title="..." 기본 툴팁을 대체.)
      this.cols = {
        all: {
          primary:   this.root.querySelector('[data-role="primary-all"]'),
          secondary: this.root.querySelector('[data-role="secondary-all"]'),
          distinct:  this.root.querySelector('[data-role="distinct-value-all"]'),
          total:     this.root.querySelector('[data-role="total-value-all"]'),
          usersTip:  this.root.querySelector('[data-role="users-tip-all"]'),
          usersList: this.root.querySelector('[data-role="users-list-all"]'),
          topnEl:    this.root.querySelector('[data-role="topn-all"]'),
        },
        customer: {
          primary:   this.root.querySelector('[data-role="primary-customer"]'),
          secondary: this.root.querySelector('[data-role="secondary-customer"]'),
          distinct:  this.root.querySelector('[data-role="distinct-value-customer"]'),
          total:     this.root.querySelector('[data-role="total-value-customer"]'),
          usersTip:  this.root.querySelector('[data-role="users-tip-customer"]'),
          usersList: this.root.querySelector('[data-role="users-list-customer"]'),
          topnEl:    this.root.querySelector('[data-role="topn-customer"]'),
        },
      };

      this.timer = null;
      this.inFlight = false;
      this._destroyed = false;
      this._runToken = 0;
      this._abortCtrl = null;
      this._cancelledCount = 0;
      this._supersedeTimer = null;

      this._onRefreshClick = () => this.run();
      this._onAutoChange   = () => this._applyAutoRefresh();

      // 접속자 ID Top N tooltip — primary 영역 hover/focus 시 표시,
      // 떠날 때 숨김. CSS 만으로도 :hover 안전망이 있지만, JS 로 명시 토글
      // 하면 keyboard focus 와 모바일 터치(focus-within) 에도 견고하다.
      this._hoverHandlers = [];
      ['all', 'customer'].forEach((scope) => {
        const col = this.cols[scope];
        if (!col || !col.primary || !col.usersTip) return;
        const show = () => { if (col.usersTip) col.usersTip.hidden = false; };
        const hide = () => { if (col.usersTip) col.usersTip.hidden = true;  };
        col.primary.addEventListener('mouseenter', show);
        col.primary.addEventListener('mouseleave', hide);
        col.primary.addEventListener('focusin',    show);
        col.primary.addEventListener('focusout',   hide);
        this._hoverHandlers.push({ el: col.primary, show, hide });
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
      // hover 핸들러 해제 (LoginTodayCard 만 있고 CountCard 에는 없음 — 안전 조건)
      if (Array.isArray(this._hoverHandlers)) {
        this._hoverHandlers.forEach(({ el, show, hide }) => {
          if (!el) return;
          el.removeEventListener('mouseenter', show);
          el.removeEventListener('mouseleave', hide);
          el.removeEventListener('focusin',    show);
          el.removeEventListener('focusout',   hide);
        });
        this._hoverHandlers = [];
      }
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
      ['all', 'customer'].forEach((scope) => {
        const col = this.cols[scope];
        if (!col) return;
        if (col.primary)   col.primary.classList.toggle('is-loading', !!on);
        if (col.secondary) col.secondary.classList.toggle('is-loading', !!on);
      });
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

    _fmtNum(n) {
      if (n == null) return '—';
      try { return Number(n).toLocaleString('ko-KR'); }
      catch (_) { return String(n); }
    }

    _setValuesForScope(scope, distinct, total) {
      const col = this.cols[scope];
      if (!col) return;
      if (col.distinct) col.distinct.textContent = this._fmtNum(distinct);
      if (col.total)    col.total.textContent    = this._fmtNum(total);
    }

    /**
     * scope 별 hover 툴팁의 "접속자 ID Top N" 리스트를 채운다.
     * @param {"all"|"customer"} scope
     * @param {Array<{user_id:string,count:number}>} users  count 내림차순 정렬된 상위 N명
     * @param {number} extra  Top N 을 초과한 추가 인원 수
     * @param {number} topN   현재 적용 중인 Top N (서버 설정값)
     */
    _setUsersForScope(scope, users, extra, topN) {
      const col = this.cols[scope];
      if (!col || !col.usersList) return;
      // Top N 배지 숫자 갱신
      if (col.topnEl && typeof topN === 'number' && topN > 0) {
        col.topnEl.textContent = String(topN);
      }
      // 비어있으면 "접속 기록 없음" 안내
      const list = Array.isArray(users) ? users : [];
      if (list.length === 0) {
        col.usersList.innerHTML = '<span class="login-today-tip-empty">아직 접속 기록이 없습니다.</span>';
        return;
      }
      // user_id 칩 + 옆에 작은 회수. user_id 는 텍스트 노드로만 넣어 XSS 방지.
      const frag = document.createDocumentFragment();
      list.forEach((u) => {
        if (!u || !u.user_id) return;
        const chip = document.createElement('span');
        chip.className = 'login-today-tip-user';
        const idSpan = document.createElement('span');
        idSpan.className = 'login-today-tip-user-id';
        idSpan.textContent = String(u.user_id);
        const cntSpan = document.createElement('span');
        cntSpan.className = 'login-today-tip-user-cnt';
        const cnt = (typeof u.count === 'number') ? u.count : Number(u.count) || 0;
        cntSpan.textContent = '×' + this._fmtNum(cnt);
        chip.appendChild(idSpan);
        chip.appendChild(cntSpan);
        frag.appendChild(chip);
      });
      col.usersList.innerHTML = '';
      col.usersList.appendChild(frag);
      // Top N 초과 인원 표기
      if (typeof extra === 'number' && extra > 0) {
        const more = document.createElement('span');
        more.className = 'login-today-tip-extra';
        more.textContent = '외 ' + this._fmtNum(extra) + '명';
        col.usersList.appendChild(more);
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
            '이전 오늘 접속자수 카드 요청을 취소하고 다시 불러옵니다.',
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

      const url = '/login-history/today';
      const startedAt = performance.now();
      try {
        const res = await fetch(url, {
          headers: { 'Accept': 'application/json' },
          signal: ctrl ? ctrl.signal : undefined,
        });
        if (this._destroyed || token !== this._runToken) return;

        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const j = await res.json();
            if (j && j.detail) detail = j.detail;
          } catch (_) {}
          throw new Error(detail);
        }
        const data = await res.json();
        if (this._destroyed || token !== this._runToken) return;

        // 양쪽 컬럼을 동시에 채운다 (한 응답에 all/customer 모두 포함).
        // 추가로 hover 툴팁용 "접속자 ID Top N" 리스트도 함께 채운다.
        const topN = (typeof data.tooltip_top_n === 'number' && data.tooltip_top_n > 0)
          ? data.tooltip_top_n
          : 10;
        ['all', 'customer'].forEach((scope) => {
          const side = (data && data[scope]) || {};
          const distinct = (typeof side.distinct === 'number') ? side.distinct : 0;
          const total    = (typeof side.total    === 'number') ? side.total    : 0;
          this._setValuesForScope(scope, distinct, total);
          const users = Array.isArray(side.users) ? side.users : [];
          const extra = (typeof side.extra_users === 'number') ? side.extra_users : 0;
          this._setUsersForScope(scope, users, extra, topN);
        });

        const elapsed = (typeof data.elapsed_ms === 'number')
          ? data.elapsed_ms
          : Math.round(performance.now() - startedAt);
        if (this.elapsedEl) this.elapsedEl.textContent = fmtElapsed(elapsed);
        this._setStatusBadge('ok');
      } catch (err) {
        if (err && (err.name === 'AbortError' || err.code === 20)) return;
        if (this._destroyed || token !== this._runToken) return;
        this._setError(err && err.message ? err.message : String(err));
        this._setStatusBadge('error');
      } finally {
        if (token === this._runToken) {
          this.inFlight = false;
          this._abortCtrl = null;
          this._setSpinner(false);
          this._setLoadingDim(false);
        }
      }
    }
  }

  // 외부 노출
  window.QueryRunner = QueryRunner;
  window.ChartCard = ChartCard;
  window.CountCard = CountCard;
  window.LoginTodayCard = LoginTodayCard;
  window.Toast = Toast;
})();
