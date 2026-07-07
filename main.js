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
 * 周循环诗序:index = 星期几 % 该时辰句数。
 * 星期几取 JS `Date.getDay()`:0=周日, 1=周一, …, 6=周六。
 * 于是「同一星期几 + 同一时辰」永远显示同一句;句数不足 7 的时辰在一周内
 * 自然重复(如 2 句时索引走 0,1,0,1,0,1,0),不会越界报错。
 * (v1.1:由 v1 的「按年内第几天」轮换改为按星期几轮换。)
 */
function poemIndexForWeekday(weekday, count) {
  return weekday % count;
}

/** 本地日历日键 yyyy-mm-dd(纯逻辑,节令查表用,不做子时滚动)。 */
function dateKey(date) {
  const m = String(date.getMonth() + 1);
  const d = String(date.getDate());
  return date.getFullYear() + '-' + (m.length < 2 ? '0' + m : m) + '-' + (d.length < 2 ? '0' + d : d);
}

/** 轮换用星期几:子时 23:xx 滚到次日再取 getDay(保持一夜同句)。 */
function weekdayForRotation(date) {
  const hour = date.getHours();
  const rd = (hour === 23) ? new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1) : date;
  return rd.getDay(); // 0=周日 … 6=周六
}

/**
 * 纯函数:给定时刻 date、数据 data、可选节日表 festivals,返回此刻此辰应显示的诗。
 * 节令层:当日(真实日历日,全天)命中节日、且本时辰存在该节日句 → 顶替常规句;
 * 否则走常规周循环(常规选诗完全排除带 festival 字段的句子)。
 * @returns {{shichen, poem, shichenIndex, poemIndex, weekday, isFestival, festival?}|null}
 */
