# 单文件 HTML 阅读版规范

仅在需要 HTML 阅读版时读取。HTML 从 Markdown 知识源派生，不能拥有 Markdown 中不存在且无来源的核心结论。

## 1. 基本要求

- 完整 HTML5 文档，`<html lang="zh-CN">`；
- 含 UTF-8、视口、标题和描述元信息；
- CSS 全部内嵌，不加载外部字体、样式、脚本、图片或图表库；
- 可使用少量无存储 JavaScript 做目录高亮或平滑滚动；
- 禁止 `localStorage`、`sessionStorage` 和远程运行依赖；
- A4 打印友好，核心块尽量不跨页；
- 引用 URL 可以联网打开，但离线时不影响正文理解。

## 2. 色板与页面

```css
:root{
  --ink:#17233b;
  --ink-2:#3c4a63;
  --ink-3:#6b7890;
  --line:#e3e8f0;
  --bg:#f6f8fb;
  --card:#ffffff;
  --accent:#1f5eff;
  --accent-soft:#eef3ff;
  --teal:#0e7f74;
  --amber:#b45309;
  --red:#b91c1c;
  --green:#15803d;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;
     background:var(--bg);color:var(--ink);line-height:1.75;font-size:15px}
main{margin-left:230px;padding:32px 40px}
.content{max-width:960px;margin:0 auto}
section{scroll-margin-top:20px;margin-bottom:42px}
h2{border-left:4px solid var(--accent);padding-left:12px}
```

## 3. 固定目录

HTML 必须包含目录；目录条目只到两级，并与正文真实 ID 一一对应。

```html
<nav class="toc" aria-label="报告目录">
  <div class="toc-title">目录</div>
  <a href="#summary">先看结论</a>
  <a href="#scope">学习目标与范围</a>
  <a href="#mechanism">核心机制</a>
  <a href="#example" class="sub">具体过程演示</a>
</nav>
<main><div class="content">……</div></main>
```

```css
.toc{position:fixed;top:0;left:0;bottom:0;width:230px;overflow-y:auto;
     background:#fff;border-right:1px solid var(--line);padding:18px 14px;z-index:10}
.toc-title{font-weight:700;font-size:13px;color:var(--ink-3);letter-spacing:2px;margin-bottom:10px}
.toc a{display:block;font-size:13px;color:var(--ink-2);text-decoration:none;
       padding:5px 8px;border-radius:6px;line-height:1.5}
.toc a:hover{background:var(--accent-soft);color:var(--accent)}
.toc a.sub{padding-left:20px;font-size:12.5px;color:var(--ink-3)}
@media (max-width:1100px){
  .toc{position:static;width:auto;border-right:0;border-bottom:1px solid var(--line)}
  main{margin-left:0;padding:24px}
}
@media print{
  .toc{display:none}
  main{margin-left:0;padding:0}
  body{background:#fff}
  @page{size:A4 portrait;margin:16mm}
}
```

目录始终固定在视口左上角；窄屏时允许降级为顶部目录。不要用悬浮按钮代替目录。

## 4. 内容组件

### TL;DR 结论块

用于聚合少量核心结论，可以使用浅色大块。结论必须在后文得到解释和证据支持。

### 因素卡片

只在因素分析模式中使用。一张卡片对应一个独立保留因素，包含机制、边界、证据、优化动作和验证指标。动作旁可使用成本与必要性徽章。

### 普通并列内容

使用 H3、小徽章和连续段落，不使用卡片网格。卡片过多会切断论证链。

### 表格

只承担结构化对比或筛选，不承载唯一的核心解释。窄屏允许横向滚动。

```css
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;background:var(--card)}
th{background:var(--accent);color:#fff;padding:10px 12px;text-align:left}
td{border-bottom:1px solid var(--line);padding:10px 12px;vertical-align:top}
```

### 注解与证据局限

```css
.note{background:#fafbfd;border:1px dashed var(--line);border-left:3px solid var(--ink-3);
      border-radius:8px;padding:12px 16px;margin:14px 0;color:var(--ink-2);break-inside:avoid}
```

注解就近解释旁支概念；证据局限需要清楚标出，不能用弱化字号隐藏。

### 徽章

```css
.badge{display:inline-block;font-size:12px;font-weight:600;padding:2px 10px;border-radius:999px;white-space:nowrap}
.cost-low{background:#e8f5ec;color:var(--green)}
.cost-mid{background:#fdf1e3;color:var(--amber)}
.cost-high{background:#fbe9e9;color:var(--red)}
.must{background:var(--accent-soft);color:var(--accent)}
.should{background:#e6f4f1;color:var(--teal)}
.case{background:#f0f1f4;color:var(--ink-3)}
```

## 5. 来源

正文引用标记链接到文末来源，例如 `<a href="#source-s1">[S1]</a>`。每条来源包含标题、作者或机构、类型、版本或日期、URL、检索日期和所支撑声明。外部链接添加 `target="_blank" rel="noopener noreferrer"`。

## 6. 打印和可访问性

- 正文与背景保持足够对比度；
- 导航具有 `aria-label`，表格使用表头，图片如存在则有替代文本；
- 因素卡片、注解和代码块设置 `break-inside:avoid`；
- 链接不能仅通过颜色表达；
- 打印隐藏目录，但保留来源 URL 的可识别文本；
- 不用整页固定高度，不让内容因分页被裁切。
