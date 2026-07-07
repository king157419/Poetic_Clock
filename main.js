'use strict';

/* ======================================================================
 * 诗意时钟 · 选诗核心(纯逻辑,不接触 DOM / 网络 / 时区外部状态)
 * ----------------------------------------------------------------------
 * 这一段是本项目的心脏,未来将「原样」移植到 ESP32 / 树莓派 + 墨水屏。
 * 网页只是它的第一个渲染器。因此:
 *   · 不引用任何 DOM、window、fetch;
 *   · 所有输入都来自参数(date, data);
 *   · 输出是确定性的——同一天同一时辰,任何时刻调用都返回同一句。
 * 渲染层(下方 UI 部分)不得内嵌任何诗句文本,一切取自 data。
 * ==================================================================== */

/**
 * 小时 → 时辰索引(0..11,子丑寅卯辰巳午未申酉戌亥)。
 * 子时跨午夜:23 时与 0 时同属子时。
 * 公式 floor(((hour + 1) % 24) / 2):
 *   23 → 0(子)  0 → 0(子)  1 → 1(丑) ... 21/22 → 11(亥)
 */
function shichenIndexForHour(hour) {
  return Math.floor(((hour + 1) % 24) / 2);
}

/**
 * 把「本地年 / 月 / 日」折算成稳定整数日序。
 * 用 Date.UTC 取该日 00:00(UTC)的毫秒再除以一天——只为得到一个
 * 随日期 +1 递增的整数,不受本地时区、夏令时抖动影响。
 */
function dayOrdinal(year, monthIndex, day) {
  return Math.floor(Date.UTC(year, monthIndex, day) / 86400000);
}

/**
 * 确定性诗序:日序 + 时辰序,对该时辰诗数取模。
 * 叠加时辰序 idx,只是让各时辰不在同一天整齐翻页、轮换更耐看;
 * 对「同日同辰恒显同一句」没有任何影响。
 */
function poemIndexFor(ord, shichenIndex, count) {
  return (((ord + shichenIndex) % count) + count) % count;
}

/**
 * 纯函数:给定时刻 date 与数据 data,返回此刻此辰应显示的诗。
 * @returns {{shichen, poem, shichenIndex, poemIndex, dayOrdinal}|null}
 */
function selectPoem(date, data) {
  if (!data || !Array.isArray(data.shichen) || data.shichen.length !== 12) return null;

  const hour = date.getHours();
  const shichenIndex = shichenIndexForHour(hour);
  const shichen = data.shichen[shichenIndex];
  if (!shichen || !Array.isArray(shichen.poems) || shichen.poems.length === 0) return null;

  // 轮换用的「诗日」。子时 23:00–00:59 属于同一个「子时之夜」,应显示同一句。
  // 故当 hour === 23 时,把日期向后滚一天,使 23:30 与次日 00:30 折算出
  // 相同的日序、命中同一句;每晚 23:00 才轮换到新的子时诗。
  let y = date.getFullYear(), m = date.getMonth(), d = date.getDate();
  if (hour === 23) {
    const rolled = new Date(y, m, d + 1);
    y = rolled.getFullYear(); m = rolled.getMonth(); d = rolled.getDate();
  }
  const ord = dayOrdinal(y, m, d);
  const poemIndex = poemIndexFor(ord, shichenIndex, shichen.poems.length);

  return {
    shichen: shichen,
    poem: shichen.poems[poemIndex],
    shichenIndex: shichenIndex,
    poemIndex: poemIndex,
    dayOrdinal: ord
  };
}

/**
 * 当前时辰内的进度 [0,1)。纯逻辑,供「香篆」细弧使用。
 * 每个时辰 120 分钟;(hour+1)%2 判定处于时辰的第一小时(0)还是第二小时(1)。
 */
