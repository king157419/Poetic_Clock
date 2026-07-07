# 诗意时钟 · 网页版 v1

打开页面,看到当前时辰对应的一句诗。**诗是主角,时间是配角。**

一页宣纸,墨字竖排居中,一枚朱红时辰印。十二时辰各配名句,按「日期 + 时辰」确定性选诗——
同一星期几、同一时辰,任何时刻打开都是同一句;一周之内逐日轮换,七日一循环。恒常,而非随机惊喜。深夜自动转入夜读模式。

> 种子里的 24 句都是可核实的古典名句,只是**占位**。这个时钟的灵魂,是你日后在阅读中
> 亲手逐句替换进来的句子——本项目只负责把容器造好。

---

## 文件结构

```
poetric_clock/
├── index.html                     # 结构:竖排诗 + 角落配角 + 香篆弧
├── style.css                      # 版式:宣纸/墨/印、竖排、夜读、响应式
├── main.js                        # selectPoem 纯逻辑 + 渲染器 + 自检测试
├── data/poems.json                # 唯一事实来源:全部诗词数据都在这里
├── fonts/
│   └── LXGWWenKai-subset.woff2    # 自托管霞鹜文楷子集(117.2 KB)
├── scripts/subset_font.py         # 字体子集化脚本(fonttools)
├── README.md
└── DECISIONS.md                   # 每个非显然决定的记录
```

渲染层(html/css/js)**不含任何诗句文本**——一切取自 `data/poems.json`。

---

## 本地预览

因为要用 `fetch` 读取 `data/poems.json`,浏览器会拦截 `file://` 直接双击打开的方式,
**需要一个本地静态服务器**(任选其一):

```bash
# 方式一:Python(几乎人人都有)
python -m http.server 8000
# 然后浏览器打开 http://localhost:8000

# 方式二:Node
npx serve .

# 方式三:VS Code 装 “Live Server” 插件,右键 index.html → Open with Live Server
```

> 断网也能完整渲染:全部资源(诗、脚本、字体)均自托管,页面不请求任何外部地址。
> 起本地服务器后拔网线,照常显示。

**跑自检测试**:在地址后加 `?selftest`,例如 `http://localhost:8000/index.html?selftest`,
页面左上角会浮现测试结果(含子时跨午夜边界),控制台亦有明细。

---

## 加一句诗(完整三步)

诗全部住在 `data/poems.json`。加/换一句,只需:

**第 1 步 · 改 JSON**
在对应时辰的 `poems` 数组里加一条(或替换现有条目):

```json
{
  "line": "床前明月光，疑是地上霜",
  "source": "《静夜思》",
  "author": "李白",
  "dynasty": "唐",
  "why": "为何配此时辰——可留空,由你日后填写"
}
```

- `line` 用**全角标点**(逗号 `，`、书名号 `《》`),竖排才好看。
- 十二时辰的 `id` / `range` / `alias` 不要改(见下表)。每辰句数不限,≥1 即可,
  `selectPoem` 会按当日索引在其中确定性地选一句。

**第 2 步 · 重跑字体子集**(让新出现的字进入 woff2)

```bash
pip install fonttools brotli          # 仅首次
python scripts/subset_font.py         # 源字体已在 fonts/ 下时
# 或者,让脚本顺便下载源字体:
python scripts/subset_font.py --download
```

脚本会扫描 `data/poems.json` 里所有字符 + 界面文字,重新生成
`fonts/LXGWWenKai-subset.woff2`,并检查是否 < 300KB。

> 若你新加的字都是常用字、原子集已包含,这步可跳过;拿不准就重跑一次,几秒钟。

**第 3 步 · 完成**
刷新页面即可。无需构建、无需打包。

十二时辰对照:

| id | 时辰 | 别名 | 区间 | id | 时辰 | 别名 | 区间 |
|----|----|----|------|----|----|----|------|
| zi | 子时 | 夜半 | 23–01 | wu | 午时 | 日中 | 11–13 |
| chou | 丑时 | 鸡鸣 | 01–03 | wei | 未时 | 日昳 | 13–15 |
| yin | 寅时 | 平旦 | 03–05 | shen | 申时 | 晡时 | 15–17 |
| mao | 卯时 | 日出 | 05–07 | you | 酉时 | 日入 | 17–19 |
| chen | 辰时 | 食时 | 07–09 | xu | 戌时 | 黄昏 | 19–21 |
| si | 巳时 | 隅中 | 09–11 | hai | 亥时 | 人定 | 21–23 |

---

## 投稿一句诗(公共曲库贡献)

诗意时钟是面向所有人的公开产品,曲库欢迎共建。为保证可信,采用「候选—审核」制:
**你不直接改 `poems.json`,而是往候选区 `data/candidates.json` 投稿,由主编核对出处后晋升。**

1. Fork 仓库,在 `data/candidates.json` 对应时辰的 `candidates` 里新增一条。字段同 poems.json
   (`line` / `source` / `author` / `dynasty` / `why`),并**必须**补两项:
   - `confidence`:`high`(用字与出处高度确信)或 `medium`(确为真句,但归属 / 用字 / 时辰匹配存疑);
   - `source_note`:该句可在哪部权威选本或全集中查证(如《唐诗三百首》《全唐诗》《XX 集》)。
2. 只投你确信真实存在、出处无误的名句。**严禁杜撰、拼接、改写;拿不准宁可不投。**
3. 提交 PR。主编 King 会逐条人工核对,通过后手动搬进 `data/poems.json`(并重跑字体子集)。

> 目标:每时辰扩至 7 句。当前候选区已备 40 句待核,见 `data/candidates.json`。

