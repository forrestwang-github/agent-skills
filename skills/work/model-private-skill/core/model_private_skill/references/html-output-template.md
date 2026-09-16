# 独立 HTML 交付模板

交付物必须是可直接打开的 UTF-8 HTML 文件，文件名为 <规范化模型-id>-deployment-plan.html。
不要只在对话中输出 HTML 片段或 Markdown 表格；保留下列章节、类名、表格列和行序，只替换 {{...}} 占位内容。

~~~html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{模型服务 ID}} 部署规划</title>
  <style>
    body { max-width:1240px; margin:36px auto; padding:0 24px 48px; color:#1f2937; background:#f8fafc; font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; }
    .plan { padding:32px; background:#fff; border:1px solid #e2e8f0; border-radius:14px; box-shadow:0 8px 28px rgba(15,23,42,.06); }
    h1 { margin:0 0 8px; color:#0f172a; font-size:30px; } h2 { margin:32px 0 12px; padding-left:11px; border-left:4px solid #2563eb; color:#0f172a; font-size:20px; } h3 { color:#1e3a8a; font-size:17px; } h4 { margin:16px 0 6px; color:#0f172a; font-size:15px; }
    p { margin:8px 0; } .summary { color:#1e3a8a; font-size:17px; } .muted { color:#64748b; font-size:13px; } .estimate-note,.technical-note { margin:8px 0; color:#64748b; font-size:12px; line-height:1.6; } .estimate-label { margin:12px 0 4px; color:#1e3a8a; font-size:13px; } .note,.table-note { padding:12px 14px; border-radius:8px; background:#eff6ff; color:#1e40af; } .table-note { font-size:13px; }
    .model-facts { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); column-gap:28px; } .conclusion-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; } .model-facts div { padding:7px 0; border-bottom:1px solid #e2e8f0; } .plan-card { padding:14px; border:1px solid #dbeafe; border-radius:10px; background:#f8fbff; } dt { color:#475569; font-size:13px; } dd { margin:2px 0 0; color:#0f172a; font-weight:600; } .plan-card h3 { margin-top:0; } .plan-card dl { display:grid; grid-template-columns:7.5em 1fr; gap:5px 10px; margin:0; } .plan-card dd { margin:0; font-weight:400; }
    table { width:100%; border-collapse:collapse; margin:14px 0 8px; font-size:14px; } caption { padding:10px; color:#0f172a; font-weight:700; text-align:left; caption-side:top; } th,td { padding:10px 12px; border:1px solid #cbd5e1; vertical-align:top; text-align:left; } thead th { background:#e0e7ff; color:#1e3a8a; } tbody th[scope="row"] { min-width:100px; background:#f8fafc; white-space:nowrap; } .category { min-width:76px; background:#eef2ff; color:#3730a3; text-align:center; vertical-align:middle; }
    .formula { padding:9px 11px; border-radius:6px; background:#f1f5f9; color:#334155; font:13px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre-wrap; } ol,ul { padding-left:22px; } li { margin:6px 0; } a { color:#1d4ed8; }
    @media (max-width:760px) { body { margin:0; padding:0; } .plan { padding:18px; border:0; border-radius:0; } .model-facts,.conclusion-grid { grid-template-columns:1fr; } table { display:block; overflow-x:auto; } }
  </style>
</head>
<body>
<main class="plan">
  <h1>{{模型服务 ID}} 部署规划</h1>
  <p class="muted">模型服务 ID：{{模型服务 ID}}；官方制品：{{官方制品 ID}}；固定 revision：{{revision 或待固定说明}}；访问日期：{{日期}}。</p>
  <section data-section="model-facts">
    <h2>模型基本信息</h2>
    <dl class="model-facts">
      <div><dt>模型服务 ID</dt><dd>{{服务调用 ID}}</dd></div><div><dt>开源制品与 revision</dt><dd>{{制品 ID；commit 或 tag}}</dd></div>
      <div><dt>参数与架构</dt><dd>{{总/激活参数；Dense 或 MoE；层数}}</dd></div><div><dt>输入形态</dt><dd>{{文本/视觉/音频等模态}}</dd></div>
      <div><dt>上下文能力</dt><dd>{{原生/扩展最大上下文}}</dd></div><div><dt>权重与制品大小</dt><dd>{{精度；权重或制品总量}}</dd></div>
      <div><dt>注意力/特殊算子</dt><dd>{{普通注意力或特殊状态需求}}</dd></div><div><dt>部署相关限制</dt><dd>{{框架兼容性、量化或并行限制}}</dd></div>
    </dl>
    <p class="technical-note" data-section="technical-terms"><strong>技术术语说明：</strong>{{模型使用混合注意力或特殊算子时，在首次出现处简述其作用、对显存/吞吐/兼容性的影响，以及框架支持、实测或限流的决策点。}}</p>
  </section>
  <section>
    <h2>部署结论</h2>
    <p class="summary">{{一句话结论：两档 GPU、拓扑和推荐框架；性能须压测验证。}}</p>
    <div class="conclusion-grid">
      <article class="plan-card" data-tier="economic"><h3><strong>经济型</strong></h3><dl><dt>GPU 与副本</dt><dd>{{GPU 型号、每副本卡数、总卡数}}</dd><dt>节点与并行</dt><dd>{{节点数；TP/PP/DP}}</dd><dt>适用负载</dt><dd>{{典型并发、典型长度、输入形态}}</dd><dt>可用性</dt><dd>{{单副本或故障影响}}</dd><dt>性能目标</dt><dd>{{TTFT、输出速度；规划值/待压测}}</dd></dl></article>
      <article class="plan-card" data-tier="peak-production"><h3><strong>峰值生产型</strong></h3><dl><dt>GPU 与副本</dt><dd>{{GPU 型号、每副本卡数、总卡数}}</dd><dt>节点与并行</dt><dd>{{节点数；TP/PP/DP}}</dd><dt>适用负载</dt><dd>{{峰值并发、最大长度并发、输入形态}}</dd><dt>可用性</dt><dd>{{双副本/active-active/故障后能力}}</dd><dt>性能目标</dt><dd>{{TTFT、输出速度；规划值/待压测}}</dd></dl></article>
    </div>
    <p class="note">默认负载、长度、最大长度同时并发和性能目标已分档写入资源配置表的规划基线，均为估算输入而非实测 SLA。</p>
  </section>
  <section>
    <h2>资源配置</h2>
    <table>
      <caption>资源配置建议（{{精度与负载假设}}；大致估算，非性能 SLA）</caption>
      <thead><tr><th scope="col">分类</th><th scope="col">资源/指标</th><th scope="col">资源/指标说明</th><th scope="col">经济型</th><th scope="col">峰值生产型</th></tr></thead>
      <tbody>
        <tr data-category="planning-baseline"><th scope="rowgroup" rowspan="5" class="category">规划基线</th><th scope="row">活跃并发</th><td>确定吞吐与缓存</td><td>{{典型活跃请求数}}</td><td>{{峰值活跃请求数}}</td></tr>
        <tr><th scope="row">输入/输出长度</th><td>确定上下文规模</td><td>{{典型输入 + 输出 Token}}</td><td>{{最大输入 + 输出 Token}}</td></tr>
        <tr><th scope="row">最大长度同时并发</th><td>校验显存上界</td><td>{{同时执行最大长度请求数}}</td><td>{{同时执行最大长度请求数}}</td></tr>
        <tr><th scope="row">性能目标</th><td>定义体验验收线</td><td>{{P95 TTFT；输出 Token/s}}</td><td>{{P95 TTFT；输出 Token/s}}</td></tr>
        <tr><th scope="row">输入形态</th><td>评估预处理开销</td><td>{{文本/多模态范围}}</td><td>{{文本/多模态范围}}</td></tr>
        <tr data-category="resource-advice"><th scope="rowgroup" rowspan="8" class="category">资源建议</th><th scope="row">显存容量</th><td>容纳权重、KV/状态池与运行工作区</td><td>{{每推理副本所需 GPU 显存}}</td><td>{{每推理副本所需 GPU 显存}}</td></tr><tr><th scope="row">GPU推荐</th><td>按显存、算力和互联确定型号与卡数</td><td>{{GPU 型号}} × {{每副本 GPU 数}} / 副本</td><td>{{GPU 型号}} × {{每副本 GPU 数}} / 副本</td></tr>
        <tr><th scope="row">CPU</th><td>承担 Tokenization、调度与预处理</td><td>{{每节点 vCPU}}</td><td>{{每节点 vCPU}}</td></tr><tr><th scope="row">内存</th><td>缓存模型加载、请求与运行时数据</td><td>{{每节点内存}}</td><td>{{每节点内存}}</td></tr>
        <tr><th scope="row">系统盘</th><td>存放操作系统、运行环境与日志</td><td>{{每节点系统盘}}</td><td>{{每节点系统盘}}</td></tr><tr><th scope="row">模型盘</th><td>存放模型权重、镜像与本地版本</td><td>{{每节点模型盘}}</td><td>{{每节点模型盘及回滚策略}}</td></tr>
        <tr><th scope="row">共享存储</th><td>集中保存版本、回滚制品与共享数据</td><td>{{集群共享存储}}</td><td>{{集群共享存储}}</td></tr><tr><th scope="row">公网带宽（用户接入）</th><td>承载用户到服务入口的请求与响应</td><td>{{用户接入公网带宽}}</td><td>{{用户接入公网带宽}}</td></tr>

        <tr data-category="deployment-advice"><th scope="rowgroup" rowspan="4" class="category">部署建议</th><th scope="row">精度</th><td>权衡效果和显存</td><td>{{权重精度 / KV 精度}}</td><td>{{权重精度 / KV 精度}}</td></tr>
        <tr><th scope="row">TP / PP / DP</th><td>定义张量、流水线和数据并行方式</td><td>{{TP / PP / DP}}</td><td>{{TP / PP / DP}}</td></tr><tr><th scope="row">部署框架</th><td>提供模型加载、调度、批处理与接口</td><td>{{框架名称；版本或镜像固定策略}}</td><td>{{框架名称；版本或镜像固定策略}}</td></tr>
        <tr><th scope="row">副本/节点</th><td>决定容量扩展、故障域与高可用</td><td>{{副本数}} 副本 / {{节点数}} 节点</td><td>{{副本数}} 副本 / {{节点数}} 节点</td></tr>
        <tr data-row="service-scenario"><th scope="row" class="category">服务能力</th><th scope="row">业务场景与能力差异</th><td>说明适用边界</td><td>{{典型并发、单副本架构、TTFT/Token/s 规划目标与故障影响}}</td><td>{{峰值并发、active-active、TTFT/Token/s 规划目标与故障后能力}}</td></tr>
      </tbody>
    </table>
    <div class="table-note" data-section="special-notes"><strong>说明</strong><ul>
<li><strong>必备资源：</strong>显存、GPU、CPU、内存和系统盘是运行服务的基础，不能省略。</li>
<li><strong>可酌情下调：</strong>纯文本、短上下文或低并发时，可下调 CPU、内存、公网用户接入带宽和共享存储；不能仅靠压缩显存余量替代压测。</li>
<li><strong>可合并资源：</strong>单节点经济型可在容量、IOPS、备份满足时合并模型盘与共享存储；生产型建议分离，系统盘不与二者合并。</li>
<li><strong>术语说明：</strong>TP 为同一模型跨卡切分，PP 为按层切分，DP 为多个完整副本并行服务；多卡配置须由模型和框架实际支持。</li>
<li><strong>混合注意力/特殊算子：</strong>{{说明各模块承担的作用、KV 或状态内存影响，以及是否必须由框架支持并通过压测核实。}}</li>
</ul></div>
  </section>
  <section>
    <h2>GPU 选型建议</h2>
    <p class="muted">部署结论和“GPU推荐”行中出现的型号（如 H100、H200）仅为优选示例，不是唯一答案。可按以下路径筛选其他卡型；最终仍以框架兼容性和压测结果定型。</p>
    <h3>简单推算路径</h3>
    <ol>
      <li><strong>先看精度与软件支持。</strong>目标精度、混合注意力/特殊算子和推理框架必须受支持；任一项不满足，直接排除。</li>
      <li><strong>再看显存能否装下一个副本。</strong>将资源表“显存容量”的每副本需求与候选卡的可用显存比较。单卡可用显存达到需求，可作为单卡候选；这只证明容量可行，不代表性能达标。</li>
      <li><strong>单卡不够时再定卡数与并行。</strong>只有框架支持目标 TP/PP、同一副本的卡间互联满足要求时，才按并行策略把一个副本分摊至多卡；不能把任意多张卡的标称显存直接相加。</li>
      <li><strong>最后用压测确认。</strong>在可部署的 1–3 个方案中，验证 TTFT、输出速度、峰值显存和稳定性，选出满足目标且总卡数合理的方案。</li>
    </ol>
    <h3>精细推算路径</h3>
    <ol>
      <li><strong>容量边界。</strong>用“权重 + KV/状态池 + 工作区”复核每副本需求，并按有效显存比例换算候选卡的可用显存；长上下文、视觉输入和特殊状态按压测上浮。</li>
      <li><strong>并行与互联边界。</strong>确定每副本卡数、TP/PP 切分、单节点容纳量和节点间网络。多卡 TP/PP 重点核对 NVLink/NVSwitch 或等效高速互联及 RDMA；纯 DP 副本主要关注网络冗余。</li>
      <li><strong>性能排序。</strong>在通过上述硬门槛的卡型中，优先比较目标精度吞吐、HBM 显存带宽、Tensor Core 能力和互联带宽；CUDA Core、RT Core 等非主要推理瓶颈指标仅作辅助参考。</li>
      <li><strong>工程与生命周期验证。</strong>核对卡型形态、功耗散热、服务器插槽/供电、驱动与框架版本、监控能力和备件可得性；以同版本模型、同长度和同并发压测结果定最终型号与卡数。</li>
    </ol>
    <p class="note">卡型先满足“精度/软件、可用显存、可实现的并行拓扑”三项硬门槛，再按性能、工程条件和压测排序；示例型号仅用于说明最终筛选结果。</p>
  </section>
  <section data-section="resource-estimates">
    <h2>估算过程</h2>
    <p class="muted">本节只解释资源配置表“资源建议”的七类资源。每项按输入、估算过程、术语备注、结果说明；GPU 型号由这些结果在上一节筛选，不在此重复估算。计算中出现的每一个数字都必须在“输入”中说明数值、单位、来源或采用理由；公式中不得出现未解释的常量。</p>
    <h3>1. 显存容量：保障权重、缓存与工作区驻留</h3>
    <p><strong>输入：</strong>{{总驻留参数、权重/KV 精度、典型/最大长度、并发、特殊状态与工作区；模型参数来自官方制品，负载来自用户输入或默认值。}}</p>
    <p class="estimate-label"><strong>估算过程：</strong></p>
    <p class="formula">权重显存 = 总驻留参数 × 权重位数 ÷ 8；KV/状态显存 = Token 数 × 同时请求数 × 每 Token 字节数；规划显存 = (权重 + KV/状态 + 工作区) ÷ 有效显存比例。</p>
    <p class="estimate-note"><strong>术语备注：</strong>{{权重是加载到显存的模型参数；KV/状态池是请求上下文的运行缓存；运行工作区是推理引擎临时占用。出现 Gated Attention 时说明其 KV 缓存随长度/并发增长；出现 Gated DeltaNet 时说明其线性注意力状态需由框架支持并单独实测。}}</p>
    <p><strong>结果：</strong>{{分别给出经济型与峰值生产型的每副本显存下限；未公开特殊状态或多模态开销写为待压测余量。}}</p>
    <h3>2. CPU：支撑分词、调度与请求预处理</h3>
    <p><strong>输入：</strong>{{每节点 GPU 数、并发、Tokenization、多模态预处理和 CPU Offload 策略。}}</p>
    <p class="estimate-label"><strong>估算过程：</strong></p>
    <p class="formula">每节点 vCPU = max(并发相关 CPU 预算, GPU 服务进程基线)；多模态预处理或 CPU Offload 单独加算。</p>
    <p class="estimate-note"><strong>术语备注：</strong>{{Tokenization 指文本与 Token 的转换；CPU Offload 指将部分模型或缓存放到内存，会显著增加 CPU 与内存需求。}}</p>
    <p><strong>结果：</strong>{{分别给出两档所需 vCPU，并说明可下调或必须上调的负载条件。}}</p>
    <h3>3. 内存：保障制品加载、缓存与运行时数据</h3>
    <p><strong>输入：</strong>{{模型制品大小、运行时缓存、加载/回滚策略和是否启用 Offload。}}</p>
    <p class="estimate-label"><strong>估算过程：</strong></p>
    <p class="formula">内存 = max(运行基线, 制品大小 × 加载与回滚系数)；Offload 或多模态缓存额外计入。</p>
    <p class="estimate-note"><strong>术语备注：</strong>{{制品是可下载的模型文件集合；ceil 表示向上取整，保证容量不足时按更大的整数容量配置。}}</p>
    <p><strong>结果：</strong>{{分别给出两档每节点内存下限；明确该配置不等于默认启用 CPU Offload。}}</p>
    <h3>4. 系统盘：承载系统、运行环境与日志</h3>
    <p><strong>输入：</strong>{{操作系统、驱动/容器、日志、监控和诊断文件的工程基线。}}</p>
    <p class="estimate-label"><strong>估算过程：</strong></p>
    <p class="formula">系统盘 = 系统与运行环境基线 + 日志与诊断预留。</p>
    <p class="estimate-note"><strong>术语备注：</strong>{{工程基线是为操作系统、驱动、容器、日志和诊断预留的最低容量，不包含模型制品。}}</p>
    <p><strong>结果：</strong>{{分别给出两档每节点系统盘容量；系统盘不得与模型盘或共享存储合并。}}</p>
    <h3>5. 模型盘：保存本地模型版本与回滚副本</h3>
    <p><strong>输入：</strong>{{官方模型制品总量、本地保留版本数和安全余量。}}</p>
    <p class="estimate-label"><strong>估算过程：</strong></p>
    <p class="formula">模型盘 = ceil(制品总量 × 本地版本数 × 余量系数)。</p>
    <p class="estimate-note"><strong>术语备注：</strong>{{制品是模型权重、配置和 tokenizer 等文件集合；ceil 为向上取整；回滚版本用于上线异常时恢复到上一可用版本。}}</p>
    <p><strong>结果：</strong>{{给出两档模型盘下限和配置值；经济型通常保留一个版本，生产型保留当前与回滚版本。}}</p>
    <h3>6. 共享存储：集中保存制品、配置与共享数据</h3>
    <p><strong>输入：</strong>{{集中版本、回滚制品、共享配置和运行数据策略。}}</p>
    <p class="estimate-label"><strong>估算过程：</strong></p>
    <p class="formula">共享存储 = 集中版本集合 + 回滚预留 + 共享运行数据；不按节点重复相乘。</p>
    <p class="estimate-note"><strong>术语备注：</strong>{{共享存储由集群共同使用，不按节点重复相乘；制品和回滚预留用于集中分发与恢复。}}</p>
    <p><strong>结果：</strong>{{分别给出两档集群共享存储容量，并说明是否可与模型盘合并。}}</p>
    <h3>7. 公网带宽（用户接入）：承载用户请求与响应</h3>
    <p><strong>输入：</strong>{{响应方式；用户实测典型/峰值到达 RPS；非流式时的响应完成 RPS；活跃流并发、单请求 Token/s、输入/输出 Token、平均字节数与协议开销。}}</p>
    <p class="estimate-note"><strong>范围说明：</strong>本项仅估算公网用户接入带宽，即用户到 API 网关或服务入口的南北向请求与响应。在实际部署中，还应注意：服务私网带宽用于网关、推理副本、存储等内部东西向通信，按部署拓扑单独核实；若同一推理副本采用跨节点 TP/PP，还需单独评估低时延高速互联与 RDMA 网络。二者均不纳入本公式。</p>
    <p class="estimate-label"><strong>估算过程：</strong></p>
    <p class="formula">公网入向峰值 = 用户实测到达 RPS × 单请求输入字节 × 协议系数；流式公网出向峰值 = 活跃流并发 × 单请求 Token/s × 平均字节数 × 8 × 协议系数；非流式公网出向峰值 = 用户实测响应完成 RPS × 单请求输出字节 × 协议系数；公网用户接入带宽 = max(入向峰值, 适用的出向峰值)。</p>
    <p class="estimate-note"><strong>术语备注：</strong>{{到达 RPS 是每秒新进入服务入口的请求数；响应完成 RPS 是每秒向用户完成发送的完整响应数；流式输出持续传输增量 Token，非流式输出集中发送完整响应。协议系数用于覆盖 JSON、TLS，以及 SSE/WebSocket 事件封装和心跳等非 Token 开销。}}</p>
    <p><strong>结果：</strong>{{分别直接给出峰值入向、峰值出向与二者较大值；任一适用方向缺少真实 RPS 或输出速度时，公网用户接入带宽为待补充，不以并发或平均时长反推。图片、视频等用户载荷必须按实际请求重新计算。}}</p>
  </section>
  <section><h2>部署注意事项</h2><ul><li>{{混合注意力、多模态、量化、缓存、并行和故障域等注意事项。}}</li></ul></section>
  <section><h2>压测与验收计划</h2><ul><li>{{典型、峰值、最大长度场景；验收 TTFT、ITL、Token/s、吞吐、显存、错误率和稳定时长。}}</li></ul></section>
  <section><h2>证据来源</h2><ul><li>{{模型、GPU、框架和性能关键结论的合格直接链接、发布者、版本和访问日期。}}</li></ul></section>
</main>
</body>
</html>
~~~

固定要求：

- 交付物必须是独立 HTML：包含 doctype、lang="zh-CN"、UTF-8、viewport、title、内嵌 CSS 与 main.plan；无需外部样式或脚本。
- 开头必须有模型基本信息，至少写明制品/revision、参数与架构、模态、上下文、权重/制品大小、注意力或特殊算子。
- 部署结论将<strong>经济型</strong>与<strong>峰值生产型</strong>并排展示，且二者均按 GPU 与副本、节点与并行、适用负载、可用性、性能目标五个维度独立成行。
- 资源配置表固定五列：分类、资源/指标、资源/指标说明、经济型、峰值生产型。资源/指标说明不超过 30 个汉字；规划默认值只能分档写入规划基线表行。
- 显存容量是资源建议的第一行，且只写每推理副本的客观显存需求，不得出现任何具体 GPU 型号；GPU推荐紧随其后；副本/节点为部署建议的最后一行。
- 业务场景与能力差异仅一行，经济型和峰值生产型分别在对应列，不能拆成上下两行；不要显示性能状态。
- 资源表下方必须有小字的“说明”：分条说明必备资源、可按负载酌情下调或合并的资源，并简要解释 TP/PP/DP 等专业词汇。
- 资源表后依次为 GPU 选型建议、估算过程。GPU 选型建议先说明示例型号非唯一答案，再分为简单推算路径和精细推算路径：前者按精度/软件、显存、并行、压测快速筛选；后者按容量、并行与互联、性能、工程与生命周期细化比较。估算过程只按显存、CPU、内存、系统盘、模型盘、共享存储、公网带宽（用户接入）七类资源展开；标题使用“序号 + 资源名：用途”，每项按输入、估算过程、术语备注、结果说明，公式中的所有数值必须在输入中标注单位、来源或采用理由；公网带宽必须按响应方式分支计算：入向只使用用户实测到达 RPS，流式出向使用活跃流并发和单请求 Token/s，非流式出向使用用户实测响应完成 RPS；不得用并发或时长反推值配置公网突发带宽。公网带宽的输入下必须以“在实际部署中，还应注意”说明服务私网与跨节点 GPU 网络按拓扑单独核实；峰值入向、峰值出向及其较大值均直接输出，不设置人为下限；结果直接陈述，不再写“与表格对应”。模型出现混合注意力或特殊算子时，须在首次出现处以小字说明“作用、资源/兼容性影响、部署决策”三点。
- 最大长度同时并发必须明确为同时执行最大长度请求数，不得把请求数表述成 Token 数。
- 最后必须包含证据来源，且只列出符合证据来源策略的直接链接。