function shichenProgress(date) {
  const hour = date.getHours();
  const withinHour = (hour + 1) % 2; // 0=时辰前半小时段, 1=后半小时段
  const mins = withinHour * 60 + date.getMinutes() + date.getSeconds() / 60;
  return Math.min(0.9999, Math.max(0, mins / 120));
}

/** 夜读模式判定:23:00–04:59 深底暖字。纯逻辑。 */
function isNightHour(hour) {
  return hour >= 23 || hour < 5;
}

/* ======================================================================
 * 自检测试(附:子时跨午夜边界)。浏览器 URL 加 ?selftest 运行;
 * Node 环境亦可 require 本文件后调用 runSelfTests()。不接触 DOM。
 * ==================================================================== */

function runSelfTests(data) {
  const results = [];
  const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

  // 1) 24 小时 → 时辰索引映射
  const expect = {
    23: 0, 0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4,
    9: 5, 10: 5, 11: 6, 12: 6, 13: 7, 14: 7, 15: 8, 16: 8,
    17: 9, 18: 9, 19: 10, 20: 10, 21: 11, 22: 11
  };
  let mapOk = true;
  for (const h in expect) if (shichenIndexForHour(+h) !== expect[h]) mapOk = false;
  ok('小时→时辰映射(全 24 小时)', mapOk);

  if (data) {
    // 2) 子时跨午夜:同一夜 23:30 与次日 00:30 → 同一时辰、同一句
    const a = selectPoem(new Date(2026, 6, 6, 23, 30), data);   // 7/6 23:30
    const b = selectPoem(new Date(2026, 6, 7, 0, 30), data);    // 7/7 00:30
    ok('子时边界:23:30 与次日 00:30 同为子时', a.shichen.id === 'zi' && b.shichen.id === 'zi');
    ok('子时边界:23:30 与次日 00:30 同一句', a.poem.line === b.poem.line, a.poem.line + ' / ' + b.poem.line);

    // 3) 22:59(亥)与 23:00(子)分属不同时辰
    const hai = selectPoem(new Date(2026, 6, 6, 22, 59), data);
    const zi = selectPoem(new Date(2026, 6, 6, 23, 0), data);
    ok('22:59 为亥、23:00 为子', hai.shichen.id === 'hai' && zi.shichen.id === 'zi');

    // 4) 恒常性:同日同辰、辰内不同时刻 → 同一句
    const w1 = selectPoem(new Date(2026, 6, 6, 11, 5), data);
    const w2 = selectPoem(new Date(2026, 6, 6, 12, 58), data);
    ok('同日午时不同时刻恒显同一句', w1.poem.line === w2.poem.line, w1.poem.line);

    // 5) 次日轮换:相邻两天同一午时 → 换句(诗数为 2 时应交替)
    const d1 = selectPoem(new Date(2026, 6, 6, 12, 0), data);
    const d2 = selectPoem(new Date(2026, 6, 7, 12, 0), data);
    ok('次日午时轮换到另一句', d1.poem.line !== d2.poem.line, d1.poem.line + ' → ' + d2.poem.line);

    // 6) 子时之夜的确会次夜轮换:今夜 23:30 与明夜 23:30 → 换句
    const n1 = selectPoem(new Date(2026, 6, 6, 23, 30), data);
    const n2 = selectPoem(new Date(2026, 6, 7, 23, 30), data);
    ok('次夜子时轮换到另一句', n1.poem.line !== n2.poem.line, n1.poem.line + ' → ' + n2.poem.line);

    // 7) 十二时辰皆可取到有效诗句
    let allValid = true, missing = [];
    for (let i = 0; i < 12; i++) {
      const hour = i === 0 ? 0 : 2 * i - 1;
      const s = selectPoem(new Date(2026, 6, 6, hour, 0), data);
      if (!s || !s.poem || !s.poem.line || !s.poem.source) { allValid = false; missing.push(i); }
    }
    ok('十二时辰均取到完整诗句', allValid, missing.length ? '缺:' + missing : '');

    // 8) 越日一致:同一逻辑日多次调用结果稳定
    const r1 = selectPoem(new Date(2026, 6, 6, 8, 0), data);
    const r2 = selectPoem(new Date(2026, 6, 6, 8, 0), data);
    ok('相同输入结果稳定', r1.poem.line === r2.poem.line);
  }

  const failed = results.filter(r => !r.pass);
  return { passed: results.length - failed.length, failedCount: failed.length, results };
}