---

## 部署到 GitHub Pages

本项目是纯静态站点,根目录即站点根,零构建:

1. 新建仓库并推送本目录全部文件:
   ```bash
   git init && git add . && git commit -m "诗意时钟 v1"
   git branch -M main
   git remote add origin git@github.com:<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
2. 仓库页 **Settings → Pages**。
3. **Build and deployment → Source** 选 **Deploy from a branch**;
   **Branch** 选 `main`、目录 `/ (root)`,保存。
4. 等一两分钟,访问 `https://<你的用户名>.github.io/<仓库名>/`。

> 确保 `fonts/LXGWWenKai-subset.woff2` 一起入库(它才 117.2KB)。源 TTF(约 25MB)
> **不必**入库,重跑子集时用 `--download` 现取即可。

---

## 部署到 Vercel(推荐,零配置)

`index.html` 就在仓库根目录、纯静态、无构建步骤,Vercel 可零配置直接导入:

1. 在 Vercel **Add New… → Project → Import** 选中本仓库(`king157419/Poetric_Clock`)。
2. **Framework Preset 选 `Other`**(无需 Build Command / Output Directory),点 **Deploy** 即可。

> 无需安装 vercel CLI、无需命令行登录——导入与授权都在浏览器里完成。后续 push 到 `main` 会自动重新部署。

---

## 移植到墨水屏(ESP32 / 树莓派)需要带走什么

网页只是第一个渲染器。换到墨水屏时,**只需带走三样**,渲染器整段可弃:

1. **`data/poems.json`** —— 唯一事实来源。你替换进去的诗,原样跟着走。
2. **`selectPoem` 纯逻辑** —— 在 `main.js` 顶部、`if (typeof document…)` 之前的一整段:
   `shichenIndexForHour` / `poemIndexForWeekday` / `selectPoem` /
   `shichenProgress` / `isNightHour`。它们不碰 DOM、不碰网络,输入 `(date, data)`
   输出该时该辰的诗,确定性、可测(`runSelfTests` 也一并带走当回归测试)。
   移植到 C / MicroPython 时,照这几十行的逻辑一比一翻译即可。
3. **版式规则** —— 即「产品本体」:
   - 宣纸底 `#f5f1e8` / 墨 `#2b2b2b`;唯一强调色印章红 `#a63f36` **只用在一处**(时辰印)。
   - 诗竖排、大字、居中;出处作者小字随行;时辰名与现代时间退到角落。
   - 留白 ≥ 六成;无阴影/渐变/图标/仪表盘感。
   - 23:00–05:00 夜读:深底暖字,版式不变。
   - 切换时旧句淡出、新句淡入 ≤ 800ms(墨水屏可简化为整屏刷新)。

墨水屏不需要:`index.html` / `style.css` / `main.js` 的渲染器部分 / woff2(用屏端自带字库或另做点阵)。

---

## 验收清单(逐项核对结果)

- [x] **12 时辰 × 2 句,出处齐全,无杜撰** —— 24 句全部为可核实名句,`line/source/author/dynasty` 齐全;`data/poems.json` 顶部注明为占位。脚本校验:12 时辰、24 句、别名全对、字段无缺。
- [x] **子时跨午夜边界正确(附测试)** —— `selectPoem` 对 `hour===23` 滚日(周循环下仍成立);`?selftest` 与 Node 双跑 **10/10 通过**,含「23:30 与次日 00:30 同为子时且同一句」「22:59 为亥、23:00 为子」「同星期几+同时辰隔周同句」「午时一周覆盖全部句」「十二时辰×七星期几均有完整句」。
- [x] **断网后本地打开仍完整渲染(字体确自托管)** —— 实测所有请求皆本地(`style.css`/`main.js`/`data/poems.json`/`fonts/…woff2`),源码无任何 `http(s)://`/CDN 引用;字体 `document.fonts.check` 为真。需经本地静态服务器(见上)。
- [x] **字体 woff2 < 300KB**(2026-07-06 复跑确认)—— 以 `D:\conda\miniconda3\python.exe`(Python 3.13 + fonttools 4.63)重跑 `scripts/subset_font.py`:任务①复跑与 v1 逐字节一致(120,364 字节);任务③因 `poems.json` 文案微调重跑,当前产物 `LXGWWenKai-subset.woff2` = **117.2 KB / 120,028 字节 / 554 字形**(含竖排标点形 `vert`),341 个渲染字形校验无缺。自托管,断网刷新照常显示文楷。
- [x] **无 console 报错** —— 加载与交互全程控制台**无警告/报错**,无失败请求。
- [x] **手机竖屏与桌面横屏两种布局都成立** —— 桌面 1280×800:诗 64px、居中、占屏 16.6%(留白 83%),无溢出;手机 390×844:诗约 34px、居中、占屏 19.3%,香篆弧与角落不重叠,无溢出。全页唯一红元素为印章。

测试环境:Windows 11 + Python 3.13(`D:\conda\miniconda3`)+ fonttools 4.63;浏览器经内置预览引擎(Chromium)核验。子集给定相同输入可逐字节复现(v1 便携 3.12 与 v1.1 conda 3.13 对同一数据均得 120,364 字节;文案微调后为 120,028 字节)。

---

## 字体来源与许可

霞鹜文楷(LXGW WenKai),开源字体,SIL Open Font License 1.1。
源:<https://github.com/lxgw/LxgwWenKai>(本项目基于 `v1.522` 的 `LXGWWenKai-Regular.ttf` 子集化)。
兜底字体链:`'LXGW WenKai Subset', 'Songti SC', 'Noto Serif CJK SC', serif`。