function selectPoem(date, data, festivals) {
  if (!data || !Array.isArray(data.shichen) || data.shichen.length !== 12) return null;

  const hour = date.getHours();
  const shichenIndex = shichenIndexForHour(hour);
  const shichen = data.shichen[shichenIndex];
  if (!shichen || !Array.isArray(shichen.poems) || shichen.poems.length === 0) return null;

  const weekday = weekdayForRotation(date);

  // ── 节令彩蛋层 ──:节日当天,若本时辰有该节日句则顶替,全天生效。
  if (festivals) {
    const names = festivals[dateKey(date)];
    if (Array.isArray(names)) {
      for (let i = 0; i < names.length; i++) {
        for (let j = 0; j < shichen.poems.length; j++) {
          if (shichen.poems[j].festival === names[i]) {
            return {
              shichen: shichen, poem: shichen.poems[j], shichenIndex: shichenIndex,
              poemIndex: j, weekday: weekday, isFestival: true, festival: names[i]
            };
          }
        }
      }
    }
  }

  // ── 常规周循环 ──:仅在「非节令句」中选,节令句平日绝不出现。
  const regular = shichen.poems.filter(function (p) { return !p.festival; });
  if (!regular.length) return null;
  const poemIndex = poemIndexForWeekday(weekday, regular.length);
  return {
    shichen: shichen, poem: regular[poemIndex], shichenIndex: shichenIndex,
    poemIndex: poemIndex, weekday: weekday, isFestival: false
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

/**
 * 拆句(纯函数):按全角/半角断句标点(,。;、?! 及其变体)把整句拆成若干短句,
 * 供竖排「一句一列、右起向左」渲染。返回去掉标点后的短句数组(空句略去)。
 *   splitClauses("姑苏城外寒山寺，夜半钟声到客船") → ["姑苏城外寒山寺","夜半钟声到客船"]
 * 单一事实来源不动——拆分只发生在渲染层,数据文件里的标点原样保留。
 * 拆列后列断即停顿,古籍竖排本无标点,故隐去句间分隔符。
 */
function splitClauses(line) {
  if (typeof line !== 'string') return [];
  return line
    .split(/[，。；、？！：,;?!:]+/)
    .map(function (s) { return s.trim(); })
    .filter(function (s) { return s.length > 0; });
}

/**
 * 拆句后长度校验(纯函数):返回 {warn:[…], err:[…]}。
 * 单句(拆分后)> 12 字 → 警告;> 16 字 → 数据错误(自检红灯)。
 */
function checkClauseLengths(line) {
  const warn = [], err = [];
  splitClauses(line).forEach(function (c) {
    if (c.length > 16) err.push(c);
    else if (c.length > 12) warn.push(c);
  });
  return { warn: warn, err: err };
}

/**
 * 编辑标准校验(纯函数):数据集每条 time_word 须①是 line 的子串,
 * ②属于其所属时辰在 timeWords 中的合法词表。仅校验带 time_word 的条目。
 * @returns {{checked:number, subMiss:string[], listMiss:string[]}}
 */
function validateTimeWords(dataset, timeWords) {
  const subMiss = [], listMiss = [];
  let checked = 0;
  const legal = {};
  if (timeWords && Array.isArray(timeWords.shichen)) {
    timeWords.shichen.forEach(function (s) {
      legal[s.id] = {};
      (s.words || []).forEach(function (w) { legal[s.id][w.word] = true; });
    });
  }
  if (dataset && Array.isArray(dataset.shichen)) {
    dataset.shichen.forEach(function (sc) {
      (sc.poems || []).forEach(function (po) {
        if (!po.time_word) return;
        checked++;
        if (po.line.indexOf(po.time_word) === -1) subMiss.push(sc.id + '「' + po.time_word + '」非 line 子串');
        if (legal[sc.id] && !legal[sc.id][po.time_word]) listMiss.push(sc.id + '「' + po.time_word + '」不在词表');
      });
    });
  }
  return { checked: checked, subMiss: subMiss, listMiss: listMiss };
}

/* ======================================================================
 * 自检测试(附:子时跨午夜边界)。浏览器 URL 加 ?selftest 运行;
 * Node 环境亦可 require 本文件后调用 runSelfTests()。不接触 DOM。
 * ==================================================================== */

function runSelfTests(data, opts) {
  opts = opts || {};   // { timeWords, standard, festivals } — 校验新标准/节令用
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

  // 1b) 拆句 splitClauses(纯函数):逗号 / 顿号 / 问号 / 三句词 各一例
  ok('拆句:逗号 → 两句', splitClauses('姑苏城外寒山寺，夜半钟声到客船').length === 2);
  ok('拆句:顿号 → 两句', splitClauses('杨柳岸、晓风残月').length === 2);
  ok('拆句:问号 → 两句', splitClauses('问君能有几多愁？恰似一江春水向东流').length === 2);
  ok('拆句:三句词 → 三句', splitClauses('枯藤老树昏鸦，小桥流水人家，古道西风瘦马').length === 3);
  ok('拆句:短句内已无标点(列断即停顿)',
    splitClauses('姑苏城外寒山寺，夜半钟声到客船').every(function (c) { return !/[，。；、？！：]/.test(c); }));

  if (data) {
    // 2) 子时跨午夜:同一夜 23:30 与次日 00:30 → 同一时辰、同一句(周循环下仍须成立)
    const a = selectPoem(new Date(2026, 6, 6, 23, 30), data);   // 周一 23:30
    const b = selectPoem(new Date(2026, 6, 7, 0, 30), data);    // 周二 00:30(同一夜)
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

    // 5) 周循环确定性:同一星期几 + 同一时辰(相隔 7 天)→ 必然同句
    const wk1 = selectPoem(new Date(2026, 6, 6, 12, 0), data);   // 周一 午时
    const wk2 = selectPoem(new Date(2026, 6, 13, 12, 0), data);  // 次周一 午时
    ok('同星期几+同午时→同句(隔周)', wk1.poem.line === wk2.poem.line && wk1.weekday === wk2.weekday,
      '周' + wk1.weekday + ' :' + wk1.poem.line);

    // 6) 子时同样按周循环:同星期几之夜的子时 → 同句(隔周)
    const zn1 = selectPoem(new Date(2026, 6, 6, 23, 30), data);
    const zn2 = selectPoem(new Date(2026, 6, 13, 23, 30), data);
    ok('同星期几之夜子时→同句(隔周)', zn1.poem.line === zn2.poem.line);

    // 7) 一周内覆盖:午时(2 句)在连续 7 天里两句都会出现
    const seen = new Set();
    for (let d = 5; d <= 11; d++) seen.add(selectPoem(new Date(2026, 6, d, 12, 0), data).poem.line);
    const wuCount = data.shichen[6].poems.length;
    ok('午时一周内覆盖到全部句', seen.size === Math.min(7, wuCount), '出现 ' + seen.size + '/' + wuCount + ' 句');

    // 8) 句数不足 7 不报错:每个时辰 × 每个星期几(连续 7 天)都取到完整诗句
    let allValid = true, bad = [];
    const repHour = [0, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21];
    for (let i = 0; i < 12; i++) {
      for (let d = 5; d <= 11; d++) {
        const s = selectPoem(new Date(2026, 6, d, repHour[i], 0), data);
        if (!s || !s.poem || !s.poem.line || !s.poem.source) { allValid = false; bad.push(i + '/' + d); }
      }
    }
    ok('十二时辰 × 七星期几均取到完整诗句', allValid, bad.length ? '缺:' + bad.join(',') : '');

    // 9) 相同输入结果稳定
    const r1 = selectPoem(new Date(2026, 6, 6, 8, 0), data);
    const r2 = selectPoem(new Date(2026, 6, 6, 8, 0), data);
    ok('相同输入结果稳定', r1.poem.line === r2.poem.line);

    // 10) 拆句长度校验:>12 字警告,>16 字数据错误
    let clauseErr = [], clauseWarn = [];
    for (const sc of data.shichen) for (const po of sc.poems) {
      const r = checkClauseLengths(po.line);
      Array.prototype.push.apply(clauseErr, r.err);
      Array.prototype.push.apply(clauseWarn, r.warn);
    }
    if (clauseWarn.length) console.warn('[诗意时钟] 拆句 >12 字(警告):', clauseWarn);
    ok('拆句后无单句 > 16 字(数据错误)', clauseErr.length === 0,
      clauseErr.length ? '超长:' + clauseErr.join('/') : (clauseWarn.length ? '(' + clauseWarn.length + ' 条 >12 字警告)' : ''));
  }

  // §2 编辑标准硬测试:对「标准数据集」(默认取迁移提案 opts.standard)校验 time_word。
  if (opts.timeWords) {
    let dup = 0, wordCount = 0; const seen = {};
    (opts.timeWords.shichen || []).forEach(function (s) {
      (s.words || []).forEach(function (w) { wordCount++; if (seen[w.word]) dup++; else seen[w.word] = s.id; });
    });
    ok('时间词表:一词只归一时辰', dup === 0, dup ? dup + ' 词跨档重复' : '(' + wordCount + ' 词唯一)');

    const std = opts.standard || data;
    const v = validateTimeWords(std, opts.timeWords);
    ok('① 每条 time_word 是 line 的子串', v.subMiss.length === 0,
      v.subMiss.length ? v.subMiss.join('; ') : '(校验 ' + v.checked + ' 条)');
    ok('② 每条 time_word 属于其时辰词表', v.listMiss.length === 0,
      v.listMiss.length ? v.listMiss.join('; ') : '(校验 ' + v.checked + ' 条)');
  }

  // §4 节令层硬测试(注入合成 12 时辰数据 + 节日表,不依赖真实曲库)。
  if (opts.festivals !== undefined || opts.testFestival) {
    const ids = ['zi', 'chou', 'yin', 'mao', 'chen', 'si', 'wu', 'wei', 'shen', 'you', 'xu', 'hai'];
    const festData = { shichen: ids.map(function (id) {
      return { id: id, name: id, alias: id, range: [0, 0], poems: [{ line: '常规' + id, source: '《测》' }] };
    }) };
    // 卯时(index 3,hour 5–6)注入一句春节彩蛋 + 两句常规
    festData.shichen[3].poems = [
      { line: '爆竹声中一岁除', source: '《元日》', festival: '春节' },
      { line: '常规卯一', source: '《测》' }, { line: '常规卯二', source: '《测》' }
    ];
    const fest = { '2026-02-17': ['春节'] };
    // ① 注入春节当天 → 卯时返回节日句
    const onFest = selectPoem(new Date(2026, 1, 17, 6, 0), festData, fest);
    ok('节令:春节当天卯时返回节日句', !!onFest && onFest.poem.festival === '春节' && onFest.isFestival === true,
      onFest ? onFest.poem.line : 'null');
    // ② 平常日 → 节日句绝不出现,且常规选句无 festival 字段
    let leaked = false;
    for (let d = 1; d <= 28; d++) {
      if (d === 17) continue;
      const s = selectPoem(new Date(2026, 1, d, 6, 0), festData, fest);
      if (s && s.poem.festival) leaked = true;
    }
    ok('节令:平常日节日句绝不出现', !leaked);
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
    let lastClauses = [];      // 当前显示的短句(供窗口尺寸变化时重算字号)
    let FESTIVALS = null;      // 节日表 { "YYYY-MM-DD": ["节日名"] }(可选)

    /* ---------- 数据加载 ---------- */
    function boot() {
      const get = (u) => fetch(u, { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
      // poems.json 为渲染必需;festivals/time_words/proposed 为可选(节令与自检用)
      Promise.all([
        get('data/poems.json'),
        get('data/festivals.json'),
        get('data/time_words.json'),
        get('data/poems.v2.proposed.json')
      ]).then(function (arr) {
        const poems = arr[0], fest = arr[1], tw = arr[2], prop = arr[3];
        if (!poems) { showLoadError(new Error('poems.json 未载入')); return; }
        DATA = poems;
        FESTIVALS = fest ? (fest.dates || fest) : null;
        if (location.search.indexOf('selftest') !== -1) showSelfTest(tw, prop);
        bindInteractions();
        tick(true);
        setInterval(function () { tick(false); }, 1000);
      });
    }

    /* ---------- 主循环 ---------- */
    function tick(first) {
      if (!DATA) return;
      const now = new Date();

      // 夜读模式(以真实此刻判定,预览不改变昼夜)
      el.body.classList.toggle('night', isNightHour(now.getHours()));

      // 角落现代时间(始终真实此刻)
      el.time.textContent = fmtTime(now);

      const current = selectPoem(now, DATA, FESTIVALS);
      if (!current) return;

      // 决定要显示的选择:预览态取相对时辰,否则取真实此刻
      let sel = current, preview = false;
      if (previewOffset !== 0) {
        const targetIndex = (current.shichenIndex + previewOffset + 12) % 12;
        const rep = new Date(now.getFullYear(), now.getMonth(), now.getDate(), REP_HOURS[targetIndex], 0, 0);
        sel = selectPoem(rep, DATA, FESTIVALS) || current;
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
        renderClauses(sel.poem);
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

    /* ---------- 拆句成列 + 自适应字号 ---------- */
    // 把整句拆成短句,一句一列注入 #poem(右起向左),句内 nowrap 绝不折行。
    function renderClauses(poem) {
      const clauses = splitClauses(poem.line);
      lastClauses = clauses;
      const tw = poem.time_word || '';
      // 移除旧列(保留 #poemMeta / #seal),把新列插在落款之前
      const old = el.poem.querySelectorAll('.clause');
      for (let i = 0; i < old.length; i++) old[i].remove();
      clauses.forEach(function (c) {
        const col = document.createElement('p');
        col.className = 'clause';
        const idx = tw ? c.indexOf(tw) : -1;
        if (idx !== -1) {
          // 用着重号(text-emphasis)标出诗中的时间词;用文本节点避免注入
          if (idx > 0) col.appendChild(document.createTextNode(c.slice(0, idx)));
          const em = document.createElement('em');
          em.className = 'tw';
          em.textContent = tw;
          col.appendChild(em);
          if (idx + tw.length < c.length) col.appendChild(document.createTextNode(c.slice(idx + tw.length)));
        } else {
          col.textContent = c;
        }
        el.poem.insertBefore(col, el.meta);
      });
      fitFont(clauses);
    }

    // 以「最长句装进可用列高」+「所有列装进可用宽」为准算字号,设上下限。
    function fitFont(clauses) {
      if (!clauses || !clauses.length) return;
      let maxChars = 1;
      for (let i = 0; i < clauses.length; i++) maxChars = Math.max(maxChars, clauses[i].length);
      const n = clauses.length;
      const availH = window.innerHeight * 0.74;   // 竖向可用(留白 + 落款余量)
      const availW = window.innerWidth * 0.82;    // 横向可用
      const CHAR_PITCH = 1.16;  // 每字竖向步距 ≈ 字号×(1 + 字距 0.14 + 余量)
      const COL_PITCH = 1.5;    // 每列横向步距 ≈ 字号×(行高 + 列距)
      const META_COLS = 2.2;    // 落款 + 印章 + 间隙约占的列数
      const byHeight = availH / (maxChars * CHAR_PITCH);
      const byWidth = availW / ((n + META_COLS) * COL_PITCH);
      const MIN = 22, MAX = 80;  // px:下限保手机可读,上限维持桌面现观感
      const fs = Math.max(MIN, Math.min(MAX, byHeight, byWidth));
      el.poem.style.setProperty('--poem-fs', fs.toFixed(1) + 'px');
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

      // 窗口尺寸变化 → 以最长句重算字号
      let rz = null;
      window.addEventListener('resize', function () {
        clearTimeout(rz);
        rz = setTimeout(function () { fitFont(lastClauses); }, 120);
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

    function showSelfTest(timeWords, proposed) {
      const r = runSelfTests(DATA, {
        timeWords: timeWords, standard: proposed, festivals: FESTIVALS, testFestival: true
      });
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
    selectPoem, shichenIndexForHour, shichenProgress, poemIndexForWeekday,
    isNightHour, splitClauses, checkClauseLengths, validateTimeWords, runSelfTests
  };
}