/* ======================================================================
 * 以下为「网页渲染器」。仅在浏览器中运行(有 document 时)。
 * 墨水屏移植时整段可弃,只带走上面的纯逻辑 + data/poems.json + 版式规则。
 * ==================================================================== */

if (typeof document !== 'undefined') {
  (function initClock() {
    const $ = (sel) => document.querySelector(sel);

    const el = {
      body: document.body,
      stage: $('#stage'),
      poem: $('#poem'),
      line: $('#poemLine'),
      meta: $('#poemMeta'),
      seal: $('#seal'),
      alias: $('#cornerShichen'),
      time: $('#cornerTime'),
      badge: $('#previewBadge'),
      arc: $('#incenseArc'),
      hint: $('#hint')
    };

    // 各时辰「代表小时」,用于预览其他时辰(取当日轮换)。
    // 子时用 0 时(而非 23 时)以避免跨日回滚,保证与其余时辰同属当日。
    const REP_HOURS = [0, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21];

    let DATA = null;
    let currentKey = null;     // 当前显示内容指纹(用于判断是否需要淡入淡出)
    let previewOffset = 0;     // 0 = 未预览;±k = 预览相对当前的第 k 个时辰
    let previewTimer = null;   // 预览 10 秒无操作自动归位
    let fadeTimer = null;

    /* ---------- 数据加载 ---------- */
    function boot() {
      fetch('data/poems.json', { cache: 'no-cache' })
        .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then((data) => {
          DATA = data;
          if (location.search.indexOf('selftest') !== -1) showSelfTest();
          bindInteractions();
          tick(true);
          setInterval(() => tick(false), 1000);
        })
        .catch((err) => showLoadError(err));
    }

    /* ---------- 主循环 ---------- */
    function tick(first) {
      if (!DATA) return;
      const now = new Date();

      // 夜读模式(以真实此刻判定,预览不改变昼夜)
      el.body.classList.toggle('night', isNightHour(now.getHours()));

      // 角落现代时间(始终真实此刻)
      el.time.textContent = fmtTime(now);

      const current = selectPoem(now, DATA);
      if (!current) return;

      // 决定要显示的选择:预览态取相对时辰,否则取真实此刻
      let sel = current, preview = false;
      if (previewOffset !== 0) {
        const targetIndex = (current.shichenIndex + previewOffset + 12) % 12;
        const rep = new Date(now.getFullYear(), now.getMonth(), now.getDate(), REP_HOURS[targetIndex], 0, 0);
        sel = selectPoem(rep, DATA) || current;
        preview = true;
      }

      paint(sel, preview, first);

      // 香篆进度弧:预览时展示目标时辰满弧的静态感?—— 用真实此刻进度更诚实。
      setArc(shichenProgress(now));
    }

    /* ---------- 渲染一句(含淡入淡出) ---------- */
    function paint(sel, preview, first) {
      const key = sel.shichen.id + '|' + sel.poemIndex + '|' + (preview ? 'p' : 'r');
      if (key === currentKey) return;      // 内容未变,不触发动画
      const firstPaint = currentKey === null;
      currentKey = key;

      const render = () => {
        el.line.textContent = sel.poem.line;
        el.meta.textContent = metaText(sel.poem);
        el.seal.textContent = sel.shichen.name.charAt(0); // 印章单字:子丑寅…
        el.seal.setAttribute('aria-label', sel.shichen.name);
        el.alias.textContent = sel.shichen.name + ' · ' + sel.shichen.alias;
        el.badge.hidden = !preview;
        el.stage.classList.toggle('previewing', preview);
      };

      if (first || firstPaint) {           // 首帧直接出现,不淡
        render();
        el.poem.classList.remove('is-out');
        return;
      }

      // 旧句淡出 → 换字 → 新句淡入(总时长 ≈ 760ms ≤ 800ms)
      clearTimeout(fadeTimer);
      el.poem.classList.add('is-out');
      fadeTimer = setTimeout(() => {
        render();
        el.poem.classList.remove('is-out');
      }, 380);
    }

    /* ---------- 香篆细弧 ---------- */
    function setArc(p) {
      if (!el.arc) return;
      // path 的 pathLength 设为 100,dashoffset 从 100→0 揭示已燃部分
      el.arc.style.strokeDashoffset = String(100 * (1 - p));
    }

    /* ---------- 交互:键盘 / 点击 / 触摸 ---------- */
    function bindInteractions() {
      document.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') { nudge(-1); e.preventDefault(); }
        else if (e.key === 'ArrowRight') { nudge(1); e.preventDefault(); }
        else if (e.key === 'Escape') { resetPreview(); }
      });

      el.stage.addEventListener('click', (e) => {
        const x = e.clientX / window.innerWidth;
        if (x < 0.4) nudge(-1);          // 左区:上一个时辰
        else if (x > 0.6) nudge(1);      // 右区:下一个时辰
        else resetPreview();             // 中区:回到当前
      });
    }

    function nudge(dir) {
      previewOffset += dir;
      if (previewOffset === 0) { resetPreview(); return; }
      // 首次触发预览时给个提示淡出
      if (el.hint) el.hint.classList.add('gone');
      armPreviewTimeout();
      tick(false);
    }

    function armPreviewTimeout() {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(resetPreview, 10000); // 10s 无操作自动归位
    }

    function resetPreview() {
      clearTimeout(previewTimer);
      previewOffset = 0;
      tick(false);
    }

    /* ---------- 小工具 ---------- */
    function metaText(p) {
      // 例:〔唐〕张继　《枫桥夜泊》
      // 全用全角/汉字,避免半角间隔号在竖排中被旋转。
      return '〔' + p.dynasty + '〕' + p.author + '　' + p.source;
    }
    function fmtTime(d) {
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      return hh + ':' + mm;
    }

    function showLoadError(err) {
      currentKey = 'error';
      el.line.textContent = '诗集未能载入';
      el.meta.textContent = '请用本地静态服务器打开(见 README)';
      el.seal.textContent = '误';
      if (el.badge) el.badge.hidden = true;
      // 仅在控制台留一条信息,便于排查;正常路径不触发。
      console.info('[诗意时钟] 数据加载失败:', err && err.message,
        '—— file:// 直接打开会被浏览器拦截 fetch,请以 http 方式预览。');
    }

    function showSelfTest() {
      const r = runSelfTests(DATA);
      const box = document.createElement('div');
      box.id = 'selftest';
      box.innerHTML = '<b>自检:' + r.passed + ' 通过 / ' + r.failedCount + ' 失败</b>' +
        r.results.map((t) =>
          '<div class="' + (t.pass ? 'ok' : 'no') + '">' +
          (t.pass ? '✓' : '✗') + ' ' + t.name +
          (t.extra ? ' <span>' + t.extra + '</span>' : '') + '</div>').join('');
      document.body.appendChild(box);
      (r.failedCount ? console.error : console.info)('[诗意时钟] 自检', r);
    }

    boot();
  })();
}

/* ---------- Node 导出(仅便于命令行跑测试;浏览器忽略) ---------- */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    selectPoem, shichenIndexForHour, shichenProgress, dayOrdinal,
    poemIndexFor, isNightHour, runSelfTests
  };
}
