const WIRE = __DATA__;
const LIVE = __LIVE__;
function decodeWire(wire){
  if(!wire||wire.v!==1)throw new Error('Unsupported dashboard data version');
  const table=wire.s||[],mark='§';
  const decode=value=>{
    if(typeof value==='string'){
      if(!value.startsWith(mark))return value;
      if(value.startsWith(mark+mark))return value.slice(1);
      return table[parseInt(value.slice(1),36)];
    }
    if(Array.isArray(value))return value.map(decode);
    if(value&&typeof value==='object'){const out={};Object.entries(value).forEach(([key,item])=>out[decode(key)]=decode(item));return out;}
    return value;
  };
  return decode(wire.d);
}
let DATA = decodeWire(WIRE);
const I18N_EXACT = Object.freeze({
  '点我有惊喜':'Click for a surprise','点我':'Click me','Token 用量':'Token Usage','查看数据可信度':'View data provenance','数据体检 —':'Data Health —','用量状态计算中':'Calculating usage status','状态 —':'Status —','切换主题':'Switch theme','主题：自动':'Theme: Auto','环境动效强度':'Ambient motion intensity','动效 · 自动':'Motion · Auto','动效 · 完整':'Motion · Full','动效 · 克制':'Motion · Low','动效 · 关闭':'Motion · Off','模块开关':'Module settings','显示模块':'Visible Modules','作息时钟':'Activity Clock','趣味换算':'Fun Conversions','5h 计费块':'5h Usage Blocks','每天趋势':'Daily Trend','作息织锦':'Activity Tapestry','每模型趋势':'Per-model Trend','数据可信度':'Data Provenance','项目透镜':'Project Lens','复用之河':'Reuse River','Token 流光图':'Token Flow Map','Token 生物':'Token Creature','柱图竞赛':'Bar Chart Race','今日运势':'Daily Fortune','Token 年鉴':'Token Almanac','成就徽章':'Achievements','Token 星云':'Token Nebula','Top 榜':'Top Lists','Dashboard 区域导航':'Dashboard section navigation','总览':'Overview','趋势':'Trend','体检':'Health','年鉴':'Almanac','项目':'Projects','节奏':'Rhythm','复用':'Reuse','流光':'Flow','成就':'Achievements','查看当前视图状态':'View current state','月 · 全部模型 · 全景':'Month · All models · Overview','Current View · 当前视图':'Current View','⧉ 复制视图链接':'⧉ Copy view link','↺ 恢复全景':'↺ Reset view','Signal Dock 信号坞':'Signal Dock','悬停或聚焦数据以 Peek':'Hover or focus data to Peek','还没有选择信号':'No signal selected','清除固定信号':'Clear pinned signal','模型、周期、项目与会话可以先 Peek；固定 Pin 后，继续比较兼容的本地聚合证据。':'Peek models, periods, projects, and sessions. Pin one to compare compatible local aggregate evidence.','未固定信号':'No pinned signal','悬停或聚焦以查看':'Hover or focus to inspect','固定后再 Peek 一个兼容信号':'Pin, then Peek a compatible signal','选择一个信号':'Select a signal','按住 Alt / Option 临时查看精确值':'Hold Alt / Option to reveal exact values','⌥ 精确层':'⌥ Exact values','数据气候计算中':'Calculating data climate','正在读取你的本地 Token 气压、活跃时段与缓存云层。':'Reading local Token pressure, active hours, and cache patterns.','相对近况':'Recent baseline','数据侦探，点击切换洞察':'Data Detective; click to cycle insights','YOU MAY NOT HAVE NOTICED · 数据侦探':'YOU MAY NOT HAVE NOTICED · DATA DETECTIVE','正在寻找藏在数字之间的线索……':'Looking for patterns hidden between the numbers…','所有发现均由本地数据计算，不调用 AI。':'All insights are computed locally without AI.','固定当前洞察':'Pin current insight','◇ 固定':'◇ Pin','换一条发现':'Show another insight','↻ 换一条':'↻ Next insight','沿当前范围开始数据寻迹（I）':'Start a Data Trail for the current scope (I)','⌁ 开始寻迹':'⌁ Start Trail','退出回看（Esc）':'Exit time probe (Esc)','退出时光探针':'Exit time probe','数据寻迹':'Data Trail','沿当前范围检查模型、项目、会话与 Context 证据；不会改变筛选，除非你明确选择。':'Inspect model, project, session, and context evidence in the current scope. Filters change only when you explicitly choose.','← 上一步':'← Back','关闭数据寻迹':'Close Data Trail','关闭':'Close','数据寻迹步骤':'Data Trail steps','总 token':'Total tokens','复制总 Token 精确值':'Copy exact total Token value','复制精确值':'Copy exact value','缓存命中 · Read':'Cache share · Read','调用次数':'Calls','命中模型数':'Models used','主力模型':'Primary model','粒度与筛选':'Granularity & Filters','统计粒度':'Aggregation granularity','按日':'Daily','按周':'Weekly','按月':'Monthly','模型筛选':'Model filters','全选':'Select all','清空':'Clear','撤销':'Undo','每期 token（按模型堆叠）':'Tokens per period (stacked by model)','按住预览上一期轮廓；点击固定对比':'Hold to preview the prior period; click to pin comparison','◫ 按住对比':'◫ Hold to Compare','拖动或用方向键预览 · Enter / Space / 点击提交':'Drag or use arrow keys to preview · Enter / Space / click to commit','数据可信度实验室 · DATA PROVENANCE':'DATA PROVENANCE LAB','解释这份快照能支持哪些分析，以及某些视图为什么可能稀疏':'Explains which analyses this snapshot supports and why some views may be sparse','复制体检摘要':'Copy health summary','Token 年鉴 · 会记得你的 Dashboard':'Token Almanac · Local Dashboard Memory','赛季、个人纪录与时间胶囊只由本地聚合快照生成；这是个人历史，不是全球排名。':'Seasons, personal records, and time capsules come only from local aggregate snapshots. This is personal history, not a global ranking.','✦ 打开时间胶囊':'✦ Open Time Capsule','导出年鉴':'Export Almanac','清除本地年鉴':'Clear Local Almanac','赛季星图':'Season Atlas','Token 赛季，使用方向键浏览':'Token seasons; use arrow keys to browse','个人纪录天文台':'Personal Record Observatory','全部模型 · 当前报告作用域':'All models · Current report scope','个人纪录星图':'Personal record star map','🏆 Achievement Center · 成就中心':'🏆 Achievement Center','解锁日期以本报告范围为界；阶位表示图鉴门槛，不代表全球用户稀有度':'Unlock dates are bounded by this report. Tiers describe catalog thresholds, not global rarity.','LAST UNLOCK · 最近解锁':'LAST UNLOCK','最近达成':'Recent Unlocks','距离最近的目标':'Nearest Goals','每个阶梯只推荐下一枚':'Only the next goal in each track is recommended','收藏与阶位':'Collection & Tiers','📜 查看完整图鉴与详情 →':'📜 View Full Catalog & Details →','项目透镜 · Project Lens':'Project Lens','追踪一个项目在当前粒度、模型筛选与时光探针下的 Token 轨迹':'Track one project across the current granularity, model filters, and time probe','选择项目':'Select project','项目 Token 趋势':'Project Token trend','项目趋势明细，可横向滚动':'Project trend details; horizontally scrollable','趣味换算 · 你的 token 约等于':'Fun Conversions · Your tokens are roughly','换一组':'Shuffle','🎲 换一组':'🎲 Shuffle','5h 计费窗口 · 近 5 小时':'5h Usage Window · Recent 5 Hours','每天 · 近 14 天':'Daily · Recent 14 Days','作息织锦 · 14 天 × 24 小时':'Activity Tapestry · 14 Days × 24 Hours','每一个方格，都是一小时留下的算力纹理':'Each cell represents one hour of Token activity','静':'Quiet','沸':'Peak','今日 token 运势':'Today’s Token Fortune','作息时钟 · 什么时段最肝':'Activity Clock · Peak Hours','每根辐条 = 一小时的 token 量 · 高亮为峰值':'Each spoke = one hour of tokens · Highlight marks the peak','模型占比':'Model Share','Context Reuse River · 上下文复用之河':'Context Reuse River','Input / Output / Cache Read / Cache Write 随时间流动，观察上下文何时开始被记住':'Input / Output / Cache Read / Cache Write over time, showing when context starts being reused','上下文复用构成随时间变化':'Context reuse composition over time','悬停或用方向键检查每一期的 Token 构成。':'Hover or use arrow keys to inspect each period’s Token composition.','Token 流光图 · 项目 → 模型 → 会话':'Token Flow Map · Project → Model → Session','光带宽度对应真实 Token 流量；悬停或聚焦 Peek，点击 Pin 到 Signal Dock':'Band width represents actual Token flow. Hover or focus to Peek; click to Pin in Signal Dock.','保存当前流光图为 SVG':'Save current flow map as SVG','保存 SVG':'Save SVG','项目到模型再到会话的 Token 流光图':'Token flow from projects to models to sessions','悬停或聚焦节点查看真实流向，点击项目或模型可锁定链路。':'Hover or focus nodes to inspect actual flow; click a project or model to lock the path.','Token 生物 · 你的数字生命':'Token Creature · Your Digital Life','Furry Token 伙伴 · 你的数字兽设':'Furry Token Companion · Your Digital Fursona','原创日系 Furry 半身角色，由本地 Token 聚合与角色设定共同塑形。':'An original Japanese-inspired Furry bust character shaped by local Token aggregates and character settings.','数据驱动的日系 Furry Token 半身伙伴':'Data-driven Japanese-inspired Furry Token bust companion','仅在当前页面显示的兽设参考图':'Fursona reference shown only on this page','本地参考':'Local reference','伙伴物种':'Companion species','由数据选择':'Data-selected','狼':'Wolf','狐狸':'Fox','猫':'Cat','兔':'Rabbit','龙':'Dragon','伙伴配色':'Companion colors','主毛色':'Primary fur','脸胸毛':'Face and chest fur','虹膜与饰品':'Iris and accessories','导入兽设配色':'Import fursona colors','移除参考图':'Remove reference','恢复数据外观':'Restore data appearance','可导入不超过 5MB 的 PNG、JPEG 或 WebP。':'Import a PNG, JPEG, or WebP up to 5 MB.','图片只在此页面本地解码并提取三种配色，不上传、不是 AI 重绘，也不会写入 URL、年鉴或保存的 SVG。':'The image is decoded locally on this page only to extract three colors. It is not uploaded, AI-redrawn, written to the URL or Almanac, or embedded in the saved SVG.','保存 SVG':'Save SVG','每模型趋势 · 日':'Per-model Trend · Daily','柱图竞赛 · 累计 token':'Bar Chart Race · Cumulative Tokens','▶ 播放':'▶ Play','柱图竞赛日期位置':'Bar chart race date position','明细':'Details','下载当前明细为 Markdown':'Download current details as Markdown','◇ 导出 MD':'◇ Export MD','下载当前明细为 CSV':'Download current details as CSV','⤓ 导出 CSV':'⤓ Export CSV','Token 明细，可横向滚动':'Token details; horizontally scrollable','Token 星云 · 你的数据深空':'Token Nebula · Your Data Deep Space','24 小时形成星云旋臂 · 模型化作彩色星团 · 缓存点亮中央星核':'24 hours form spiral arms · Models become colored clusters · Cache lights the core','📥 收藏这片星云':'📥 Save This Nebula','Top 项目 / 会话':'Top Projects / Sessions','烧 token 的项目（cwd）':'Projects by tokens (cwd)','烧 token 的会话':'Sessions by tokens','✦ 生成 Token 护照':'✦ Generate Token Passport','▤ 打印 Token 收据':'▤ Print Token Receipt','返回数据宇宙顶部':'Return to the top','返回顶部':'Back to top','Token 分享卡':'Token share card','关闭分享卡':'Close share card','保存为 HTML':'Save as HTML','命令面板':'Command palette','输入命令或搜索…（例如：月、暗、导出）':'Type a command or search… (for example: month, dark, export)','关闭时间胶囊':'Close time capsule','来自过去快照的数据来信':'A Message from Past Snapshots','← 上一页':'← Previous','下一页 →':'Next →','🏆 成就图鉴':'🏆 Achievement Catalog','搜索成就':'Search achievements','搜索 2000+ 成就（名称/描述/分类）…':'Search 2,000+ achievements (name, description, category)…','筛选成就':'Filter achievements','全部':'All','已解锁':'Unlocked','未解锁':'Locked','隐藏':'Hidden','青铜':'Bronze','白银':'Silver','黄金':'Gold','彩钻':'Prismatic','庆祝成就进度':'Celebrate achievement progress','选择一枚成就查看状态、日期、目标与图鉴阶位。':'Select an achievement to inspect status, date, target, and catalog tier.','快捷键与交互说明':'Keyboard Shortcuts & Interaction Guide','关闭快捷键帮助':'Close keyboard shortcuts','切换日 / 周 / 月':'Switch day / week / month','打开命令面板':'Open command palette','切换主题':'Switch theme','导出当前 CSV':'Export current CSV','退出时光探针 / 关闭弹层':'Exit time probe / close overlay','打开本帮助':'Open this guide','数据侦探前后切换':'Cycle Data Detective insights','流光节点锁定 / 回放':'Pin flow node / replay','浏览年鉴赛季 / 胶囊章节':'Browse Almanac seasons / capsule chapters','打开赛季 / 纪录详情':'Open season / record details','打开 / 返回数据寻迹':'Open / return to Data Trail','寻迹步骤前后移动':'Move between trail steps','寻迹选项浏览':'Browse trail options','选择线索 / 打开证据':'Select clue / open evidence','寻迹返回上一步':'Go back one trail step','先关闭寻迹，再退出时光探针':'Close Data Trail before exiting the time probe','悬停 / 聚焦 · 点击':'Hover / focus · click','清除 Pin / 精确层':'Clear Pin / exact layer','临时显露精确值与分母':'Temporarily reveal exact values and denominators','按住 ⌥ Alt':'Hold ⌥ Alt','临时查看上一期轮廓':'Temporarily view prior-period outline','按住 C':'Hold C','固定 / 取消上一期对比':'Pin / unpin prior-period comparison','点击“按住对比”':'Click “Hold to Compare”','点击 · 全选 / 清空 / 撤销':'Click · select all / clear / undo','复制总 Token 精确值':'Copy exact total Token value','⧉ 复制按钮':'⧉ Copy button','会话回放':'Session Replay','会话回放轮次':'Session replay turn','无数据':'No data','暂无足够数据':'Not enough data yet','当前范围没有记录':'No records in the current scope','没有选择模型':'No models selected','当前时光探针没有活动':'No activity in the current time probe','当前日志缺少所需字段':'Required fields are missing from current logs','当前范围没有可显示数据':'No displayable data in the current scope','恢复全部模型':'Restore all models','查看数据体检':'View data health','自动':'Auto','亮色':'Light','暗色':'Dark','全景':'Overview','已固定':'Pinned','临时预览':'Preview','全部模型':'All models','时光探针':'Time Probe','时间范围':'Date range','已恢复月度全景':'Monthly overview restored','当前视图链接已复制':'Current view link copied','复制失败，请从地址栏复制':'Copy failed; copy from the address bar','精确层已固定':'Exact values pinned','精确层已取消固定':'Exact values unpinned','幻影对比已固定':'Prior-period comparison pinned','幻影对比已取消':'Prior-period comparison unpinned','正在临时预览上一期轮廓':'Previewing the prior-period outline','已复制':'Copied','复制失败':'Copy failed','调用':'Calls','Markdown 报告已生成':'Markdown report generated','分享卡已保存为 HTML':'Share card saved as HTML','当前范围':'Current scope','模型线索':'Model clue','证据分支':'Evidence branch','深入模块':'Open module','当前全景':'Current overview','无可比较上一期':'No comparable prior period','先选择一个模型线索。':'Select a model clue first.','范围':'Scope','粒度':'Granularity','模型覆盖':'Model coverage','调用记录':'Call records','项目证据':'Project evidence','会话证据':'Session evidence','Context 证据':'Context evidence','当前不可用':'Unavailable','证据边界':'Evidence boundary','需要 Pin 与 Peek 两个信号':'Pin and Peek are both required','混合类型仅并排查看，不计算 Delta':'Mixed types are shown side by side without Delta','同类型本地聚合可比较':'Same-type local aggregates are comparable','模型':'Model','周期':'Period','信号':'Signal','起始':'Start','至今':'Present','当前筛选无观察值':'No observations under current filters','无上一期':'No prior period','无百分比变化':'No percentage change','无上一期绝对变化':'No prior-period absolute change','无上一期百分比变化':'No prior-period percentage change','无模型构成':'No model composition','当前探针范围':'Current probe scope','当前报告范围':'Current report scope','最多最近 200 轮':'Most recent 200 turns maximum','完整保留序列':'Complete retained series','横轴是轮次，不代表耗时':'Horizontal axis is turn number, not elapsed time','未触及 200 轮边界':'Did not reach the 200-turn limit','回放不按模型或时光探针裁剪':'Replay is not clipped by model or time probe','当前信号没有可比较 Token 聚合':'Current signal has no comparable Token aggregate','缺少可比较聚合':'No comparable aggregate','Peek 相对 Pin':'Peek relative to Pin','只看此模型':'Show only this model','打开会话回放':'Open Session Replay','本地上下文':'Local context','当前范围信号':'Current-scope signal','已清除 Pin':'Pin cleared','已退出时光探针':'Time probe exited','已恢复全部模型':'All models restored','跟随系统主题':'Follow system theme','亮色主题':'Light theme','暗色主题':'Dark theme','导出 CSV':'Export CSV','导出 Markdown':'Export Markdown','查看快捷键与交互说明':'View keyboard shortcuts and interaction guide','播放柱图竞赛':'Play bar chart race','打开模块开关':'Open module settings','无匹配结果 · 试试 whoami、42、matrix、coffee':'No matches · Try whoami, 42, matrix, or coffee','范围快照':'Scope snapshot','日期未知':'Date unknown','缺少可比较的日期范围':'No comparable date range','刚刚同步':'Just synced','最后数据日与生成日一致':'Last data day matches generation day','近期快照':'Recent snapshot','历史快照':'Historical snapshot','等待数据':'Waiting for data','当前范围没有可体检的已解析记录。':'No parsed records to inspect in the current scope.','项目透镜':'Project Lens','会话回放':'Session Replay','作息分析':'Activity Analysis','复用之河':'Reuse River','流光关系':'Flow Relationships','当前范围缺少所需数据。':'Required data is unavailable in the current scope.','时间戳':'Timestamps','项目字段':'Project fields','会话字段':'Session fields','标准化组成字段':'Normalized composition fields','已解析记录':'Parsed records','回放保留':'Replay retention','当前筛选下无项目':'No projects under current filters','项目 Token':'Project Tokens','当前占比':'Current share','活跃期':'Active periods','峰值期':'Peak period','范围内首次观察':'First observed in scope','主力模型':'Primary model','当前筛选没有可导出的流向':'No exportable flow under current filters','当前流光图已保存为 SVG':'Current flow map saved as SVG','Token 生物已保存':'Token Creature saved','数据不足':'Insufficient data','截至':'Through','最高 Token 日':'Highest-token day','最活跃时刻':'Most active hour','▶ 播放':'▶ Play','⏸ 暂停':'⏸ Pause','至少需要两期数据才能计算状态':'At least two periods are required to calculate status','升温':'Rising','此前均值为 0，本期出现新活动':'Prior average was zero; new activity appeared this period','平稳':'Steady','本期与此前均值均为 0':'Both this period and the prior average are zero','降温':'Falling','数据体检摘要已复制':'Data health summary copied','继续':'Continue','开始':'Start','跳转 · 总览':'Go to · Overview','跳转 · 趋势':'Go to · Trend','跳转 · 数据可信度实验室':'Go to · Data Provenance Lab','跳转 · Token 年鉴':'Go to · Token Almanac','打开 · 数据时间胶囊':'Open · Data Time Capsule','跳转 · 项目透镜':'Go to · Project Lens','跳转 · 节奏':'Go to · Rhythm','跳转 · Context Reuse River':'Go to · Context Reuse River','跳转 · Token 流光图':'Go to · Token Flow Map','跳转 · 成就':'Go to · Achievements','跳转 · Top':'Go to · Top','下一个数据时刻':'Next data moment','当前筛选没有可回看的数据时刻':'No data moments under current filters','切换幻影对比':'Toggle prior-period comparison','复制当前视图链接':'Copy current view link','换一组趣味换算':'Shuffle fun conversions','成就未找到':'Achievement not found','不可用':'Unavailable','当前报告没有可划分的活跃赛季。':'No active seasons can be derived from this report.','当前范围没有可重建的个人纪录。':'No personal records can be reconstructed in the current scope.','日期不可还原':'Date cannot be reconstructed','本地年鉴已导出为 JSON':'Local Almanac exported as JSON','Token 年鉴历史已清除，并以当前快照重新建立基线':'Token Almanac history cleared; current snapshot is now the new baseline','图鉴':'Catalog','阶位':'Tier','来源':'Source','已解锁':'Unlocked','未解锁':'Locked','隐藏成就，达成自动揭晓':'Hidden achievement; revealed when unlocked','本地快照收藏':'Local snapshot collection','最早':'Earliest','最新':'Latest','当前报告全部数据':'All data in current report','还没有可展示的已解锁成就。':'No unlocked achievements to display yet.','当前聚合快照无法还原精确达成日期。':'The current aggregate snapshot cannot reconstruct exact unlock dates.','当前没有适合推荐的单调目标。':'No suitable monotonic goals to recommend.','已解锁':'Unlocked','最高阶位':'Highest tier','图鉴总数':'Catalog total','尚未达成':'Not unlocked yet','当前显示':'Currently shown','个分类':'categories','总图鉴':'Catalog total','展开分类时按需渲染':'Categories render on demand when expanded','该会话无逐轮数据':'No per-turn data for this session','（最近 200 轮）':'(most recent 200 turns)','轮':'turn','当前轮':'Current turn','累计':'Cumulative','累计占比':'Cumulative share','Token 晴朗':'Token Clear','用量平稳，算力气压舒适。今天适合把注意力留给代码本身。':'Usage is steady and Token pressure is comfortable. A good time to focus on the code.','稳定':'Stable','tk · 紧凑显示':'tk · compact','已选':'Selected','个模型 · 覆盖':'models · coverage','实体分析较完整':'Strong entity coverage','在已解析记录中，时间、项目、会话和标准化 Token 组成字段可用性较高。':'Parsed records have strong coverage for time, project, session, and normalized Token composition.','每个会话最多保留最近 200 轮':'Each session retains at most the most recent 200 turns','Claude total 由 input、output、cache read/write 组成；通常保留 cwd 与 session。':'Claude totals include input, output, cache read, and cache write; cwd and session are usually available.','一行代码':'one line of code','一条推文':'one post','一首流行歌词':'one pop-song lyric','近 6 个小时桶（按生成时刻往前）':'Recent 6 hourly buckets (counting back from generation time)','日间稳定型':'Daytime Steady','算力主要沿着白昼平稳展开。':'Token activity is spread steadily through daylight hours.','末吉':'Minor Luck','运势':'Fortune','宜':'Do','忌':'Avoid','宜喝口水':'Drink water','忌不留缓存':'Discarding all cache','token 如流水，缓存尚可留。':'Tokens flow like water; useful cache can remain.','峰值时段':'Peak hour','算力最常在':'Activity most often peaks at','亮起。':'peaks.','最近 14 天每小时 Token 作息织锦':'Hourly Token activity tapestry for the recent 14 days','每小时 token 分布':'Hourly Token distribution','需要已解析记录包含 cwd 项目路径':'Requires parsed records with cwd project paths','需要已解析记录可归属到 session，且逐轮值实际保留在回放序列中':'Requires parsed records attributable to sessions with per-turn values retained in replay','需要已解析记录含可解析时间戳':'Requires parsed records with parseable timestamps','需要标准化 input/output/cache read/cache write 组成字段可用':'Requires normalized input/output/cache read/cache write composition fields','需要已解析记录包含项目或会话 identity':'Requires parsed records with project or session identity'
});
const I18N_CORE_EXACT = Object.freeze({
  '月份':'Month','已解析记录':'parsed records','· 算力主要沿着白昼平稳展开。':'· Token activity is spread steadily through daylight hours.','自动':'Auto','静态快照':'Static snapshot','静态离线快照':'Static offline snapshot','本地实时':'Live locally','正在检查':'Checking','刚刚更新':'Just updated','刷新已暂停':'Refresh paused','实时刷新频率':'Live refresh frequency','刷新 · 1 分钟':'Refresh · 1 minute','刷新 · 5 分钟':'Refresh · 5 minutes','刷新 · 15 分钟':'Refresh · 15 minutes','刷新 · 30 分钟':'Refresh · 30 minutes','刷新 · 暂停':'Refresh · Paused','暂时断开':'Temporarily disconnected','同步错误':'Sync error'
});
const I18N_LABS_EXACT = Object.freeze({
  'FIRST OBSERVATION · 初次装订':'FIRST OBSERVATION · BASELINE','年鉴已安静地记住这份快照':'The Almanac quietly saved this snapshot','首次打开只建立基线，不会把旧数据假装成刚刚发生。下一份不同快照到来时，时间胶囊才会回信。':'The first visit only establishes a baseline; old data is never presented as newly occurring. The time capsule responds after a different snapshot arrives.','月界或 ≥7 日静默切季':'A month boundary or ≥7 silent days starts a new season','初生':'Dawn','最长连续活跃':'Longest active streak','单会话累计轮数':'Most turns in one session','单日缓存量峰值':'Daily cache-read peak','单日调用峰值':'Daily call peak','单日输入峰值':'Daily input peak','单日输出峰值':'Daily output peak','单日 Token 峰值':'Daily Token peak','单小时峰值':'Hourly peak','单日模型多样性':'Daily model diversity','首次观察':'First observed','报告范围开始时已在保持':'Already held at report start','本地快照收藏':'Local snapshot collection','小成':'Early Progress','摸鱼':'Getting Started','顺手':'Comfortable','坚持':'Persistent','起步':'First Steps','连胜':'Streak','上手':'Getting the Hang of It','熟练':'Proficient','图鉴青铜阶位':'Bronze catalog tier','还差':'Remaining','图鉴阶位与“该阶梯前 X% 门槛”只描述本地目录中的门槛位置，不是全球用户稀有度。':'Catalog tiers and “top X% of thresholds” describe positions within the local catalog only, not global user rarity.','总 Token':'Total Tokens','静默·微光幼体':'Quiet · Glimmerling','由总量、模型、项目、缓存与作息共同塑形 · 每份数据只会诞生这一只':'Shaped by total usage, models, projects, cache, and activity rhythm · Each dataset creates a unique creature','形态':'Form','进化阶段':'Evolution stage','模型触须':'Model tendrils','项目星斑':'Project marks','晶核纯度':'Core purity','夜行倾向':'Night tendency','生命年轮':'Life rings','个星团':'clusters','模型光谱':'Model spectrum','最亮轨道':'Brightest orbit','星核亮度':'Core brightness','按':'Press','复制项目 Token 精确值':'Copy exact project Token value','次':'calls','种':'models','轮':'turns','· 全景':'· Overview','幻影对比':'Prior-period comparison','· 关闭':'· Off','数据时刻已并入趋势注释轨道；悬停、聚焦或固定一个信号，可查看跨模块上下文。':'Data moments now appear on the trend annotation rail. Hover, focus, or pin a signal to inspect cross-module context.','宜重构':'Refactor','忌动数据库':'Avoid database changes','重构像减肥，明天再说。':'Refactoring is like dieting: tomorrow will do.','悬停 Peek · 点击 Pin 信号':'Hover to Peek · Click to Pin','① 悬停或聚焦 Peek　② 点击 Pin 到 Signal Dock　③ 在信号坞中选择深入动作':'① Hover or focus to Peek　② Click to Pin in Signal Dock　③ Choose a deeper action in the dock','单日峰值':'Daily peak','连续天数':'Consecutive days','累计活跃天':'Total active days','活跃小时数':'Active hours','模型种类':'Model count','项目足迹':'Project footprint','会话数量':'Session count','缓存命中':'Cache share','缓存读取量':'Cache read volume','单会话轮数':'Turns per session','日均 token':'Daily average tokens','累计输入':'Total input','累计输出':'Total output','缓存写入':'Cache writes','每次调用密度':'Tokens per call','每日调用密度':'Calls per day','平均会话体量':'Average session size','会话中位数':'Median session size','最大会话':'Largest session','每日会话密度':'Sessions per day','平均项目体量':'Average project size','最大项目':'Largest project','夜猫指数':'Night-owl index','晨光指数':'Morning index','工时集中度':'Work-hour concentration','黄昏指数':'Evening index','波动指数':'Volatility index','增长连击':'Growth streak','回落连击':'Decline streak','近期加速度':'Recent acceleration','七日均值':'Seven-day average','三十日均值':'Thirty-day average','活跃小时跨度':'Active-hour span','活跃小时均值':'Average active hour','主力模型占比':'Primary-model share','模型专注指数':'Model focus index','星期时空坐标':'Weekday coordinates','月份四时':'Seasonal months','模型时段羁绊':'Model-time affinity','复合炼金术':'Composite alchemy','时刻战士':'Time-of-day warrior','星期人格':'Weekday persona','月份里程碑':'Monthly milestones','模型图鉴':'Model catalog','奇思妙想 · 隐藏':'Curiosities · Hidden','枚':'items','时间胶囊已建立基线':'Time capsule baseline established','这是本设备在当前作用域第一次观察这份年鉴。等下一份不同快照到来后，它才会展开真实的前后变化。':'This is the first Almanac observation for the current scope on this device. It will show real changes after a different snapshot arrives.','没有伪造过去':'No fabricated history','本页装载了':'This page holds','Token 的痕迹。':'traces of Tokens.','本地数据宇宙居民':'Resident of the local data universe','及格':'On Track','晨光启动型':'Morning Starter','· 大部分算力在清晨苏醒，像一台提前预热的机器。':'· Most Token activity wakes early, like a machine warmed up before the day begins.','范围末端仍活跃':'Active through the end of the range','起点为报告边界':'Starts at the report boundary','终点为报告边界':'Ends at the report boundary','工作模式图鉴':'Work Mode Atlas','星轨狼':'Startrail Wolf','流光狐':'Glowstream Fox','缓存猫':'Cache Cat','月跃兔':'Moonhop Rabbit','晶角龙':'Crystalhorn Dragon','伙伴物种':'Companion species','模型饰带':'Model ribbons','模型饰珠':'Model beads','缓存晶核':'Cache core','晶核亮度':'Core brightness','夜行气质':'Nocturnal tendency','累计 Token':'Cumulative Tokens','原创日系 Furry 伙伴':'Original Japanese-inspired Furry companion','当前外观仅在本地生成':'Current appearance is generated locally only','请选择 PNG、JPEG 或 WebP 图片。':'Choose a PNG, JPEG, or WebP image.','图片超过 5MB，未读取。':'The image exceeds 5 MB and was not read.','已在本地提取配色；原图仅保留到本页关闭。':'Colors were extracted locally; the original image remains only until this page closes.','无法读取这张图片，未应用任何内容。':'This image could not be read; nothing was applied.','参考图已从当前页面移除。':'The reference image was removed from this page.','已恢复由 Token 数据决定的物种与配色。':'Restored the species and colors determined by Token data.','Furry Token 伙伴已保存':'Furry Token Companion saved','按每日聚合特征描述使用形态；不评价生产力、代码质量或工作表现。':'Describes usage patterns from daily aggregates; it does not evaluate productivity, code quality, or work performance.','每日工作模式，使用方向键浏览':'Daily work modes; use arrow keys to browse','当前模型筛选 · 全部日期':'Current model filters · All dates','当前时光探针':'Current time probe','缓存园丁':'Cache Gardener','上下文复用在当天占据明显份额。':'Context reuse represents a notable share of the day.','探索巡游':'Exploration Roam','多个模型或项目共同参与了当天活动。':'Multiple models or projects contributed to the day.','集中深潜':'Focused Dive','大部分 Token 集中在少数连续小时。':'Most Tokens are concentrated in a few consecutive hours.','高能冲刺':'High-energy Sprint','当天总量明显高于当前范围的典型活跃日。':'The day is notably above a typical active day in the current scope.','稳定巡航':'Steady Cruise','活动达到可分析规模，但没有单一特征占据主导。':'Activity is large enough to analyze, without one feature dominating.','当天 Token 未达到模式分类的最低样本量。':'The day did not reach the minimum Token sample for classification.','达到样本量，且缓存、探索、集中度与冲刺规则均未优先命中。':'The sample is large enough, and no cache, exploration, concentration, or sprint rule took priority.','当前日期均未达到 ':'No dates reached ',' 的分类样本量。':' required for classification.','规则顺序：Cache Read ≥35% → ≥3 模型或 ≥4 项目 → ≤6 活跃小时且最集中 4 小时 ≥72% → ≥活跃日中位数 1.8× → 稳定巡航。最低样本量 1,000 Token；只描述使用形态。':'Rule order: Cache Read ≥35% → ≥3 models or ≥4 projects → ≤6 active hours with ≥72% in the busiest 4 hours → ≥1.8× the active-day median → Steady Cruise. Minimum sample: 1,000 Tokens; patterns only.','回看这一天':'Inspect this day','只描述使用形态。':'Describes usage patterns only.'
});

const I18N_REPLACEMENTS = Object.freeze([
['当前来源：','Current sources: '],['起始','Start'],['至今','Present'],['最后数据距生成日 ','Last data is '],['分母仅包含读取器已经接受并标准化的记录','The denominator includes only records accepted and normalized by readers'],['被解析器拒绝的原始事件不在其中','Raw events rejected by parsers are excluded'],['本结论不代表原始日志绝对完整、准确，也不是隐私或安全保证','This does not guarantee absolute completeness or accuracy of raw logs, privacy, or security'],['已解析记录','parsed records'],['算力主要沿着白昼平稳展开','Token activity is spread steadily through daylight hours'],['点击查看数据可信度','Click to view data provenance'],['至少需要两期数据才能计算状态','At least two periods are required to calculate status'],['新观察项目 ','Newly observed project '],['需要已解析记录包含 cwd 项目路径','Requires parsed records with cwd project paths'],['需要已解析记录可归属到 session，且逐轮值实际保留在回放序列中','Requires parsed records attributable to sessions with per-turn values retained in replay'],['需要已解析记录含可解析时间戳','Requires parsed records with parseable timestamps'],['需要标准化 input/output/cache read/cache write 组成字段可用','Requires normalized input/output/cache read/cache write composition fields'],['需要已解析记录包含项目或会话 identity','Requires parsed records with project or session identity'],[' · 自包含 HTML，离线可用 · 亮/暗随系统 · 按 ',' · Self-contained HTML · Works offline · Light/dark follows system · Press '],[' 唤起命令面板',' to open the command palette'],['随时打开 · 所有操作都在本地完成','to open anytime · Everything stays local'],['期 · 拖动或用方向键预览 · Enter / Space / 点击提交',' periods · Drag or use arrow keys to preview · Enter / Space / click to commit'],[' · Enter / Space / 点击提交',' · Enter / Space / click to commit'],['预览 ','Preview '],['。提交后进入时光探针。','. Commit to enter the time probe.'],['正在预览 ','Previewing '],[' tk · 松开仍为预览，点击或按 Enter 提交',' tk · Release to keep previewing; click or press Enter to commit'],[' · 尚未提交',' · Not committed'],[' · 主力 ',' · Primary '],['% 较上期同期','% vs same point in prior period'],['% 环比','% vs prior'],['预计月末 ','Projected month-end '],['%进度','% elapsed'],['上一期 ','Prior period '],['，峰值',', peak'],['，当前时光探针',', current time probe'],['，按 Enter 回看',', press Enter to inspect'],['▲峰值 ','▲ Peak '],['点击提交回看 ','Click to inspect '],['数据时刻，','Data moment, '],['，按 Enter 回看 ',']; press Enter to inspect '],[' 个模型',' models'],['已选 <b>','Selected <b>'],['</b> 个模型','</b> models'],['覆盖 <b>','Coverage <b>'],['点击切换模型筛选','Click to toggle model filter'],['已选择全部模型','All models selected'],['已清空模型筛选','Model filters cleared'],['已撤销上一次模型筛选','Previous model filter restored'],['主力 ','Primary '],[' · 当前模型筛选构成',' · Current model-filter composition'],['当前回看期 · ','Current probe period · '],['按当前模型筛选重新计算 Top · 悬停 Peek，点击 Pin 后从 Signal Dock 深入','Top lists recomputed for current model filters · Hover to Peek; Pin to explore from Signal Dock'],['最猛烈的一天是 ','Your highest-token day was '],['，单日燃烧 ', ', with '],['相当于日均值的 ','That is '],[' 倍','× the daily average'],['就贡献了全部 Token 的 ',' contributed '],['你的算力生物最喜欢在 ','Your activity peaks around '],['这个小时累计 ','This hour accumulated '],['夜色承载了你 ','Nighttime accounts for '],['% 的 Token','% of Tokens'],[' 是你的主力引擎，独自承载 ',' is your primary engine, handling '],['你使用过 ','You used '],[' 种模型',' models'],['累计 ','Cumulative '],['缓存占比 ','Cache share '],['最近七天的日均 Token 比此前七天 ','The recent seven-day Token average is '],[' 个会话',' sessions'],['所有发现均由本地数据计算。','All insights are computed locally.'],[' · 当前洞察已固定',' · Insight pinned'],['◆ 已固定','◆ Pinned'],['当前洞察已固定，取消固定后可切换','Current insight is pinned; unpin it to cycle'],['纯本地生成 · 没有任何数据离开这台电脑。','Generated locally · No data left this computer.'],[' 枚成就',' achievements'],['生成于 ','Generated at '],[' · 脱敏导出（标识已替换）',' · Pseudonymized export (identifiers replaced)'],['项目路径、会话标识与自然语言标题已替换；精确日期、Token、模型与逐轮序列仍保留。','Project paths, session identifiers, and natural-language titles are replaced; exact dates, Tokens, models, and per-turn series remain.'],['主题：','Theme: '],['（点击切换）','(click to switch)'],['本地生成于 ','Generated locally at '],['，未上传任何数据。', '; no data was uploaded.'],['数据还在沉睡，等第一批 Token 落下后，故事会从这里开始。','No Token data yet. The story starts here after the first records arrive.'],['调整日期范围或来源后重新生成报告。','Regenerate the report after adjusting the date range or sources.'],['恢复模型后可重新计算当前视图。','Restore models to recalculate the current view.'],['退出回看后查看完整范围。','Exit the time probe to view the full scope.'],['尝试调整日期范围、来源或模型筛选。','Try adjusting the date range, sources, or model filters.'],['达到 ','Reached '],['当前范围与时光探针下的完整模型聚合；Pin 不会修改模型筛选。','Complete model aggregate under the current scope and time probe. Pinning does not change model filters.'],[' 条调用记录',' calls'],['分子 ','Numerator '],[' / 分母 ',' / denominator '],[' 个模型分量',' model components'],[' 轮已保留',' retained turns'],['保留边界：最近 200 轮','Retention boundary: most recent 200 turns'],['已 Pin ','Pinned '],['模型线索已选择：','Model clue selected: '],['已展开','Opened '],['证据。',' evidence.'],['统计粒度已切换为 ','Granularity changed to '],['当前占比','Current share'],['活跃期','Active periods'],['峰值期','Peak period'],['范围内首次观察','First observed in scope'],[' 个项目',' projects'],[' 个会话',' sessions'],[' 条真实流向',' actual flows'],[' Token，占比 ',' Tokens, share '],['当前筛选总量 ','current filtered total '],['截至 ','Through '],['，第 ', ', period '],[' 期',''],['最后一期 ','Latest period '],[' Token；此前均值 ',' Tokens; prior average '],['；', '; '],[' · 点击查看趋势',' · Click to view trend'],[' 个活跃日',' active days'],[' 个自然日',' calendar days'],['峰值 ','Peak '],['主力占比 ','Primary share '],['最长连续 ','Longest streak '],[' 天',' days'],['本报告范围内记录于 ','Recorded within this report on '],[' · 比此前高 ',' · Above prior by '],[' 个章节',' chapters'],[' 份紧凑快照',' compact snapshots'],['不保存 cwd、session、标题或逐轮 Token。','No cwd, session identifiers, titles, or per-turn Tokens are stored.'],['当前 <b>','Current <b>'],['</b> / 目标 <b>','</b> / target <b>'],[' · 还差 <b>',' · remaining <b>'],[' 枚已解锁成就',' unlocked achievements'],[' token · 横轴为轮次，不代表真实耗时',' tokens · Horizontal axis is turn number, not elapsed time'],['第 ','Turn '],[' 轮，', ', '],[' Token，累计 ',' Tokens, cumulative '],[' tk</span><span>累计 ',' tk</span><span>Cumulative ']
]);
const I18N_PATTERNS = Object.freeze([
  [/^(\d{1,2})月(\d{1,2})日星期([一二三四五六日])$/,(_,month,day,weekday)=>`${['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']['一二三四五六日'.indexOf(weekday)]}, ${month}/${day}`],
  [/^(\d{4}-\d{2}-\d{2}) · ([\d,.]+) tk（([\d,.]+) 次）$/,(_,date,tokens,calls)=>`${date} · ${tokens} tk (${calls} calls)`],
  [/^模型 (.+)，([\d,.]+) Token，点击或按 Enter Pin 到 Signal Dock$/,(_,name,tokens)=>`Model ${name}, ${tokens} Tokens; click or press Enter to Pin in Signal Dock`],
  [/^项目 (.+)，([\d,.]+) Token，点击或按 Enter Pin 到 Signal Dock$/,(_,name,tokens)=>`Project ${name}, ${tokens} Tokens; click or press Enter to Pin in Signal Dock`],
  [/^会话 (.+)，([\d,.]+) Token，点击或按 Enter Pin 到 Signal Dock$/,(_,name,tokens)=>`Session ${name}, ${tokens} Tokens; click or press Enter to Pin in Signal Dock`],
  [/^你最猛烈的一天是 (.+)，单日燃烧 ([\d,.]+) Token。$/,(_,day,tokens)=>`Your highest-token day was ${day}, with ${tokens} Tokens.`],
  [/^最后数据距生成日 (\d+) 天$/,(_,days)=>`Last data is ${days} days before generation`],
  [/^来源 (.+)$/,(_,sources)=>`Sources: ${sources}`],
  [/^项目 ([\d.]+)%$/,(_,value)=>`Projects ${value}%`],
  [/^会话 ([\d.]+)%$/,(_,value)=>`Sessions ${value}%`],
  [/^● 项目透镜 · (.+)%$/,(_,value)=>`● Project Lens · ${value}%`],
  [/^● 会话回放 · (.+)%$/,(_,value)=>`● Session Replay · ${value}%`],
  [/^● 作息分析 · (.+)%$/,(_,value)=>`● Activity Analysis · ${value}%`],
  [/^● 复用之河 · (.+)%$/,(_,value)=>`● Reuse River · ${value}%`],
  [/^● 流光关系 · (.+)%$/,(_,value)=>`● Flow Relationships · ${value}%`],
  [/^主题：(自动|亮色|暗色)（点击切换）$/,(_,theme)=>`Theme: ${{'自动':'Auto','亮色':'Light','暗色':'Dark'}[theme]} (click to switch)`],
  [/^需要已解析记录包含 cwd 项目路径；当前来源：(.+)。$/,(_,sources)=>`Requires parsed records with cwd project paths; current sources: ${sources}.`],
  [/^需要已解析记录可归属到 session，且逐轮值实际保留在回放序列中；当前来源：(.+)。$/,(_,sources)=>`Requires parsed records attributable to sessions with per-turn values retained in replay; current sources: ${sources}.`],
  [/^需要已解析记录含可解析时间戳；当前来源：(.+)。$/,(_,sources)=>`Requires parsed records with parseable timestamps; current sources: ${sources}.`],
  [/^需要标准化 input\/output\/cache read\/cache write 组成字段可用；当前来源：(.+)。$/,(_,sources)=>`Requires normalized input/output/cache read/cache write composition fields; current sources: ${sources}.`],
  [/^需要已解析记录包含项目或会话 identity；当前来源：(.+)。$/,(_,sources)=>`Requires parsed records with project or session identity; current sources: ${sources}.`],
  [/^(\d+) 个活跃日 · 跨 (\d+) 个自然日(?: · (起点为报告边界))?(?: · (终点为报告边界))?$/,(_,active,span,start,end)=>`${active} active days · spans ${span} calendar days${start?' · Starts at the report boundary':''}${end?' · Ends at the report boundary':''}`],
  [/^(\d+) 个可回看时刻$/,(_,count)=>`${count} replayable moments`],
  [/^(\d+)\/(\d+) 模型$/,(_,selected,total)=>`${selected}/${total} models`],
  [/^末端静默 (\d+) (?:天|days)$/,(_,days)=>`${days} quiet days at range end`],
  [/^(\d+) 个章节 · 月界或 ≥7 日静默切季$/,(_,count)=>`${count} chapters · A month boundary or ≥7 silent days starts a new season`],
  [/^(\d+) 日 · (.+)$/,(_,days,total)=>`${days} days · ${total}`],
  [/^(.+) SEASON$/,(_,label)=>`${I18N_LABS_EXACT[label]||label} SEASON`],
  [/^报告固定到 (\d{4}-\d{2}-\d{2})。分母仅包含读取器已经接受并标准化的记录；被解析器拒绝的原始事件不在其中。本结论不代表原始日志绝对完整、准确，也不是隐私或安全保证。$/,(_,date)=>`Report fixed through ${date}. The denominator includes only records accepted and normalized by readers; raw events rejected by parsers are excluded. This does not guarantee absolute completeness or accuracy of raw logs, privacy, or security.`],
  [/^报告固定到 (\d{4}-\d{2}-\d{2})。?$/,(_,date)=>`Report fixed through ${date}.`],
  [/^(\d{4}-\d{2}-\d{2}) 在本报告范围、当前模型筛选中首次观察到项目 (.+?)。；(\d{4}-\d{2}-\d{2}) 与前一自然日连续，且每日唯一主力模型由 (.+) 变为 (.+)。$/,(_,projectDate,project,relayDate,from,to)=>`${projectDate}: Project ${project} was first observed within this report and current model filters; ${relayDate} is consecutive with the prior calendar day, and the sole daily primary model changed from ${from} to ${to}.`],
  [/^(\d{4}-\d{2}-\d{2}) 在本报告范围、当前模型筛选中首次观察到项目 (.+)。$/,(_,date,project)=>`${date}: Project ${project} was first observed within this report and current model filters.`],
  [/^(\d{4}-\d{2}-\d{2}) 与前一自然日连续，且每日唯一主力模型由 (.+) 变为 (.+)。$/,(_,date,from,to)=>`${date} is consecutive with the prior calendar day, and the sole daily primary model changed from ${from} to ${to}.`],
  [/^(.+) · (\d+) days$/,(_,label,days)=>`${I18N_LABS_EXACT[label]||label} · ${days} days`],
  [/^已解锁 (\d+) \/ (\d+) · 图鉴阶位并非全球稀有度$/,(_,unlocked,total)=>`${unlocked} unlocked / ${total} · Catalog tiers do not represent global rarity`],
  [/^(.+) · 本地数据宇宙居民$/,(_,creature)=>`${I18N_LABS_EXACT[creature]||creature} · Resident of the local data universe`],
  [/^报告范围开始时已在保持 · 截至 (.+)$/,(_,date)=>`Already held at report start · Through ${date}`],
  [/^报告范围开始时已在保持 · Through (.+)$/,(_,date)=>`Already held at report start · Through ${date}`],
  [/^本地年鉴保存最多 (\d+) 份紧凑快照 \/ 作用域；不保存 cwd、session、标题或逐轮 Token。raw 与脱敏报告、固定日期范围和时区不会互相合并。$/,(_,limit)=>`The local Almanac stores at most ${limit} compact snapshots per scope. No cwd, session identifiers, titles, or per-turn Tokens are stored. Raw and pseudonymized reports, fixed date ranges, and timezones are kept separate.`],
  [/^本地年鉴保存最多 (\d+) compact snapshots \/ 作用域; No cwd, session identifiers, titles, or per-turn Tokens are stored\.raw 与脱敏报告、固定日期范围和时区不会互相合并。$/,(_,limit)=>`The local Almanac stores at most ${limit} compact snapshots per scope. No cwd, session identifiers, titles, or per-turn Tokens are stored. Raw and pseudonymized reports, fixed date ranges, and timezones are kept separate.`],
  [/^枚 · 本地快照收藏$/,()=>`items · Local snapshot collection`],
  [/^(.+) · 该阶梯前 (\d+)% 门槛$/,(_,label,rank)=>`${I18N_LABS_EXACT[label]||label} · Top ${rank}% threshold in this track`],
  [/^本报告范围内首次达到 (\d{4}-\d{2}-\d{2})$/,(_,date)=>`First reached within this report on ${date}`],
  [/^本报告范围内首次Reached (\d{4}-\d{2}-\d{2})$/,(_,date)=>`First reached within this report on ${date}`],
  [/^范围 (.+) → (.+)$/,(_,start,end)=>`Range ${start} → ${end}`],
  [/^(坚持|起步|及格|摸鱼|顺手) · (\d+)$/,(_,label,level)=>`${I18N_LABS_EXACT[label]||label} · ${level}`],
  [/^(⚡|🗓️?|🕐️?)\s*(坚持|起步|及格|摸鱼|顺手|小成|连胜|上手|熟练) · (\d+)$/,(_,icon,label,level)=>`${icon} ${I18N_LABS_EXACT[label]||label} · ${level}`],
  [/^([⚡🗓🕐](?:️)?\s*)(.+) · (\d+)$/,(_,icon,label,level)=>`${icon}${I18N_LABS_EXACT[label]||label} · ${level}`],
  [/^还差 (.+)$/,(_,value)=>`${value} remaining`],
  [/^缓存复用 (.+)$/,(_,value)=>`Cache reuse ${value}`],
  [/^形态 (\d+)\/(\d+)$/,(_,current,total)=>`Form ${current}/${total}`],
  [/^(.+)，(.+) (天|轮|次|种)，首次观察$/,(_,label,value,unit)=>`${I18N_LABS_EXACT[label]||label}, ${value} ${{'天':'days','轮':'turns','次':'calls','种':'models'}[unit]}, first observed`],
  [/^报告固定到 (\d{4}-\d{2}-\d{2}) · 点击查看数据可信度$/,(_,date)=>`Report fixed through ${date} · Click to view data provenance`],
  [/^项目 (.+)，([\d,.]+) Token，占比 (.+)$/,(_,name,tokens,share)=>`Project ${name}, ${tokens} Tokens, ${share} share`],
  [/^会话 (.+)，([\d,.]+) Token，占比 (.+)$/,(_,name,tokens,share)=>`Session ${name}, ${tokens} Tokens, ${share} share`],
  [/^模型 (.+)，([\d,.]+) Token，占比 (.+)$/,(_,name,tokens,share)=>`Model ${name}, ${tokens} Tokens, ${share} share`],
  [/^(\d{4}-\d{2}) Token 构成$/,(_,period)=>`${period} Token composition`],
  [/^Projects (.+)，([\d,.]+) Token，占比 (.+)$/,(_,name,tokens,share)=>`Project ${name}, ${tokens} Tokens, ${share} share`],
  [/^模型 (.+)，([\d,.]+) Tokens, share (.+)$/,(_,name,tokens,share)=>`Model ${name}, ${tokens} Tokens, ${share} share`],
  [/^Sessions (.+)，([\d,.]+) Token，占比 (.+)$/,(_,name,tokens,share)=>`Session ${name}, ${tokens} Tokens, ${share} share`],
  [/^(.+) · (\d+) 天$/,(_,label,days)=>`${I18N_LABS_EXACT[label]||label} · ${days} days`],
  [/^(.+)，(.+)，首次观察$/,(_,label,value)=>`${I18N_LABS_EXACT[label]||label}, ${value}, first observed`],
  [/^(.+) · (\d+) 进度 (\d+)%$/,(_,label,level,progress)=>`${I18N_LABS_EXACT[label]||label} · ${level}, ${progress}% progress`],
  [/^(\d+) (轮|次|种)$/,(_,value,unit)=>`${value} ${{'轮':'turns','次':'calls','种':'models'}[unit]}`],
  [/^(\d+) 条$/,(_,value)=>`${value} tendrils`],
  [/^(\d+) 枚$/,(_,value)=>`${value} marks`],
  [/^(\d+) 个星团$/,(_,value)=>`${value} clusters`],
  [/^(午夜|晶核|虹彩|星尘)·(星轨狼|流光狐|缓存猫|月跃兔|晶角龙)$/,(_,prefix,name)=>`${{'午夜':'Midnight','晶核':'Crystal Core','虹彩':'Iridescent','星尘':'Stardust'}[prefix]} · ${I18N_LABS_EXACT[name]||name}`],
  [/^原创日系 Furry 半身伙伴 · (狼|狐狸|猫|兔|龙) · 累计成长阶段 (\d+)\/(\d+) · 所有造型与配色均在当前设备生成$/,(_,species,stage,total)=>`Original Japanese-inspired Furry bust companion · ${{'狼':'Wolf','狐狸':'Fox','猫':'Cat','兔':'Rabbit','龙':'Dragon'}[species]} · Cumulative growth stage ${stage}/${total} · All styling and colors are generated on this device`],
  [/^累计成长阶段 (\d+)\/(\d+)$/,(_,stage,total)=>`Cumulative growth stage ${stage}/${total}`],
  [/^([\d.]+)(万|亿)? 累计 Token$/,(_,amount,unit)=>{const value=Number(amount)*(unit==='亿'?1e8:unit==='万'?1e4:1),label=value>=1e9?(value/1e9).toFixed(2)+'B':value>=1e6?(value/1e6).toFixed(2)+'M':value>=1e3?(value/1e3).toFixed(1)+'K':String(Math.round(value));return `${label} cumulative Tokens`;}],
  [/^(\d+) 天 · ([\d.]+)%$/,(_,days,share)=>`${days} days · ${share}%`],
  [/^当前日期均未达到 ([\d,.]+) Token 的分类样本量。$/,(_,minimum)=>`No dates reached the ${minimum}-Token classification sample.`],
  [/^需要至少 ([\d,.]+) Token；当天为 ([\d,.]+)。$/,(_,minimum,total)=>`Requires at least ${minimum} Tokens; this day has ${total}.`],
  [/^Cache Read 占 ([\d.]+)%，达到 (\d+)% 规则。$/,(_,share,threshold)=>`Cache Read is ${share}%, meeting the ${threshold}% rule.`],
  [/^(\d+) 个模型 · (\d+) 个项目达到探索规则。$/,(_,models,projects)=>`${models} models · ${projects} projects meet the exploration rule.`],
  [/^活跃 (\d+) 小时，最集中 4 小时占 ([\d.]+)%。$/,(_,hours,share)=>`${hours} active hours; the busiest 4 hours hold ${share}%.`],
  [/^([\d,.]+) Token，是活跃日中位数的 ([\d.]+)×。$/,(_,tokens,multiple)=>`${tokens} Tokens, ${multiple}× the active-day median.`],
  [/^(\d+) 个模型 · (\d+) 个项目$/,(_,models,projects)=>`${models} models · ${projects} projects`],
  [/^Cache ([\d.]+)% · (\d+) 活跃小时$/,(_,share,hours)=>`Cache ${share}% · ${hours} active hours`],
  [/^(\d{4}-\d{2}-\d{2})，(.+)，(.+)$/,(_,day,label,evidence)=>`${day}, ${I18N_LABS_EXACT[label]||label}, ${englishText(evidence)}`]
]);
const I18N_ATTRIBUTES = ['aria-label','title','placeholder'];
const i18nTextSource = new WeakMap();
const i18nAttributeSource = new WeakMap();
let dashboardLanguage = document.documentElement.lang.toLowerCase().startsWith('zh') ? 'zh' : 'en';
let i18nObserver = null;
let i18nRestoring = false;

function englishText(value){
  const match=String(value).match(/^(\s*)([\s\S]*?)(\s*)$/),body=match[2];
  if(!body)return value;
  let translated=I18N_EXACT[body]||I18N_CORE_EXACT[body]||I18N_LABS_EXACT[body]||body;
  if(translated===body&&/[㐀-鿿]/.test(body)){
    for(const [pattern,replacement] of I18N_PATTERNS){
      if(pattern.test(body)){translated=body.replace(pattern,replacement);break;}
    }
  }
  if(translated===body)I18N_REPLACEMENTS.forEach(([source,target])=>{translated=translated.split(source).join(target);});
  return match[1]+translated+match[3];
}
function localizeTextNode(node){
  if(!node||node.nodeType!==Node.TEXT_NODE||node.parentElement?.closest('script,style,[data-i18n-skip]'))return;
  if(dashboardLanguage==='zh'){
    if(i18nRestoring&&i18nTextSource.has(node))node.nodeValue=i18nTextSource.get(node);
    else i18nTextSource.set(node,node.nodeValue);
    return;
  }
  const source=node.nodeValue;
  if(!/[㐀-鿿]/.test(source)&&i18nTextSource.has(node))return;
  i18nTextSource.set(node,source);
  node.nodeValue=englishText(source);
}
function localizeAttributes(element){
  if(!(element instanceof Element)||element.closest('[data-i18n-skip]'))return;
  let sources=i18nAttributeSource.get(element);
  if(!sources){sources={};i18nAttributeSource.set(element,sources);}
  I18N_ATTRIBUTES.forEach(name=>{
    if(dashboardLanguage==='zh'){
      if(i18nRestoring&&Object.prototype.hasOwnProperty.call(sources,name))element.setAttribute(name,sources[name]);
      else if(element.hasAttribute(name))sources[name]=element.getAttribute(name);
      return;
    }
    if(!element.hasAttribute(name))return;
    const source=element.getAttribute(name);if(!/[㐀-鿿]/.test(source)&&Object.prototype.hasOwnProperty.call(sources,name))return;sources[name]=source;element.setAttribute(name,englishText(source));
  });
}
function localizeTree(root=document.body){
  if(!root)return;
  if(root.nodeType===Node.TEXT_NODE){localizeTextNode(root);return;}
  if(root instanceof Element)localizeAttributes(root);
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){
    const node=walker.currentNode;
    if(node.nodeType===Node.TEXT_NODE)localizeTextNode(node);else localizeAttributes(node);
  }
}
function observeLanguageChanges(){
  if(!i18nObserver)i18nObserver=new MutationObserver(records=>{
    i18nObserver.disconnect();
    const textNodes=new Set(),elements=new Set(),trees=new Set();
    records.forEach(record=>{
      if(record.type==='characterData')textNodes.add(record.target);
      else if(record.type==='attributes')elements.add(record.target);
      else record.addedNodes.forEach(node=>trees.add(node));
    });
    trees.forEach(localizeTree);
    textNodes.forEach(localizeTextNode);
    elements.forEach(localizeAttributes);
    observeLanguageChanges();
  });
  i18nObserver.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:I18N_ATTRIBUTES});
}
function syncLanguageControl(){
  const button=document.getElementById('lang-btn');
  if(!button)return;
  const english=dashboardLanguage==='en';
  button.textContent=english?'中文':'English';
  button.setAttribute('aria-label',english?'Switch language':'切换语言');
  button.title=english?'Switch to Chinese':'切换到英文';
}
function applyLanguage(language,persist=true){
  dashboardLanguage=language==='zh'?'zh':'en';
  if(i18nObserver)i18nObserver.disconnect();
  document.documentElement.lang=dashboardLanguage==='zh'?'zh-CN':'en';
  document.title=dashboardLanguage==='zh'?'Token 用量 Dashboard':'Token Usage Dashboard';
  i18nRestoring=dashboardLanguage==='zh';
  localizeTree();
  i18nRestoring=false;
  syncLanguageControl();
  if(persist)try{localStorage.setItem('tk-lang',dashboardLanguage);}catch(e){}
  observeLanguageChanges();
}
function toggleLanguage(){
  const next=dashboardLanguage==='en'?'zh':'en';
  if(i18nObserver)i18nObserver.disconnect();
  dashboardLanguage='zh';
  i18nRestoring=true;
  localizeTree();
  i18nRestoring=false;
  render();
  applyLanguage(next);
}

const state = { gran: 'month', models: new Set(DATA.models), focusPeriod:null, compare:false };
const trailState = {open:false,step:'scope',reached:0,model:null,opener:null,destination:null,branch:null};
const signalState = {peek:null,peekSource:null,pinnedSignal:null,exactHeld:false,exactPinned:false,compareHeld:false,opener:null};
const scrubState = {period:null,index:-1,source:null,pointerId:null,startX:0,startY:0,intent:null,dragged:false,raf:0,pendingIndex:null,suppressClickUntil:0};
Object.defineProperties(signalState,{preview:{get(){return this.peek;},set(value){this.peek=value;}},pinned:{get(){return this.pinnedSignal;},set(value){this.pinnedSignal=value;}}});
let selectedProject=null;
let lastTotal = 0;
let stateRevision=0,derivedRevision=-1,derivedCache={};
function invalidateDerived(){stateRevision++;derivedCache={};derivedRevision=stateRevision;}
function memoDerived(key,build){if(derivedRevision!==stateRevision){derivedCache={};derivedRevision=stateRevision;}if(!Object.prototype.hasOwnProperty.call(derivedCache,key))derivedCache[key]=build();return derivedCache[key];}
function stateKey(){return state.gran+'|'+[...state.models].sort().join(',')+'|'+(state.focusPeriod||'');}
const LABEL = {day:'日期', week:'周(始)', month:'月份'};

function compareActive(){return state.compare||signalState.compareHeld;}
function exactnessActive(){return signalState.exactHeld||signalState.exactPinned;}
function syncExactness(){const active=exactnessActive();document.documentElement.classList.toggle('exact-on',active);const button=document.getElementById('exact-btn');button.classList.toggle('on',active);button.setAttribute('aria-pressed',String(signalState.exactPinned));button.textContent=signalState.exactPinned?'⌥ 精确层已固定':signalState.exactHeld?'⌥ 精确层预览':'⌥ 精确层';}
function setCompareHeld(on){if(signalState.compareHeld===on)return;signalState.compareHeld=on;renderBar();renderViewCapsule();}

const fmt = n => Number(n||0).toLocaleString('en-US');
function human(n){ if(n>=1e8) return (n/1e8).toFixed(1)+'亿'; if(n>=1e4) return (n/1e4).toFixed(1)+'万'; return String(Math.round(n)); }
function metric(n){ if(n>=1e9)return (n/1e9).toFixed(2)+'B'; if(n>=1e6)return (n/1e6).toFixed(2)+'M'; if(n>=1e3)return (n/1e3).toFixed(1)+'K'; return String(Math.round(n)); }
function displayNumber(n){ return human(n); }
const pretty = m => DATA.pretty[m] || m;
const pct = (a,b) => b? ((a/b*100).toFixed(1)+'%') : '0%';
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function periodDays(period, gran){
  if(gran==='day') return [period];
  const start=new Date(period+'T00:00:00'), out=[];
  if(Number.isNaN(start.getTime())) return out;
  if(gran==='week'){ for(let i=0;i<7;i++){const d=new Date(start);d.setDate(start.getDate()+i);out.push(localISO(d));} }
  else { const y=start.getFullYear(),m=start.getMonth(); for(let d=1;d<=new Date(y,m+1,0).getDate();d++) out.push(localISO(new Date(y,m,d))); }
  return out;
}
function localISO(d){ return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); }
function focusDays(){ return state.focusPeriod?new Set(periodDays(state.focusPeriod,state.gran)):null; }
function filteredHourly(){
  const fd=focusDays(), out=Array(24).fill(0);
  Object.entries(DATA.day_details||{}).forEach(([day,det])=>{
    if(fd&&!fd.has(day))return;
    Object.entries(det.hourly_models||{}).forEach(([m,h])=>{if(state.models.has(m))h.forEach((v,i)=>out[i]+=v||0);});
  });
  return out;
}
function aggregateEntities(days,kind,limit=6){const buckets={};days.forEach(day=>{const detail=DATA.day_details?.[day];if(!detail)return;const rows=kind==='session'?(detail.sessions||detail.top_sessions||[]):(detail.cwds||detail.top_cwds||[]);rows.forEach(row=>{const id=row[2]||row[0],item=buckets[id]||(buckets[id]=[row[0],0,id,{}]);Object.entries(row[3]||{}).forEach(([m,v])=>{if(state.models.has(m)&&v){item[3][m]=(item[3][m]||0)+v;item[1]+=v;}});});});const rows=Object.values(buckets).filter(row=>row[1]>0).sort((a,b)=>b[1]-a[1]||String(a[0]).localeCompare(String(b[0])));return limit==null?rows:rows.slice(0,limit);}
function scopedEntities(kind){return aggregateEntities(focusDays()||Object.keys(DATA.day_details||{}),kind,null);}
function focusDetail(){
  const fd=focusDays(); if(!fd)return null;
  let cache_read=0;fd.forEach(day=>{const x=DATA.day_details[day];if(!x)return;Object.entries(x.cache_read_models||{}).forEach(([m,v])=>{if(state.models.has(m))cache_read+=v||0;});});
  return {cache_read,top_cwds:aggregateEntities(fd,'project'),top_sessions:aggregateEntities(fd,'session')};
}
function selectedTopEntities(kind){return aggregateEntities(Object.keys(DATA.day_details||{}),kind);}

function spanYears(gran){ const ys=[...new Set(DATA[gran].map(r=>(r.period||'').slice(0,4)))]; return ys.length>1; }
function fmtLabel(period, gran){
  const p=(period||'').split('-');
  if(gran==='month') return p[0]+'-'+(p[1]||'');
  if(gran==='day'||gran==='week'){ return spanYears(gran)?period:(p[1]||'')+'-'+(p[2]||''); }
  return period;
}
function selectedCacheRead(){
  const fd=focusDays();let total=0;
  Object.entries(DATA.day_details||{}).forEach(([day,detail])=>{if(fd&&!fd.has(day))return;Object.entries(detail.cache_read_models||{}).forEach(([m,v])=>{if(state.models.has(m))total+=v||0;});});
  return total;
}

function selectedRows(all=false){
  const key='rows|'+stateKey()+'|'+(all?'all':'focus');
  return memoDerived(key,()=>{
    let src=DATA[state.gran];
    if(state.focusPeriod&&!all) src=src.filter(r=>r.period===state.focusPeriod);
    return src.map(r=>{
      const models={}; let total=0,calls=0;
      state.models.forEach(m=>{ const v=r.models[m]||0; if(v){models[m]=v;total+=v;}calls+=(r.model_calls||{})[m]||0; });
      return {period:r.period, calls, models, total};
    });
  });
}

function motionDisabled(){return document.documentElement.dataset.motion==='off'||window.matchMedia('(prefers-reduced-motion: reduce)').matches;}
function scrollBehavior(){return motionDisabled()?'auto':'smooth';}
/* count-up 数字动画 */
function animateNum(el, to, dur, formatter=fmt){
  if(!el)return;
  const from=Number.isFinite(el.__metricValue)?el.__metricValue:to;el.__metricValue=to;
  if(motionDisabled()||from===to){el.textContent=formatter(to);return;}
  const start=performance.now(),delta=to-from;
  function tick(t){if(motionDisabled()){el.textContent=formatter(to);return;}const k=Math.min(1,(t-start)/dur),e=1-Math.pow(1-k,3);el.textContent=formatter(Math.round(from+delta*e));if(k<1)requestAnimationFrame(tick);}
  requestAnimationFrame(tick);
}

function selectedDayTotal(day){
  const detail=DATA.day_details?.[day];if(!detail)return 0;
  let total=0;Object.entries(detail.hourly_models||{}).forEach(([model,hours])=>{if(state.models.has(model))total+=hours.reduce((sum,value)=>sum+(value||0),0);});return total;
}
function periodDelta(rows){
  if(rows.length<2)return null;
  const current=rows[rows.length-1],previous=rows[rows.length-2],generatedDay=String(DATA.generated||'').slice(0,10),until=DATA.range?.until;
  const currentDays=periodDays(current.period,state.gran),open=currentDays.includes(generatedDay)&&(!until||until>=generatedDay);
  if(!open)return previous.total>0?{value:(current.total-previous.total)/previous.total*100,label:'环比'}:null;
  if(state.gran==='day')return null;
  const elapsed=currentDays.filter(day=>day<generatedDay).length;if(!elapsed)return null;
  const currentComparable=currentDays.slice(0,elapsed).reduce((sum,day)=>sum+selectedDayTotal(day),0),previousComparable=periodDays(previous.period,state.gran).slice(0,elapsed).reduce((sum,day)=>sum+selectedDayTotal(day),0);
  return previousComparable>0?{value:(currentComparable-previousComparable)/previousComparable*100,label:'较上期同期'}:null;
}

function forecastForLatestMonth(rows){
  if(state.gran!=='month'||state.focusPeriod||!rows.length)return null;
  const last=rows[rows.length-1],generated=String(DATA.generated||'').slice(0,10),month=generated.slice(0,7);
  if(!generated||last.period!==month)return null;
  const until=DATA.range?.until;if(until&&until<generated)return null;
  const coveredDay=Number(generated.slice(8,10)),[yy,mm]=last.period.split('-').map(Number),dim=new Date(yy,mm,0).getDate(),day=Math.max(1,Math.min(dim,coveredDay||1));
  if(day>=dim)return null;
  return {total:Math.round(last.total/day*dim),progress:Math.round(day/dim*100)};
}

function renderKPI(){
  const rows=selectedRows();
  const total=rows.reduce((a,r)=>a+r.total,0); lastTotal=total;
  const calls=rows.reduce((a,r)=>a+r.calls,0);
  const mtot={};
  rows.forEach(r=>Object.entries(r.models).forEach(([m,v])=>mtot[m]=(mtot[m]||0)+v));
  let dom='—', domv=-1;
  Object.entries(mtot).forEach(([m,v])=>{ if(v>domv){domv=v;dom=m;} });
  animateNum(document.getElementById('k-total'), total, 600, displayNumber);
  document.getElementById('k-total-exact').textContent=fmt(total);
  document.getElementById('k-total-u').textContent = 'tk · 紧凑显示';
  animateNum(document.getElementById('k-calls'), calls, 500);
  animateNum(document.getElementById('k-models'), Object.keys(mtot).length, 400);
  document.getElementById('k-dom').textContent = dom!=='—' ? pretty(dom) : '—';
  // 完整周期做整期环比；进行中的周/月只比较双方相同数量的完整天。
  const comparison=periodDelta(rows),dEl=document.getElementById('k-delta');
  if(comparison){
    const d=comparison.value;dEl.style.display='';dEl.className='delta '+(d>=0?'up':'down');
    dEl.textContent=(d>=0?'▲ ':'▼ ')+Math.abs(d).toFixed(1)+'% '+comparison.label;
  } else dEl.style.display='none';
  // 缓存命中：cache_read 占当前 Token 总量的比例；下方显示读取量，不推断货币节省
  const detail=focusDetail();
  const cr=detail?detail.cache_read:selectedCacheRead(), hit=total?(cr/total*100):0;
  animateNum(document.getElementById('k-cache-pct'), Math.round(hit), 500);
  document.getElementById('k-saved').textContent = human(cr)+' tk';
  setTimeout(()=>{ document.getElementById('gauge-fill').style.width=Math.min(100,hit).toFixed(1)+'%'; }, 60);
  // 本月预测：按已过天数速率推算月末
  const fEl=document.getElementById('k-forecast'),forecast=forecastForLatestMonth(rows);
  if(forecast){fEl.style.display='';fEl.textContent='预计月末 '+human(forecast.total)+' tk · '+forecast.progress+'%进度';}
  else fEl.style.display='none';
  renderSpark(rows);
}

/* 总量 KPI 里的迷你折线（最近若干期） */
function renderSpark(rows){
  const svg=document.getElementById('spark');
  const vals=rows.slice(-16).map(r=>r.total);
  if(vals.length<2){ svg.innerHTML=''; return; }
  const W=96,H=30,max=Math.max(...vals),min=Math.min(...vals),sp=(max-min)||1;
  const pts=vals.map((v,i)=>[ (i/(vals.length-1))*W, H-3-((v-min)/sp)*(H-6) ]);
  const line='M'+pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join('L');
  const area=line+` L ${W} ${H} L 0 ${H} Z`;
  const last=pts[pts.length-1];
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  svg.innerHTML=`<path d="${area}" fill="var(--accent-soft)"/><path d="${line}" fill="none" stroke="var(--accent-2)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2" fill="var(--accent)"/>`;
}

let barCursor=0,momentCursor=0;
function trendPeriodIndex(clientX,left,width,count){
  if(!Number.isFinite(clientX)||!Number.isFinite(left)||!Number.isFinite(width)||width<=0||count<=0)return -1;
  return Math.max(0,Math.min(count-1,Math.floor((clientX-left)/width*count)));
}
function trendPreviewCopy(row){
  if(!row)return '';
  const dom=Object.entries(row.models||{}).sort((a,b)=>b[1]-a[1])[0];
  return fmtLabel(row.period,state.gran)+' · '+fmt(row.total)+' Token'+(dom?' · 主力 '+pretty(dom[0])+' '+pct(dom[1],row.total):'');
}
function scrubRow(){return scrubState.index<0?null:selectedRows(true)[scrubState.index]||null;}
function renderScrubPreview(announce=false){
  const rows=selectedRows(true),row=scrubRow(),stacks=[...document.querySelectorAll('#bar .barstack')],previewPeriod=row?.period||null;
  stacks.forEach((el,index)=>{const preview=index===scrubState.index;el.classList.toggle('scrub-preview',preview);el.classList.toggle('scrub-away',!!row&&!preview);el.setAttribute('aria-current',preview?'true':'false');});
  const hint=document.getElementById('bar-hint'),status=document.getElementById('scrub-status'),probe=document.getElementById('time-probe');
  if(row){const copy=trendPreviewCopy(row);hint.textContent=copy+' · Enter / Space / 点击提交';status.textContent=announce?'预览 '+copy+'。提交后进入时光探针。':'';probe.classList.add('scrubbing');probe.dataset.scrubPeriod=previewPeriod;document.getElementById('probe-copy').innerHTML='<b>正在预览 '+esc(fmtLabel(row.period,state.gran))+'</b> · '+human(row.total)+' tk · 松开仍为预览，点击或按 Enter 提交';const pulse=document.getElementById('status-pulse'),pulseText=document.getElementById('status-text');pulse.classList.remove('warming','steady','cooling');pulse.classList.add('scrub-preview');pulseText.textContent='预览 '+fmtLabel(row.period,state.gran);pulse.title=copy+' · 尚未提交';}
  else {hint.textContent=rows.length+' 期 · 拖动或用方向键预览 · Enter / Space / 点击提交';status.textContent='';probe.classList.remove('scrubbing');delete probe.dataset.scrubPeriod;renderProbe();}
}
function setScrubPreview(index,source='pointer',focus=false,announce=false){
  const rows=selectedRows(true);if(!rows.length)return false;index=Math.max(0,Math.min(rows.length-1,Number(index)||0));const changed=scrubState.index!==index||scrubState.source!==source;scrubState.index=index;scrubState.period=rows[index].period;scrubState.source=source;barCursor=index;document.querySelectorAll('#bar .barstack').forEach((el,i)=>el.setAttribute('tabindex',i===index?'0':'-1'));renderScrubPreview(announce&&changed);if(focus)document.querySelector('#bar .barstack[data-index="'+index+'"]')?.focus({preventScroll:true});return changed;
}
function clearScrub(reason='',announce=false){
  const had=!!scrubState.period;if(scrubState.raf){cancelAnimationFrame(scrubState.raf);scrubState.raf=0;}scrubState.pendingIndex=null;scrubState.period=null;scrubState.index=-1;scrubState.source=null;scrubState.pointerId=null;scrubState.intent=null;scrubState.dragged=false;renderScrubPreview(false);if(had)renderStatusPulse();if(announce&&reason)document.getElementById('scrub-status').textContent=reason;
}
function queueScrubPreview(index,source='pointer'){scrubState.pendingIndex=index;if(scrubState.raf)return;scrubState.raf=requestAnimationFrame(()=>{scrubState.raf=0;const next=scrubState.pendingIndex;scrubState.pendingIndex=null;if(next!=null)setScrubPreview(next,source,false,false);});}
function commitScrub(period=scrubState.period,restoreBar=false){if(!period)return;clearScrub();toggleFocus(period,restoreBar);}
function describeBar(el,focus=true){
  const i=Number(el.dataset.index||0);setScrubPreview(i,'keyboard',focus,true);
}
function periodForMoment(day,gran){return projectPeriod(day,gran);}
function momentEventsForRows(rows,events=buildMomentEvents()){const grouped={};events.forEach(event=>{const period=periodForMoment(event.day,state.gran);if(!rows.some(row=>row.period===period))return;(grouped[period]||(grouped[period]=[])).push(event);});return Object.entries(grouped).map(([period,events])=>({period,day:events[events.length-1].day,events,label:events.map(event=>event.label).join(' · '),description:events.map(event=>event.description).join('；')})).sort((a,b)=>a.period.localeCompare(b.period));}
function describeMoment(el,focus=true){const marker=el.__moment;if(!marker)return;const markers=[...document.querySelectorAll('#bar .moment-marker')],index=markers.indexOf(el);momentCursor=Math.max(0,index);markers.forEach((item,i)=>item.setAttribute('tabindex',i===momentCursor?'0':'-1'));document.getElementById('bar-hint').textContent='◆ 数据时刻 · '+marker.description+' · Enter 回看 '+marker.day;if(focus)el.focus();}
function handleMomentKey(e,markers,index){if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();const next=Math.max(0,Math.min(markers.length-1,index+(e.key==='ArrowRight'?1:-1)));describeMoment(markers[next]);return true;}if(e.key==='Home'||e.key==='End'){e.preventDefault();describeMoment(markers[e.key==='Home'?0:markers.length-1]);return true;}if(e.key==='Enter'||e.key===' '){e.preventDefault();focusMomentDay(markers[index].__moment.day);return true;}return false;}
function barAnnotationLayout(barTop,compareTop){return {peak:Math.max(24,barTop-7),value:Math.max(24,barTop-6),delta:Math.max(9,compareTop-21)};}
function renderBar(){
  const rows=selectedRows(true);
  const events=buildMomentEvents();
  const moments=momentEventsForRows(rows,events),momentByPeriod=Object.fromEntries(moments.map(moment=>[moment.period,moment]));
  const W=1040,H=340,padL=56,padR=18,padT=34;
  const plotW=W-padL-padR;
  const n=Math.max(1,rows.length), step=plotW/n;
  // 每根柱都标日期：少→横排，中→斜排(-45)，密→竖排(-90)，永不抽稀、不重叠
  const ang = n<=10 ? 0 : step>=26 ? -45 : -90;
  const labelPad = ang===0 ? 40 : ang===-90 ? 48 : 56;
  const railH=moments.length?20:0,padB=labelPad+railH;
  const plotH=H-padT-padB;
  const compared=compareActive()?rows.map((r,i)=>i?rows[i-1].total:0):[];
  const vmax=Math.max(1, ...rows.map(r=>r.total), ...compared);
  // 整图锁定单一单位，避免 y 轴/标签 万与亿混用造成「629→7.5」歧义
  const U = vmax>=1e8?['亿',1e8]:vmax>=1e4?['万',1e4]:['',1];
  const vfmt = nn => { const v=nn/U[1]; return U[0] ? (v<10?v.toFixed(1):String(Math.round(v)))+U[0] : String(Math.round(nn)); };
  const bw=Math.max(3,Math.min(54,step*0.6));
  const showVal = n<=12;
  const p=['<svg viewBox="0 0 '+W+' '+H+'" class="chart" preserveAspectRatio="xMidYMid meet">'];
  for(let i=0;i<=4;i++){
    const frac=i/4, y=padT+plotH*(1-frac), val=Math.round(vmax*frac);
    p.push('<line class="grid-l" x1="'+padL+'" y1="'+y.toFixed(1)+'" x2="'+(W-padR)+'" y2="'+y.toFixed(1)+'"/>');
    if(i>0) p.push('<text x="'+(padL-8)+'" y="'+(y+3.5).toFixed(1)+'" text-anchor="end" class="tick">'+vfmt(val)+'</text>');
  }
  p.push('<line class="axis" x1="'+padL+'" y1="'+(padT+plotH).toFixed(1)+'" x2="'+(W-padR)+'" y2="'+(padT+plotH).toFixed(1)+'"/>');
  if(rows.length===0){ p.push('<text x="'+(W/2)+'" y="'+(H/2)+'" text-anchor="middle" class="tick">无数据</text></svg>'); document.getElementById('bar').innerHTML=p.join(''); return; }
  const _vals=rows.map(r=>r.total);
  const mean=_vals.reduce((a,b)=>a+b,0)/_vals.length;
  let peakI=0; for(let i=1;i<rows.length;i++){ if(rows[i].total>rows[peakI].total) peakI=i; }
  rows.forEach((r,i)=>{
    const x=padL+step*i+(step-bw)/2;
    p.push('<rect class="bar-track" x="'+x.toFixed(1)+'" y="'+padT.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+plotH.toFixed(1)+'" rx="4"/>');
    if(compareActive()&&i>0){
      const pv=rows[i-1].total, gh=(pv/vmax)*plotH, gy=padT+plotH-gh;
      p.push('<rect class="ghostbar" x="'+(x-3).toFixed(1)+'" y="'+gy.toFixed(1)+'" width="'+(bw+6).toFixed(1)+'" height="'+gh.toFixed(1)+'" rx="5"><title>上一期 '+esc(rows[i-1].period)+' · '+fmt(pv)+' tk</title></rect>');
    }
    let segs=''; let y0=padT+plotH;
    state.models.forEach(m=>{ const v=r.models[m]||0; if(v<=0) return;
      const h=(v/vmax)*plotH, y=y0-h;
      segs+='<rect class="seg model-mark" data-model="'+esc(m)+'"'+dataSignalAttrs('model',m,pretty(m),v,'trend',false)+' x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+h.toFixed(1)+'" rx="2" fill="'+DATA.colors[m]+'"><title>'+esc(r.period)+' · '+esc(pretty(m))+': '+fmt(v)+' ('+pct(v,r.total)+')</title></rect>';
      y0-=h;
    });
    const barTop=padT+plotH-r.total/vmax*plotH;
    const annotation=barAnnotationLayout(barTop,compareActive()&&i>0?padT+plotH-Math.max(r.total,rows[i-1].total)/vmax*plotH:barTop);
    const isPeak = rows.length>1 && i===peakI;
    const isFocus=state.focusPeriod===r.period;
    const aria=fmtLabel(r.period,state.gran)+'，'+fmt(r.total)+' Token'+(isPeak?'，峰值':'')+(isFocus?'，当前时光探针':'')+'，按 Enter 回看';
    p.push('<g class="barstack'+(isPeak?' peak':'')+(isFocus?' focused':'')+(state.focusPeriod&&!isFocus?' muted':'')+'" data-period="'+esc(r.period)+'" data-index="'+i+'"'+dataSignalAttrs('period',r.period,fmtLabel(r.period,state.gran),r.total,'trend',false)+' tabindex="'+(i===Math.min(barCursor,rows.length-1)?'0':'-1')+'" role="button" aria-label="'+esc(aria)+'"><rect class="bar-focus" x="'+(padL+step*i+2).toFixed(1)+'" y="'+(padT+1).toFixed(1)+'" width="'+Math.max(1,step-4).toFixed(1)+'" height="'+(plotH+padB-2).toFixed(1)+'" rx="6"/>'+segs+'</g>');
    if(isPeak&&!state.focusPeriod){
      p.push('<text class="peak-flag" x="'+(x+bw/2).toFixed(1)+'" y="'+annotation.peak.toFixed(1)+'" text-anchor="middle">▲峰值 '+vfmt(r.total)+'</text>');
    } else if(showVal){
      p.push('<text class="vlabel" x="'+(x+bw/2).toFixed(1)+'" y="'+annotation.value.toFixed(1)+'" text-anchor="middle">'+vfmt(r.total)+'</text>');
    }
    if(compareActive()&&i>0&&rows[i-1].total>0&&n<=18){
      const d=(r.total-rows[i-1].total)/rows[i-1].total*100;
      p.push('<text class="delta-tag" x="'+(x+bw/2).toFixed(1)+'" y="'+annotation.delta.toFixed(1)+'" text-anchor="middle">'+(d>=0?'+':'')+d.toFixed(0)+'%</text>');
    }
    const lx=padL+step*i+step/2;
    const moment=momentByPeriod[r.period];
    let ly, anchor, tr;
    if(ang===0){ ly=H-labelPad+18; anchor='middle'; tr=''; }
    else if(ang===-45){ ly=H-labelPad+30; anchor='end'; tr='transform="rotate(-45 '+lx.toFixed(1)+' '+ly.toFixed(1)+')"'; }
    else { ly=H-8; anchor='start'; tr='transform="rotate(-90 '+lx.toFixed(1)+' '+ly.toFixed(1)+')"'; }
    p.push('<text x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'" text-anchor="'+anchor+'" class="xlabel" '+tr+'>'+esc(fmtLabel(r.period,state.gran))+'</text>');
    p.push('<rect class="bar-hit" data-period="'+esc(r.period)+'" data-index="'+i+'" x="'+(padL+step*i).toFixed(1)+'" y="'+padT+'" width="'+step.toFixed(1)+'" height="'+(plotH+padB).toFixed(1)+'"><title>点击提交回看 '+esc(r.period)+'</title></rect>');
    if(moment){const mi=moments.indexOf(moment),hitW=Math.min(step,44),hitX=lx-hitW/2; p.push('<rect class="moment-target" data-moment-day="'+esc(moment.day)+'" x="'+hitX.toFixed(1)+'" y="'+(padT+plotH).toFixed(1)+'" width="'+hitW.toFixed(1)+'" height="20" rx="6"/><g class="moment-marker'+(moment.events.length>1?' merged':'')+'" data-moment-period="'+esc(r.period)+'" data-moment-day="'+esc(moment.day)+'" tabindex="'+(mi===Math.min(momentCursor,moments.length-1)?'0':'-1')+'" role="button" aria-label="数据时刻，'+esc(moment.label)+'，按 Enter 回看 '+esc(moment.day)+'"><line x1="'+lx.toFixed(1)+'" y1="'+(padT+plotH+4).toFixed(1)+'" x2="'+lx.toFixed(1)+'" y2="'+(padT+plotH+12).toFixed(1)+'"/><circle cx="'+lx.toFixed(1)+'" cy="'+(padT+plotH+8).toFixed(1)+'" r="'+(moment.events.length>1?'4':'3')+'"><title>'+esc(moment.description)+'</title></circle></g>');}
  });
  if(rows.length>1 && mean>0){
    const my=padT+plotH-(mean/vmax)*plotH;
    p.push('<line class="mean-line" x1="'+padL+'" y1="'+my.toFixed(1)+'" x2="'+(W-padR)+'" y2="'+my.toFixed(1)+'"/>');
    p.push('<text class="mean-lab" x="'+(W-padR-2)+'" y="'+(my-4).toFixed(1)+'" text-anchor="end">μ '+vfmt(mean)+'</text>');
  }
  p.push('</svg>');
  const box=document.getElementById('bar');box.innerHTML=p.join('');renderScrubPreview(false);
  const trendTarget=target=>target?.closest?.('.barstack,.bar-hit'),periodFromTarget=target=>trendTarget(target)?.dataset.period||null,indexFromTarget=target=>{const el=trendTarget(target);if(!el)return -1;if(el.dataset.index!=null)return Number(el.dataset.index);return rows.findIndex(row=>row.period===el.dataset.period);};
  box.onfocusin=e=>{const stack=e.target.closest('.barstack');if(stack)setScrubPreview(Number(stack.dataset.index||0),'keyboard',false,true);};
  box.onfocusout=e=>{if(e.relatedTarget&&!box.contains(e.relatedTarget))clearScrub('预览已清除',true);};
  box.onkeydown=e=>{const stack=e.target.closest('.barstack');if(!stack)return;const current=scrubState.index>=0?scrubState.index:Number(stack.dataset.index||0);if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();setScrubPreview(current+(e.key==='ArrowRight'?1:-1),'keyboard',true,true);}else if(e.key==='Home'||e.key==='End'){e.preventDefault();setScrubPreview(e.key==='Home'?0:rows.length-1,'keyboard',true,true);}else if(e.key==='Enter'||e.key===' '){e.preventDefault();commitScrub(scrubState.period||stack.dataset.period,true);}};
  box.onclick=e=>{const marker=e.target.closest('.moment-marker'),target=e.target.closest('.moment-target');if(marker||target){e.stopPropagation();clearScrub();focusMomentDay((marker||target).dataset.momentDay);return;}const period=periodFromTarget(e.target);if(!period)return;if(performance.now()<scrubState.suppressClickUntil){e.preventDefault();e.stopPropagation();return;}e.preventDefault();commitScrub(period);};
  box.onpointerdown=e=>{const target=trendTarget(e.target);if(!target||e.button!==0)return;const index=indexFromTarget(target);if(index<0)return;scrubState.pointerId=e.pointerId;scrubState.startX=e.clientX;scrubState.startY=e.clientY;scrubState.intent=null;scrubState.dragged=false;setScrubPreview(index,e.pointerType==='touch'?'touch':'pointer',false,false);try{box.setPointerCapture(e.pointerId);}catch(error){}};
  box.onpointermove=e=>{if(scrubState.pointerId!==e.pointerId)return;const dx=e.clientX-scrubState.startX,dy=e.clientY-scrubState.startY;if(!scrubState.intent&&Math.max(Math.abs(dx),Math.abs(dy))>=8)scrubState.intent=Math.abs(dx)>Math.abs(dy)*1.15?'horizontal':'vertical';if(scrubState.intent!=='horizontal')return;e.preventDefault();scrubState.dragged=scrubState.dragged||Math.abs(dx)>=10;const rect=box.getBoundingClientRect(),index=trendPeriodIndex(e.clientX,rect.left,rect.width,rows.length);if(index>=0)queueScrubPreview(index,e.pointerType==='touch'?'touch':'pointer');};
  const finishPointer=e=>{if(scrubState.pointerId!==e.pointerId)return;const dragged=scrubState.intent==='horizontal'&&scrubState.dragged;scrubState.pointerId=null;scrubState.intent=null;scrubState.dragged=false;if(dragged)scrubState.suppressClickUntil=performance.now()+450;try{if(box.hasPointerCapture(e.pointerId))box.releasePointerCapture(e.pointerId);}catch(error){}};
  box.onpointerup=finishPointer;box.onpointercancel=e=>{if(scrubState.pointerId===e.pointerId){scrubState.suppressClickUntil=performance.now()+450;clearScrub('预览已取消',true);}};box.onlostpointercapture=e=>{if(scrubState.pointerId===e.pointerId)clearScrub('预览已取消',true);};
  const markers=[...box.querySelectorAll('.moment-marker')];markers.forEach((el,i)=>{el.__moment=moments[i];el.addEventListener('focus',()=>{clearScrub();describeMoment(el,false);});el.addEventListener('keydown',e=>handleMomentKey(e,markers,i));});
}

function renderDonut(){
  const rows=selectedRows();
  const mtot={};
  rows.forEach(r=>Object.entries(r.models).forEach(([m,v])=>mtot[m]=(mtot[m]||0)+v));
  const entries=Object.entries(mtot).sort((a,b)=>b[1]-a[1]);
  const total=entries.reduce((a,[,v])=>a+v,0);
  const box=document.getElementById('donut');
  if(total===0){ box.innerHTML=contextEmptyHTML('rhythm'); document.getElementById('donut-legend').innerHTML=''; return; }
  const size=220, cx=size/2, cy=size/2, r=size/2-8;
  let angle=-Math.PI/2; const p=['<svg viewBox="0 0 '+size+' '+size+'" class="pie">'];
  entries.forEach(([m,v])=>{
    const frac=v/total, a0=angle, a1=angle+frac*2*Math.PI;
    if(frac>=0.999){
      p.push('<circle class="slice model-mark" data-model="'+esc(m)+'"'+dataSignalAttrs('model',m,pretty(m),v,'composition')+' cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="'+DATA.colors[m]+'"><title>'+esc(pretty(m))+' '+pct(v,total)+'</title></circle>');
    }else{
      const large=frac>0.5?1:0;
      const x0=cx+r*Math.cos(a0), y0=cy+r*Math.sin(a0), x1=cx+r*Math.cos(a1), y1=cy+r*Math.sin(a1);
      p.push('<path class="slice model-mark" data-model="'+esc(m)+'"'+dataSignalAttrs('model',m,pretty(m),v,'composition')+' d="M '+cx+' '+cy+' L '+x0.toFixed(2)+' '+y0.toFixed(2)+' A '+r+' '+r+' 0 '+large+' 1 '+x1.toFixed(2)+' '+y1.toFixed(2)+' Z" fill="'+DATA.colors[m]+'"><title>'+esc(pretty(m))+' '+pct(v,total)+'</title></path>');
    }
    angle=a1;
  });
  p.push('<circle class="pie-hole" cx="'+cx+'" cy="'+cy+'" r="'+(r*0.58).toFixed(1)+'"/>');
  p.push('<text x="'+cx+'" y="'+(cy-2)+'" text-anchor="middle" class="pie-center">'+human(total)+'</text>');
  p.push('<text x="'+cx+'" y="'+(cy+14)+'" text-anchor="middle" class="pie-sub">TOKENS</text></svg>');
  box.innerHTML=p.join('');
  document.getElementById('donut-legend').innerHTML=entries.map(([m,v])=>
    '<li class="model-mark" data-model="'+esc(m)+'"'+dataSignalAttrs('model',m,pretty(m),v,'composition')+'><span class="ldot" style="background:'+DATA.colors[m]+'"></span>'+esc(pretty(m))+' <em>'+pct(v,total)+'</em></li>').join('');
}

function renderTable(){
  const rows=selectedRows();
  const cols=DATA.models.filter(m=>state.models.has(m));
  const th=cols.map(m=>'<th class=num>'+esc(pretty(m))+'</th>').join('');
  const body=rows.map(r=>{
    const tds=cols.map(m=> r.models[m]?'<td class=num>'+fmt(r.models[m])+'</td>':'<td class=num><span class=dim>·</span></td>').join('');
    return '<tr><td>'+esc(fmtLabel(r.period,state.gran))+'</td><td class=num>'+fmt(r.total)+'</td>'+tds+'<td class=num>'+fmt(r.calls)+'</td></tr>';
  }).join('');
  document.getElementById('thead').innerHTML='<tr><th>'+LABEL[state.gran]+'</th><th class=num>总 token</th>'+th+'<th class=num>调用</th></tr>';
  document.getElementById('tbody').innerHTML=body || '<tr><td colspan="' +(cols.length+3)+ '" class="hint">无数据</td></tr>';
}

let previousModels=null;
function announceViewChange(message,targets=[]){
  const capsule=document.getElementById('view-capsule');capsule.classList.remove('state-ack');void capsule.offsetWidth;capsule.classList.add('state-ack');
  targets.forEach(id=>{const card=document.getElementById(id);if(!card||card.offsetParent===null)return;card.classList.remove('state-changed');void card.offsetWidth;card.classList.add('state-changed');});
  const label=document.getElementById('view-label');label.setAttribute('aria-live','polite');if(message)toast(message);
}
function signalVisible(signal){
  if(!signal)return false;
  if(signal.type==='model')return DATA.models.includes(signal.id)&&state.models.has(signal.id);
  if(signal.type==='period')return validFocus(signal.id,state.gran);
  if(signal.type==='project')return scopedEntities('project').some(item=>item[2]===signal.id);
  if(signal.type==='session')return scopedEntities('session').some(item=>item[2]===signal.id);
  return false;
}
function reconcileSignalState(){
  if(signalState.peek&&!signalVisible(signalState.peek)){signalState.peek=null;signalState.peekSource=null;}
  if(signalState.pinnedSignal&&!signalVisible(signalState.pinnedSignal))signalState.pinnedSignal=null;
}
function setModels(next,label){clearScrub();previousModels=new Set(state.models);state.models=new Set(next);reconcileTrailState();invalidateDerived();reconcileSignalState();renderFilters();renderDataViews();announceViewChange(label||('模型筛选已更新 · '+state.models.size+'/'+DATA.models.length+' 个模型'),['section-overview','section-trend','section-top']);}
function renderFilterLedger(){
  const rows=DATA[state.gran]||[],all=rows.reduce((a,r)=>a+(r.total||0),0),selected=rows.reduce((a,r)=>a+Object.entries(r.models||{}).reduce((s,[m,v])=>s+(state.models.has(m)?v:0),0),0);
  document.getElementById('filter-summary').innerHTML='已选 <b>'+state.models.size+'/'+DATA.models.length+'</b> 个模型 · 覆盖 <b>'+pct(selected,all)+'</b> Token';document.getElementById('filter-undo').disabled=!previousModels;
}
function renderFilters(){
  const box=document.getElementById('filters');
  if(DATA.models.length===0){ box.innerHTML='<span class=hint>无模型数据</span>'; return; }
  box.innerHTML=DATA.models.map(m=>{
    const on=state.models.has(m);
    return '<label class="chip'+(on?'':' off')+'"'+dataSignalAttrs('model',m,pretty(m),0,'filters',false)+'><input type=checkbox value="'+esc(m)+'" '+(on?'checked':'')+'><span class=cdot style="background:'+DATA.colors[m]+'"></span>'+esc(pretty(m))+'</label>';
  }).join('');
  box.querySelectorAll('input').forEach(cb=>{
    cb.addEventListener('change',e=>{const next=new Set(state.models);e.target.checked?next.add(e.target.value):next.delete(e.target.value);setModels(next);});
    cb.closest('.chip').title='点击切换模型筛选';
  });
  renderFilterLedger();
}
document.getElementById('filter-all').addEventListener('click',()=>setModels(DATA.models,'已选择全部模型'));
document.getElementById('filter-none').addEventListener('click',()=>setModels([],'已清空模型筛选'));
document.getElementById('filter-undo').addEventListener('click',()=>{if(!previousModels)return;clearScrub();state.models=new Set(previousModels);previousModels=null;reconcileTrailState();invalidateDerived();reconcileSignalState();renderFilters();renderDataViews();announceViewChange('已撤销上一次模型筛选',['section-overview','section-trend','section-top']);});

function lbRows(items,sessionRows=false,kind='project'){
  if(!items || !items.length) return contextEmptyHTML(kind);
  const filtered=items.map(it=>{const parts=Object.entries(it[3]||{}).filter(([m])=>state.models.has(m)).sort((a,b)=>b[1]-a[1]),total=parts.reduce((a,[,v])=>a+v,0);return {it,parts,total};}).filter(x=>x.total>0);
  if(!filtered.length)return contextEmptyHTML(kind);
  const max=Math.max(1,...filtered.map(x=>x.total));
  return filtered.map(({it,parts,total},i)=>{
    const w=total/max*100,full=it[2]||it[0],dom=parts[0],comp=parts.map(([m,v])=>'<i style="width:'+(v/total*100).toFixed(1)+'%;background:'+DATA.colors[m]+'" title="'+esc(pretty(m))+' '+pct(v,total)+'"></i>').join('');
    const attrs=sessionRows?' role="button" tabindex="0" data-session="'+esc(it[2]||it[0])+'" data-session-label="'+esc(it[0])+'"'+dataSignalAttrs('session',it[2]||it[0],it[0],total,'top')+' aria-label="会话 '+esc(it[0])+'，'+fmt(total)+' Token，点击或按 Enter Pin 到 Signal Dock"':' role="button" tabindex="0"'+dataSignalAttrs('project',it[2]||it[0],it[0],total,'top')+' aria-label="项目 '+esc(it[0])+'，'+fmt(total)+' Token，点击或按 Enter Pin 到 Signal Dock"';
    return '<div class=lb-row'+attrs+'><span class=rk>'+String(i+1).padStart(2,'0')+'</span>'
      +'<span class=lb-name title="'+esc(full)+'">'+esc(it[0])+'</span>'
      +'<span class=lb-bar><i style="width:'+w.toFixed(1)+'%"></i></span>'
      +'<span class=lb-val>'+human(total)+'</span><span class=lb-comp>'+comp+'</span><span class=lb-dom>'+(dom?'主力 '+esc(pretty(dom[0]))+' · 当前模型筛选构成':'')+'</span></div>';
  }).join('');
}
function renderTop(){
  const detail=focusDetail(), cwds=detail?detail.top_cwds:selectedTopEntities('project'), sessions=detail?detail.top_sessions:selectedTopEntities('session');
  document.getElementById('top-cwd').innerHTML = lbRows(cwds,false,'project');
  document.getElementById('top-sess').innerHTML = lbRows(sessions,true,'session');
  document.getElementById('top-hint').textContent=(state.focusPeriod?'当前回看期 · ':'')+'按当前模型筛选重新计算 Top · 悬停 Peek，点击 Pin 后从 Signal Dock 深入';
}

function renderClock(){
  const h=filteredHourly(), box=document.getElementById('clock');
  const total=h.reduce((a,b)=>a+(b||0),0);
  if(total===0){ box.innerHTML=contextEmptyHTML('rhythm'); return; }
  const max=Math.max.apply(null,h);
  let peak=0; for(let i=1;i<24;i++) if((h[i]||0)>(h[peak]||0)) peak=i;
  const size=270, cx=size/2, cy=size/2, rmax=size/2-28, rmin=34;
  const sw=Math.max(3, 2*Math.PI*rmin/24-3);
  const p=['<svg viewBox="0 0 '+size+' '+size+'" class="clock" aria-label="每小时 token 分布">'];
  p.push('<circle cx="'+cx+'" cy="'+cy+'" r="'+rmax+'" fill="none" stroke="var(--border)" stroke-dasharray="2 5"/>');
  for(let i=0;i<24;i++){
    const ang=(i/24)*2*Math.PI - Math.PI/2;
    if(i%3===0){
      const r2=rmax+5;
      p.push('<line x1="'+(cx+Math.cos(ang)*rmax).toFixed(1)+'" y1="'+(cy+Math.sin(ang)*rmax).toFixed(1)+'" x2="'+(cx+Math.cos(ang)*r2).toFixed(1)+'" y2="'+(cy+Math.sin(ang)*r2).toFixed(1)+'" class="clk-tick"/>');
      p.push('<text x="'+(cx+Math.cos(ang)*(r2+10)).toFixed(1)+'" y="'+(cy+Math.sin(ang)*(r2+10)+3).toFixed(1)+'" text-anchor="middle" class="clk-h">'+String(i).padStart(2,'0')+'</text>');
    }
  }
  for(let i=0;i<24;i++){
    const v=h[i]||0; if(v<=0) continue;
    const frac=v/max, ang=(i/24)*2*Math.PI - Math.PI/2;
    const ri=rmin, ro=rmin+frac*(rmax-rmin), isPeak=i===peak;
    p.push('<line class="clk-spoke'+(isPeak?' peak':'')+'" x1="'+(cx+Math.cos(ang)*ri).toFixed(1)+'" y1="'+(cy+Math.sin(ang)*ri).toFixed(1)+'" x2="'+(cx+Math.cos(ang)*ro).toFixed(1)+'" y2="'+(cy+Math.sin(ang)*ro).toFixed(1)+'" stroke-width="'+sw.toFixed(1)+'"><title>'+String(i).padStart(2,'0')+':00 · '+human(v)+' tk</title></line>');
  }
  p.push('<circle class="clk-core" cx="'+cx+'" cy="'+cy+'" r="'+rmin+'"/>');
  p.push('<text x="'+cx+'" y="'+(cy-2)+'" text-anchor="middle" class="clk-center">'+String(peak).padStart(2,'0')+':00</text>');
  p.push('<text x="'+cx+'" y="'+(cy+14)+'" text-anchor="middle" class="clk-sub">峰值时段</text></svg>');
  box.innerHTML=p.join('');
}

function buildDiscoveries(){
  const days=DATA.day||[], vals=days.map(d=>d.total||0), total=vals.reduce((a,b)=>a+b,0), avg=vals.length?total/vals.length:0;
  if(!days.length)return [{t:'数据还在沉睡，等第一批 Token 落下后，故事会从这里开始。',s:'暂无足够数据'}];
  const top=[...days].sort((a,b)=>b.total-a.total), h=DATA.hourly||[], ht=h.reduce((a,b)=>a+b,0), peak=h.indexOf(Math.max(...h));
  const mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const me=Object.entries(mt).sort((a,b)=>b[1]-a[1]);
  const wd=Array(7).fill(0);days.forEach(d=>{const p=d.period.split('-'),x=new Date(Date.UTC(+p[0],+p[1]-1,+p[2]));wd[(x.getUTCDay()+6)%7]+=d.total;});
  const out=[];
  if(top[0])out.push({t:'你最猛烈的一天是 '+fmtLabel(top[0].period,'day')+'，单日燃烧 '+human(top[0].total)+' Token。',s:avg?'相当于日均值的 '+(top[0].total/avg).toFixed(1)+' 倍':''});
  if(top.length>=3){const v=top.slice(0,3).reduce((a,d)=>a+d.total,0);out.push({t:'仅仅三个最高峰日，就贡献了全部 Token 的 '+(v/total*100).toFixed(1)+'%。',s:'少数时刻塑造了大部分数据地貌'});}
  if(peak>=0)out.push({t:'你的算力生物最喜欢在 '+String(peak).padStart(2,'0')+':00 出没。',s:'这个小时累计 '+human(h[peak]||0)+' Token'});
  const night=(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))/(ht||1);if(night>.25)out.push({t:'夜色承载了你 '+(night*100).toFixed(1)+'% 的 Token，屏幕熄灭得比城市更晚。',s:'统计范围：22:00–06:00'});
  if(me[0])out.push({t:pretty(me[0][0])+' 是你的主力引擎，独自承载 '+(me[0][1]/total*100).toFixed(1)+'% 的算力。',s:me[1]?'是第二名的 '+(me[0][1]/me[1][1]).toFixed(1)+' 倍':'目前没有第二名'});
  if(me.length>=3)out.push({t:'你使用过 '+me.length+' 种模型，数据光谱已经不再是单色。',s:'每种模型都在 Token 星云中凝聚成不同颜色的星团'});
  const best=wd.indexOf(Math.max(...wd));out.push({t:['周一','周二','周三','周四','周五','周六','周日'][best]+'是你一周里算力气压最高的一天。',s:'累计 '+human(wd[best])+' Token'});
  const cr=DATA.cache_read||0;if(total&&cr/total>.5)out.push({t:'超过一半的 Token 曾被缓存记住，你的上下文很少真正从零开始。',s:'缓存占比 '+(cr/total*100).toFixed(1)+'%'});
  if(DATA.top_cwds&&DATA.top_cwds[0])out.push({t:'「'+DATA.top_cwds[0][0]+'」是这座数据宇宙里质量最大的项目。',s:'累计 '+human(DATA.top_cwds[0][1])+' Token'});
  const recent=vals.slice(-7),old=vals.slice(-14,-7),ra=recent.reduce((a,b)=>a+b,0)/(recent.length||1),oa=old.reduce((a,b)=>a+b,0)/(old.length||1);if(oa)out.push({t:'最近七天的日均 Token 比此前七天 '+(ra>=oa?'高':'低')+' '+Math.abs((ra/oa-1)*100).toFixed(1)+'%。',s:ra>=oa?'数据天气正在升温':'算力气压正在回落'});
  out.push({t:'你的 '+fmt(DATA.n_sessions||0)+' 个会话，正在共同组成一份无法复制的开发者轨迹。',s:'它只存在于这份本地生成的 HTML 中'});
  return out;
}
let discoveryIndex=0, discoveryPinned=false;
const DISCOVERY_KEY='tk-discovery';
function loadDiscovery(){try{const v=JSON.parse(localStorage.getItem(DISCOVERY_KEY)||'{}');discoveryIndex=Math.max(0,Number(v.index)||0);discoveryPinned=!!v.pinned;}catch(e){}}
function saveDiscovery(){try{localStorage.setItem(DISCOVERY_KEY,JSON.stringify({index:discoveryIndex,pinned:discoveryPinned}));}catch(e){}}
function renderDiscovery(step=0,force=false){const a=buildDiscoveries();if(step&&(!discoveryPinned||force))discoveryIndex=(discoveryIndex+step+a.length)%a.length;discoveryIndex%=a.length;document.getElementById('discovery-text').textContent=a[discoveryIndex].t;document.getElementById('discovery-sub').textContent=(a[discoveryIndex].s||'所有发现均由本地数据计算。')+(discoveryPinned?' · 当前洞察已固定':'');document.getElementById('discovery-pos').textContent=(discoveryIndex+1)+'/'+a.length;const pin=document.getElementById('discovery-pin'),card=document.getElementById('discovery-card');pin.classList.toggle('on',discoveryPinned);pin.setAttribute('aria-pressed',String(discoveryPinned));pin.textContent=discoveryPinned?'◆ 已固定':'◇ 固定';card.classList.toggle('pinned',discoveryPinned);saveDiscovery();}
function stepDiscovery(step){if(discoveryPinned){toast('当前洞察已固定，取消固定后可切换');return;}renderDiscovery(step,true);}
loadDiscovery();
document.getElementById('discovery-next').addEventListener('click',e=>{e.stopPropagation();stepDiscovery(1);});
document.getElementById('discovery-pin').addEventListener('click',e=>{e.stopPropagation();discoveryPinned=!discoveryPinned;renderDiscovery();});
document.getElementById('discovery-card').addEventListener('click',e=>{if(e.target.closest('button'))return;stepDiscovery(1);});
document.getElementById('discovery-card').addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();stepDiscovery(e.key==='ArrowRight'?1:-1);}else if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button')){e.preventDefault();stepDiscovery(1);}});
function renderFooter(){
  const h=DATA.hourly||[], peak=h.indexOf(Math.max(...h)), lines=[
    'by <b>LingXi</b> · 本页装载了 <b>'+human(DATA.day.reduce((s,d)=>s+d.total,0))+'</b> Token 的痕迹。',
    '你的缓存替你记住了 <b>'+human(DATA.cache_read||0)+'</b> Token。',
    '算力最常在 <b>'+String(Math.max(0,peak)).padStart(2,'0')+':00</b> 亮起。',
    '纯本地生成 · 没有任何数据离开这台电脑。'
  ];if(_ach)lines.splice(2,0,'<b>'+fmt(_ach.all.length-_ach.got)+'</b> 枚成就仍在数据深处沉睡。');document.getElementById('dynamic-footer').innerHTML=lines[(new Date().getDate()+DATA.day.length)%lines.length];
}

function shareStats(){
  if(!lazyState.creature?.rendered){lazyState.creature=Object.assign({},lazyState.creature,{visible:true});renderLazy('creature',true);}
  const days=DATA.day||[],total=days.reduce((a,d)=>a+d.total,0),calls=days.reduce((a,d)=>a+d.calls,0),h=DATA.hourly||[],peak=h.indexOf(Math.max(...h)),mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const dom=Object.entries(mt).sort((a,b)=>b[1]-a[1])[0];
  return {total,calls,peak,dom:dom?pretty(dom[0]):'—',cache:total?(DATA.cache_read||0)/total:0,ach:_ach||getBadgeData(),creature:document.getElementById('creature-name').textContent||'Token 生物'};
}
function openShare(type){
  const x=shareStats(), content=document.getElementById('share-content');
  if(type==='passport')content.innerHTML='<div class=passport id=share-card><div class=pass-head><div><div class=pass-k>LOCAL DEVELOPER IDENTITY</div><h3>TOKEN PASSPORT</h3></div><div class=pass-id>ISSUED '+esc(DATA.generated)+'<br>NO DATA UPLOADED</div></div><div class=pass-grid><div><div class=pass-k>DEVELOPER TYPE</div><div class=pass-hero>'+(x.peak<6||x.peak>=22?'MIDNIGHT<br>NAVIGATOR':'DAYLIGHT<br>BUILDER')+'</div><div class=pass-sub>'+esc(x.creature)+' · 本地数据宇宙居民</div></div><div class=pass-fields><div class=pass-field><span>TOTAL TOKENS</span><b>'+fmt(x.total)+'</b></div><div class=pass-field><span>PRIMARY MODEL</span><b>'+esc(x.dom)+'</b></div><div class=pass-field><span>PEAK GATE</span><b>'+String(Math.max(0,x.peak)).padStart(2,'0')+':00</b></div><div class=pass-field><span>CACHE</span><b>'+Math.round(x.cache*100)+'%</b></div><div class=pass-field><span>CALLS</span><b>'+fmt(x.calls)+'</b></div><div class=pass-field><span>ACHIEVEMENTS</span><b>'+fmt(x.ach.got)+' / '+fmt(x.ach.all.length)+'</b></div></div></div><div class=pass-foot><span>VALID IN ALL LOCAL TERMINALS<br>PRIVACY CLASS: OFFLINE</span><span class=barcode>||| || ||| | |||| || |</span></div></div>';
  else content.innerHTML='<div class=receipt id=share-card><h3>TOKEN STORE</h3><div class=receipt-center>LOCAL TERMINAL · '+esc(DATA.generated.slice(0,10))+'<br>ORDER #'+String(x.total%100000).padStart(5,'0')+'</div><hr>'+(DATA.models||[]).map(m=>{const v=(DATA.day||[]).reduce((a,d)=>a+(d.models[m]||0),0);return '<div class=receipt-row><span>'+esc(pretty(m)).slice(0,18)+'</span><b>'+fmt(v)+'</b></div>';}).join('')+'<hr><div class=receipt-row><span>CALLS</span><b>'+fmt(x.calls)+'</b></div><div class=receipt-row><span>CACHE READ</span><b>'+fmt(DATA.cache_read||0)+'</b></div><div class=receipt-row><span>ACHIEVEMENTS</span><b>'+fmt(x.ach.got)+'</b></div><hr><div class="receipt-row receipt-total"><span>TOTAL</span><b>'+fmt(x.total)+' TK</b></div><div class=receipt-code>|||| || ||||| | ||| ||</div><div class=receipt-note>THANK YOU FOR CODING<br>OPEN 24 HOURS · NO DATA UPLOADED</div></div>';
  openModal(document.getElementById('share-modal'),document.getElementById('share-close'));document.getElementById('share-modal').dataset.type=type;
}
function closeShare(){closeModal(document.getElementById('share-modal'));}
document.getElementById('passport-btn').addEventListener('click',()=>openShare('passport'));document.getElementById('receipt-btn').addEventListener('click',()=>openShare('receipt'));document.getElementById('share-close').addEventListener('click',closeShare);document.getElementById('share-modal').addEventListener('click',e=>{if(e.target.id==='share-modal')closeShare();});document.getElementById('share-modal').addEventListener('keydown',e=>trapModalFocus(e,e.currentTarget));
document.getElementById('share-save').addEventListener('click',()=>{const card=document.getElementById('share-card'),style=[...document.querySelectorAll('style')].map(x=>x.textContent).join('\n'),html='<!doctype html><meta charset=utf-8><style>'+style+'body{display:grid;place-items:center;min-height:100vh;background:#080b12;padding:30px}</style>'+card.outerHTML;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));a.download='token-'+document.getElementById('share-modal').dataset.type+'.html';a.click();toast('分享卡已保存为 HTML');});

function renderWeather(){
  const days=(DATA.day||[]).slice(-14), recent=days.slice(-7), prev=days.slice(-14,-7);
  const rt=recent.reduce((a,d)=>a+d.total,0), pt=prev.reduce((a,d)=>a+d.total,0), ratio=pt?rt/pt:1;
  const h=filteredHourly(), ht=h.reduce((a,b)=>a+b,0), night=ht?(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))/ht:0;
  const total=selectedRows().reduce((a,r)=>a+r.total,0), detail=focusDetail(), cr=detail?detail.cache_read:selectedCacheRead(), cache=total?cr/total:0;
  let w={i:'☀️',t:'Token 晴朗',c:'用量平稳，算力气压舒适。今天适合把注意力留给代码本身。',m:'稳定',g:'rgba(245,158,11,.28)'};
  if(cache>=.72) w={i:'🌈',t:'缓存彩虹',c:'大量上下文被成功复用，重复算力正在悄悄变成你的隐形红利。',m:Math.round(cache*100)+'%',g:'rgba(167,139,250,.34)'};
  if(ratio>=1.35) w={i:'🌧️',t:'局部 Token 暴雨',c:'最近七期明显高于此前节奏，算力云层正在快速增厚。',m:'+'+Math.round((ratio-1)*100)+'%',g:'rgba(91,141,239,.42)'};
  if(ratio>=1.8) w={i:'⛈️',t:'模型风暴',c:'Token 气压出现强烈跃升。建议点开柱状图，定位是哪一期掀起了风暴。',m:'×'+ratio.toFixed(1),g:'rgba(244,114,182,.38)'};
  if(night>=.42) w={i:'🌙',t:'深夜低压',c:'大量算力聚集在夜间，屏幕亮着的时候，城市可能已经睡了。',m:Math.round(night*100)+'%',g:'rgba(99,102,241,.38)'};
  if(state.focusPeriod) w.c='时光探针已锁定 '+fmtLabel(state.focusPeriod,state.gran)+'。此刻的天气只属于这一段时间。';
  document.getElementById('w-icon').textContent=w.i; document.getElementById('w-title').textContent=w.t; document.getElementById('w-copy').textContent=w.c; document.getElementById('w-metric').textContent=w.m; document.getElementById('w-metric-label').textContent=state.focusPeriod?'局部气候':'相对近况'; document.getElementById('weather-card').style.setProperty('--weather-glow',w.g);
}
function renderProbe(){
  const el=document.getElementById('time-probe'),trailButton=document.getElementById('trail-open');
  if(scrubState.period){const row=scrubRow();if(row){document.getElementById('probe-copy').innerHTML='<b>正在预览 '+esc(fmtLabel(row.period,state.gran))+'</b> · '+human(row.total)+' tk · 点击或按 Enter 提交';el.classList.add('scrubbing');}return;}
  el.classList.remove('scrubbing');delete el.dataset.scrubPeriod;
  if(!state.focusPeriod){el.classList.remove('on');trailButton.setAttribute('aria-expanded',String(trailState.open));return;}
  const row=selectedRows()[0], dom=row?Object.entries(row.models).sort((a,b)=>b[1]-a[1])[0]:null;
  document.getElementById('probe-copy').innerHTML='<b>正在回看 '+esc(fmtLabel(state.focusPeriod,state.gran))+'</b> · '+human(row?row.total:0)+' tk'+(dom?' · 主力 '+esc(pretty(dom[0])):'')+' · Esc 返回全景';
  trailButton.innerHTML=trailState.open?'⌁ 返回寻迹 <kbd>I</kbd>':'⌁ 开始寻迹 <kbd>I</kbd>';trailButton.setAttribute('aria-expanded',String(trailState.open));
  el.classList.add('on');
}

const TRAIL_STEPS=['scope','model','evidence','destination'],TRAIL_LABELS={scope:'当前范围',model:'模型线索',evidence:'证据分支',destination:'深入模块'};
function trailScope(){
  const rows=selectedRows(),allRows=selectedRows(true),sourceByPeriod=Object.fromEntries((DATA[state.gran]||[]).map(row=>[row.period,row])),current=rows.reduce((out,row)=>{out.total+=row.total;out.calls+=row.calls;Object.entries(row.models).forEach(([model,value])=>{const item=out.models[model]||(out.models[model]={model,total:0,calls:0});item.total+=value;item.calls+=(sourceByPeriod[row.period]?.model_calls||{})[model]||0;});return out;},{total:0,calls:0,models:{}}),period=state.focusPeriod||null,index=period?allRows.findIndex(row=>row.period===period):-1,previous=index>0?allRows[index-1]:null;
  const days=period?periodDays(period,state.gran).filter(day=>DATA.day_details?.[day]):Object.keys(DATA.day_details||{}).sort(),first=days[0]||null,last=days[days.length-1]||null;
  return {period,days,first,last,total:current.total,calls:current.calls,models:Object.values(current.models).sort((a,b)=>b.total-a.total||pretty(a.model).localeCompare(pretty(b.model))),previous,delta:previous?current.total-previous.total:null};
}
function trailScopeLabel(scope=trailScope()){if(scope.period)return fmtLabel(scope.period,state.gran);if(scope.first&&scope.last)return scope.first===scope.last?scope.first:scope.first+' → '+scope.last;return '当前全景';}
function trailDeltaText(value,previous){if(!previous)return '无可比较上一期';if(value===0)return '与上一可用期持平';return '较上一可用期 '+(value>0?'增加 ':'减少 ')+human(Math.abs(value))+' tk';}
function trailModelPrevious(model,scope=trailScope()){if(!scope.previous)return null;return {period:scope.previous.period,total:scope.previous.models[model]||0,calls:(DATA[state.gran].find(row=>row.period===scope.previous.period)?.model_calls||{})[model]||0};}
function trailEntityEvidence(kind,model=trailState.model,scope=trailScope()){
  if(!model)return [];
  const buckets={};scope.days.forEach(day=>{const detail=DATA.day_details?.[day];if(!detail)return;const rows=kind==='session'?(detail.sessions||detail.top_sessions||[]):(detail.cwds||detail.top_cwds||[]);rows.forEach(row=>{const value=(row[3]||{})[model]||0;if(!value)return;const id=row[2]||row[0],item=buckets[id]||(buckets[id]={id,label:row[0],total:0});item.total+=value;});});
  return Object.values(buckets).sort((a,b)=>b.total-a.total||a.label.localeCompare(b.label));
}
function trailReuseEvidence(model=trailState.model,scope=trailScope()){
  const rows=(DATA.reuse||{})[state.gran]||[],parts=[0,0,0,0,0];let matched=0;
  rows.forEach(([period,byModel])=>{if(scope.period&&period!==scope.period)return;const values=(byModel||{})[model];if(!values)return;matched++;values.forEach((value,index)=>parts[index]+=value||0);});
  return {period:scope.period,matched,parts,total:parts.reduce((sum,value)=>sum+value,0)};
}
function trailEvidenceAvailability(kind){
  if(!trailState.model)return {available:false,reason:'先选择一个模型线索。'};
  if(kind==='project'){const items=trailEntityEvidence('project');return {available:items.length>0,items,reason:items.length?'':capabilityReason('project')};}
  if(kind==='session'){const items=trailEntityEvidence('session');return {available:items.length>0,items,reason:items.length?'':capabilityReason('session')};}
  const reuse=trailReuseEvidence();return {available:reuse.total>0,reuse,reason:reuse.total?'':capabilityReason('reuse')};
}
function reconcileTrailState(message=''){
  if(trailState.model&&!state.models.has(trailState.model)){trailState.model=null;trailState.branch=null;trailState.destination=null;trailState.step='model';trailState.reached=1;message=message||'原寻迹模型已不在全局筛选中，已返回模型线索。';}
  if(!TRAIL_STEPS.includes(trailState.step))trailState.step='scope';
  if(!trailState.model&&['evidence','destination'].includes(trailState.step)){trailState.step='model';trailState.reached=Math.min(trailState.reached,1);}
  if(!trailState.branch&&trailState.step==='destination'){trailState.step='evidence';trailState.reached=Math.min(trailState.reached,2);}
  trailState.reached=Math.max(trailState.reached,TRAIL_STEPS.indexOf(trailState.step));
  if(message)trailAnnounce(message);
}
function trailAnnounce(message){const node=document.getElementById('trail-status');if(node)node.textContent=message||'';}
function setTrailStep(step,focus=true){const index=TRAIL_STEPS.indexOf(step);if(index<0||index>trailState.reached)return;trailState.step=step;if(step!=='destination')trailState.destination=null;renderDataTrail();if(focus)setTimeout(()=>document.querySelector('#trail-body [data-trail-roving="0"],#trail-body button')?.focus(),0);}
function openDataTrail(opener=document.activeElement){if(!trailState.open||!trailState.opener)trailState.opener=opener&&document.contains(opener)?opener:trailState.opener;trailState.open=true;reconcileTrailState();renderProbe();renderDataTrail();setTimeout(()=>{document.getElementById('trail-title')?.focus();document.getElementById('data-trail')?.scrollIntoView({behavior:trailScrollBehavior(),block:'nearest'});},0);}
function closeDataTrail(restore=true){const opener=trailState.opener;trailState.open=false;trailState.destination=null;renderProbe();renderDataTrail();if(restore)setTimeout(()=>{if(opener&&document.contains(opener))opener.focus();else document.getElementById('trail-open')?.focus();},0);}
function trailBack(){const index=TRAIL_STEPS.indexOf(trailState.step);if(index<=0){closeDataTrail();return;}trailState.step=TRAIL_STEPS[index-1];if(trailState.step==='model'){trailState.branch=null;trailState.destination=null;}else if(trailState.step==='evidence')trailState.destination=null;renderDataTrail();trailAnnounce('已返回'+TRAIL_LABELS[trailState.step]+'。');}
function trailStepHTML(){const current=TRAIL_STEPS.indexOf(trailState.step);return TRAIL_STEPS.map((step,index)=>'<li class="trail-step '+(index<current?'done ':index===current?'on ':'')+'"><button type=button data-trail-step="'+step+'"'+(index>trailState.reached?' disabled':'')+(index===current?' aria-current="step"':'')+'><i>'+(index<current?'✓':index+1)+'</i><span>'+TRAIL_LABELS[step]+'</span></button></li>').join('');}
function trailScopeHTML(scope){const selected=state.models.size+'/'+DATA.models.length,delta=trailDeltaText(scope.delta,scope.previous);return '<div class=trail-scope-grid><div class=trail-metric><span>范围</span><b>'+esc(trailScopeLabel(scope))+'</b></div><div class=trail-metric><span>粒度</span><b>'+esc({day:'日',week:'周',month:'月'}[state.gran])+'</b></div><div class=trail-metric><span>模型覆盖</span><b>'+selected+'</b></div><div class=trail-metric><span>Token</span><b>'+fmt(scope.total)+'</b></div><div class=trail-metric><span>调用记录</span><b>'+fmt(scope.calls)+'</b></div></div><div class=trail-note><b>'+esc(delta)+'</b>。上一期指同一粒度中紧邻的上一条可用聚合记录；Token 增减不代表更好或更差。</div><div class=trail-controls><p>下一步会选择临时模型线索，不会偷偷修改页面筛选。</p><button class=ghostbtn type=button data-trail-action="models">查看模型线索 →</button></div>';}
function trailModelHTML(scope){
  if(!scope.models.length)return '<div class=trail-note><b>当前范围没有已选模型数据。</b> 恢复模型后才能继续寻迹。 <button class=ghostbtn type=button data-trail-action="restore-models">恢复全部模型</button></div>';
  const options=scope.models.map((item,index)=>{const previous=trailModelPrevious(item.model,scope),delta=previous?item.total-previous.total:null,on=trailState.model===item.model;return '<button type=button class="trail-option '+(on?'on':'')+'" data-trail-model="'+esc(item.model)+'" data-trail-roving="'+(index===0?'0':'-1')+'" tabindex="'+(index===0?'0':'-1')+'" style="--trail-color:'+(DATA.colors[item.model]||'var(--accent)')+'"><i class=trail-dot></i><b>'+esc(pretty(item.model))+'</b><strong>'+human(item.total)+' tk</strong><small>'+fmt(item.calls)+' 条调用记录 · '+esc(trailDeltaText(delta,previous))+'</small></button>';}).join('');
  return '<div class=trail-note>选择模型只决定这条证据线；点击“只看此模型”才会修改全局筛选。</div><div class=trail-list role=listbox aria-label="模型线索，使用上下方向键浏览">'+options+'</div>'+(trailState.model?'<div class=trail-controls><p>已选择 '+esc(pretty(trailState.model))+'</p><div><button class=ghostbtn type=button data-trail-action="solo-model">只看此模型</button> <button class=ghostbtn type=button data-trail-action="evidence">展开证据 →</button></div></div>':'');
}
function trailEvidenceHTML(){const project=trailEvidenceAvailability('project'),session=trailEvidenceAvailability('session'),reuse=trailEvidenceAvailability('reuse'),branch=(key,icon,title,summary,item,index)=>'<button type=button class="trail-branch '+(trailState.branch===key?'on':'')+'" data-trail-branch="'+key+'" data-trail-roving="'+(index===0?'0':'-1')+'" tabindex="'+(index===0?'0':'-1')+'"'+(item.available?'':' disabled title="'+esc(item.reason)+'"')+'><span class=trail-icon>'+icon+'</span><b>'+title+'</b><span>'+esc(summary)+'</span><small>'+(item.available?'Enter 查看证据':esc(item.reason))+'</small></button>';
  return '<div class=trail-note><b>'+esc(pretty(trailState.model))+'</b> 的三类证据是同范围、同模型的平行聚合；项目与会话之间不构造配对关系。</div><div class=trail-branches role=listbox aria-label="证据分支，使用上下方向键浏览">'+branch('project','▣','项目证据',project.available?project.items.length+' 个项目，按 Token 排序':'当前不可用',project,0)+branch('session','◉','会话证据',session.available?session.items.length+' 个会话，按 Token 排序':'当前不可用',session,1)+branch('reuse','≈','Context 证据',reuse.available?human(reuse.reuse.total)+' tk 标准化构成':'当前不可用',reuse,2)+'</div>';
}
function trailDestinationHTML(){
  const branch=trailState.branch;if(branch==='project'||branch==='session'){const data=trailEvidenceAvailability(branch),items=data.items||[],noun=branch==='project'?'项目':'会话',rows=items.slice(0,6).map(item=>'<button type=button class=trail-evidence-item data-trail-'+branch+'="'+esc(item.id)+'" data-trail-label="'+esc(item.label)+'"><b>'+esc(item.label)+'</b><strong>'+human(item.total)+' tk</strong><small>'+(branch==='project'?'打开项目透镜':'打开报告内实际保留的完整会话序列')+'</small></button>').join('');const caveat=branch==='project'?'项目证据遵守当前范围与寻迹模型。':'回放不会按寻迹模型或时光探针周期裁剪；每会话最多保留最近 200 轮。';return '<div class=trail-evidence><div class=trail-evidence-list>'+rows+'</div><div class=trail-note><b>'+noun+'证据边界</b><br>'+esc(caveat)+'<br><br>项目和会话是平行聚合，不是已证明的关联。</div></div>';}
  const data=trailEvidenceAvailability('reuse').reuse,labels=['Fresh Input','Output','Cache Read','Cache Write','Other'],colors=['#5b8def','#f472b6','#14b8a6','#a78bfa','#94a3b8'],max=Math.max(1,...data.parts),parts=data.parts.map((value,index)=>'<div class=trail-part><span>'+labels[index]+'</span><i style="width:'+Math.max(2,value/max*100).toFixed(1)+'%;--trail-color:'+colors[index]+'"></i><b>'+fmt(value)+'</b></div>').join('');return '<div class=trail-evidence><div class=trail-composition>'+parts+'</div><div class=trail-note><b>合计 '+fmt(data.total)+' Token</b><br>Cache Read 是缓存 Token 读取量，不等于已确认的货币节省。Other 是标准化分量与来源 total 对齐后的剩余量，非零时不会隐藏。<br><br><button class=ghostbtn type=button data-trail-reuse>前往复用之河 →</button></div></div>';
}
function renderDataTrail(){
  const rail=document.getElementById('data-trail');if(!rail)return;reconcileTrailState();document.getElementById('trail-open').setAttribute('aria-expanded',String(trailState.open));if(!trailState.open){rail.hidden=true;rail.setAttribute('aria-hidden','true');rail.classList.remove('open');return;}rail.hidden=false;rail.setAttribute('aria-hidden','false');rail.classList.add('open');rail.classList.toggle('motion-static',motionDisabled()||document.documentElement.dataset.motion==='low');document.getElementById('trail-steps').innerHTML=trailStepHTML();document.getElementById('trail-back').disabled=trailState.step==='scope';const scope=trailScope(),body=document.getElementById('trail-body');body.innerHTML=trailState.step==='scope'?trailScopeHTML(scope):trailState.step==='model'?trailModelHTML(scope):trailState.step==='evidence'?trailEvidenceHTML():trailDestinationHTML();
}
function trailScrollBehavior(){return motionDisabled()||document.documentElement.dataset.motion==='low'?'auto':'smooth';}
function activateTrailDestination(card,focusTarget){if(!card)return;card.classList.remove('trail-destination');void card.offsetWidth;card.classList.add('trail-destination');setTimeout(()=>card.classList.remove('trail-destination'),700);setTimeout(()=>focusTarget?.focus(),80);}
function openTrailProject(id){selectedProject=id;trailState.destination='project';renderLazy('project',true);scrollToSection('section-project');activateTrailDestination(document.getElementById('section-project'),document.getElementById('project-select'));trailAnnounce('已前往项目透镜。');}
function openTrailSession(id,label){trailState.destination='session';trailAnnounce('正在打开会话回放；回放不按寻迹模型或周期裁剪。');openReplay(id,label);}
function openTrailReuse(){trailState.destination='reuse';renderLazy('reuse',true);scrollToSection('section-reuse');setTimeout(()=>{const period=trailScope().period,hit=period?[...document.querySelectorAll('#reuse-chart .reuse-hit')].find((node,index)=>selectedReuseRows().filter(row=>!state.focusPeriod||row[0]===state.focusPeriod)[index]?.[0]===period):document.querySelector('#reuse-chart .reuse-hit[tabindex="0"]');activateTrailDestination(document.getElementById('section-reuse'),hit||document.getElementById('reuse-chart'));},40);trailAnnounce('已前往 Context Reuse River。');}
function trailRoving(event){const item=event.target.closest('[data-trail-roving]');if(!item)return false;const root=item.parentElement,items=[...root.querySelectorAll('[data-trail-roving]:not([disabled])')];if(!items.length)return false;let index=items.indexOf(item),next=null;if(event.key==='ArrowDown'||event.key==='ArrowRight')next=Math.min(items.length-1,index+1);else if(event.key==='ArrowUp'||event.key==='ArrowLeft')next=Math.max(0,index-1);else if(event.key==='Home')next=0;else if(event.key==='End')next=items.length-1;if(next==null)return false;event.preventDefault();items.forEach((node,i)=>{node.tabIndex=i===next?0:-1;node.dataset.trailRoving=i===next?'0':'-1';});items[next].focus();return true;}
function editableTarget(target){const tag=(target?.tagName||'').toUpperCase();return tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||target?.isContentEditable;}

function dataSignalAttrs(type,id,label,value,scope='',pin=true){return ' data-signal-type="'+type+'" data-signal-id="'+esc(id)+'" data-signal-label="'+esc(label)+'" data-signal-value="'+Number(value||0)+'" data-signal-scope="'+esc(scope)+'"'+(pin?' data-signal-pin="true"':'');}

function signalKey(signal){return signal?signal.type+':'+signal.id:'';}
function sameSignal(a,b){return !!a&&!!b&&a.type===b.type&&a.id===b.id;}
function signalFromElement(element){if(!element)return null;const type=element.dataset.signalType,id=element.dataset.signalId;if(!type||!id)return null;return {type,id,label:element.dataset.signalLabel||id,value:Number(element.dataset.signalValue||0),meta:{scope:element.dataset.signalScope||''}};}
function focusedPeriodSignal(){if(!state.focusPeriod)return null;const row=selectedRows(true).find(item=>item.period===state.focusPeriod);return {type:'period',id:state.focusPeriod,label:fmtLabel(state.focusPeriod,state.gran),value:row?.total||0,meta:{scope:'trend'}};}
function pinnedSignal(){return signalState.pinnedSignal;}
function currentPinnedSignal(){return pinnedSignal()||focusedPeriodSignal();}
function signalPair(){const pin=currentPinnedSignal(),peek=signalState.peek;return {pin,peek:peek&&!sameSignal(peek,pin)?peek:null};}
const SIGNAL_COMPATIBILITY={model:new Set(['model']),period:new Set(['period']),project:new Set(['project']),session:new Set(['session'])};
function signalCompatibility(pin,peek){if(!pin||!peek)return {compatible:false,reason:'需要 Pin 与 Peek 两个信号'};if(!SIGNAL_COMPATIBILITY[pin.type]?.has(peek.type))return {compatible:false,reason:'混合类型仅并排查看，不计算 Delta'};return {compatible:true,reason:'同类型本地聚合可比较'};}
function effectiveSignal(){return signalState.peek||currentPinnedSignal();}
function signalTypeLabel(type){return {model:'模型',period:'周期',project:'项目',session:'会话'}[type]||'信号';}
function resolveSignalEvidence(signal){
  if(!signal){const rows=selectedDailyRows(),end=snapshotEndDate(),quiet=trailingQuietDays(rows,end),events=buildMomentEvents();return {copy:'数据时刻已并入趋势注释轨道；悬停、聚焦或固定一个信号，可查看跨模块上下文。',stamps:[(DATA.range?.since||'起始')+' → '+(DATA.range?.until||'至今'),state.models.size+'/'+DATA.models.length+' 模型',events.length+' 个可回看时刻',quiet.kind==='quiet'?'末端静默 '+quiet.days+' 天':quiet.kind==='active'?'范围末端仍活跃':'当前筛选无观察值']};}
  if(signal.type==='model'){
    const rows=selectedRows(),sourceByPeriod=Object.fromEntries((DATA[state.gran]||[]).map(row=>[row.period,row])),total=rows.reduce((sum,row)=>sum+(row.models[signal.id]||0),0),calls=rows.reduce((sum,row)=>sum+((sourceByPeriod[row.period]?.model_calls||{})[signal.id]||0),0),all=rows.reduce((sum,row)=>sum+row.total,0);
    return {total,calls,copy:'当前范围与时光探针下的完整模型聚合；Pin 不会修改模型筛选。',stamps:[human(total)+' tk',pct(total,all)+' 当前占比',fmt(calls)+' 条调用记录',state.focusPeriod?'时光探针 '+fmtLabel(state.focusPeriod,state.gran):'当前全景'],exact:[fmt(total)+' Token','分子 '+fmt(total)+' / 分母 '+fmt(all),fmt(calls)+' 条调用记录',state.focusPeriod?'周期 '+state.focusPeriod:'报告范围']};
  }
  if(signal.type==='period'){
    const rows=selectedRows(true),index=rows.findIndex(row=>row.period===signal.id),row=rows[index],previous=index>0?rows[index-1]:null,delta=row&&previous&&previous.total?((row.total-previous.total)/previous.total*100):null;
    return {total:row?.total||0,calls:row?.calls||0,copy:'周期 Pin 继续使用 state.focusPeriod；上一期是同粒度中紧邻的上一条聚合记录。',stamps:[human(row?.total||0)+' tk',fmt(row?.calls||0)+' 条调用记录',row&&previous?((row.total-previous.total)>=0?'+':'')+human(row.total-previous.total)+' tk':'无上一期',delta==null?'无百分比变化':(delta>=0?'+':'')+delta.toFixed(1)+'%'],exact:[fmt(row?.total||0)+' Token',fmt(row?.calls||0)+' 条调用记录',row&&previous?((row.total-previous.total)>=0?'+':'')+fmt(row.total-previous.total)+' Token':'无上一期绝对变化',delta==null?'无上一期百分比变化':(delta>=0?'+':'')+delta.toFixed(1)+'%']};
  }
  if(signal.type==='project'){
    const item=scopedEntities('project').find(row=>row[2]===signal.id),models=item?.[3]||{},dominant=Object.entries(models).sort((a,b)=>b[1]-a[1])[0],total=item?.[1]||0,all=selectedRows().reduce((sum,row)=>sum+row.total,0);
    return {total,calls:null,copy:'项目信号来自完整筛选项目聚合及真实项目→模型流向，不会推断项目与会话的配对关系。',stamps:[human(total)+' tk',pct(total,all)+' 当前占比',dominant?'主力 '+pretty(dominant[0]):'无模型构成',state.focusPeriod?'当前探针范围':'当前报告范围'],exact:[fmt(total)+' Token','分子 '+fmt(total)+' / 当前范围 '+fmt(all),Object.keys(models).length+' 个模型分量',dominant?'主力 '+pretty(dominant[0])+' '+fmt(dominant[1])+' Token':'无模型构成']};
  }
  const series=DATA.session_series?.[signal.id]||[],item=scopedEntities('session').find(row=>row[2]===signal.id),total=item?.[1]||0;
  return {total,calls:null,copy:'会话信号来自完整筛选会话聚合及真实模型→会话流向；它与项目证据保持平行，不构造配对关系。',stamps:[human(total)+' tk',series.length+' 轮已保留',series.length>=200?'最多最近 200 轮':'完整保留序列','横轴是轮次，不代表耗时'],exact:[fmt(total)+' Token',fmt(series.length)+' 轮已保留',series.length>=200?'保留边界：最近 200 轮':'未触及 200 轮边界','回放不按模型或时光探针裁剪']};
}
function signalEvidence(signal){return resolveSignalEvidence(signal);}
function signalComparison(pair=signalPair()){const compatibility=signalCompatibility(pair.pin,pair.peek);if(!pair.pin||!pair.peek)return {compatible:false,label:'固定后再 Peek 一个兼容信号',reason:compatibility.reason};if(!compatibility.compatible)return {compatible:false,mixed:true,label:compatibility.reason,reason:compatibility.reason};const pin=resolveSignalEvidence(pair.pin),peek=resolveSignalEvidence(pair.peek);if(!Number.isFinite(pin.total)||!Number.isFinite(peek.total))return {compatible:false,label:'当前信号没有可比较 Token 聚合',reason:'缺少可比较聚合'};const delta=peek.total-pin.total,ratio=pin.total?delta/pin.total:null;return {compatible:true,delta,ratio,label:(delta>=0?'+':'')+human(delta)+' tk'+(ratio==null?'':(' · '+(ratio>=0?'+':'')+(ratio*100).toFixed(1)+'%')),reason:'Peek 相对 Pin'};}
function signalActions(signal){if(!signal)return {label:'选择一个信号',disabled:true};if(signal.type==='model')return {label:'只看此模型',run:()=>setModels([signal.id],'只看 '+signal.label)};if(signal.type==='period')return {label:state.focusPeriod===signal.id?'退出时光探针':'进入时光探针',run:()=>toggleFocus(signal.id,true)};if(signal.type==='project')return {label:'打开项目透镜',run:()=>{selectedProject=signal.id;renderLazy('project',true);scrollToSection('section-project');setTimeout(()=>document.getElementById('project-select')?.focus(),60);}};return {label:'打开会话回放',run:()=>openReplay(signal.id,signal.label)};}
function renderSignalDock(){
  const pair=signalPair(),signal=effectiveSignal(),evidence=resolveSignalEvidence(signal),comparison=signalComparison(pair),action=signalActions(signal),pinned=!!pair.pin,dock=document.getElementById('signal-dock');if(!dock)return;
  dock.classList.toggle('has-signal',!!signal);dock.classList.toggle('is-pinned',pinned);document.getElementById('signal-label').textContent=pair.peek?'Peek · '+pair.peek.label:pair.pin?'Pin · '+pair.pin.label:'Signal Dock';document.getElementById('signal-detail').textContent=signal?signalTypeLabel(signal.type)+' · '+(Number.isFinite(evidence.total)?human(evidence.total)+' tk':'本地上下文'):'悬停或聚焦数据以 Peek';document.getElementById('signal-pop-title').textContent=signal?signalTypeLabel(signal.type)+' · '+signal.label:'当前范围信号';document.getElementById('signal-pop-copy').textContent=evidence.copy;const summary=(item,empty)=>item?signalTypeLabel(item.type)+' · '+item.label+' · '+human(resolveSignalEvidence(item).total||0)+' tk':empty;document.getElementById('signal-pin-copy').textContent=summary(pair.pin,'未固定信号');document.getElementById('signal-peek-copy').textContent=summary(pair.peek,'悬停或聚焦以查看');const delta=document.getElementById('signal-delta-summary');delta.classList.toggle('compatible',comparison.compatible);delta.classList.toggle('mixed',!!comparison.mixed);document.getElementById('signal-delta-copy').textContent=comparison.label;const stamps=exactnessActive()&&evidence.exact?evidence.exact:evidence.stamps;document.getElementById('signal-stamps').innerHTML=(stamps||[]).map(stamp=>'<span>'+esc(stamp)+'</span>').join('');const clear=document.getElementById('signal-clear');clear.disabled=!pinned;clear.setAttribute('aria-label',pair.pin?.type==='period'&&state.focusPeriod===pair.pin.id?'退出时光探针':'清除固定信号');const button=document.getElementById('signal-action');button.textContent=action.label;button.disabled=!!action.disabled;button.__signalRun=action.run||null;
}
function signalScopeRoot(source){if(!source)return null;const scope=source.dataset?.signalScope;if(!scope||scope==='filters')return null;if(scope==='flow')return document.getElementById('flow-map');if(scope==='top')return source.closest('#section-top');if(scope==='trend')return source.closest('#section-trend');if(scope==='composition')return source.closest('.card');if(scope==='project')return source.closest('#section-project');if(scope==='multiples')return source.closest('[data-module="multiples"]');return source.closest('.card,section');}
function applySignalClasses(){
  const signal=effectiveSignal(),pair=signalPair();document.querySelectorAll('.signal-hot,.signal-related,.signal-dim,.signal-pinned').forEach(el=>el.classList.remove('signal-hot','signal-related','signal-dim','signal-pinned'));if(!signal)return;
  const source=signalState.peek?signalState.peekSource:signalState.opener,root=signalScopeRoot(source),scope=source?.dataset?.signalScope||signal.meta?.scope||'',canDim=!!root&&scope!=='filters'&&(!pair.pin||!pair.peek||pair.pin.type===pair.peek.type),peers=root?[...root.querySelectorAll('[data-signal-type="'+signal.type+'"]')]:[...document.querySelectorAll('[data-signal-type="'+signal.type+'"]')];peers.forEach(el=>{const direct=el.dataset.signalId===signal.id;el.classList.toggle('signal-hot',direct);if(canDim)el.classList.toggle('signal-dim',!direct);if(direct&&sameSignal(signal,pair.pin))el.classList.add('signal-pinned');});
  const links=[...document.querySelectorAll('#flow-map .flow-link')],nodes=[...document.querySelectorAll('#flow-map .flow-node')],related=new Set();if(signal.type==='model'){links.forEach(link=>{if(link.dataset.flowModel===signal.id){link.classList.add('signal-related');if(link.dataset.flowFrom)related.add(link.dataset.flowFrom);if(link.dataset.flowTo)related.add(link.dataset.flowTo);}});}if(signal.type==='project'){const key='project:'+signal.id;links.forEach(link=>{if(link.dataset.flowFrom===key){link.classList.add('signal-related');related.add('model:'+link.dataset.flowModel);}});}if(signal.type==='session'){const key='session:'+signal.id;links.forEach(link=>{if(link.dataset.flowTo===key){link.classList.add('signal-related');related.add('model:'+link.dataset.flowModel);}});}nodes.forEach(node=>{if(related.has(node.dataset.flowType+':'+node.dataset.flowId))node.classList.add('signal-related');});
}
function applySignalLens(){applySignalClasses();renderSignalDock();}
function setSignalPeek(signal,source=null){if(sameSignal(signal,signalState.peek)&&signalState.peekSource===source)return;signalState.peek=signal;signalState.peekSource=source;applySignalLens();}
function clearSignalPeek(signal){if(signal&&!sameSignal(signal,signalState.peek))return;signalState.peek=null;signalState.peekSource=null;applySignalLens();}
function setSignalPreview(signal,source=null){setSignalPeek(signal,source);}
function clearSignalPreview(signal){clearSignalPeek(signal);}
function toggleSignalPin(signal){if(!signal)return;clearScrub();signalState.pinnedSignal=sameSignal(signalState.pinnedSignal,signal)?null:signal;signalState.peek=null;signalState.peekSource=null;if(signal.type==='period'){const entering=state.focusPeriod!==signal.id;state.focusPeriod=entering?signal.id:null;if(!entering){trailState.step='scope';trailState.reached=0;trailState.branch=null;trailState.destination=null;}invalidateDerived();renderDataViews();announceViewChange(entering?'时光探针已锁定 '+fmtLabel(signal.id,state.gran):'已返回当前粒度全景',['section-trend','section-overview','section-top']);}document.getElementById('signal-status').textContent=signalState.pinnedSignal?'已 Pin '+signalTypeLabel(signal.type)+' '+signal.label:'已清除 Pin';applySignalLens();}
function clearSignal(restore=true){const opener=signalState.opener,pin=currentPinnedSignal(),period=pin?.type==='period'&&state.focusPeriod===pin.id?state.focusPeriod:null;signalState.peek=null;signalState.peekSource=null;signalState.pinnedSignal=null;if(period){state.focusPeriod=null;trailState.step='scope';trailState.reached=0;trailState.branch=null;trailState.destination=null;invalidateDerived();renderDataViews();announceViewChange('已退出时光探针',['section-trend','section-overview','section-top']);}else applySignalLens();if(restore&&opener&&document.contains(opener))opener.focus();}
function bindSignalLens(){
  if(document.body.dataset.signalDelegated)return;document.body.dataset.signalDelegated='1';
  document.addEventListener('pointerover',event=>{const el=event.target.closest('[data-signal-type]');if(el)setSignalPeek(signalFromElement(el),el);});
  document.addEventListener('pointerout',event=>{const el=event.target.closest('[data-signal-type]');if(el&&!el.contains(event.relatedTarget)){const next=event.relatedTarget?.closest?.('[data-signal-type]');if(!next||signalKey(signalFromElement(next))!==signalKey(signalFromElement(el)))clearSignalPeek(signalFromElement(el));}});
  document.addEventListener('focusin',event=>{const el=event.target.closest('[data-signal-type]');if(el)setSignalPeek(signalFromElement(el),el);});
  document.addEventListener('focusout',event=>{const el=event.target.closest('[data-signal-type]');if(el&&!el.contains(event.relatedTarget)){const next=event.relatedTarget?.closest?.('[data-signal-type]');if(!next||signalKey(signalFromElement(next))!==signalKey(signalFromElement(el)))clearSignalPeek(signalFromElement(el));}});
  document.addEventListener('click',event=>{const el=event.target.closest('[data-signal-pin="true"]');if(!el)return;if(el.matches('select,input,textarea,option'))return;event.preventDefault();event.stopPropagation();signalState.opener=el;toggleSignalPin(signalFromElement(el));});
  document.addEventListener('keydown',event=>{const el=event.target.closest('[data-signal-pin="true"]');if(!el||(event.key!=='Enter'&&event.key!==' '))return;if(el.matches('select,input,textarea,option'))return;event.preventDefault();event.stopPropagation();signalState.opener=el;toggleSignalPin(signalFromElement(el));});
}

document.getElementById('trail-open').addEventListener('click',e=>openDataTrail(e.currentTarget));document.getElementById('trail-close').addEventListener('click',()=>closeDataTrail());document.getElementById('trail-back').addEventListener('click',trailBack);document.getElementById('data-trail').addEventListener('click',event=>{const step=event.target.closest('[data-trail-step]');if(step){setTrailStep(step.dataset.trailStep,false);return;}const action=event.target.closest('[data-trail-action]');if(action){const key=action.dataset.trailAction;if(key==='models'){trailState.reached=Math.max(trailState.reached,1);setTrailStep('model');}else if(key==='restore-models')setModels(DATA.models,'已恢复全部模型');else if(key==='solo-model'&&trailState.model)setModels([trailState.model],'Solo · '+pretty(trailState.model));else if(key==='evidence'){trailState.reached=Math.max(trailState.reached,2);setTrailStep('evidence');}return;}const model=event.target.closest('[data-trail-model]');if(model){trailState.model=model.dataset.trailModel;trailState.branch=null;trailState.destination=null;trailState.reached=Math.max(trailState.reached,1);renderDataTrail();trailAnnounce('模型线索已选择：'+pretty(trailState.model)+'。');return;}const branch=event.target.closest('[data-trail-branch]');if(branch){trailState.branch=branch.dataset.trailBranch;trailState.step='destination';trailState.reached=3;renderDataTrail();trailAnnounce('已展开'+({project:'项目',session:'会话',reuse:'Context'}[trailState.branch])+'证据。');return;}const project=event.target.closest('[data-trail-project]');if(project)openTrailProject(project.dataset.trailProject);const session=event.target.closest('[data-trail-session]');if(session)openTrailSession(session.dataset.trailSession,session.dataset.trailLabel);if(event.target.closest('[data-trail-reuse]'))openTrailReuse();});document.getElementById('data-trail').addEventListener('keydown',event=>{if(trailRoving(event))return;if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-trail-model],[data-trail-branch]')){event.preventDefault();event.target.click();}});

function toggleFocus(period,restoreBar=false){clearScrub();const entering=state.focusPeriod!==period;state.focusPeriod=entering?period:null;if(signalState.pinnedSignal?.type==='period'&&signalState.pinnedSignal.id!==state.focusPeriod)signalState.pinnedSignal=null;if(!entering){trailState.step='scope';trailState.reached=0;trailState.branch=null;trailState.destination=null;}invalidateDerived();renderDataViews();announceViewChange(entering?'时光探针已锁定 '+fmtLabel(period,state.gran):'已返回当前粒度全景',['section-trend','section-overview','section-top']);if(restoreBar){const el=[...document.querySelectorAll('#bar .barstack')].find(x=>x.dataset.period===period);if(el){barCursor=Number(el.dataset.index||0);el.focus();}} }
function clearFocus(restoreBar=false){clearScrub();if(!state.focusPeriod)return;const period=state.focusPeriod;state.focusPeriod=null;if(signalState.pinnedSignal?.type==='period')signalState.pinnedSignal=null;trailState.step='scope';trailState.reached=0;trailState.branch=null;trailState.destination=null;invalidateDerived();renderDataViews();announceViewChange('已退出时光探针',['section-trend','section-overview','section-top']);if(restoreBar){const el=[...document.querySelectorAll('#bar .barstack')].find(x=>x.dataset.period===period);if(el){barCursor=Number(el.dataset.index||0);el.focus();}} }

document.getElementById('probe-close').addEventListener('click',clearFocus);

const THEMES=[['auto','🌗','自动'],['light','☀️','亮色'],['dark','🌙','暗色']];
let restoringView=true;
function currentTheme(){return document.documentElement.getAttribute('data-theme')||'auto';}
function validFocus(period,gran){return !!period&&DATA[gran].some(r=>r.period===period);}
function viewParams(){
  const p=new URLSearchParams();p.set('gran',state.gran);
  if(state.models.size!==DATA.models.length)DATA.models.filter(m=>state.models.has(m)).forEach(m=>p.append('model',m));
  if(state.focusPeriod)p.set('focus',state.focusPeriod);
  if(state.compare)p.set('compare','1');
  const theme=currentTheme();if(theme!=='auto')p.set('t',theme);
  return p;
}
function viewURL(){const u=new URL(location.href);u.search=viewParams().toString();u.hash='';return u.toString();}
function portableViewURL(){if(location.protocol!=='file:')return viewURL();const q=viewParams().toString(),name=location.pathname.split('/').pop()||'dashboard.html';return name+(q?'?'+q:'');}
function syncViewURL(replace=true){if(restoringView||!history.replaceState)return;const u=viewURL();history[replace?'replaceState':'pushState'](null,'',u);}
function restoreViewFromURL(){
  const p=new URLSearchParams(location.search),g=p.get('gran')||((location.hash||'').replace('#',''));
  if(['day','week','month'].includes(g))state.gran=g;
  const requested=p.getAll('model'),legacy=p.get('models');if(requested.length||legacy!==null){const allowed=new Set(DATA.models),models=(requested.length?requested:(legacy?legacy.split(','):[])).filter(m=>allowed.has(m));state.models=new Set(models);}else state.models=new Set(DATA.models);previousModels=null;
  const focus=p.get('focus');state.focusPeriod=validFocus(focus,state.gran)?focus:null;state.compare=p.get('compare')==='1';
  const theme=(p.get('t')||'').toLowerCase();if(['auto','light','dark'].includes(theme))applyTheme(theme);
}
function viewDescription(){const gran={day:'按日',week:'按周',month:'按月'}[state.gran],modelCount=state.models.size,focus=state.focusPeriod?fmtLabel(state.focusPeriod,state.gran):'全景',compare=state.compare?'已固定':signalState.compareHeld?'临时预览':'关闭';return {gran,modelCount,focus,compare};}
function syncGranControls(){document.querySelectorAll('#tabs button').forEach(x=>{const on=x.dataset.gran===state.gran;x.classList.toggle('on',on);x.setAttribute('aria-pressed',String(on));});}
function renderViewCapsule(){
  const d=viewDescription(),label=document.getElementById('view-label'),capsule=document.getElementById('view-capsule');
  label.textContent=d.gran.replace('按','')+' · '+(d.modelCount===DATA.models.length?'全部模型':d.modelCount+'/'+DATA.models.length+' 模型')+' · '+d.focus;
  capsule.classList.toggle('dirty',!!state.focusPeriod||state.models.size!==DATA.models.length||state.compare);
  document.getElementById('view-summary').innerHTML='<b>'+d.gran+'</b> · '+d.modelCount+' / '+DATA.models.length+' 个模型<br><b>'+(state.focusPeriod?'时光探针':'时间范围')+'</b> · '+esc(d.focus)+'<br><b>幻影对比</b> · '+d.compare;
  syncGranControls();const compare=document.getElementById('compare-btn');compare.classList.toggle('on',compareActive());compare.classList.toggle('held',signalState.compareHeld&&!state.compare);compare.setAttribute('aria-pressed',String(state.compare));
}
function resetView(){clearScrub();state.gran='month';state.models=new Set(DATA.models);state.focusPeriod=null;state.compare=false;signalState.peek=null;signalState.pinnedSignal=null;signalState.compareHeld=false;previousModels=null;trailState.step='scope';trailState.reached=0;trailState.model=null;trailState.branch=null;trailState.destination=null;invalidateDerived();renderFilters();renderDataViews();announceViewChange('已恢复月度全景',['section-overview','section-trend','section-top']);}
async function copyText(text){try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);return true;}}catch(e){}const ta=document.createElement('textarea');ta.value=text;ta.style.cssText='position:fixed;left:-9999px;top:0';document.body.appendChild(ta);ta.select();let ok=false;try{ok=document.execCommand('copy');}catch(e){}ta.remove();return ok;}
function copyViewLink(){copyText(portableViewURL()).then(ok=>toast(ok?'当前视图链接已复制':'复制失败，请从地址栏复制'));}
document.getElementById('view-capsule').addEventListener('click',e=>{e.stopPropagation();const pop=document.getElementById('view-pop'),open=!pop.classList.contains('open');pop.classList.toggle('open',open);e.currentTarget.setAttribute('aria-expanded',String(open));});
document.getElementById('view-copy').addEventListener('click',copyViewLink);document.getElementById('view-reset').addEventListener('click',resetView);document.addEventListener('click',e=>{if(!e.target.closest('.view-wrap')){document.getElementById('view-pop').classList.remove('open');document.getElementById('view-capsule').setAttribute('aria-expanded','false');}if(!e.target.closest('#signal-dock')){document.getElementById('signal-pop').classList.remove('open');document.getElementById('signal-main').setAttribute('aria-expanded','false');}});
document.getElementById('signal-main').addEventListener('click',event=>{event.stopPropagation();const pop=document.getElementById('signal-pop'),open=!pop.classList.contains('open');pop.classList.toggle('open',open);event.currentTarget.setAttribute('aria-expanded',String(open));if(open){renderSignalDock();setTimeout(()=>{const action=document.getElementById('signal-action');(action&&!action.disabled?action:document.getElementById('exact-btn'))?.focus();},0);}});
document.getElementById('signal-pop').addEventListener('click',event=>event.stopPropagation());document.getElementById('signal-clear').addEventListener('click',()=>clearSignal());document.getElementById('signal-action').addEventListener('click',event=>{const run=event.currentTarget.__signalRun;if(run)run();});document.getElementById('exact-btn').addEventListener('click',()=>{signalState.exactPinned=!signalState.exactPinned;syncExactness();renderSignalDock();document.getElementById('signal-status').textContent=signalState.exactPinned?'精确层已固定':'精确层已取消固定';});
window.addEventListener('popstate',()=>{clearScrub();restoringView=true;restoreViewFromURL();invalidateDerived();renderFilters();renderDataViews();restoringView=false;});

const compareButton=document.getElementById('compare-btn');let compareHoldTimer=null,compareHoldReached=false;
function togglePinnedCompare(){state.compare=!state.compare;setCompareHeld(false);renderBar();renderViewCapsule();syncViewURL();announceViewChange(state.compare?'幻影对比已固定':'幻影对比已取消',['section-trend']);}
compareButton.addEventListener('pointerdown',event=>{if(event.button!==0)return;compareHoldReached=false;clearTimeout(compareHoldTimer);compareHoldTimer=setTimeout(()=>{compareHoldReached=true;setCompareHeld(true);document.getElementById('signal-status').textContent='正在临时预览上一期轮廓';},240);});
function releaseCompareHold(){clearTimeout(compareHoldTimer);compareHoldTimer=null;if(compareHoldReached){setCompareHeld(false);compareHoldReached=false;}}
compareButton.addEventListener('pointerup',event=>{clearTimeout(compareHoldTimer);compareHoldTimer=null;if(compareHoldReached){event.preventDefault();setCompareHeld(false);compareHoldReached=false;return;}togglePinnedCompare();});compareButton.addEventListener('pointercancel',releaseCompareHold);compareButton.addEventListener('pointerleave',()=>{if(compareHoldReached)releaseCompareHold();});compareButton.addEventListener('click',event=>event.preventDefault());compareButton.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&!event.repeat){event.preventDefault();togglePinnedCompare();}});

const LAZY_RENDERERS={project:renderProjectLens,reuse:renderReuseRiver,flow:renderFlow,creature:renderCreature,race:renderRace,modes:renderWorkModes,almanac:renderAlmanac,badges:renderBadges,dna:renderDNA};
const lazyState={};
function renderLazy(name,force=false){const card=document.querySelector('[data-lazy="'+name+'"]');if(!card||card.style.display==='none')return;if(!force&&!lazyState[name]?.visible){card.classList.add('lazy-pending');lazyState[name]=Object.assign({},lazyState[name],{dirty:true});return;}card.classList.remove('lazy-pending');LAZY_RENDERERS[name]();lazyState[name]=Object.assign({},lazyState[name],{dirty:false,rendered:true});}
function markLazyDirty(){['project','reuse','flow','modes','dna'].forEach(name=>{lazyState[name]=Object.assign({},lazyState[name],{dirty:true});if(lazyState[name].visible)renderLazy(name,true);});}
function markStaticLazyDirty(){['creature','race','almanac','badges'].forEach(name=>{if(!lazyState[name]?.rendered)lazyState[name]=Object.assign({},lazyState[name],{dirty:true});});}
function initLazyRendering(){
  document.querySelectorAll('[data-lazy]').forEach(card=>{const name=card.dataset.lazy;lazyState[name]={visible:false,dirty:true,rendered:false};card.classList.add('lazy-pending');});
  if(!('IntersectionObserver'in window)){Object.keys(LAZY_RENDERERS).forEach(name=>{lazyState[name].visible=true;renderLazy(name,true);});return;}
  const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{const name=entry.target.dataset.lazy;lazyState[name]=Object.assign({},lazyState[name],{visible:entry.isIntersecting});if(entry.isIntersecting&&(lazyState[name].dirty||!lazyState[name].rendered))renderLazy(name,true);}),{rootMargin:'500px 0px'});
  document.querySelectorAll('[data-lazy]').forEach(card=>observer.observe(card));
}
function renderCoreViews(){renderKPI();renderBar();renderDonut();renderTable();renderTop();renderStatusPulse();renderViewCapsule();}
function renderTimeViews(){renderClock();renderWeather();renderProbe();renderRhythm();renderBlock();renderDaily();}
function renderModelViews(){renderMultiples();markLazyDirty();markStaticLazyDirty();}
function renderDataViews(){renderCoreViews();renderTimeViews();renderModelViews();renderProvenance();renderFunFacts();renderFortune();renderDiscovery();renderFooter();renderDataTrail();applySignalLens();syncViewURL();}
function render(){renderDataViews();}


document.getElementById('tabs').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b) return;
  setGran(b.dataset.gran);
});
function setGran(g){
  if(!['day','week','month'].includes(g)||g===state.gran)return;
  clearScrub();state.gran=g;state.focusPeriod=null;if(signalState.pinnedSignal?.type==='period')signalState.pinnedSignal=null;if(signalState.peek?.type==='period')signalState.peek=null;trailState.step='scope';trailState.reached=0;trailState.model=null;trailState.branch=null;trailState.destination=null;invalidateDerived();reconcileSignalState();renderDataViews();announceViewChange('统计粒度已切换为 '+({day:'按日',week:'按周',month:'按月'}[g]),['section-trend','section-overview']);
}

function renderSnapshotMeta(){
  document.getElementById('meta').textContent =
    '生成于 '+DATA.generated+' · '+(DATA.range.since||'起始')+' ~ '+(DATA.range.until||'至今')+(DATA.anonymized?' · 脱敏导出（标识已替换）':'');
  document.getElementById('source-txt').textContent = '来源 '+(DATA.source.join(' / ')||'无');
  document.getElementById('source-pill').title=DATA.anonymized?'项目路径、会话标识与自然语言标题已替换；精确日期、Token、模型与逐轮序列仍保留。':'';
}
renderSnapshotMeta();

/* 主题：自动 / 亮 / 暗 三态，localStorage 记忆，覆盖系统 */
function applyTheme(t){
  if(t==='light'||t==='dark') document.documentElement.setAttribute('data-theme',t);
  else document.documentElement.removeAttribute('data-theme');
  const c=THEMES.find(x=>x[0]===t)||THEMES[0];
  const b=document.getElementById('theme-btn');
  b.textContent=c[1]; b.title='主题：'+c[2]+'（点击切换）';
  try{localStorage.setItem('tk-theme',t);}catch(e){}
  if(typeof restoringView!=='undefined')syncViewURL();
}
document.getElementById('theme-btn').addEventListener('click',()=>{
  const order=['auto','light','dark'], cur=localStorage.getItem('tk-theme')||'auto';
  applyTheme(order[(order.indexOf(cur)+1)%order.length]);
});
function defaultMotion(){if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return 'off';if(window.matchMedia('(pointer: coarse)').matches||innerWidth<760)return 'low';const mem=navigator.deviceMemory||8,cores=navigator.hardwareConcurrency||8;return mem<=4||cores<=4?'low':'full';}
function applyMotion(choice,persist=true){if(!['auto','full','low','off'].includes(choice))choice='auto';const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches,effective=reduce?'off':choice==='auto'?defaultMotion():choice;document.documentElement.setAttribute('data-motion',effective);document.getElementById('motion-select').value=choice;if(persist)try{localStorage.setItem('tk-motion',choice);}catch(e){}window.dispatchEvent(new CustomEvent('tk-motion-change',{detail:{choice,effective}}));}
document.getElementById('motion-select').addEventListener('change',e=>applyMotion(e.target.value));
let motionChoice='auto';try{motionChoice=localStorage.getItem('tk-motion')||'auto';}catch(e){}applyMotion(motionChoice,false);
const motionMedia=window.matchMedia('(prefers-reduced-motion: reduce)');if(motionMedia.addEventListener)motionMedia.addEventListener('change',()=>applyMotion(document.getElementById('motion-select').value,false));
let motionResizeT=0;addEventListener('resize',()=>{if(document.getElementById('motion-select').value!=='auto')return;clearTimeout(motionResizeT);motionResizeT=setTimeout(()=>applyMotion('auto',false),120);},{passive:true});
// 初始主题：URL ?t=light|dark 优先（可分享/截图），否则 localStorage，否则跟随系统
(function(){
  const q=(new URLSearchParams(location.search).get('t')||'').toLowerCase();
  applyTheme(['light','dark'].includes(q)?q:(localStorage.getItem('tk-theme')||'auto'));
})();

function markdownCell(value){return String(value).replace(/\\/g,'\\\\').replace(/\|/g,'\\|').replace(/[\r\n]+/g,' ');}
function copyExactValue(label,value){return copyText(String(value)).then(ok=>toast(ok?'已复制 '+label+'：'+fmt(value):'复制失败'));}
function downloadBlob(content,type,filename){const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),0);}

const modalState=new WeakMap();
function modalFocusables(modal){return [...modal.querySelectorAll('button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])')].filter(x=>!x.disabled&&x.getClientRects().length);}
function openModal(modal,initialFocus){modalState.set(modal,{returnFocus:document.activeElement});modal.classList.add('open');modal.setAttribute('aria-hidden','false');document.body.classList.add('modal-open');setTimeout(()=>{const target=initialFocus||modalFocusables(modal)[0];if(target)target.focus();},0);}
function closeModal(modal){modal.classList.remove('open');modal.setAttribute('aria-hidden','true');if(!document.querySelector('.share-modal.open,.almanac-modal.open,.ach-modal.open,.help-modal.open,.modal.open'))document.body.classList.remove('modal-open');const state=modalState.get(modal);modalState.delete(modal);if(state?.returnFocus&&document.contains(state.returnFocus))state.returnFocus.focus();}
function trapModalFocus(e,modal){if(e.key!=='Tab'||!modal.classList.contains('open'))return;const items=modalFocusables(modal);if(!items.length){e.preventDefault();return;}const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
function activeModal(){return document.querySelector('.share-modal.open,.almanac-modal.open,.ach-modal.open,.help-modal.open,.modal.open');}

// CSV 导出（当前粒度 + 所选模型）
function exportCSV(){
  const rows=selectedRows(), cols=DATA.models.filter(m=>state.models.has(m));
  const head=['period','total_tokens',...cols.map(pretty),'calls'];
  const body=rows.map(r=>[r.period,r.total,...cols.map(m=>r.models[m]||0),r.calls]);
  const csv=[head,...body].map(r=>r.map(x=>/[,\"\n]/.test(String(x))?'"'+String(x).replace(/"/g,'""')+'"':x).join(',')).join('\n');
  downloadBlob('﻿'+csv,'text/csv;charset=utf-8','tokens-'+state.gran+'.csv');
}
document.getElementById('csv-btn').addEventListener('click', exportCSV);
function exportMarkdown(){
  const rows=selectedRows(), cols=DATA.models.filter(m=>state.models.has(m));
  const head=[LABEL[state.gran],'总 token',...cols.map(pretty),'调用'];
  const body=rows.map(r=>[r.period,fmt(r.total),...cols.map(m=>fmt(r.models[m]||0)),fmt(r.calls)]);
  const line=a=>'| '+a.map(markdownCell).join(' | ')+' |';
  const md=['# Token 用量报告','',line(head),line(head.map((_,i)=>i?'---:':'---')),...body.map(line),'','> 本地生成于 '+markdownCell(DATA.generated)+'，未上传任何数据。'].join('\n');
  downloadBlob(md,'text/markdown;charset=utf-8','tokens-'+state.gran+'.md');toast('Markdown 报告已生成');
}
document.getElementById('md-btn').addEventListener('click',exportMarkdown);
function openHelp(){const modal=document.getElementById('help-modal');openModal(modal,document.getElementById('help-close'));}
function closeHelp(){closeModal(document.getElementById('help-modal'));}
document.getElementById('help-close').addEventListener('click',closeHelp);document.getElementById('help-modal').addEventListener('click',e=>{if(e.target.id==='help-modal')closeHelp();});document.getElementById('help-modal').addEventListener('keydown',e=>trapModalFocus(e,e.currentTarget));
// 键盘：1/2/3 切粒度，T 切主题，E 导出 CSV，I 打开寻迹，? 查看帮助
function globalShortcutBlocked(event){return event.defaultPrevented||editableTarget(event.target)||!!activeModal()||document.getElementById('scrim').classList.contains('open');}
document.addEventListener('keydown',e=>{
  if(globalShortcutBlocked(e))return;
  if(e.key==='i'||e.key==='I'){e.preventDefault();openDataTrail(e.target);}
  else if(e.key==='1') setGran('day');
  else if(e.key==='2') setGran('week');
  else if(e.key==='3') setGran('month');
  else if(e.key==='t'||e.key==='T'){ const o=['auto','light','dark'],c=localStorage.getItem('tk-theme')||'auto'; applyTheme(o[(o.indexOf(c)+1)%3]); }
  else if(e.key==='e'||e.key==='E') exportCSV();
  else if(e.key==='?') openHelp();
});

document.addEventListener('keydown',e=>{
  if(e.key==='Alt'&&!signalState.exactHeld){signalState.exactHeld=true;syncExactness();renderSignalDock();}
  if((e.key==='c'||e.key==='C')&&!e.repeat&&!globalShortcutBlocked(e)){e.preventDefault();setCompareHeld(true);}
});
document.addEventListener('keyup',e=>{if(e.key==='Alt'){signalState.exactHeld=false;syncExactness();renderSignalDock();}if(e.key==='c'||e.key==='C')setCompareHeld(false);});
function clearHeldSignals(){if(signalState.exactHeld){signalState.exactHeld=false;syncExactness();}if(signalState.compareHeld)setCompareHeld(false);}
window.addEventListener('blur',()=>{clearHeldSignals();clearScrub('预览已清除');});document.addEventListener('visibilitychange',()=>{if(document.hidden){clearHeldSignals();clearScrub('预览已清除');}});

/* ---- 趣味 / 意想不到的交互 ---- */
function toast(msg, ms=2600){
  let t=document.getElementById('toast');
  if(!t){t=document.createElement('div');t.id='toast';t.setAttribute('role','status');t.setAttribute('aria-live','polite');t.setAttribute('aria-atomic','true');document.body.appendChild(t);}
  t.textContent=msg;t.classList.add('show');clearTimeout(t._t);
  t._t=setTimeout(()=>t.classList.remove('show'),ms);
}
function confetti(){
  if(motionDisabled())return;
  const cs=['#5b8def','#a78bfa','#f472b6','#14b8a6','#f59e0b','#7aa2f7'];
  for(let i=0;i<90;i++){
    const d=document.createElement('div');d.className='confetti';
    d.style.left=(Math.random()*100)+'vw';d.style.background=cs[i%cs.length];
    d.style.animationDelay=(Math.random()*.5)+'s';d.style.animationDuration=(1.6+Math.random()*1)+'s';
    document.body.appendChild(d);setTimeout(()=>d.remove(),2700);
  }
}
// Konami ↑↑↓↓←→←→BA
(function(){
  const SEQ=['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];
  let i=0;
  document.addEventListener('keydown',e=>{
    const k=e.key.length===1?e.key.toLowerCase():e.key;
    if(k===SEQ[i]){i++;if(i===SEQ.length){i=0;confetti();toast('🎉 Konami 触发！真·肝帝已觉醒');}}
    else i=(k===SEQ[0])?1:0;
  });
})();
// 点 Logo：随机吐槽/夸奖
document.getElementById('logo').addEventListener('click',()=>{
  const lg=document.getElementById('logo');lg.classList.remove('spin');void lg.offsetWidth;lg.classList.add('spin');
  const h=DATA.hourly||[];let ph=-1,pi=-1;for(let i=0;i<24;i++)if((h[i]||0)>ph){ph=h[i]||0;pi=i;}
  const top=(DATA.top_cwds&&DATA.top_cwds[0])?DATA.top_cwds[0][0]:'—';
  const calls=(DATA.day||[]).reduce((a,r)=>a+r.calls,0);
  const F=[
    '缓存读取量为 '+human(DATA.cache_read||0)+' token，代表复用体量而非已确认费用',
    '峰值在 '+(pi>=0?String(pi).padStart(2,'0')+':00':'?')+'，夜猫子实锤',
    human(lastTotal)+' token ≈ '+fmt(Math.max(0,Math.round(lastTotal/27000)))+' 篇毕业论文',
    '最肝的项目：'+top,
    '别肝了，站起来活动活动 🧘',
    '已累计 '+fmt(calls)+' 次调用，键盘冒烟了',
    '今日份的算力已燃烧 ✨'
  ];
  toast(F[Math.floor(Math.random()*F.length)]);
});
// Hero 总量保留稳定的紧凑表达；精确值通过复制按钮与 Exactness Key 暴露
document.getElementById('k-total-copy').addEventListener('click',e=>{e.stopPropagation();copyExactValue('总 Token',lastTotal);});

// Hero 跟手光斑
(function(){
  const el=document.querySelector('.kpi.is-primary');
  if(!el)return;
  el.addEventListener('mousemove',e=>{const r=el.getBoundingClientRect();el.style.setProperty('--mx',(e.clientX-r.left)+'px');el.style.setProperty('--my',(e.clientY-r.top)+'px');});
})();
// 趣味换算
const FUN=[
  ['一本《红楼梦》全文',1000000],['一部《三体》三部曲',1200000],['整部《哈利波特》',1300000],
  ['一部《指环王》三部曲',1700000],['一集美剧字幕',10000],['一首流行歌词',400],
  ['一篇本科毕业论文',27000],['一次深度对话',5000],['一行代码',8],['一条推文',30],
  ['小时人类高速打字',18000],['杯程序员续命美式',250000],['次完整阅读技术文档',45000],
  ['小时键盘持续敲击',12000],['个中型函数的代码量',1800]
];
function renderFunFacts(){
  const box=document.getElementById('funfacts'), t=lastTotal||0;
  if(t<=0){box.innerHTML='<div class="hint">无数据</div>';return;}
  let cands=FUN.map(([l,p])=>({l,p,n:t/p})).filter(x=>x.n>=0.3&&x.n<1e7).sort((a,b)=>b.n-a.n);
  for(let i=cands.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[cands[i],cands[j]]=[cands[j],cands[i]];}
  box.innerHTML=cands.slice(0,3).map(x=>{
    const num=x.n>=100?fmt(Math.round(x.n)):(x.n>=10?x.n.toFixed(1):x.n.toFixed(2));
    return '<div class=ff><span class=ff-n>'+num+'</span><span class=ff-l>'+x.l+'</span></div>';
  }).join('') || '<div class="hint">数据太少，肝得还不够</div>';
}
document.getElementById('fun-shuffle').addEventListener('click',renderFunFacts);

/* ---- 模块开关（附加功能可勾选 + 记忆）---- */
const MODS_KEY='tk-mods', MOD_DEFAULT={clock:true,fun:true,block:true,daily:true,rhythm:true,modes:true,fortune:true,multiples:true,provenance:true,project:true,reuse:true,flow:true,creature:true,race:true,almanac:true,badges:true,dna:true,top:true};
function loadMods(){ try{ const m=Object.assign({},JSON.parse(localStorage.getItem(MODS_KEY)||'{}'));let legacy;if(Object.prototype.hasOwnProperty.call(m,'orbit'))legacy=m.orbit;else if(Object.prototype.hasOwnProperty.call(m,'city'))legacy=m.city;if(!Object.prototype.hasOwnProperty.call(m,'flow')&&legacy!==undefined)m.flow=legacy;delete m.orbit;delete m.city;localStorage.setItem(MODS_KEY,JSON.stringify(m));return m; }catch(e){ return {}; } }
function applyMods(){
  const m=Object.assign({},MOD_DEFAULT,loadMods());
  document.querySelectorAll('[data-module]').forEach(el=>{const hidden=m[el.dataset.module]===false;el.style.display=hidden?'none':'';if(!hidden&&el.dataset.lazy&&typeof lazyState!=='undefined'){const name=el.dataset.lazy;lazyState[name]=Object.assign({},lazyState[name],{dirty:true});if(lazyState[name].visible||!('IntersectionObserver'in window))renderLazy(name,true);}});
  document.querySelectorAll('[data-sw]').forEach(sw=>{
    const on=m[sw.dataset.sw]!==false; sw.classList.toggle('on',on);
    const cb=document.querySelector('input[data-mod="'+sw.dataset.sw+'"]'); if(cb) cb.checked=on;
  });
}
document.getElementById('mods-btn').addEventListener('click',e=>{e.stopPropagation();const pop=document.getElementById('mods-pop'),open=!pop.classList.contains('open');pop.classList.toggle('open',open);e.currentTarget.setAttribute('aria-expanded',String(open));if(open)setTimeout(()=>pop.querySelector('input')?.focus(),0);});
document.addEventListener('click',e=>{if(!e.target.closest('#mods-pop')&&!e.target.closest('#mods-btn')){document.getElementById('mods-pop').classList.remove('open');document.getElementById('mods-btn').setAttribute('aria-expanded','false');}});
document.querySelectorAll('#mods-pop input[data-mod]').forEach(cb=>{
  cb.addEventListener('change',()=>{const k=cb.dataset.mod,m=Object.assign({},MOD_DEFAULT,loadMods());m[k]=cb.checked;try{localStorage.setItem(MODS_KEY,JSON.stringify(m));}catch(e){}applyMods();});
});

/* ---- 5h 计费窗口 ---- */
function renderBlock(){
  const b=DATA.block||{total:0,buckets:[]}, bars=document.getElementById('block-bars');
  document.getElementById('block-total').textContent=human(b.total)+' tk';
  const bk=b.buckets||[], max=Math.max(1,...bk.map(x=>x.total));
  bars.innerHTML=bk.map(x=>'<div class=bb style="height:'+Math.max(3,x.total/max*100).toFixed(1)+'%" title="'+String(x.h).padStart(2,'0')+':00 · '+human(x.total)+' tk"><span>'+String(x.h).padStart(2,'0')+'</span></div>').join('');
  document.getElementById('block-now').textContent='近 6 个小时桶（按生成时刻往前）';
}

function recentCalendarDays(count=14){
  const periods=(DATA.day||[]).map(d=>d.period).filter(Boolean).sort(),fallback=periods[periods.length-1],end=DATA.range?.until||String(DATA.generated||'').slice(0,10)||fallback;
  if(!end)return [];
  const p=end.split('-').map(Number),last=new Date(p[0],p[1]-1,p[2]),byPeriod=Object.fromEntries((DATA.day||[]).map(d=>[d.period,d]));
  return Array.from({length:count},(_,i)=>{const d=new Date(last);d.setDate(last.getDate()-(count-1-i));const period=localISO(d);return byPeriod[period]||{period,total:0,calls:0,models:{},model_calls:{},synthetic:true};});
}

/* ---- 每天（近 14 天）迷你柱条 ---- */
function renderDaily(){
  const box=document.getElementById('daily-bars'), days=recentCalendarDays();
  if(!days.length){ box.innerHTML='<div class="hint" style="width:100%">无数据</div>'; document.getElementById('daily-total').textContent=''; return; }
  const max=Math.max(1,...days.map(d=>d.total)), tot=days.reduce((a,d)=>a+d.total,0);
  document.getElementById('daily-total').textContent=human(tot)+' tk · '+days.length+' 天';
  box.innerHTML=days.map(d=>{
    const h=Math.max(3,d.total/max*100), dd=(d.period||'').split('-')[2]||'?';
    return '<div class=bb style="height:'+h.toFixed(1)+'%" title="'+esc(d.period)+' · '+human(d.total)+' tk（'+d.calls+' 次）"><span>'+dd+'</span></div>';
  }).join('');
}

function showRhythmTip(cell,e){
  const tip=document.getElementById('rhythm-tip'), v=Number(cell.dataset.value||0), share=cell.dataset.share||'0.0', h=Number(cell.dataset.hour||0);
  const part=h<5?'深夜':h<9?'清晨':h<12?'上午':h<14?'午间':h<18?'下午':h<22?'夜晚':'深夜';
  tip.innerHTML='<b>'+esc(cell.dataset.day)+' · '+String(h).padStart(2,'0')+':00–'+String((h+1)%24).padStart(2,'0')+':00</b><div><span class="rh-v">'+fmt(v)+'</span> Token</div><span>'+part+'时段 · 占当天 '+share+'% · 点击回看这一天</span>';
  tip.classList.add('on'); moveRhythmTip(e);
}
function moveRhythmTip(e){
  const tip=document.getElementById('rhythm-tip'), gap=14, w=tip.offsetWidth||190, h=tip.offsetHeight||70;
  let x=e.clientX+gap,y=e.clientY+gap;if(x+w>innerWidth-8)x=e.clientX-w-gap;if(y+h>innerHeight-8)y=e.clientY-h-gap;
  tip.style.left=x+'px';tip.style.top=y+'px';
}
function hideRhythmTip(){document.getElementById('rhythm-tip').classList.remove('on');}

function rhythmLevel(value,positiveValues){
  if(!value)return 0;
  const min=Math.min(...positiveValues),max=Math.max(...positiveValues);
  if(max<=min)return 4;
  return Math.min(4,Math.max(1,Math.ceil((value-min)/(max-min)*4)));
}

function activateRhythmCell(cell){
  if(!DATA.day.some(d=>d.period===cell.dataset.day)){toast(cell.dataset.day+' 无 Token 记录');return;}
  clearScrub();state.gran='day';state.focusPeriod=cell.dataset.day;trailState.step='scope';trailState.reached=0;trailState.model=null;trailState.branch=null;trailState.destination=null;invalidateDerived();hideRhythmTip();renderDataViews();
}
function focusRhythmCell(cells,index){const next=Math.max(0,Math.min(cells.length-1,index));cells.forEach((cell,i)=>cell.tabIndex=i===next?0:-1);cells[next].focus();}

function renderRhythm(){
  const box=document.getElementById('rhythm'), days=recentCalendarDays(), det=DATA.day_details||{};
  if(!days.length){box.innerHTML='<div class="hint">无数据</div>';document.getElementById('rhythm-persona').textContent='';return;}
  const matrix=days.map(d=>{ const x=det[d.period], out=Array(24).fill(0); if(x) Object.entries(x.hourly_models||{}).forEach(([m,h])=>{if(state.models.has(m))h.forEach((v,i)=>out[i]+=v||0);}); return out; });
  const vals=matrix.flat().filter(v=>v>0);let html='<div class="rhythm-grid"><div></div>'+days.map(d=>'<div class="rh-day">'+esc((d.period||'').slice(5).replace('-','/'))+'</div>').join('');
  const dayTotals=matrix.map(a=>a.reduce((x,y)=>x+y,0));
  for(let h=0;h<24;h++){html+='<div class="rh-hour">'+(h%3===0?String(h).padStart(2,'0'):'')+'</div>';for(let d=0;d<days.length;d++){const v=matrix[d][h],lv=rhythmLevel(v,vals),share=dayTotals[d]?v/dayTotals[d]*100:0,index=h*days.length+d;html+='<div class="rh-cell l'+lv+'" role=gridcell tabindex="'+(index===0?'0':'-1')+'" data-index="'+index+'" data-day="'+esc(days[d].period)+'" data-hour="'+h+'" data-value="'+v+'" data-share="'+share.toFixed(1)+'" aria-label="'+esc(days[d].period)+' '+String(h).padStart(2,'0')+':00，'+fmt(v)+' token"></div>';}}
  box.innerHTML='<div class="rhythm-grid" role=grid aria-label="最近 14 天每小时 Token 作息织锦">'+html.slice('<div class="rhythm-grid">'.length)+'</div>';
  const cells=[...box.querySelectorAll('.rh-cell')];
  cells.forEach((c,index)=>{
    c.addEventListener('click',()=>activateRhythmCell(c));
    c.addEventListener('mouseenter',e=>showRhythmTip(c,e));
    c.addEventListener('mousemove',moveRhythmTip);
    c.addEventListener('mouseleave',hideRhythmTip);
    c.addEventListener('focus',()=>{const r=c.getBoundingClientRect();showRhythmTip(c,{clientX:r.left+r.width/2,clientY:r.top+r.height/2});});
    c.addEventListener('blur',hideRhythmTip);
    c.addEventListener('keydown',e=>{let next=null;if(e.key==='ArrowLeft')next=index-1;else if(e.key==='ArrowRight')next=index+1;else if(e.key==='ArrowUp')next=index-days.length;else if(e.key==='ArrowDown')next=index+days.length;else if(e.key==='Home')next=index-index%days.length;else if(e.key==='End')next=index+(days.length-1-index%days.length);else if(e.key==='Enter'||e.key===' '){e.preventDefault();activateRhythmCell(c);return;}if(next!==null){e.preventDefault();focusRhythmCell(cells,next);}});
  });
  const hs=Array(24).fill(0);matrix.forEach(a=>a.forEach((v,i)=>hs[i]+=v));const total=hs.reduce((a,b)=>a+b,0),sum=(a,b)=>hs.slice(a,b).reduce((x,y)=>x+y,0);
  let p=['☀️','日间稳定型','算力主要沿着白昼平稳展开。'];
  if(total&&sum(0,6)+sum(22,24)>total*.42)p=['🌙','午夜航行型','你的高密度思考更常发生在城市熄灯以后。'];
  else if(total&&sum(5,10)>total*.38)p=['🌅','晨光启动型','大部分算力在清晨苏醒，像一台提前预热的机器。'];
  else if(total&&sum(17,22)>total*.4)p=['🌆','黄昏冲刺型','越接近夜幕，Token 越开始加速。'];
  else if(hs.filter(v=>v>0).length>=20)p=['🌐','全时域高能体','一天几乎没有真正的静默区。'];
  document.getElementById('rhythm-persona').innerHTML=p[0]+' <b>'+p[1]+'</b> · '+p[2];
}

const WORK_MODE_RULES=Object.freeze({minimumTokens:1000,cacheRatio:.35,exploreModels:3,exploreProjects:4,deepActiveHours:6,deepFourHourShare:.72,sprintMedianMultiple:1.8});
const WORK_MODE_META=Object.freeze({
  cache:{icon:'🌱',label:'缓存园丁',copy:'上下文复用在当天占据明显份额。'},
  explore:{icon:'🧭',label:'探索巡游',copy:'多个模型或项目共同参与了当天活动。'},
  deep:{icon:'🌊',label:'集中深潜',copy:'大部分 Token 集中在少数连续小时。'},
  sprint:{icon:'⚡',label:'高能冲刺',copy:'当天总量明显高于当前范围的典型活跃日。'},
  cruise:{icon:'🛶',label:'稳定巡航',copy:'活动达到可分析规模，但没有单一特征占据主导。'},
  insufficient:{icon:'·',label:'数据不足',copy:'当天 Token 未达到模式分类的最低样本量。'}
});
function workModeDailyRows(data,selectedModels,focus=null){
  const models=selectedModels instanceof Set?selectedModels:new Set(selectedModels||[]),details=data.day_details||{};
  return [...(data.day||[])].filter(row=>!focus||focus.has(row.period)).sort((a,b)=>a.period.localeCompare(b.period)).map(row=>{
    const detail=details[row.period]||{},modelValues={};let total=0,calls=0,cache=0;
    models.forEach(model=>{const value=(row.models||{})[model]||0;if(value){modelValues[model]=value;total+=value;}calls+=(row.model_calls||{})[model]||0;cache+=(detail.cache_read_models||{})[model]||0;});
    const hourly=Array(24).fill(0);Object.entries(detail.hourly_models||{}).forEach(([model,values])=>{if(models.has(model))values.forEach((value,hour)=>hourly[hour]+=value||0);});
    const activeHours=hourly.filter(value=>value>0).length,circularHours=hourly.concat(hourly.slice(0,3)),fourHourPeak=hourly.reduce((best,_,hour)=>Math.max(best,circularHours.slice(hour,hour+4).reduce((sum,value)=>sum+value,0)),0);
    let projectCount=0;(detail.cwds||detail.top_cwds||[]).forEach(project=>{const projectTotal=Object.entries(project[3]||{}).reduce((sum,[model,value])=>sum+(models.has(model)?value||0:0),0);if(projectTotal>0)projectCount++;});
    return {day:row.period,total,calls,cache,cacheRatio:total?cache/total:0,modelCount:Object.keys(modelValues).length,projectCount,activeHours,fourHourShare:total?fourHourPeak/total:0};
  });
}
function classifyWorkMode(row,median){
  const r=WORK_MODE_RULES;
  if(row.total<r.minimumTokens)return {key:'insufficient',evidence:'需要至少 '+fmt(r.minimumTokens)+' Token；当天为 '+fmt(row.total)+'。'};
  if(row.cacheRatio>=r.cacheRatio)return {key:'cache',evidence:'Cache Read 占 '+(row.cacheRatio*100).toFixed(1)+'%，达到 '+Math.round(r.cacheRatio*100)+'% 规则。'};
  if(row.modelCount>=r.exploreModels||row.projectCount>=r.exploreProjects)return {key:'explore',evidence:row.modelCount+' 个模型 · '+row.projectCount+' 个项目达到探索规则。'};
  if(row.activeHours>0&&row.activeHours<=r.deepActiveHours&&row.fourHourShare>=r.deepFourHourShare)return {key:'deep',evidence:'活跃 '+row.activeHours+' 小时，最集中 4 小时占 '+(row.fourHourShare*100).toFixed(1)+'%。'};
  if(median>0&&row.total>=median*r.sprintMedianMultiple)return {key:'sprint',evidence:fmt(row.total)+' Token，是活跃日中位数的 '+(row.total/median).toFixed(1)+'×。'};
  return {key:'cruise',evidence:'达到样本量，且缓存、探索、集中度与冲刺规则均未优先命中。'};
}
function deriveWorkModes(data,selectedModels,focus=null){
  const rows=workModeDailyRows(data,selectedModels,focus),active=rows.filter(row=>row.total>=WORK_MODE_RULES.minimumTokens).map(row=>row.total).sort((a,b)=>a-b),middle=Math.floor(active.length/2),median=active.length?(active.length%2?active[middle]:(active[middle-1]+active[middle])/2):0;
  return {median,rows:rows.map(row=>{const mode=classifyWorkMode(row,median);return {...row,...mode};})};
}
let workModeCursor=0;
function renderWorkModeDetail(rows,index){
  const detail=document.getElementById('mode-detail'),row=rows[index];if(!row){detail.innerHTML='';return;}
  const mode=WORK_MODE_META[row.key];detail.innerHTML='<div class="mode-detail-icon mode-'+row.key+'">'+mode.icon+'</div><div><span>'+esc(row.day)+'</span><h3>'+mode.label+'</h3><p>'+mode.copy+'</p><small>'+esc(row.evidence)+'</small><button class=mode-replay type=button>回看这一天</button></div><div class=mode-evidence><b>'+metric(row.total)+' tk</b><span>'+row.modelCount+' 个模型 · '+row.projectCount+' 个项目</span><span>Cache '+(row.cacheRatio*100).toFixed(1)+'% · '+row.activeHours+' 活跃小时</span></div>';
  detail.querySelector('.mode-replay').addEventListener('click',()=>focusMomentDay(row.day));
}
function focusWorkMode(items,index){const next=Math.max(0,Math.min(items.length-1,index));workModeCursor=next;items.forEach((item,i)=>{item.tabIndex=i===next?0:-1;item.setAttribute('aria-selected',String(i===next));item.classList.toggle('on',i===next);});items[next].focus();renderWorkModeDetail(items[0].__modeRows,next);}
function renderWorkModes(){
  const focus=focusDays(),derived=deriveWorkModes(DATA,state.models,focus),rows=derived.rows,classified=rows.filter(row=>row.key!=='insufficient'),summary=document.getElementById('mode-summary'),timeline=document.getElementById('mode-timeline');
  document.getElementById('mode-scope').textContent=focus?'当前时光探针':'当前模型筛选 · 全部日期';
  if(!state.models.size){summary.innerHTML='';timeline.innerHTML='';document.getElementById('mode-detail').innerHTML=contextEmptyHTML('modes');document.getElementById('mode-rules').textContent='';return;}
  if(!rows.length){summary.innerHTML='';timeline.innerHTML='';document.getElementById('mode-detail').innerHTML=contextEmptyHTML('rhythm');document.getElementById('mode-rules').textContent='';return;}
  const counts={};classified.forEach(row=>counts[row.key]=(counts[row.key]||0)+1);summary.innerHTML=Object.entries(counts).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).map(([key,count])=>'<div class="mode-summary-item mode-'+key+'"><i>'+WORK_MODE_META[key].icon+'</i><span><b>'+WORK_MODE_META[key].label+'</b><small>'+count+' 天 · '+(classified.length?count/classified.length*100:0).toFixed(1)+'%</small></span></div>').join('')||'<div class=mode-empty>当前日期均未达到 '+fmt(WORK_MODE_RULES.minimumTokens)+' Token 的分类样本量。</div>';
  workModeCursor=Math.max(0,Math.min(workModeCursor,rows.length-1));timeline.innerHTML=rows.map((row,index)=>{const mode=WORK_MODE_META[row.key];return '<button type=button class="mode-day mode-'+row.key+(index===workModeCursor?' on':'')+'" role=option aria-selected="'+String(index===workModeCursor)+'" tabindex="'+(index===workModeCursor?'0':'-1')+'" data-mode-index="'+index+'" aria-label="'+esc(row.day+'，'+mode.label+'，'+row.evidence)+'"><i>'+mode.icon+'</i><b>'+esc(row.day.slice(5))+'</b><span>'+mode.label+'</span></button>';}).join('');
  const items=[...timeline.querySelectorAll('.mode-day')];items.forEach(item=>{item.__modeRows=rows;item.addEventListener('click',()=>focusWorkMode(items,Number(item.dataset.modeIndex)));item.addEventListener('keydown',event=>{const index=Number(item.dataset.modeIndex);let next=null;if(event.key==='ArrowLeft'||event.key==='ArrowUp')next=index-1;else if(event.key==='ArrowRight'||event.key==='ArrowDown')next=index+1;else if(event.key==='Home')next=0;else if(event.key==='End')next=items.length-1;if(next!==null){event.preventDefault();focusWorkMode(items,next);}});});
  renderWorkModeDetail(rows,workModeCursor);document.getElementById('mode-rules').textContent='规则顺序：Cache Read ≥35% → ≥3 模型或 ≥4 项目 → ≤6 活跃小时且最集中 4 小时 ≥72% → ≥活跃日中位数 1.8× → 稳定巡航。最低样本量 1,000 Token；只描述使用形态。';
}

function emptyStateReason(kind){
  const p=DATA.provenance||{};if(!(p.records>0)||!DATA.models.length)return {title:'当前范围没有记录',detail:'调整日期范围或来源后重新生成报告。',action:'provenance'};
  if(!state.models.size)return {title:'没有选择模型',detail:'恢复模型后可重新计算当前视图。',action:'models'};
  if(state.focusPeriod&&!selectedRows().some(r=>r.total>0))return {title:'当前时光探针没有活动',detail:'退出回看后查看完整范围。',action:'focus'};
  const cap=capabilityInfo().find(x=>x.key===kind);if(cap&&cap.status==='off')return {title:'当前日志缺少所需字段',detail:capabilityReason(kind),action:'provenance'};
  return {title:'当前范围没有可显示数据',detail:'尝试调整日期范围、来源或模型筛选。',action:'provenance'};
}
function contextEmptyHTML(kind){const x=emptyStateReason(kind),label=x.action==='models'?'恢复全部模型':x.action==='focus'?'退出时光探针':'查看数据体检';return '<div class=context-empty><b>'+esc(x.title)+'</b><span>'+esc(x.detail)+'</span><button type=button data-empty-action="'+x.action+'">'+label+'</button></div>';}
function handleEmptyAction(action){if(action==='models')setModels(DATA.models,'已恢复全部模型');else if(action==='focus')clearFocus();else scrollToSection('section-provenance');}

function snapshotEndDate(){return DATA.range?.until||String(DATA.generated||'').slice(0,10)||(DATA.day||[]).map(d=>d.period).filter(Boolean).sort().slice(-1)[0]||null;}
function selectedDailyRows(){return (DATA.day||[]).map(row=>{const models={};let total=0;state.models.forEach(m=>{const value=row.models[m]||0;if(value){models[m]=value;total+=value;}});return {period:row.period,total,models};});}
function continuousCalendar(rows,end,count){if(!end)return [];const by=Object.fromEntries(rows.map(r=>[r.period,r])),p=end.split('-').map(Number),last=new Date(p[0],p[1]-1,p[2]);return Array.from({length:count},(_,i)=>{const d=new Date(last);d.setDate(last.getDate()-(count-1-i));const period=localISO(d);return by[period]||{period,total:0,models:{},synthetic:true};});}
function currentActiveStreak(rows,end){if(!end)return 0;const by=Object.fromEntries(rows.map(r=>[r.period,r.total||0])),p=end.split('-').map(Number),day=new Date(p[0],p[1]-1,p[2]);let streak=0;while(true){const period=localISO(day);if(!(by[period]>0))break;streak++;day.setDate(day.getDate()-1);}return streak;}
function activeStreakDays(rows,end){return currentActiveStreak(rows,end);}
function longestActiveStreak(rows){const active=new Set(rows.filter(r=>r.total>0).map(r=>r.period));let longest=0,current=0,previous=null;[...active].sort().forEach(period=>{const p=period.split('-').map(Number),day=new Date(p[0],p[1]-1,p[2]);if(previous){const next=new Date(previous);next.setDate(next.getDate()+1);current=localISO(next)===period?current+1:1;}else current=1;longest=Math.max(longest,current);previous=day;});return longest;}
function trailingQuietDays(rows,end){if(!state.models.size)return {kind:'no-observation',days:0};const observed=rows.filter(r=>r.total>0).sort((a,b)=>a.period.localeCompare(b.period));if(!observed.length||!end)return {kind:'no-observation',days:0};const latest=observed[observed.length-1].period;if(latest===end)return {kind:'active',days:0};const finish=new Date(end+'T00:00:00'),last=new Date(latest+'T00:00:00'),days=Math.max(0,Math.round((finish-last)/86400000));return days?{kind:'quiet',days}:{kind:'active',days:0};}
function latestMilestone(rows){const thresholds=[1e3,1e4,1e5,1e6,1e7,1e8,1e9,1e10,1e11,1e12];let total=0,latest=null;rows.forEach(r=>{const before=total;total+=r.total;const reached=thresholds.filter(value=>before<value&&total>=value).slice(-1)[0];if(reached)latest={day:r.period,value:reached,total};});return latest;}
function dominantModel(row){let best=null,bestValue=0,tied=false;DATA.models.forEach(m=>{if(!state.models.has(m))return;const value=row.models[m]||0;if(value>bestValue){best=m;bestValue=value;tied=false;}else if(value>0&&value===bestValue)tied=true;});return bestValue>0&&!tied?best:null;}
function latestModelRelay(rows){let previous=null,previousDay=null,latest=null;[...rows].sort((a,b)=>a.period.localeCompare(b.period)).forEach(row=>{const current=dominantModel(row),p=row.period.split('-').map(Number),day=new Date(p[0],p[1]-1,p[2]);let consecutive=false;if(previousDay){const next=new Date(previousDay);next.setDate(next.getDate()+1);consecutive=localISO(next)===row.period;}if(current&&previous&&consecutive&&previous!==current)latest={day:row.period,from:previous,to:current};previous=current;previousDay=day;if(!current){previous=null;previousDay=day;}});return latest;}
function projectFirstSeenInRange(projectId){let first=null;Object.entries(DATA.day_details||{}).sort((a,b)=>a[0].localeCompare(b[0])).forEach(([day,detail])=>{const row=(detail.cwds||detail.top_cwds||[]).find(x=>(x[2]||x[0])===projectId);if(!row)return;const total=Object.entries(row[3]||{}).reduce((sum,[m,v])=>sum+(state.models.has(m)?v||0:0),0);if(total>0&&!first)first={day,label:row[0]};});return first;}
function newestProjectMoment(){const seen={};Object.entries(DATA.day_details||{}).sort((a,b)=>a[0].localeCompare(b[0])).forEach(([day,detail])=>(detail.cwds||detail.top_cwds||[]).forEach(row=>{const id=row[2]||row[0],total=Object.entries(row[3]||{}).reduce((sum,[m,v])=>sum+(state.models.has(m)?v||0:0),0);if(total>0&&!seen[id])seen[id]={day,id,label:row[0]};}));return Object.values(seen).sort((a,b)=>b.day.localeCompare(a.day))[0]||null;}
function focusMomentDay(day){if(!day)return;clearScrub();state.gran='day';state.focusPeriod=day;trailState.step='scope';trailState.reached=0;trailState.model=null;trailState.branch=null;trailState.destination=null;invalidateDerived();renderDataViews();setTimeout(()=>{scrollToSection('section-trend');const marker=[...document.querySelectorAll('#bar .moment-marker')].find(x=>x.dataset.momentDay===day);if(marker){marker.classList.add('moment-active');marker.focus();setTimeout(()=>marker.classList.remove('moment-active'),900);return;}const el=[...document.querySelectorAll('#bar .barstack')].find(x=>x.dataset.period===day);if(el)el.focus();},0);}
function buildMomentEvents(){const rows=selectedDailyRows(),milestone=latestMilestone(rows),relay=latestModelRelay(rows),project=newestProjectMoment(),events=[];if(milestone)events.push({kind:'milestone',day:milestone.day,label:'达到 '+human(milestone.value),description:milestone.day+' 在本报告范围、当前模型筛选的累计中首次达到 '+human(milestone.value)+' Token。',icon:'◆'});if(project)events.push({kind:'project',day:project.day,label:'新观察项目 '+project.label,description:project.day+' 在本报告范围、当前模型筛选中首次观察到项目 '+project.label+'。',icon:'◇'});if(relay)events.push({kind:'relay',day:relay.day,label:pretty(relay.from)+' → '+pretty(relay.to),description:relay.day+' 与前一自然日连续，且每日唯一主力模型由 '+pretty(relay.from)+' 变为 '+pretty(relay.to)+'。',icon:'↗'});return events.sort((a,b)=>a.day.localeCompare(b.day)||a.kind.localeCompare(b.kind));}

const SOURCE_NOTES={claude:'Claude total 由 input、output、cache read/write 组成；通常保留 cwd 与 session。',gemini:'Gemini total 以日志报告值为准；通常有 session，但缺少 cwd。',codex:'Codex input 通常包含 cached input；当前记录通常缺少 cwd 与 session。'};
function coverageRatio(value,total){return total?value/total:0;}
function standardizedComponentCount(p){return p.with_components||0;}
function freshnessInfo(){const p=DATA.provenance||{},generated=String(DATA.generated||'').slice(0,10),last=p.last_day||'',explicit=DATA.range?.until;if(explicit)return {key:'range',label:'范围快照',detail:'报告固定到 '+explicit};if(!generated||!last)return {key:'stale',label:'日期未知',detail:'缺少可比较的日期范围'};const days=Math.max(0,Math.round((new Date(generated+'T00:00:00')-new Date(last+'T00:00:00'))/86400000));return days===0?{key:'fresh',label:'刚刚同步',detail:'最后数据日与生成日一致'}:days<=3?{key:'recent',label:'近期快照',detail:'最后数据距生成日 '+days+' 天'}:{key:'stale',label:'历史快照',detail:'最后数据距生成日 '+days+' 天'};}
function provenanceHealth(){const p=DATA.provenance||{},n=p.records||0,ts=coverageRatio(p.valid_ts,n),cwd=coverageRatio(p.with_cwd,n),session=coverageRatio(p.with_session,n),components=coverageRatio(standardizedComponentCount(p),n),fresh=freshnessInfo();if(!n)return {key:'base',label:'等待数据',detail:'当前范围没有可体检的已解析记录。'};if(ts>=.95&&cwd>=.7&&session>=.7&&components>=.9)return {key:'full',label:'实体分析较完整',detail:'在已解析记录中，时间、项目、会话和标准化 Token 组成字段可用性较高。'};if(ts>=.9&&(cwd>=.25||session>=.25))return {key:'trend',label:fresh.key==='stale'?'历史趋势':'趋势数据',detail:'适合趋势与部分实体分析；字段比例只描述已解析记录，不代表原始日志完整率。'};return {key:'base',label:'基础数据',detail:'主要适合总量、模型和来源趋势；字段比例只描述已解析记录。'};}
function capabilityInfo(){const p=DATA.provenance||{},n=p.records||1,ratio=k=>coverageRatio(p[k]||0,n),replay=coverageRatio(p.replay_retained||0,n),items=[
  {key:'project',label:'项目透镜',ratio:ratio('with_cwd'),target:'section-project',reason:'需要已解析记录包含 cwd 项目路径'},
  {key:'session',label:'会话回放',ratio:replay,target:'section-top',reason:'需要已解析记录可归属到 session，且逐轮值实际保留在回放序列中'},
  {key:'rhythm',label:'作息分析',ratio:ratio('valid_ts'),target:'section-rhythm',reason:'需要已解析记录含可解析时间戳'},
  {key:'reuse',label:'复用之河',ratio:coverageRatio(standardizedComponentCount(p),n),target:'section-reuse',reason:'需要标准化 input/output/cache read/cache write 组成字段可用'},
  {key:'flow',label:'流光关系',ratio:Math.max(ratio('with_cwd'),ratio('with_session')),target:'section-flow',reason:'需要已解析记录包含项目或会话 identity'},
];return items.map(x=>({...x,status:x.ratio>=.85?'ok':x.ratio>0?'partial':'off'}));}
function capabilityReason(key){const item=capabilityInfo().find(x=>x.key===key);if(!item)return '当前范围缺少所需数据。';const sources=Object.keys((DATA.provenance||{}).sources||{});return item.reason+(sources.length?'；当前来源：'+sources.join(' / '):'')+'。';}
function renderProvenance(){const p=DATA.provenance||{},n=p.records||0,health=provenanceHealth(),fresh=freshnessInfo(),percent=v=>coverageRatio(v,n)*100;
  document.getElementById('prov-stamp').innerHTML='<div><span>PARSED RECORD CHECK</span><b>'+health.label+'</b><small>'+fresh.label+'</small></div>';
  document.getElementById('prov-copy').innerHTML='<b>'+health.detail+'</b><br>'+fresh.detail+'。分母仅包含读取器已经接受并标准化的记录；被解析器拒绝的原始事件不在其中。本结论不代表原始日志绝对完整、准确，也不是隐私或安全保证。<span class=exact-inline> 精确语义：时间戳 '+fmt(p.valid_ts||0)+' / '+fmt(n)+'；项目 '+fmt(p.with_cwd||0)+' / '+fmt(n)+'；会话 '+fmt(p.with_session||0)+' / '+fmt(n)+'；标准化组成 '+fmt(standardizedComponentCount(p))+' / '+fmt(n)+'；回放保留 '+fmt(p.replay_retained||0)+' / 可归属 '+fmt(p.replay_eligible||0)+'。</span>';
  const meters=[['时间戳',p.valid_ts],['项目字段',p.with_cwd],['会话字段',p.with_session],['标准化组成字段',standardizedComponentCount(p)]];document.getElementById('prov-meters').innerHTML=meters.map(([label,value])=>{const pc=percent(value);return '<div class=prov-meter><div class=pm-head><span>'+label+'</span><b>'+pc.toFixed(1)+'%</b></div><div class=pm-track><i style="width:'+Math.min(100,pc).toFixed(1)+'%"></i></div><small>'+fmt(value||0)+' / '+fmt(n)+' 已解析记录</small></div>';}).join('')+'<div class=prov-meter><div class=pm-head><span>回放保留</span><b>'+fmt(p.replay_retained||0)+' / '+fmt(p.replay_eligible||0)+'</b></div><div class=pm-track><i style="width:'+Math.min(100,coverageRatio(p.replay_retained||0,p.replay_eligible||0)*100).toFixed(1)+'%"></i></div><small>每个会话最多保留最近 200 轮</small></div>';
  const sources=Object.entries(p.sources||{}).sort((a,b)=>b[1].total-a[1].total);document.getElementById('prov-sources').innerHTML=sources.map(([source,x])=>'<article class=prov-source><h3>'+esc(source)+'</h3><p>'+esc(SOURCE_NOTES[source]||'该来源按统一 record 进入趋势；具体字段能力取决于本地日志版本。')+'</p><div class=ps-meta><span>'+fmt(x.records)+' parsed records</span><span>'+human(x.total)+' tk</span><span>项目 '+(coverageRatio(x.with_cwd,x.records)*100).toFixed(0)+'%</span><span>会话 '+(coverageRatio(x.with_session,x.records)*100).toFixed(0)+'%</span></div></article>').join('');
  document.getElementById('prov-capabilities').innerHTML=capabilityInfo().map(x=>'<button type=button class="prov-cap '+x.status+'" data-cap="'+x.key+'" data-target="'+x.target+'" title="'+esc(capabilityReason(x.key))+'">'+(x.status==='ok'?'●':x.status==='partial'?'◐':'○')+' '+x.label+' · '+(x.ratio*100).toFixed(0)+'%</button>').join('');
  const beacon=document.getElementById('freshness-beacon');beacon.classList.toggle('stale',fresh.key==='stale');beacon.classList.toggle('range',fresh.key==='range');document.getElementById('freshness-text').textContent=fresh.label;beacon.title=fresh.detail+' · 点击查看数据可信度';}
function provenanceSummary(){const p=DATA.provenance||{},n=p.records||0,line=(label,value)=>label+'：'+fmt(value||0)+' / '+fmt(n)+'（'+(coverageRatio(value,n)*100).toFixed(1)+'%）';return ['tokens 已解析记录体检',provenanceHealth().label+' · '+freshnessInfo().label,'范围：'+(p.first_day||'—')+' ~ '+(p.last_day||'—'),'来源：'+Object.keys(p.sources||{}).join(' / '),'已解析 Records：'+fmt(n),'Token：'+fmt(p.total||0),line('时间戳',p.valid_ts),line('项目字段',p.with_cwd),line('会话字段',p.with_session),line('标准化组成字段',standardizedComponentCount(p)),'回放保留：'+fmt(p.replay_retained||0)+' / 可归属 '+fmt(p.replay_eligible||0)+'（每会话最多最近 200 轮）','说明：解析器拒绝的原始事件不在分母；不包含 cwd、session 或逐轮 Token 明细。'].join('\n');}

document.addEventListener('click',e=>{const b=e.target.closest('[data-empty-action]');if(b)handleEmptyAction(b.dataset.emptyAction);});

function projectPeriod(day,gran){
  if(gran==='day')return day;if(gran==='month')return day.slice(0,7)+'-01';
  const p=day.split('-').map(Number),d=new Date(p[0],p[1]-1,p[2]),offset=(d.getDay()+6)%7;d.setDate(d.getDate()-offset);return localISO(d);
}
function projectCatalog(){
  const fd=focusDays(),items={};
  Object.entries(DATA.day_details||{}).forEach(([day,detail])=>{if(fd&&!fd.has(day))return;(detail.cwds||detail.top_cwds||[]).forEach(row=>{const id=row[2]||row[0],item=items[id]||(items[id]={id,label:row[0],total:0});Object.entries(row[3]||{}).forEach(([m,v])=>{if(state.models.has(m))item.total+=v||0;});});});
  return Object.values(items).filter(x=>x.total>0).sort((a,b)=>b.total-a.total||a.label.localeCompare(b.label));
}
function projectRows(projectId){
  const fd=focusDays(),buckets={};
  Object.entries(DATA.day_details||{}).forEach(([day,detail])=>{if(fd&&!fd.has(day))return;const row=(detail.cwds||detail.top_cwds||[]).find(x=>(x[2]||x[0])===projectId);if(!row)return;const period=projectPeriod(day,state.gran),item=buckets[period]||(buckets[period]={period,total:0,models:{}});Object.entries(row[3]||{}).forEach(([m,v])=>{if(state.models.has(m)&&v){item.models[m]=(item.models[m]||0)+v;item.total+=v;}});});
  return Object.values(buckets).filter(x=>x.total>0).sort((a,b)=>a.period.localeCompare(b.period));
}
function renderProjectLens(){
  const select=document.getElementById('project-select'),catalog=projectCatalog();
  if(!catalog.length){selectedProject=null;select.innerHTML='<option>当前筛选下无项目</option>';select.disabled=true;select.removeAttribute('data-signal-type');select.removeAttribute('data-signal-id');select.removeAttribute('data-signal-label');select.removeAttribute('data-signal-value');select.removeAttribute('data-signal-scope');select.removeAttribute('data-signal-pin');document.getElementById('project-kpis').innerHTML='';document.getElementById('project-chart').innerHTML='';document.getElementById('project-panel').innerHTML=contextEmptyHTML('project');document.getElementById('project-thead').innerHTML='';document.getElementById('project-tbody').innerHTML='';return;}
  select.disabled=false;if(!selectedProject||!catalog.some(x=>x.id===selectedProject))selectedProject=catalog[0].id;
  select.innerHTML=catalog.map(x=>'<option value="'+esc(x.id)+'"'+(x.id===selectedProject?' selected':'')+'>'+esc(x.label)+' · '+human(x.total)+'</option>').join('');
  const chosen=catalog.find(x=>x.id===selectedProject),rows=projectRows(selectedProject),total=rows.reduce((a,r)=>a+r.total,0),overall=selectedRows().reduce((a,r)=>a+r.total,0),peak=rows.reduce((a,r)=>!a||r.total>a.total?r:a,null),mt={};rows.forEach(r=>Object.entries(r.models).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const dom=Object.entries(mt).sort((a,b)=>b[1]-a[1])[0];
  select.dataset.signalType='project';select.dataset.signalId=selectedProject;select.dataset.signalLabel=chosen?.label||selectedProject;select.dataset.signalValue=String(total);select.dataset.signalScope='project';select.removeAttribute('data-signal-pin');
  const firstSeen=projectFirstSeenInRange(selectedProject);document.getElementById('project-kpis').innerHTML=[['项目 Token',human(total)],['当前占比',pct(total,overall)],['活跃期',rows.length],['峰值期',peak?fmtLabel(peak.period,state.gran):'—'],['范围内首次观察',firstSeen?firstSeen.day:'—'],['主力模型',dom?pretty(dom[0]):'—']].map((x,index)=>'<div><b>'+esc(x[1])+(index===0?' <button class="k-copy project-copy" type=button aria-label="复制项目 Token 精确值">⧉</button>':'')+'</b>'+x[0]+'</div>').join('');
  const svg=document.getElementById('project-chart'),W=1080,H=280,pad=38,plotH=190,max=Math.max(1,...rows.map(r=>r.total)),step=(W-pad*2)/Math.max(1,rows.length),parts=[];for(let g=0;g<=3;g++){const y=24+plotH*g/3;parts.push('<line class="project-grid" x1="'+pad+'" y1="'+y+'" x2="'+(W-pad)+'" y2="'+y+'"/>');}
  rows.forEach((r,i)=>{const x=pad+i*step+step*.16,w=Math.max(3,step*.68);let y=24+plotH;Object.entries(r.models).sort((a,b)=>b[1]-a[1]).forEach(([m,v])=>{const h=v/max*plotH;y-=h;parts.push('<rect class="project-bar model-mark" data-model="'+esc(m)+'"'+dataSignalAttrs('model',m,pretty(m),v,'project',false)+' x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+w.toFixed(1)+'" height="'+Math.max(.5,h).toFixed(1)+'" fill="'+DATA.colors[m]+'"><title>'+esc(pretty(m))+' · '+fmt(v)+' Token</title></rect>');});parts.push('<rect class="project-hit" data-i="'+i+'" tabindex="'+(i===rows.length-1?'0':'-1')+'" role="button" aria-label="'+esc(fmtLabel(r.period,state.gran))+'，'+fmt(r.total)+' Token" x="'+(pad+i*step).toFixed(1)+'" y="20" width="'+step.toFixed(1)+'" height="'+(plotH+12)+'"/>');if(rows.length<=16||i%Math.ceil(rows.length/12)===0)parts.push('<text class="reuse-label" x="'+(x+w/2).toFixed(1)+'" y="242" text-anchor="middle">'+esc(fmtLabel(r.period,state.gran))+'</text>');});svg.innerHTML=parts.join('');
  const panel=document.getElementById('project-panel'),hits=[...svg.querySelectorAll('.project-hit')],inspect=i=>{const r=rows[i];if(!r)return;hits.forEach((h,j)=>h.tabIndex=j===i?0:-1);const mix=Object.entries(r.models).sort((a,b)=>b[1]-a[1]).map(([m,v])=>pretty(m)+' '+human(v)).join(' · ');panel.textContent=fmtLabel(r.period,state.gran)+' · '+human(r.total)+' tk'+(mix?' · '+mix:'');};hits.forEach((hit,i)=>{hit.addEventListener('pointerenter',()=>inspect(i));hit.addEventListener('focus',()=>inspect(i));hit.addEventListener('click',()=>inspect(i));hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const n=Math.max(0,Math.min(hits.length-1,i+(e.key==='ArrowRight'?1:-1)));inspect(n);hits[n].focus();}});});if(rows.length)inspect(rows.length-1);
  const models=DATA.models.filter(m=>rows.some(r=>r.models[m]));document.getElementById('project-thead').innerHTML='<tr><th>'+LABEL[state.gran]+'</th><th class=num>总 Token</th>'+models.map(m=>'<th class=num>'+esc(pretty(m))+'</th>').join('')+'</tr>';document.getElementById('project-tbody').innerHTML=rows.map(r=>'<tr><td>'+esc(fmtLabel(r.period,state.gran))+'</td><td class=num>'+fmt(r.total)+'</td>'+models.map(m=>'<td class=num>'+fmt(r.models[m]||0)+'</td>').join('')+'</tr>').join('');
  document.querySelector('#project-kpis .project-copy')?.addEventListener('click',()=>copyExactValue('项目 Token',total));
  select.title=chosen?chosen.id:'';
}
document.getElementById('project-select').addEventListener('change',e=>{selectedProject=e.target.value;renderProjectLens();document.activeElement===e.target?setSignalPeek(signalFromElement(e.target),e.target):applySignalLens();});

function currentFlow(){
  const fd=focusDays(),pm={},ms={};
  (fd||Object.keys(DATA.day_details||{})).forEach(day=>{const f=DATA.day_details[day]?.flow;if(!f)return;(f.project_model||[]).forEach(x=>{if(!state.models.has(x[2]))return;const k=x[1]+'::'+x[2],v=pm[k]||[x[0],x[1],x[2],0];v[3]+=x[3]||0;pm[k]=v;});(f.model_session||[]).forEach(x=>{if(!state.models.has(x[0]))return;const k=x[0]+'::'+x[2],v=ms[k]||[x[0],x[1],x[2],0];v[3]+=x[3]||0;ms[k]=v;});});
  return {project_model:Object.values(pm),model_session:Object.values(ms)};
}
function selectedReuseRows(){
  const rows=(DATA.reuse||{})[state.gran]||[];
  return rows.map(([period,byModel])=>{const parts=[0,0,0,0,0];Object.entries(byModel||{}).forEach(([m,v])=>{if(state.models.has(m))v.forEach((n,i)=>parts[i]+=n||0);});return [period,...parts];});
}
function renderReuseRiver(){
  const rows=selectedReuseRows(),svg=document.getElementById('reuse-chart'),panel=document.getElementById('reuse-panel'),selectedTotal=rows.reduce((a,r)=>a+r.slice(1).reduce((x,y)=>x+(y||0),0),0);
  if(!rows.length||!selectedTotal){svg.innerHTML='';document.getElementById('reuse-summary').textContent='0 Token';panel.innerHTML=contextEmptyHTML('reuse');return;}
  let data=state.focusPeriod?rows.filter(r=>r[0]===state.focusPeriod):rows;if(data.length===1)data=[data[0],data[0]];
  const W=1080,H=300,pad=34,plotW=W-pad*2,plotH=H-60,series=[1,2,3,4,5],colors=['#5b8def','#f472b6','#14b8a6','#a78bfa','#94a3b8'],labels=['Fresh Input','Output','Cache Read','Cache Write','Other'];
  const totals=data.map(r=>series.reduce((a,i)=>a+(r[i]||0),0)),max=Math.max(1,...totals),step=plotW/Math.max(1,data.length-1);let lower=Array(data.length).fill(0),parts=['<defs>'];colors.forEach((c,i)=>parts.push('<linearGradient id="reuse-g-'+i+'" x1="0" y1="0" x2="0" y2="1"><stop stop-color="'+c+'" stop-opacity=".72"/><stop offset="1" stop-color="'+c+'" stop-opacity=".16"/></linearGradient>'));parts.push('</defs>');
  for(let g=0;g<=3;g++){const y=24+plotH*g/3;parts.push('<line class="reuse-grid" x1="'+pad+'" y1="'+y+'" x2="'+(W-pad)+'" y2="'+y+'"/>');}
  series.forEach((idx,si)=>{const upper=data.map((r,i)=>lower[i]+(r[idx]||0)),top=upper.map((v,i)=>(pad+i*step).toFixed(1)+','+(24+plotH-v/max*plotH).toFixed(1)),bottom=lower.map((v,i)=>(pad+i*step).toFixed(1)+','+(24+plotH-v/max*plotH).toFixed(1)).reverse(),d='M'+top.join(' L')+' L'+bottom.join(' L')+' Z';parts.push('<path class="reuse-area" d="'+d+'" fill="url(#reuse-g-'+si+')" opacity=".86"><title>'+labels[si]+'</title></path>');lower=upper;});
  const original=state.focusPeriod?rows.filter(r=>r[0]===state.focusPeriod):rows,hitW=plotW/Math.max(1,original.length);original.forEach((r,i)=>parts.push('<rect class="reuse-hit" data-i="'+i+'" tabindex="'+(i===original.length-1?'0':'-1')+'" role="button" aria-label="'+esc(fmtLabel(r[0],state.gran))+' Token 构成" x="'+(pad+i*hitW).toFixed(1)+'" y="20" width="'+Math.max(.5,hitW).toFixed(1)+'" height="'+(plotH+12)+'"/>'));
  parts.push('<line class="reuse-cursor" id="reuse-cursor" x1="-1" y1="20" x2="-1" y2="'+(24+plotH)+'"/>');svg.innerHTML=parts.join('');
  const totalAll=original.reduce((a,r)=>a+series.reduce((s,i)=>s+(r[i]||0),0),0),cacheAll=original.reduce((a,r)=>a+(r[3]||0),0);document.getElementById('reuse-summary').textContent='缓存复用 '+pct(cacheAll,totalAll);
  const hits=[...svg.querySelectorAll('.reuse-hit')],pointStep=plotW/Math.max(1,original.length-1),inspect=i=>{const r=original[i];if(!r)return;hits.forEach((h,j)=>h.setAttribute('tabindex',j===i?'0':'-1'));const x=original.length===1?pad+plotW/2:pad+i*pointStep,c=document.getElementById('reuse-cursor');c.setAttribute('x1',x);c.setAttribute('x2',x);panel.textContent=fmtLabel(r[0],state.gran)+' · Fresh '+human(r[1])+' · Output '+human(r[2])+' · Read '+human(r[3])+' · Write '+human(r[4])+' · Other '+human(r[5]);};
  hits.forEach((hit,i)=>{hit.addEventListener('pointerenter',()=>inspect(i));hit.addEventListener('click',()=>inspect(i));hit.addEventListener('focus',()=>inspect(i));hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const next=Math.max(0,Math.min(hits.length-1,i+(e.key==='ArrowRight'?1:-1)));inspect(next);hits[next].focus();}});});if(original.length)inspect(original.length-1);
}


function renderFlow(){
  const svg=document.getElementById('flow-map'),raw=currentFlow(),selectedTotal=selectedRows().reduce((a,r)=>a+r.total,0);
  const pm=(raw.project_model||[]).filter(x=>state.models.has(x[2])&&x[3]>0),ms=(raw.model_session||[]).filter(x=>state.models.has(x[0])&&x[3]>0);
  const sumBy=(arr,key,val)=>{const o={};arr.forEach(x=>o[x[key]]=(o[x[key]]||0)+(x[val]||0));return o;};
  const pmModels=sumBy(pm,2,3),msModels=sumBy(ms,0,3),allModels=new Set([...Object.keys(pmModels),...Object.keys(msModels)]),mt={};allModels.forEach(m=>mt[m]=Math.max(pmModels[m]||0,msModels[m]||0));
  const modelIds=Object.keys(mt).filter(m=>state.models.has(m)).sort((a,b)=>(mt[b]||0)-(mt[a]||0)).slice(0,7),modelSet=new Set(modelIds),modelPM=pm.filter(x=>modelSet.has(x[2])),modelMS=ms.filter(x=>modelSet.has(x[0])),pt=sumBy(modelPM,1,3),st=sumBy(modelMS,2,3);
  const projectIds=Object.keys(pt).sort((a,b)=>pt[b]-pt[a]).slice(0,7),sessionIds=Object.keys(st).sort((a,b)=>st[b]-st[a]).slice(0,8),projectSet=new Set(projectIds),sessionSet=new Set(sessionIds),linksPM=modelPM.filter(x=>projectSet.has(x[1])),linksMS=modelMS.filter(x=>sessionSet.has(x[2]));
  if(!linksPM.length&&!linksMS.length){svg.innerHTML='';document.getElementById('flow-stats').innerHTML='<span>0 条流光链路</span>';document.getElementById('flow-panel').innerHTML=contextEmptyHTML('flow');return;}
  const W=1120,H=470,xpos={project:130,model:560,session:990},layout=(ids,totals,type)=>{const gap=(H-90)/Math.max(1,ids.length),out={};ids.forEach((id,i)=>out[id]={x:xpos[type],y:55+gap*(i+.5),total:totals[id]||0});return out;},P=layout(projectIds,pt,'project'),M=layout(modelIds,mt,'model'),S=layout(sessionIds,st,'session'),maxLink=Math.max(1,...linksPM.map(x=>x[3]),...linksMS.map(x=>x[3]));
  const sessionLabels={};ms.forEach(x=>sessionLabels[x[2]]=x[1]);const projectLabels={};pm.forEach(x=>projectLabels[x[1]]=x[0]);
  let p=['<defs>'];modelIds.forEach((m,i)=>{const c=DATA.colors[m]||'#7aa2f7';p.push('<linearGradient id="flow-g-'+i+'" x1="0" x2="1"><stop stop-color="'+c+'" stop-opacity=".25"/><stop offset=".5" stop-color="'+c+'"/><stop offset="1" stop-color="'+c+'" stop-opacity=".35"/></linearGradient>');});p.push('</defs><text class="flow-col" x="55" y="28">PROJECT</text><text class="flow-col" x="520" y="28">MODEL</text><text class="flow-col" x="942" y="28">SESSION</text>');
  const path=(a,b)=>'M '+a.x+' '+a.y+' C '+(a.x+150)+' '+a.y+' '+(b.x-150)+' '+b.y+' '+b.x+' '+b.y;
  linksPM.forEach(x=>{const mi=modelIds.indexOf(x[2]),w=2+Math.sqrt(x[3]/maxLink)*17;p.push('<path class="flow-link motion" data-flow-from="project:'+esc(x[1])+'" data-flow-model="'+esc(x[2])+'" d="'+path(P[x[1]],M[x[2]])+'" stroke="url(#flow-g-'+mi+')" stroke-width="'+w.toFixed(1)+'"><title>'+esc(x[0])+' → '+esc(pretty(x[2]))+' · '+fmt(x[3])+' Token</title></path>');});
  linksMS.forEach(x=>{const mi=modelIds.indexOf(x[0]),w=2+Math.sqrt(x[3]/maxLink)*17;p.push('<path class="flow-link motion" data-flow-model="'+esc(x[0])+'" data-flow-to="session:'+esc(x[2])+'" d="'+path(M[x[0]],S[x[2]])+'" stroke="url(#flow-g-'+mi+')" stroke-width="'+w.toFixed(1)+'"><title>'+esc(pretty(x[0]))+' → '+esc(x[1])+' · '+fmt(x[3])+' Token</title></path>');});
  const node=(type,id,pos,label,total,color)=>{const share=Math.min(100,selectedTotal?total/selectedTotal*100:0),boxX=pos.x-80,boxY=pos.y-20;return '<g class="flow-node '+type+'" data-flow-type="'+type+'" data-flow-id="'+esc(id)+'" data-flow-name="'+esc(label)+'" data-flow-total="'+total+'" data-flow-share="'+share.toFixed(2)+'"'+dataSignalAttrs(type,id,label,total,'flow')+' tabindex="0" role="button" aria-label="'+(type==='project'?'项目 ':type==='model'?'模型 ':'会话 ')+esc(label)+'，'+fmt(total)+' Token，占比 '+share.toFixed(1)+'%"><rect class="flow-hit" x="'+(boxX-6)+'" y="'+(boxY-4)+'" width="172" height="48" rx="12"/><rect class="flow-box" x="'+boxX+'" y="'+boxY+'" width="160" height="40" rx="10" fill="'+color+'" fill-opacity=".22"/><text x="'+pos.x+'" y="'+(pos.y-2)+'" text-anchor="middle">'+esc(label.length>20?label.slice(0,19)+'…':label)+'</text><text class="flow-value" x="'+pos.x+'" y="'+(pos.y+13)+'" text-anchor="middle">'+human(total)+' tk</text><title>悬停 Peek · 点击 Pin 信号</title></g>';};
  projectIds.forEach((id,i)=>p.push(node('project',id,P[id],projectLabels[id]||id,pt[id],['#5b8def','#14b8a6','#a78bfa','#38bdf8'][i%4])));modelIds.forEach(m=>p.push(node('model',m,M[m],pretty(m),mt[m],DATA.colors[m]||'#7aa2f7')));sessionIds.forEach((id,i)=>p.push(node('session',id,S[id],sessionLabels[id]||id,st[id],['#f472b6','#f59e0b','#a78bfa','#38bdf8'][i%4])));
  svg.innerHTML=p.join('');document.getElementById('flow-stats').innerHTML='<span>'+projectIds.length+' 个项目</span><span>'+modelIds.length+' 个模型</span><span>'+sessionIds.length+' 个会话</span><span>'+(linksPM.length+linksMS.length)+' 条真实流向</span>';
  const nodes=[...svg.querySelectorAll('.flow-node')];
  nodes.forEach(node=>{node.addEventListener('pointerenter',()=>showFlowPanel({type:node.dataset.flowType,id:node.dataset.flowId,name:node.dataset.flowName,total:Number(node.dataset.flowTotal),share:Number(node.dataset.flowShare)}));node.addEventListener('focus',()=>showFlowPanel({type:node.dataset.flowType,id:node.dataset.flowId,name:node.dataset.flowName,total:Number(node.dataset.flowTotal),share:Number(node.dataset.flowShare)}));node.addEventListener('pointerleave',()=>{if(!signalState.pinnedSignal)showFlowPanel(null);});node.addEventListener('blur',()=>{if(!signalState.pinnedSignal)showFlowPanel(null);});});showFlowPanel(signalState.pinnedSignal&&['project','model','session'].includes(signalState.pinnedSignal.type)?{type:signalState.pinnedSignal.type,id:signalState.pinnedSignal.id,name:signalState.pinnedSignal.label,total:signalState.pinnedSignal.value||0,share:selectedTotal?(signalState.pinnedSignal.value||0)/selectedTotal*100:0}:null);
}
function showFlowPanel(d){const panel=document.getElementById('flow-panel');if(!d){panel.innerHTML='<b>Token 流光图</b><span>① 悬停或聚焦 Peek　② 点击 Pin 到 Signal Dock　③ 在信号坞中选择深入动作</span>';return;}const type=d.type==='project'?'项目':d.type==='model'?'模型':'会话';panel.innerHTML='<b>'+type+' · '+esc(d.name)+'</b><span>'+fmt(d.total)+' Token · 占当前筛选总量 '+d.share.toFixed(1)+'% · 点击 Pin 到 Signal Dock</span>';}
function saveFlowSVG(){const source=document.getElementById('flow-map');if(!source.querySelector('.flow-node')){toast('当前筛选没有可导出的流向');return;}const svg=source.cloneNode(true);svg.setAttribute('xmlns','http://www.w3.org/2000/svg');svg.setAttribute('width','1120');svg.setAttribute('height','470');const bg=document.createElementNS('http://www.w3.org/2000/svg','rect');bg.setAttribute('width','1120');bg.setAttribute('height','470');bg.setAttribute('fill','#0b1120');svg.insertBefore(bg,svg.firstChild);const style=document.createElementNS('http://www.w3.org/2000/svg','style');style.textContent='.flow-col{fill:#8fa3c0;font:800 10px sans-serif;letter-spacing:.14em}.flow-link{fill:none;stroke-linecap:round;opacity:.58}.flow-box{stroke:rgba(255,255,255,.7);stroke-width:1}.flow-node text{fill:#e1ecfb;font:700 10px sans-serif}.flow-node .flow-value{fill:#9badc7;font:600 8.5px sans-serif}.flow-hit{display:none}';svg.insertBefore(style,bg.nextSibling);const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['<?xml version="1.0"?>\n'+svg.outerHTML],{type:'image/svg+xml'}));a.download='token-flow-'+state.gran+(state.focusPeriod?'-'+state.focusPeriod:'')+'.svg';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);toast('当前流光图已保存为 SVG');}
document.getElementById('flow-save').addEventListener('click',saveFlowSVG);

const CREATURE_PREFS_KEY='tk-creature-v1';
const CREATURE_SPECIES=Object.freeze(['auto','wolf','fox','cat','rabbit','dragon']);
const CREATURE_DEFAULT_COLORS=Object.freeze({primary:'#6f8fc9',secondary:'#d8e6ff',accent:'#7dd3c7'});
const CREATURE_SPECIES_META=Object.freeze({
  wolf:{label:'狼',title:'星轨狼'},fox:{label:'狐狸',title:'流光狐'},cat:{label:'猫',title:'缓存猫'},rabbit:{label:'兔',title:'月跃兔'},dragon:{label:'龙',title:'晶角龙'}
});
let creatureReferenceURL=null;
function validCreatureColor(value){return typeof value==='string'&&/^#[0-9a-f]{6}$/i.test(value);}
function normalizeCreaturePrefs(value){
  const source=value&&typeof value==='object'?value:{};
  return {
    species:CREATURE_SPECIES.includes(source.species)?source.species:'auto',
    primary:validCreatureColor(source.primary)?source.primary:null,
    secondary:validCreatureColor(source.secondary)?source.secondary:null,
    accent:validCreatureColor(source.accent)?source.accent:null
  };
}
function loadCreaturePrefs(){try{return normalizeCreaturePrefs(JSON.parse(localStorage.getItem(CREATURE_PREFS_KEY)||'{}'));}catch(e){return normalizeCreaturePrefs({});}}
function saveCreaturePrefs(prefs){const clean=normalizeCreaturePrefs(prefs);try{localStorage.setItem(CREATURE_PREFS_KEY,JSON.stringify(clean));}catch(e){}return clean;}
function creatureMetrics(data=DATA){
  const days=data.day||[],total=days.reduce((sum,row)=>sum+(row.total||0),0),hourly=data.hourly||[],hourlyTotal=hourly.reduce((sum,value)=>sum+(value||0),0),night=(hourly.slice(0,6).reduce((a,b)=>a+(b||0),0)+hourly.slice(22).reduce((a,b)=>a+(b||0),0))/(hourlyTotal||1),cache=total?(data.cache_read||0)/total:0;
  return {total,night,cache,models:Math.max(1,(data.models||[]).length),projects:Math.max(1,data.n_cwds||1),streak:Math.min(40,days.filter(row=>(row.total||0)>0).length),stage:total>=1e9?5:total>=1e8?4:total>=1e7?3:total>=1e6?2:1};
}
function defaultCreatureSpecies(metrics){const score=(Math.floor(metrics.total||0)+(metrics.models||0)*17+(metrics.projects||0)*31+Math.round((metrics.night||0)*100)+Math.round((metrics.cache||0)*100))%5;return ['wolf','fox','cat','rabbit','dragon'][score];}
function hslCreatureColor(hue,saturation,lightness){const s=saturation/100,l=lightness/100,c=(1-Math.abs(2*l-1))*s,x=c*(1-Math.abs((hue/60)%2-1)),m=l-c/2;let r=0,g=0,b=0;if(hue<60){r=c;g=x;}else if(hue<120){r=x;g=c;}else if(hue<180){g=c;b=x;}else if(hue<240){g=x;b=c;}else if(hue<300){r=x;b=c;}else{r=c;b=x;}return '#'+[r,g,b].map(value=>Math.round((value+m)*255).toString(16).padStart(2,'0')).join('');}
function creatureDataPalette(metrics,species='wolf'){
  const palettes={
    wolf:['#7189c7','#eef2ff','#79d6c4'],
    fox:['#d87968','#fff0df','#75d2bd'],
    cat:['#8878c5','#f6eeff','#efa8c5'],
    rabbit:['#9b8fd3','#fff1f5','#78cec7'],
    dragon:['#527f91','#e7f4ee','#efb567']
  },base=palettes[species]||palettes.wolf,shift=((Math.floor(metrics.total||0)+(metrics.models||0)*13)%9-4)/100;
  return {primary:creatureTone(base[0],shift),secondary:creatureTone(base[1],shift/2),accent:creatureTone(base[2],shift)};
}function creaturePaletteFromPixels(pixels){
  const bins=new Map();
  for(let index=0;index+3<pixels.length;index+=4){const r=pixels[index],g=pixels[index+1],b=pixels[index+2],a=pixels[index+3];if(a<128)continue;const light=(Math.max(r,g,b)+Math.min(r,g,b))/2;if(light<18||light>242)continue;const key=((r>>5)<<6)|((g>>5)<<3)|(b>>5),item=bins.get(key)||{count:0,r:0,g:0,b:0};item.count++;item.r+=r;item.g+=g;item.b+=b;bins.set(key,item);}
  const candidates=[...bins.values()].sort((a,b)=>b.count-a.count).map(item=>({count:item.count,r:Math.round(item.r/item.count),g:Math.round(item.g/item.count),b:Math.round(item.b/item.count)}));
  const chosen=[];for(const color of candidates){if(chosen.every(existing=>Math.hypot(color.r-existing.r,color.g-existing.g,color.b-existing.b)>=72))chosen.push(color);if(chosen.length===3)break;}
  for(const color of candidates){if(chosen.length===3)break;if(!chosen.includes(color))chosen.push(color);}
  const hex=color=>'#'+[color.r,color.g,color.b].map(value=>value.toString(16).padStart(2,'0')).join(''),shade=(color,factor)=>hex({r:Math.max(0,Math.min(255,Math.round(color.r*factor))),g:Math.max(0,Math.min(255,Math.round(color.g*factor))),b:Math.max(0,Math.min(255,Math.round(color.b*factor)))});if(!chosen.length)return [];if(chosen.length===1)return [hex(chosen[0]),shade(chosen[0],1.38),shade(chosen[0],.68)];if(chosen.length===2)chosen.push({r:Math.round((chosen[0].r+chosen[1].r)/2),g:Math.round((chosen[0].g+chosen[1].g)/2),b:Math.round((chosen[0].b+chosen[1].b)/2)});return chosen.slice(0,3).map(hex);
}
function creatureTone(hex,amount){const value=parseInt(hex.slice(1),16),target=amount<0?0:255,weight=Math.abs(amount),channel=shift=>Math.round(((value>>shift)&255)*(1-weight)+target*weight);return '#'+[16,8,0].map(shift=>channel(shift).toString(16).padStart(2,'0')).join('');}
function creatureSpeciesParts(species,colors){
  const {primary,secondary,accent,outline,shadow}=colors;
  const parts={
    wolf:{
      head:'M91 194Q91 107 177 91q82 12 91 91l-3 65-20 39-24 15-18 28-30-13-31 13-17-27-27-16-22-39Z',
      back:'<g class="creature-ear"><path d="M104 139 93 38l70 66Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round"/><path d="m113 112-9-52 39 48Z" fill="'+accent+'" opacity=".65"/></g><g class="creature-ear"><path d="m218 104 68-65-19 109Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round"/><path d="m237 109 36-48-10 58Z" fill="'+accent+'" opacity=".65"/></g>',
      tail:'<path d="M286 363q61-53 41-116-8 50-55 51 33 12 14 65Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5"/><path d="M315 274q17-13 13-34-12 23-34 26Z" fill="'+secondary+'"/>',
      marks:'<path d="m112 187 29-24 13 31-30 8Zm137-2-25-24-13 31 28 9Z" fill="'+shadow+'" opacity=".48"/>'
    },
    fox:{
      head:'M87 185Q91 103 178 91q86 11 93 91l-8 62-18 31-22 13-18 36-31-12-30 14-18-34-28-14-21-39Z',
      back:'<g class="creature-ear"><path d="M105 139 87 24l80 79Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round"/><path d="m111 108-11-58 46 55Z" fill="'+secondary+'"/></g><g class="creature-ear"><path d="m216 102 82-77-31 121Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round"/><path d="m239 107 44-57-18 68Z" fill="'+secondary+'"/></g>',
      tail:'<path d="M272 371q83 12 72-71-6-47-52-54 30 29 10 58-12 18-42 19Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5"/><path d="M324 339q28-19 18-54-8 31-41 37Z" fill="'+secondary+'"/>',
      marks:'<path d="M104 190q27-34 53-34l-18 61-31 16Zm149-1q-25-34-50-34l15 60 31 16Z" fill="'+secondary+'" opacity=".92"/>'
    },
    cat:{
      head:'M92 191Q94 108 178 94q81 12 88 88l-1 65-19 36-30 15-14 27-27-12-28 12-15-27-28-15-18-38Z',
      back:'<g class="creature-ear"><path d="M107 137 102 48l62 57Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round"/><path d="m117 112-4-42 34 37Z" fill="'+accent+'" opacity=".65"/></g><g class="creature-ear"><path d="m218 105 62-55-11 92Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round"/><path d="m239 109 29-37-5 46Z" fill="'+accent+'" opacity=".65"/></g>',
      tail:'<path d="M281 376q69 3 62-58-5-42-45-35 29 10 22 36-5 20-36 18" fill="none" stroke="'+outline+'" stroke-width="29" stroke-linecap="round"/><path d="M281 376q69 3 62-58-5-42-45-35 29 10 22 36-5 20-36 18" fill="none" stroke="'+primary+'" stroke-width="18" stroke-linecap="round"/>',
      marks:'<path d="m148 103 13 45 16-49 14 49 16-43" fill="none" stroke="'+shadow+'" stroke-width="10" stroke-linecap="round" opacity=".55"/>'
    },
    rabbit:{
      head:'M94 188Q96 110 178 96q80 12 87 85l1 67-19 35-31 17-14 25-27-11-28 11-15-26-29-16-18-39Z',
      back:'<g class="creature-ear"><path d="M118 116Q76 28 111 10q39 26 54 98Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5"/><path d="M124 93Q98 35 112 25q21 24 36 76Z" fill="'+accent+'" opacity=".58"/></g><g class="creature-ear"><path d="M207 109q14-78 52-96 31 26-7 113Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5"/><path d="M224 102q13-54 34-72 9 17-20 80Z" fill="'+accent+'" opacity=".58"/></g>',
      tail:'<circle cx="310" cy="344" r="35" fill="'+secondary+'" stroke="'+outline+'" stroke-width="5.5"/><circle cx="300" cy="334" r="12" fill="#fff" opacity=".28"/>',
      marks:'<path d="M119 199q24-31 45-26l-16 46-28 13Zm132-1q-23-29-43-25l15 45 27 13Z" fill="'+secondary+'" opacity=".7"/>'
    },
    dragon:{
      head:'M91 191Q93 113 177 94q83 16 92 88l-8 62-19 30-22 17-19 35-27-14-29 13-17-33-27-17-21-39Z',
      back:'<path d="M109 137 78 66l74 39Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round"/><path d="m218 104 72-39-38 82Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round"/><path d="m128 102 8-65 34 58m44 5-2-64-34 58" fill="'+secondary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round"/><path d="m140 68 5-29 14 28m43 0 1-29-14 30" fill="'+accent+'"/>',
      tail:'<path d="M279 374q78-17 54-86l-27 21-22-24q29 52-19 55Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5"/><path d="m331 287 21-10-8 23Z" fill="'+accent+'" stroke="'+outline+'" stroke-width="4"/>',
      marks:'<path d="m117 177 34-21-7 45-31 20Zm137 0-32-21 5 45 31 20Z" fill="'+shadow+'" opacity=".5"/><path d="m174 111 15 19-15 17-15-17Z" fill="'+accent+'" opacity=".7"/>'
    }
  };return parts[species]||parts.wolf;
}
function renderCreature(){
  const svg=document.getElementById('creature'),metrics=creatureMetrics(),prefs=loadCreaturePrefs(),species=prefs.species==='auto'?defaultCreatureSpecies(metrics):prefs.species,dataPalette=creatureDataPalette(metrics,species),primary=prefs.primary||dataPalette.primary,secondary=prefs.secondary||dataPalette.secondary,accent=prefs.accent||dataPalette.accent,meta=CREATURE_SPECIES_META[species],stage=metrics.stage;
  document.getElementById('creature-species').value=prefs.species;document.getElementById('creature-primary').value=validCreatureColor(primary)?primary:CREATURE_DEFAULT_COLORS.primary;document.getElementById('creature-secondary').value=validCreatureColor(secondary)?secondary:CREATURE_DEFAULT_COLORS.secondary;document.getElementById('creature-accent').value=validCreatureColor(accent)?accent:CREATURE_DEFAULT_COLORS.accent;
  const outline=creatureTone(primary,-.48),shadow=creatureTone(primary,-.2),deep=creatureTone(primary,-.38),highlight=creatureTone(secondary,.26),iris=accent,parts=creatureSpeciesParts(species,{primary,secondary,accent,outline,shadow}),spots=Math.min(9,Math.ceil(metrics.projects/3)),ribbons=Math.min(5,metrics.models),p=[];
  p.push('<defs><filter id="fur-shadow"><feDropShadow dx="0" dy="11" stdDeviation="8" flood-color="#060b18" flood-opacity=".3"/></filter><filter id="soft-glow"><feGaussianBlur stdDeviation="10"/></filter><linearGradient id="body-shade" x1="0" y1="0" x2="1" y2="1"><stop stop-color="'+creatureTone(primary,.15)+'"/><stop offset=".58" stop-color="'+primary+'"/><stop offset="1" stop-color="'+shadow+'"/></linearGradient><radialGradient id="eye-shine" cx="35%" cy="25%"><stop stop-color="'+highlight+'"/><stop offset=".45" stop-color="'+iris+'"/><stop offset="1" stop-color="'+deep+'"/></radialGradient><clipPath id="portrait-head"><path d="'+parts.head+'"/></clipPath></defs>');
  p.push('<ellipse cx="180" cy="389" rx="126" ry="19" fill="'+accent+'" opacity=".16" filter="url(#soft-glow)"/><circle cx="180" cy="201" r="145" fill="none" stroke="'+highlight+'" stroke-width="2" opacity=".12"/>',parts.tail,parts.back);
  p.push('<path d="M47 420q4-87 71-116l62 13 63-13q66 29 70 116Z" fill="url(#body-shade)" stroke="'+outline+'" stroke-width="5.5" filter="url(#fur-shadow)"/><path d="M91 420q8-72 43-97l46 15 46-15q36 25 43 97Z" fill="'+secondary+'" opacity=".2"/>');
  p.push('<path d="'+parts.head+'" fill="'+primary+'" stroke="'+outline+'" stroke-width="5.5" stroke-linejoin="round" filter="url(#fur-shadow)"/>',parts.marks);
  p.push('<path class="creature-bangs" d="M111 151q17-42 43-51l-1 25q18-31 38-36l-3 32q20-20 42-13l-18 42q-49-22-101 1Z" fill="'+shadow+'"/><path d="M108 157q17-28 39-40l-1 20q17-23 35-29l-2 25q20-16 38-10l-12 26q-47-17-97 8Z" fill="'+primary+'"/>');
  p.push('<path class="creature-cheek-fur" d="M99 218q-23 8-28 27l23 1-13 21 27-5 1 21 27-17q-20-21-21-54Zm160-1q23 8 28 27l-23 1 13 21-27-5-1 21-27-17q20-21 21-54Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="4.5" stroke-linejoin="round"/>');
  p.push('<path d="M111 184q22-30 52-13l-7 46q-31 13-48-8Z" fill="'+secondary+'" opacity=".92"/><path d="M249 184q-21-29-50-13l6 45q29 13 47-8Z" fill="'+secondary+'" opacity=".92"/>');
  p.push('<g class="creature-eye"><path d="M110 187q24-33 53-5-5 43-30 44-22-1-23-39Z" fill="#fbfdff" stroke="'+outline+'" stroke-width="4"/><ellipse cx="137" cy="195" rx="15" ry="22" fill="url(#eye-shine)"/><ellipse cx="139" cy="199" rx="6" ry="13" fill="'+outline+'"/><circle cx="131" cy="186" r="6" fill="#fff"/><circle cx="143" cy="195" r="3" fill="#fff"/><path d="M112 178q24-18 48-3" fill="none" stroke="'+outline+'" stroke-width="4.5" stroke-linecap="round" opacity=".78"/><path d="M250 187q-21-32-49-5 4 42 27 43 21-2 22-38Z" fill="#fbfdff" stroke="'+outline+'" stroke-width="4"/><ellipse cx="224" cy="195" rx="14" ry="21" fill="url(#eye-shine)"/><ellipse cx="222" cy="199" rx="5.8" ry="12.5" fill="'+outline+'"/><circle cx="217" cy="186" r="5.5" fill="#fff"/><circle cx="228" cy="195" r="2.8" fill="#fff"/><path d="M248 178q-22-18-45-3" fill="none" stroke="'+outline+'" stroke-width="4.5" stroke-linecap="round" opacity=".78"/></g>');
  p.push('<path class="creature-muzzle" d="M135 231q13-18 43-12 31-6 45 11l-3 30q-14 22-41 23-28-1-43-22Z" fill="'+secondary+'" stroke="'+outline+'" stroke-width="4"/><path d="m168 232 11-5 12 5-2 10-10 6-10-6Z" fill="'+deep+'"/><ellipse cx="175" cy="231" rx="3.5" ry="2" fill="#fff" opacity=".58"/><path d="M179 247q0 12-13 16m13-16q1 12 14 16" fill="none" stroke="'+outline+'" stroke-width="3.2" stroke-linecap="round"/><path d="M166 266q13 9 27 0-4 14-14 14-9 0-13-14Z" fill="'+creatureTone(accent,-.1)+'"/><path d="M172 273q7-4 14 0" fill="none" stroke="'+highlight+'" stroke-width="2.5" stroke-linecap="round"/>');
  p.push('<path class="creature-chest-fur" d="M137 307q15-19 28-10l15 20 15-20q14-9 29 10l-10 12 11 10-18 4 3 17-16-7-14 19-13-19-17 7 4-17-18-4 11-10Z" fill="'+secondary+'" stroke="'+outline+'" stroke-width="4.5" stroke-linejoin="round"/><path d="m157 316 23 16 22-16-9 24-13 16-13-16Z" fill="'+highlight+'" opacity=".34"/>');
  p.push('<path class="creature-paw" d="M91 420q7-47 39-61 30 10 39 47l-10 14Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5"/><path d="M191 406q10-37 39-47 32 14 39 61h-68Z" fill="'+primary+'" stroke="'+outline+'" stroke-width="5"/><path d="M119 392q7-12 13 1m7-1q7-11 13 2m57 0q6-13 13-2m7 1q6-12 13-1" fill="none" stroke="'+shadow+'" stroke-width="3.5" stroke-linecap="round"/><path d="M151 408q27 12 58 0" fill="none" stroke="'+highlight+'" stroke-width="3" stroke-linecap="round" opacity=".55"/>');
  p.push('<g class="creature-charm"><path d="M180 337v25" stroke="'+accent+'" stroke-width="4"/><path d="m180 358 11 12-11 15-11-15Z" fill="'+accent+'" stroke="'+outline+'" stroke-width="3"/><circle cx="177" cy="365" r="3" fill="#fff" opacity=".72"/></g>');
  for(let i=0;i<spots;i++){const x=120+(i*29)%126,y=119+((i*43)%42);p.push('<circle cx="'+x+'" cy="'+y+'" r="'+(2+i%2)+'" fill="'+accent+'" opacity="'+(.2+metrics.cache*.42).toFixed(2)+'" clip-path="url(#portrait-head)"/>');}
  for(let i=0;i<ribbons;i++){const x=133+i*(94/Math.max(1,ribbons-1)),y=399+(i%2)*5;p.push('<circle cx="'+x+'" cy="'+y+'" r="5" fill="'+accent+'" stroke="'+outline+'" stroke-width="2"/>');}
  if(metrics.cache>.35)p.push('<path d="M148 91q31-31 61 0" fill="none" stroke="'+accent+'" stroke-width="5" stroke-linecap="round" opacity=".8"/><circle cx="179" cy="74" r="7" fill="'+accent+'" stroke="#fff" stroke-width="2"/>');
  if(stage>=4)p.push('<path d="M55 342 28 320l16 36-24 17 40 3m245-34 27-22-16 36 24 17-40 3" fill="'+accent+'" opacity=".55"/>');
  svg.innerHTML=p.join('');document.getElementById('creature-name').textContent=(metrics.night>.42?'午夜':metrics.cache>.55?'晶核':metrics.models>=5?'虹彩':'星尘')+'·'+meta.title;document.getElementById('creature-desc').textContent='原创日系 Furry 半身伙伴 · '+meta.label+' · 累计成长阶段 '+stage+'/5 · 所有造型与配色均在当前设备生成';document.getElementById('creature-info').innerHTML='<div><b>累计成长阶段 '+stage+'/5</b>'+human(metrics.total)+' 累计 Token</div><div><b>'+meta.label+'</b>伙伴物种</div><div><b>'+ribbons+'</b>模型饰珠</div><div><b>'+spots+'</b>项目星斑</div><div><b>'+Math.round(metrics.cache*100)+'%</b>晶核亮度</div><div><b>'+Math.round(metrics.night*100)+'%</b>夜行气质</div>';
}
function currentCreaturePrefs(){return normalizeCreaturePrefs({species:document.getElementById('creature-species').value,primary:document.getElementById('creature-primary').value,secondary:document.getElementById('creature-secondary').value,accent:document.getElementById('creature-accent').value});}
function updateCreatureColors(){saveCreaturePrefs(currentCreaturePrefs());renderCreature();}
function updateCreatureSpecies(){const prefs=loadCreaturePrefs();prefs.species=document.getElementById('creature-species').value;saveCreaturePrefs(prefs);renderCreature();}
function clearCreatureReference(){if(creatureReferenceURL){URL.revokeObjectURL(creatureReferenceURL);creatureReferenceURL=null;}const wrap=document.getElementById('creature-reference'),image=document.getElementById('creature-reference-image');image.removeAttribute('src');wrap.hidden=true;document.getElementById('creature-remove').disabled=true;document.getElementById('creature-file').value='';}
async function applyCreatureReference(file){
  const status=document.getElementById('creature-upload-status'),allowed=new Set(['image/png','image/jpeg','image/webp']);if(!file||!allowed.has(file.type)){status.textContent='请选择 PNG、JPEG 或 WebP 图片。';return;}if(file.size>5*1024*1024){status.textContent='图片超过 5MB，未读取。';return;}
  const url=URL.createObjectURL(file),image=new Image();try{await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=url;});if(!image.naturalWidth||!image.naturalHeight||image.naturalWidth>12000||image.naturalHeight>12000)throw new Error('size');const scale=Math.min(1,128/Math.max(image.naturalWidth,image.naturalHeight)),canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0,canvas.width,canvas.height);const palette=creaturePaletteFromPixels(context.getImageData(0,0,canvas.width,canvas.height).data);if(!palette.length)throw new Error('palette');clearCreatureReference();creatureReferenceURL=url;document.getElementById('creature-reference-image').src=url;document.getElementById('creature-reference').hidden=false;document.getElementById('creature-remove').disabled=false;const controls=['creature-primary','creature-secondary','creature-accent'];controls.forEach((id,index)=>{if(palette[index])document.getElementById(id).value=palette[index];});updateCreatureColors();status.textContent='已在本地提取配色；原图仅保留到本页关闭。';}catch(e){URL.revokeObjectURL(url);status.textContent='无法读取这张图片，未应用任何内容。';}
}
document.getElementById('creature-species').addEventListener('change',updateCreatureSpecies);['creature-primary','creature-secondary','creature-accent'].forEach(id=>document.getElementById(id).addEventListener('input',updateCreatureColors));document.getElementById('creature-file').addEventListener('change',event=>applyCreatureReference(event.target.files?.[0]));document.getElementById('creature-remove').addEventListener('click',()=>{clearCreatureReference();document.getElementById('creature-upload-status').textContent='参考图已从当前页面移除。';});document.getElementById('creature-reset').addEventListener('click',()=>{clearCreatureReference();try{localStorage.removeItem(CREATURE_PREFS_KEY);}catch(e){}renderCreature();document.getElementById('creature-upload-status').textContent='已恢复由 Token 数据决定的物种与配色。';});
document.getElementById('creature-save').addEventListener('click',()=>{const s=document.getElementById('creature').cloneNode(true);s.setAttribute('xmlns','http://www.w3.org/2000/svg');s.setAttribute('width','600');s.setAttribute('height','640');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([s.outerHTML],{type:'image/svg+xml'}));a.download='furry-token-companion.svg';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);toast('Furry Token 伙伴已保存');});

/* ---- 每模型迷你趋势（small multiples）---- */
function renderMultiples(){
  const box=document.getElementById('multiples'), days=DATA.day||[];
  if(!days.length||!DATA.models.length){ box.innerHTML='<div class="hint">无数据</div>'; return; }
  box.innerHTML=DATA.models.map(m=>{
    const s=days.map(d=>d.models[m]||0), total=s.reduce((a,b)=>a+b,0), max=Math.max(1,...s), W=120,H=32,c=DATA.colors[m];
    let path=''; s.forEach((v,i)=>{ const x=i/Math.max(1,s.length-1)*W, y=H-3-(v/max)*(H-6); path+=(i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)+' '; });
    const area=path+'L '+W+' '+H+' L 0 '+H+' Z';
    return '<div class="mp model-mark" data-model="'+esc(m)+'"'+dataSignalAttrs('model',m,pretty(m),total,'multiples')+' tabindex="0" role="button" aria-label="模型 '+esc(pretty(m))+'，'+fmt(total)+' Token，点击或按 Enter Pin 到 Signal Dock"><div class=nm><i style="background:'+c+'"></i>'+esc(pretty(m))+'</div><div class=vt>'+human(total)+'</div>'
      +'<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none"><path d="'+area+'" fill="'+c+'" fill-opacity="0.16"/><path d="'+path+'" fill="none" stroke="'+c+'" stroke-width="1.5" stroke-linejoin="round"/></svg></div>';
  }).join('');
}

/* ---- 柱图竞赛（累计 token 随日演变）---- */
let raceTimer=null, raceIdx=0;
function raceData(){
  const days=DATA.day||[], cum={}, out=[];
  days.forEach(d=>{ Object.keys(d.models).forEach(m=>cum[m]=(cum[m]||0)+d.models[m]); out.push({day:d.period,cum:Object.assign({},cum)}); });
  return out;
}
function renderRace(){
  const data=raceData(), box=document.getElementById('race');
  if(data.length<2){ box.innerHTML='<div class="hint">数据不足</div>'; document.getElementById('race-day').textContent='';const scrub=document.getElementById('race-scrub');scrub.disabled=true;scrub.max='0';scrub.value='0';scrub.removeAttribute('aria-valuetext'); return; }
  document.getElementById('race-scrub').disabled=false;
  raceIdx=Math.min(raceIdx,data.length-1);
  const cur=data[raceIdx], entries=Object.entries(cur.cum).sort((a,b)=>b[1]-a[1]).slice(0,6), max=Math.max(1,...entries.map(e=>e[1]));
  box.innerHTML=entries.map(([m,v])=>{
    const w=v/max*100;
    return '<div class=race-row><span class=race-name><i style="background:'+DATA.colors[m]+'"></i>'+esc(pretty(m))+'</span>'
      +'<span class=race-bar><i style="width:'+w.toFixed(1)+'%;background:'+DATA.colors[m]+'"></i></span><span class=race-val>'+human(v)+'</span></div>';
  }).join('');
  document.getElementById('race-day').textContent='截至 '+fmtLabel(cur.day,'day');
  document.getElementById('race-pos').textContent=(raceIdx+1)+'/'+data.length;
  const scrub=document.getElementById('race-scrub');scrub.max=String(data.length-1);scrub.value=String(raceIdx);scrub.setAttribute('aria-valuetext','截至 '+fmtLabel(cur.day,'day')+'，第 '+(raceIdx+1)+' / '+data.length+' 期');
}
document.getElementById('race-scrub').addEventListener('input',e=>{if(raceTimer){clearInterval(raceTimer);raceTimer=null;document.getElementById('race-play').textContent='▶ 播放';}raceIdx=Number(e.target.value||0);renderRace();});

document.getElementById('race-play').addEventListener('click',function(){
  const data=raceData();
  if(raceTimer){ clearInterval(raceTimer); raceTimer=null; this.textContent='▶ 播放'; return; }
  if(data.length<2) return;
  raceIdx=0; renderRace(); this.textContent='⏸ 暂停';
  raceTimer=setInterval(()=>{ raceIdx++; if(raceIdx>=data.length){ clearInterval(raceTimer); raceTimer=null; this.textContent='▶ 播放'; raceIdx=data.length-1; } renderRace(); },700);
});

function dataCommands(){
  const days=DATA.day||[],top=[...days].sort((a,b)=>b.total-a.total)[0],h=DATA.hourly||[],peak=h.indexOf(Math.max(...h)),mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));
  const out=[];if(top)out.push({ic:'🔍',t:'最高 Token 日 · '+top.period+' · '+human(top.total),k:'数据',run:()=>{setGran('day');setTimeout(()=>toggleFocus(top.period),30);}});if(peak>=0)out.push({ic:'🌙',t:'最活跃时刻 · '+String(peak).padStart(2,'0')+':00 · '+human(h[peak]),k:'数据',run:()=>document.querySelector('[data-module=clock]').scrollIntoView({behavior:scrollBehavior()})});Object.entries(mt).sort((a,b)=>b[1]-a[1]).forEach(([m,v])=>out.push({ic:'🤖',t:pretty(m)+' · '+human(v)+' · '+(v/Object.values(mt).reduce((a,b)=>a+b,0)*100).toFixed(1)+'%',k:'模型',run:()=>setModels([m],'Solo · '+pretty(m))}));return out;
}
function secretCommand(q){
  q=q.trim().toLowerCase();
  const secrets={
    'whoami':()=>{const x=shareStats();toast((x.peak<6||x.peak>=22?'午夜航行型':'日光构筑型')+'开发者 · '+x.dom+' · '+Math.round(x.cache*100)+'% 缓存',4200);},
    '42':()=>toast('宇宙终极答案是 42，但你的答案是 '+human(lastTotal)+' Token。',4200),
    'coffee':()=>toast('你的 Token 大约够续命 '+fmt(Math.round(lastTotal/250000))+' 杯程序员美式 ☕',4200),
    'sudo':()=>toast('权限不足：算力宇宙拒绝 root 接管。'),
    'rm -rf':()=>toast('操作已拦截。你的 '+fmt((_ach||getBadgeData()).got)+' 枚成就松了一口气。',4200),
    'matrix':()=>{document.body.style.filter='hue-rotate(75deg) saturate(1.5)';toast('Wake up, developer…');setTimeout(()=>document.body.style.filter='',2600);},
    'midnight':()=>{const h=DATA.hourly||[];toast('深夜共留下 '+human(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))+' Token。',4200);},
    'receipt':()=>openShare('receipt'),'passport':()=>openShare('passport'),'flow':()=>scrollToSection('section-flow'),'orbit':()=>scrollToSection('section-flow'),'city':()=>scrollToSection('section-flow'),'creature':()=>document.querySelector('[data-module=creature]').scrollIntoView({behavior:scrollBehavior()})
  };if(secrets[q]){closePalette();setTimeout(secrets[q],80);return true;}return false;
}

function scrollToSection(id){const el=document.getElementById(id);if(!el)return;const lazy=el.dataset.lazy;if(lazy){lazyState[lazy]=Object.assign({},lazyState[lazy],{visible:true});renderLazy(lazy,true);}el.scrollIntoView({behavior:scrollBehavior(),block:'start'});}
const SECTION_LINKS=[['section-overview','总览'],['section-trend','趋势'],['section-provenance','体检'],['section-almanac','年鉴'],['section-project','项目'],['section-rhythm','节奏'],['section-reuse','复用'],['section-flow','流光'],['section-achievements','成就'],['section-top','Top']];
function initSectionDock(){
  const dock=document.getElementById('section-dock');dock.addEventListener('click',e=>{const b=e.target.closest('button[data-target]');if(b)scrollToSection(b.dataset.target);});
  const mark=id=>dock.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.target===id));
  if('IntersectionObserver'in window){const obs=new IntersectionObserver(entries=>{const hit=entries.filter(x=>x.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];if(hit)mark(hit.target.id);},{rootMargin:'-18% 0px -65% 0px',threshold:[0,.15,.4]});SECTION_LINKS.forEach(([id])=>{const el=document.getElementById(id);if(el)obs.observe(el);});}
}
initSectionDock();
document.getElementById('freshness-beacon').addEventListener('click',()=>scrollToSection('section-provenance'));
document.getElementById('status-pulse').addEventListener('click',()=>scrollToSection('section-trend'));
document.getElementById('provenance-copy').addEventListener('click',()=>copyText(provenanceSummary()).then(ok=>toast(ok?'数据体检摘要已复制':'复制失败')));
document.getElementById('prov-capabilities').addEventListener('click',e=>{const b=e.target.closest('[data-cap]');if(!b)return;const item=capabilityInfo().find(x=>x.key===b.dataset.cap);if(!item)return;if(item.status==='off'){toast(capabilityReason(item.key));return;}scrollToSection(item.target);});
function usageStatus(rows){if(rows.length<2)return {label:'—',cls:'',last:rows.length?rows[rows.length-1].total:0,avg:null,delta:null,detail:'至少需要两期数据才能计算状态'};const last=rows[rows.length-1].total,prior=rows.slice(Math.max(0,rows.length-5),-1),avg=prior.reduce((a,r)=>a+r.total,0)/Math.max(1,prior.length);if(avg===0){if(last>0)return {label:'升温',cls:'warming',last,avg,delta:null,detail:'此前均值为 0，本期出现新活动'};return {label:'平稳',cls:'steady',last,avg,delta:0,detail:'本期与此前均值均为 0'};}const delta=last/avg-1,label=delta>.12?'升温':delta<-.12?'降温':'平稳',cls=delta>.12?'warming':delta<-.12?'cooling':'steady';return {label,cls,last,avg,delta,detail:'变化 '+(delta>=0?'+':'')+(delta*100).toFixed(1)+'%'};}
function renderStatusPulse(){const el=document.getElementById('status-pulse'),text=document.getElementById('status-text'),preview=scrubRow(),s=usageStatus(preview?[preview]:selectedRows(true));el.classList.remove('warming','steady','cooling','scrub-preview');if(preview){el.classList.add('scrub-preview');text.textContent='预览 '+fmtLabel(preview.period,state.gran);el.title=trendPreviewCopy(preview)+' · 尚未提交';return;}if(s.cls)el.classList.add(s.cls);text.textContent='状态 '+s.label;el.title=s.avg===null?s.detail+' · 点击查看趋势':'最后一期 '+fmt(s.last)+' Token；此前均值 '+fmt(s.avg)+'；'+s.detail+' · 点击查看趋势';}

/* ---- 命令面板 Cmd+K ---- */
function cmdActions(){ return [
  {ic:'⌁',t:(trailState.open?'继续':'开始')+' · 数据寻迹',k:'I',run:()=>openDataTrail(document.getElementById('trail-open'))},
  {ic:'◎',t:'跳转 · 总览',k:'',run:()=>scrollToSection('section-overview')},
  {ic:'↗',t:'跳转 · 趋势',k:'',run:()=>scrollToSection('section-trend')},
  {ic:'⌁',t:'跳转 · 数据可信度实验室',k:'',run:()=>scrollToSection('section-provenance')},
  {ic:'✦',t:'跳转 · Token 年鉴',k:'',run:()=>scrollToSection('section-almanac')},
  {ic:'◉',t:'打开 · 数据时间胶囊',k:'',run:()=>{scrollToSection('section-almanac');setTimeout(openAlmanacCapsule,60);}},
  {ic:'▣',t:'跳转 · 项目透镜',k:'',run:()=>scrollToSection('section-project')},
  {ic:'◫',t:'跳转 · 节奏',k:'',run:()=>scrollToSection('section-rhythm')},
  {ic:'≈',t:'跳转 · Context Reuse River',k:'',run:()=>scrollToSection('section-reuse')},
  {ic:'≋',t:'跳转 · Token 流光图',k:'',run:()=>scrollToSection('section-flow')},
  {ic:'◇',t:'跳转 · 成就',k:'',run:()=>scrollToSection('section-achievements')},
  {ic:'№',t:'跳转 · Top',k:'',run:()=>scrollToSection('section-top')},
  {ic:'📅',t:'按日',k:'1',run:()=>setGran('day')},
  {ic:'📆',t:'按周',k:'2',run:()=>setGran('week')},
  {ic:'🗓️',t:'按月',k:'3',run:()=>setGran('month')},
  {ic:'☀️',t:'亮色主题',k:'',run:()=>applyTheme('light')},
  {ic:'🌙',t:'暗色主题',k:'',run:()=>applyTheme('dark')},
  {ic:'🌗',t:'跟随系统主题',k:'T',run:()=>applyTheme('auto')},
  {ic:'⤓',t:'导出 CSV',k:'E',run:exportCSV},
  {ic:'◇',t:'导出 Markdown',k:'',run:exportMarkdown},
  {ic:'◆',t:'下一个数据时刻',k:'',run:()=>{const events=buildMomentEvents();if(!events.length){toast('当前筛选没有可回看的数据时刻');return;}const current=state.focusPeriod||'';focusMomentDay(events.find(event=>event.day>current)?.day||events[0].day);}},
  {ic:'◫',t:'切换幻影对比',k:'',run:togglePinnedCompare},
  {ic:'⧉',t:'复制当前视图链接',k:'',run:copyViewLink},
  {ic:'?',t:'查看快捷键与交互说明',k:'?',run:openHelp},
  {ic:'🎲',t:'换一组趣味换算',k:'',run:renderFunFacts},
  {ic:'▶',t:'播放柱图竞赛',k:'',run:()=>{ if(!document.getElementById('race').closest('[data-module]')||document.getElementById('race').closest('[data-module]').style.display!=='none') document.getElementById('race-play').click(); }},
  {ic:'⚙️',t:'打开模块开关',k:'',run:()=>document.getElementById('mods-btn').click()},
  {ic:'🎉',t:'撒花彩蛋',k:'',run:()=>{confetti();toast('🎉');}}
]; }
let pal={items:[],i:0},paletteOpener=null;
function openPalette(){paletteOpener=document.activeElement;renderPalette('');const scrim=document.getElementById('scrim');scrim.classList.add('open');scrim.setAttribute('aria-hidden','false');setTimeout(()=>document.getElementById('palette-q').focus(),10);}
function closePalette(){const scrim=document.getElementById('scrim');scrim.classList.remove('open');scrim.setAttribute('aria-hidden','true');document.getElementById('palette-q').value='';document.getElementById('palette-q').removeAttribute('aria-activedescendant');const opener=paletteOpener;paletteOpener=null;if(opener&&document.contains(opener))opener.focus();}
function renderPalette(q){
  const ul=document.getElementById('palette-list'), base=[...cmdActions(),...dataCommands()];
  pal.items=base.filter(a=>!q||(a.t+a.ic+a.k).toLowerCase().includes(q.toLowerCase())); pal.i=0;
  ul.innerHTML = pal.items.length ? pal.items.map((a,i)=>'<li id="palette-opt-'+i+'" role=option aria-selected="'+(i===0?'true':'false')+'" data-i="'+i+'"><span class=ic>'+a.ic+'</span>'+a.t+(a.k?'<span class=k>'+a.k+'</span>':'')+'</li>').join('') : '<div class="empty">无匹配结果 · 试试 whoami、42、matrix、coffee</div>';
  syncPal();
}
function runPalette(i){ const a=pal.items[i]; if(!a) return; closePalette(); setTimeout(a.run,30); }
document.getElementById('palette-q').addEventListener('input',e=>renderPalette(e.target.value));
document.getElementById('palette-q').addEventListener('keydown',e=>{if(e.key==='Enter'&&secretCommand(e.target.value)){e.preventDefault();e.stopImmediatePropagation();}});
document.getElementById('palette-list').addEventListener('click',e=>{ const li=e.target.closest('li'); if(li) runPalette(+li.dataset.i); });
document.getElementById('scrim').addEventListener('click',e=>{ if(e.target.id==='scrim') closePalette(); });
function syncPal(){const input=document.getElementById('palette-q');document.querySelectorAll('#palette-list li').forEach((li,i)=>{const active=i===pal.i;li.classList.toggle('active',active);li.setAttribute('aria-selected',String(active));});if(pal.items.length)input.setAttribute('aria-activedescendant','palette-opt-'+pal.i);else input.removeAttribute('aria-activedescendant');}
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&(e.key==='k'||e.key==='K')){ e.preventDefault(); document.getElementById('scrim').classList.contains('open')?closePalette():openPalette(); return; }
  if(e.key==='Escape'){const modal=activeModal();if(modal){e.preventDefault();if(modal.id==='replay-modal')closeReplay();else if(modal.id==='help-modal')closeHelp();else if(modal.id==='share-modal')closeShare();else if(modal.id==='almanac-modal')closeAlmanacCapsule();else if(modal.id==='ach-modal')closeAchievements();return;}}
  const palette=document.getElementById('scrim');if(palette.classList.contains('open')){if(e.key==='Tab'){e.preventDefault();document.getElementById('palette-q').focus();}else if(e.key==='Escape'){e.preventDefault();closePalette();}else if(e.key==='ArrowDown'){e.preventDefault();pal.i=(pal.i+1)%Math.max(1,pal.items.length);syncPal();}else if(e.key==='ArrowUp'){e.preventDefault();pal.i=(pal.i-1+Math.max(1,pal.items.length))%Math.max(1,pal.items.length);syncPal();}else if(e.key==='Enter'){e.preventDefault();runPalette(pal.i);}return;}
  if(e.key==='Escape'&&scrubState.period){e.preventDefault();clearScrub('预览已清除',true);return;}
  if(trailState.open){if(e.key==='Escape'){e.preventDefault();closeDataTrail();return;}if(e.key==='Backspace'&&!editableTarget(e.target)){e.preventDefault();trailBack();return;}if((e.key==='ArrowLeft'||e.key==='ArrowRight')&&!e.target.closest('[data-trail-roving]')){const index=TRAIL_STEPS.indexOf(trailState.step),next=Math.max(0,Math.min(trailState.reached,index+(e.key==='ArrowRight'?1:-1)));if(next!==index){e.preventDefault();setTrailStep(TRAIL_STEPS[next]);}return;}}
  if(e.key==='Escape'&&signalState.pinnedSignal){e.preventDefault();clearSignal();return;}
  if(e.key==='Escape'&&state.focusPeriod){e.preventDefault();clearFocus(true);return;}
});

/* ---- Token Almanac：跨快照赛季、个人纪录与时间胶囊 ---- */
const ALMANAC_KEY='tk-almanac-v1',ALMANAC_VERSION=1,ALMANAC_SCOPE_LIMIT=8,ALMANAC_SNAPSHOT_LIMIT=24;
function isoDayNumber(day){const p=String(day||'').split('-').map(Number);return p.length===3?Math.floor(Date.UTC(p[0],p[1]-1,p[2])/86400000):0;}
function dayDistance(a,b){return isoDayNumber(b)-isoDayNumber(a);}
function almanacDailyRows(data=DATA){
  const extras=Object.fromEntries((data.achievement_daily||[]).map(x=>[x.day,x]));
  return [...(data.day||[])].sort((a,b)=>a.period.localeCompare(b.period)).map(row=>{
    const detail=(data.day_details||{})[row.period]||{},extra=extras[row.period]||{},hourly=detail.hourly||[],peakValue=Math.max(0,...hourly),peakHour=peakValue?hourly.indexOf(peakValue):null,models=Object.entries(row.models||{}).filter(([,value])=>value>0);
    return {day:row.period,total:row.total||0,calls:row.calls||0,models:Object.fromEntries(models),modelCount:models.length,cache:detail.cache_read||0,input:extra.input||0,output:extra.output||0,cacheWrite:extra.cache_write||0,maxTurns:extra.max_turns||0,peakHour,peakHourValue:peakValue};
  });
}
function seasonCharacter(season,previous){
  if(!season.activeDays)return {key:'quiet',label:'静默'};
  if(season.activeDays<5)return {key:'incipient',label:'初生'};
  if(previous&&season.dominantModel&&previous.dominantModel&&season.dominantModel!==previous.dominantModel)return {key:'migration',label:'迁徙'};
  const mean=season.total/season.activeDays,variance=season.rows.reduce((sum,row)=>sum+Math.pow(row.total-mean,2),0)/season.activeDays,cv=mean?Math.sqrt(variance)/mean:0;
  if(cv>=1.15)return {key:'surge',label:'潮涌'};
  if(cv<=.28)return {key:'steady',label:'恒定'};
  return {key:'echo',label:'回声'};
}
function finalizeSeason(rows,index,range,previous){
  const first=rows[0],last=rows[rows.length-1],models={};rows.forEach(row=>Object.entries(row.models).forEach(([model,value])=>models[model]=(models[model]||0)+value));
  const total=rows.reduce((sum,row)=>sum+row.total,0),calls=rows.reduce((sum,row)=>sum+row.calls,0),cache=rows.reduce((sum,row)=>sum+row.cache,0),dominant=Object.entries(models).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0],peak=rows.reduce((best,row)=>!best||row.total>best.total?row:best,null),streak=longestActiveStreak(rows.map(row=>({period:row.day,total:row.total})));
  const season={id:first.day+'..'+last.day,index,start:first.day,end:last.day,rows,total,calls,cache,activeDays:rows.length,spanDays:dayDistance(first.day,last.day)+1,dominantModel:dominant?.[0]||null,dominantShare:total&&dominant?dominant[1]/total:0,peakDay:peak?.day||null,peakValue:peak?.total||0,longestStreak:streak,truncatedStart:!!(range?.since&&range.since===first.day),truncatedEnd:!!(range?.until&&range.until===last.day)};
  season.character=seasonCharacter(season,previous);return season;
}
function deriveSeasons(rows,range={}){
  const active=rows.filter(row=>row.total>0).sort((a,b)=>a.day.localeCompare(b.day));if(!active.length)return [];
  const groups=[];let current=[];active.forEach(row=>{const prev=current[current.length-1],monthBreak=prev&&prev.day.slice(0,7)!==row.day.slice(0,7),quietBreak=prev&&dayDistance(prev.day,row.day)>=8;if(prev&&(monthBreak||quietBreak)){groups.push(current);current=[];}current.push(row);});if(current.length)groups.push(current);
  const seasons=[];groups.forEach((group,index)=>seasons.push(finalizeSeason(group,index,range,seasons[seasons.length-1])));return seasons;
}
function bestRecord(rows,id,label,unit,valueOf,extra={}){
  let best=null;rows.forEach(row=>{const candidate=valueOf(row);if(candidate==null||!Number.isFinite(candidate.value)||candidate.value<=0)return;if(!best||candidate.value>best.value||(candidate.value===best.value&&row.day<best.achievedDay))best={id,label,unit,value:candidate.value,achievedDay:row.day,precision:'exact-day',detail:candidate.detail||'',format:candidate.format||'number',...extra};});return best;
}
function derivePersonalRecords(rows){
  if(!rows.length)return [];
  const records=[
    bestRecord(rows,'peak-day-token','单日 Token 峰值','tk',row=>({value:row.total})),
    bestRecord(rows,'peak-day-calls','单日调用峰值','次',row=>({value:row.calls})),
    bestRecord(rows,'peak-hour-token','单小时峰值','tk',row=>row.peakHour==null?null:{value:row.peakHourValue,detail:String(row.peakHour).padStart(2,'0')+':00'}),
    bestRecord(rows,'peak-day-cache','单日缓存量峰值','tk',row=>({value:row.cache})),
    bestRecord(rows,'peak-cache-ratio','单日缓存占比','%',row=>row.total>=1000?{value:row.cache/row.total,format:'percent'}:null,{note:'仅比较单日总量至少 1K Token 的日期'}),
    bestRecord(rows,'peak-day-input','单日输入峰值','tk',row=>({value:row.input})),
    bestRecord(rows,'peak-day-output','单日输出峰值','tk',row=>({value:row.output})),
    bestRecord(rows,'peak-day-cache-write','单日缓存写入峰值','tk',row=>({value:row.cacheWrite})),
    bestRecord(rows,'max-session-turns','单会话累计轮数','轮',row=>({value:row.maxTurns}),{precision:'range-day'}),
    bestRecord(rows,'peak-model-diversity','单日模型多样性','种',row=>({value:row.modelCount}))
  ].filter(Boolean);
  const active=rows.filter(row=>row.total>0),activeSet=new Set(active.map(row=>row.day));let current=0,longest=0,end=null,previous=null;active.forEach(row=>{current=previous&&dayDistance(previous,row.day)===1?current+1:1;if(current>longest){longest=current;end=row.day;}previous=row.day;});if(longest)records.push({id:'longest-active-streak',label:'最长连续活跃',unit:'天',value:longest,achievedDay:end,precision:activeSet.has(rows[0].day)&&end===rows[Math.max(0,longest-1)]?.day?'range-boundary':'exact-day',detail:'截至 '+end,format:'number'});
  return records.sort((a,b)=>a.id.localeCompare(b.id));
}
function almanacScopeKey(data=DATA){const s=data.snapshot||{},until=data.range?.until?'fixed:'+data.range.until:'rolling';return ['v1',data.anonymized?'anon':'raw',[...(data.source||[])].sort().join(','),data.range?.since||'all',until,s.timezone||'local','m'+(s.metric_schema||1)].join('|');}
function readAlmanacStore(storage=localStorage){try{const parsed=JSON.parse(storage.getItem(ALMANAC_KEY)||'{}');return parsed&&parsed.v===ALMANAC_VERSION&&parsed.scopes&&typeof parsed.scopes==='object'?parsed:{v:ALMANAC_VERSION,scopes:{}};}catch(e){return {v:ALMANAC_VERSION,scopes:{}};}}
function recordDisplay(record){const value=Number(record.value||0);return record.format==='percent'?(value*100).toFixed(1)+'%':fmt(Math.round(value))+(record.unit?' '+record.unit:'');}
function recordDeltaDisplay(record,delta){return record.format==='percent'?(delta*100).toFixed(1)+' 个百分点':fmt(Math.round(delta))+(record.unit?' '+record.unit:'');}
function summarizeAlmanacSnapshot(rows,seasons,records,data=DATA){const models={};rows.forEach(row=>Object.entries(row.models).forEach(([model,value])=>models[model]=(models[model]||0)+value));return {id:data.snapshot?.id||['legacy',data.generated,rows.length,rows.reduce((sum,row)=>sum+row.total,0)].join(':'),generated:String(data.generated||''),coverage:data.snapshot?.coverage||{first_day:rows[0]?.day||null,last_day:rows[rows.length-1]?.day||null},totals:{tokens:rows.reduce((sum,row)=>sum+row.total,0),calls:rows.reduce((sum,row)=>sum+row.calls,0),cache:rows.reduce((sum,row)=>sum+row.cache,0)},models,records:records.map(({id,label,unit,value,achievedDay,precision,detail,format})=>({id,label,unit,value,achievedDay,precision,detail,format})),seasons:seasons.map(({id,start,end,total,calls,activeDays,spanDays,dominantModel,dominantShare,peakDay,peakValue,longestStreak,character})=>({id,start,end,total,calls,activeDays,spanDays,dominantModel,dominantShare,peakDay,peakValue,longestStreak,character}))};}
function compareAlmanacRecords(current,history){const prior={};history.forEach(snapshot=>(snapshot.records||[]).forEach(record=>{const old=prior[record.id];if(!old||record.value>old.value)prior[record.id]=record;}));return current.map(record=>{const old=prior[record.id];let status='baseline',delta=null;if(old){delta=record.value-old.value;if(record.value>old.value)status='broken';else if(record.value===old.value&&record.achievedDay!==old.achievedDay)status='tied';else if(record.value===old.value)status='standing';else status='historic';}return {...record,status,delta,prior:old||null};});}
function writeAlmanacObservation(summary,storage=localStorage,data=DATA){
  const store=readAlmanacStore(storage),scope=almanacScopeKey(data),existing=store.scopes[scope]||{updated:'',snapshots:[]},all=(existing.snapshots||[]).filter(item=>item&&item.id),isDuplicate=all.some(item=>item.id===summary.id),snapshots=all.filter(item=>item.id!==summary.id),history=[...snapshots].sort((a,b)=>String(a.generated).localeCompare(String(b.generated))),comparison=compareAlmanacRecords(summary.records,history),previous=history[history.length-1]||null;
  snapshots.push(summary);snapshots.sort((a,b)=>String(a.generated).localeCompare(String(b.generated)));existing.updated=summary.generated;existing.snapshots=snapshots.slice(-ALMANAC_SNAPSHOT_LIMIT);store.scopes[scope]=existing;
  const scoped=Object.entries(store.scopes).sort((a,b)=>String(b[1].updated).localeCompare(String(a[1].updated))).slice(0,ALMANAC_SCOPE_LIMIT);store.scopes=Object.fromEntries(scoped);try{storage.setItem(ALMANAC_KEY,JSON.stringify(store));}catch(e){}
  return {store,scope,history,previous,comparison,isBaseline:history.length===0,isDuplicate};
}
function dominantModelFromSnapshot(snapshot){return Object.entries(snapshot?.models||{}).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0]?.[0]||null;}
function buildCapsuleStories(observation,summary,seasons){
  if(observation.isBaseline)return [{k:'BASELINE SEALED',title:'时间胶囊已建立基线',copy:'这是本设备在当前作用域第一次观察这份年鉴。等下一份不同快照到来后，它才会展开真实的前后变化。',metric:'没有伪造过去'}];
  const previous=observation.previous,stories=[{k:'CAPSULE OPENED',title:'过去的快照回信了',copy:'正在比较 '+(previous.coverage?.last_day||previous.generated||'上一份快照')+' 与 '+(summary.coverage?.last_day||summary.generated||'当前快照')+'。',metric:observation.isDuplicate?'内容与既有快照相同':'发现新的快照内容'}];
  const delta=summary.totals.tokens-(previous.totals?.tokens||0),ratio=previous.totals?.tokens?delta/previous.totals.tokens:null;stories.push({k:'TOKEN TIDE',title:delta===0?'总量没有可辨认变化':delta>0?'新的 Token 已进入年鉴':'当前范围比上一快照更窄',copy:delta>=0?'当前聚合总量相对上一份本地快照的差异。':'这通常来自日期范围收缩；年鉴不会把它描述为负向表现。',metric:(delta>=0?'+':'')+fmt(delta)+' tk'+(ratio==null?'':' · '+(ratio>=0?'+':'')+(ratio*100).toFixed(1)+'%')});
  const broken=observation.comparison.filter(record=>record.status==='broken');if(broken.length)stories.push({k:'NEW CONSTELLATIONS',title:'有 '+broken.length+' 项个人纪录被改写',copy:broken.slice(0,4).map(record=>record.label+' '+recordDisplay(record)).join(' · '),metric:'只与本设备既有快照比较'});else stories.push({k:'STANDING STARS',title:'旧纪录仍在轨道上',copy:'当前快照没有超过本设备此前观察到的个人纪录；保持不变也是一种真实状态。',metric:'0 项新纪录'});
  const before=dominantModelFromSnapshot(previous),now=dominantModelFromSnapshot(summary);stories.push({k:'MODEL COMPASS',title:before&&now&&before!==now?'主力模型发生迁徙':'主力模型方向保持稳定',copy:before&&now?pretty(before)+' → '+pretty(now):'当前快照不足以比较主力模型。',metric:now?pretty(now):'—'});
  const priorSeasons=previous.seasons||[],latest=seasons[seasons.length-1];if(latest)stories.push({k:'SEASON MEMORIAL',title:priorSeasons.some(season=>season.id===latest.id)?'当前赛季继续生长':'年鉴出现了新的赛季章节',copy:latest.start+' → '+latest.end+' · '+latest.character.label+' · '+latest.activeDays+' 个活跃日。',metric:human(latest.total)+' tk'});
  return stories;
}
let _almanac=null,seasonCursor=0,recordCursor=0,capsuleCursor=0;
function almanacHash(value){let h=2166136261;for(const ch of String(value))h=Math.imul(h^ch.charCodeAt(0),16777619);return h>>>0;}
function recordStatusLabel(record){return {baseline:'首次观察',broken:'新纪录',tied:'追平纪录',standing:'纪录保持',historic:'历史纪录在范围外'}[record.status]||record.status;}
function renderSeasonDetail(season){const el=document.getElementById('season-detail');if(!season){el.innerHTML='<div class=ach-empty>当前报告没有可划分的活跃赛季。</div>';return;}const clipped=[season.truncatedStart?'起点为报告边界':'',season.truncatedEnd?'终点为报告边界':''].filter(Boolean).join(' · ');el.innerHTML='<div><span>'+esc(season.character.label)+' SEASON</span><b>'+season.start+' → '+season.end+'</b><small>'+season.activeDays+' 个活跃日 · 跨 '+season.spanDays+' 个自然日'+(clipped?' · '+clipped:'')+'</small></div><div><b>'+human(season.total)+' tk</b><small>峰值 '+season.peakDay+' · '+human(season.peakValue)+'</small></div><div><b>'+(season.dominantModel?esc(pretty(season.dominantModel)):'—')+'</b><small>主力占比 '+(season.dominantShare*100).toFixed(1)+'% · 最长连续 '+season.longestStreak+' 天</small></div>';}
function focusSeason(index,focus=true){if(!_almanac?.seasons.length)return;seasonCursor=Math.max(0,Math.min(_almanac.seasons.length-1,index));const buttons=[...document.querySelectorAll('.season-node')];buttons.forEach((button,i)=>{button.tabIndex=i===seasonCursor?0:-1;button.setAttribute('aria-selected',String(i===seasonCursor));button.classList.toggle('on',i===seasonCursor);});renderSeasonDetail(_almanac.seasons[seasonCursor]);if(focus)buttons[seasonCursor]?.focus();}
function renderRecordDetail(record){const el=document.getElementById('record-detail');if(!record){el.textContent='当前范围没有可重建的个人纪录。';return;}const date=record.precision==='range-boundary'?'报告范围开始时已在保持':record.achievedDay?'本报告范围内记录于 '+record.achievedDay:'日期不可还原',delta=record.status==='broken'&&record.delta!=null?' · 比此前高 '+recordDeltaDisplay(record,record.delta):'';el.innerHTML='<span>'+recordStatusLabel(record)+'</span><b>'+esc(record.label)+' · '+esc(recordDisplay(record))+'</b><small>'+esc(date+(record.detail?' · '+record.detail:'')+delta)+'</small>';}
function focusRecord(index,focus=true){if(!_almanac?.records.length)return;recordCursor=Math.max(0,Math.min(_almanac.records.length-1,index));document.querySelectorAll('[data-record-index]').forEach((node,i)=>{node.setAttribute('tabindex',i===recordCursor?'0':'-1');node.classList.toggle('on',i===recordCursor);});renderRecordDetail(_almanac.records[recordCursor]);if(focus)document.querySelector('[data-record-index="'+recordCursor+'"]')?.focus();}
function renderCapsuleStory(){const stories=_almanac?.stories||[],story=stories[capsuleCursor];if(!story)return;document.getElementById('capsule-story').innerHTML='<div class=capsule-k>'+esc(story.k)+'</div><h4>'+esc(story.title)+'</h4><p>'+esc(story.copy)+'</p><strong>'+esc(story.metric)+'</strong>';document.getElementById('capsule-pos').textContent=(capsuleCursor+1)+' / '+stories.length;document.getElementById('capsule-progress').innerHTML=stories.map((_,i)=>'<i class="'+(i===capsuleCursor?'on':'')+'"></i>').join('');document.getElementById('capsule-prev').disabled=capsuleCursor===0;document.getElementById('capsule-next').disabled=capsuleCursor===stories.length-1;}
function openAlmanacCapsule(){if(!_almanac)return;capsuleCursor=0;renderCapsuleStory();openModal(document.getElementById('almanac-modal'),document.getElementById('almanac-x'));if(!_almanac.observation.isBaseline&&_almanac.records.some(record=>record.status==='broken')&&document.documentElement.dataset.motion==='full')confetti();}
function closeAlmanacCapsule(){closeModal(document.getElementById('almanac-modal'));}
function renderAlmanac(){
  const rows=almanacDailyRows(),seasons=deriveSeasons(rows,DATA.range||{}),records=derivePersonalRecords(rows),summary=summarizeAlmanacSnapshot(rows,seasons,records),observation=writeAlmanacObservation(summary),compared=observation.comparison,stories=buildCapsuleStories(observation,summary,seasons);_almanac={rows,seasons,records:compared,summary,observation,stories};
  const letter=document.getElementById('almanac-letter'),broken=compared.filter(record=>record.status==='broken');letter.innerHTML=observation.isBaseline?'<div class=almanac-seal>◉</div><div><span>FIRST OBSERVATION · 初次装订</span><b>年鉴已安静地记住这份快照</b><p>首次打开只建立基线，不会把旧数据假装成刚刚发生。下一份不同快照到来时，时间胶囊才会回信。</p></div>':'<div class="almanac-seal '+(broken.length?'lit':'')+'">'+(broken.length?'✦':'◉')+'</div><div><span>LETTER FROM '+esc(observation.previous?.coverage?.last_day||'PAST SNAPSHOT')+'</span><b>'+(broken.length?'过去的你目击了 '+broken.length+' 项新纪录':'旧纪录仍在星图中保持')+'</b><p>'+esc(stories[1]?.metric||'打开时间胶囊查看完整变化')+'</p></div>';
  document.getElementById('season-meta').textContent=seasons.length+' 个章节 · 月界或 ≥7 日静默切季';document.getElementById('season-rail').innerHTML=seasons.map((season,index)=>'<button type=button class=season-node data-season-index="'+index+'" role=option aria-selected="'+(index===0?'true':'false')+'" tabindex="'+(index===0?'0':'-1')+'" style="--season-color:'+(season.dominantModel?(DATA.colors[season.dominantModel]||'var(--accent)'):'var(--accent)')+';--season-span:'+Math.max(1,Math.min(5,season.spanDays/7)).toFixed(2)+'"><i></i><span>'+esc(season.character.label)+'</span><b>'+season.start.slice(5)+' → '+season.end.slice(5)+'</b><small>'+season.activeDays+' 日 · '+human(season.total)+'</small></button>').join('')||'<div class=ach-empty>当前报告没有活跃赛季。</div>';
  const maxHistory=Math.max(1,...compared.map(record=>Math.max(record.value,record.prior?.value||0)));document.getElementById('record-sky').innerHTML='<defs><radialGradient id="record-glow"><stop offset="0" stop-color="#fff"/><stop offset=".25" stop-color="#9fc1ff"/><stop offset="1" stop-color="#5b8def" stop-opacity="0"/></radialGradient></defs>'+compared.map((record,index)=>{const seed=almanacHash(record.id),x=42+seed%436,y=35+Math.floor(seed/521)%225,r=record.status==='broken'?7:4+Math.min(3,record.value/maxHistory*8);return '<g class="record-star '+record.status+'" data-record-index="'+index+'" role=button tabindex="'+(index===0?'0':'-1')+'" aria-label="'+esc(record.label+'，'+recordDisplay(record)+'，'+recordStatusLabel(record))+'"><circle class=halo cx="'+x+'" cy="'+y+'" r="'+(r*4)+'"/><circle class=core cx="'+x+'" cy="'+y+'" r="'+r+'"/><text x="'+(x+10)+'" y="'+(y+4)+'">'+esc(record.label)+'</text></g>';}).join('');
  document.getElementById('record-list').innerHTML=compared.map((record,index)=>'<button type=button data-record-index="'+index+'" tabindex="'+(index===0?'0':'-1')+'" class="record-chip '+record.status+'"><span>'+recordStatusLabel(record)+'</span><b>'+esc(record.label)+'</b><small>'+esc(recordDisplay(record))+'</small></button>').join('');document.getElementById('almanac-privacy').textContent='本地年鉴保存最多 '+ALMANAC_SNAPSHOT_LIMIT+' 份紧凑快照 / 作用域；不保存 cwd、session、标题或逐轮 Token。raw 与脱敏报告、固定日期范围和时区不会互相合并。';
  seasonCursor=Math.min(seasonCursor,Math.max(0,seasons.length-1));recordCursor=Math.min(recordCursor,Math.max(0,compared.length-1));focusSeason(seasonCursor,false);focusRecord(recordCursor,false);
}
function handleAlmanacNav(event,selector,index,activate){const items=[...document.querySelectorAll(selector)];if(!items.length)return;let next=null;if(event.key==='ArrowRight'||event.key==='ArrowDown')next=Math.min(items.length-1,index+1);else if(event.key==='ArrowLeft'||event.key==='ArrowUp')next=Math.max(0,index-1);else if(event.key==='Home')next=0;else if(event.key==='End')next=items.length-1;else if(event.key==='Enter'||event.key===' '){event.preventDefault();activate(index);return;}if(next!=null){event.preventDefault();activate(next);}}
document.getElementById('season-rail').addEventListener('click',event=>{const button=event.target.closest('[data-season-index]');if(button)focusSeason(Number(button.dataset.seasonIndex),false);});document.getElementById('season-rail').addEventListener('keydown',event=>{const button=event.target.closest('[data-season-index]');if(button)handleAlmanacNav(event,'.season-node',Number(button.dataset.seasonIndex),focusSeason);});
document.getElementById('record-sky').addEventListener('click',event=>{const node=event.target.closest('[data-record-index]');if(node)focusRecord(Number(node.dataset.recordIndex),false);});document.getElementById('record-sky').addEventListener('keydown',event=>{const node=event.target.closest('[data-record-index]');if(node)handleAlmanacNav(event,'#record-sky [data-record-index]',Number(node.dataset.recordIndex),focusRecord);});document.getElementById('record-list').addEventListener('click',event=>{const node=event.target.closest('[data-record-index]');if(node)focusRecord(Number(node.dataset.recordIndex),false);});document.getElementById('record-list').addEventListener('keydown',event=>{const node=event.target.closest('[data-record-index]');if(node)handleAlmanacNav(event,'#record-list [data-record-index]',Number(node.dataset.recordIndex),focusRecord);});
document.getElementById('almanac-open').addEventListener('click',openAlmanacCapsule);document.getElementById('almanac-x').addEventListener('click',closeAlmanacCapsule);document.getElementById('almanac-modal').addEventListener('click',event=>{if(event.target.id==='almanac-modal')closeAlmanacCapsule();});document.getElementById('almanac-modal').addEventListener('keydown',event=>{if(event.key==='ArrowLeft'&&event.target.tagName!=='BUTTON'){event.preventDefault();capsuleCursor=Math.max(0,capsuleCursor-1);renderCapsuleStory();}else if(event.key==='ArrowRight'&&event.target.tagName!=='BUTTON'){event.preventDefault();capsuleCursor=Math.min((_almanac?.stories.length||1)-1,capsuleCursor+1);renderCapsuleStory();}trapModalFocus(event,event.currentTarget);});document.getElementById('capsule-prev').addEventListener('click',()=>{capsuleCursor=Math.max(0,capsuleCursor-1);renderCapsuleStory();});document.getElementById('capsule-next').addEventListener('click',()=>{capsuleCursor=Math.min((_almanac?.stories.length||1)-1,capsuleCursor+1);renderCapsuleStory();});
document.getElementById('almanac-export').addEventListener('click',()=>{const store=readAlmanacStore(),scope=almanacScopeKey(),payload={version:ALMANAC_VERSION,exported_from:DATA.snapshot?.id||null,scope,almanac:store.scopes[scope]||null,privacy:'No cwd, session identifiers, titles, or per-turn series.'};downloadBlob(JSON.stringify(payload,null,2),'application/json;charset=utf-8','token-almanac.json');toast('本地年鉴已导出为 JSON');});document.getElementById('almanac-clear').addEventListener('click',()=>{if(!confirm('只清除 Token 年鉴的本地跨快照历史？主题、模块设置和成就基线不会被删除。'))return;try{localStorage.removeItem(ALMANAC_KEY);}catch(e){}renderAlmanac();toast('Token 年鉴历史已清除，并以当前快照重新建立基线');});

/* ---- 成就徽章（生成器：3000+ 枚，四等 + 隐藏 + 分类折叠）---- */
function tierFor(i,n){ const r=n<=1?1:i/Math.max(1,n-1); return r>=.85?'prismatic':r>=.6?'gold':r>=.35?'silver':'bronze'; }
function achievementSlug(value){return String(value).normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,'-').replace(/^-|-$/g,'')||'achievement';}
function mk(emoji, value, thresholds, unit, fmt, pool, secret){
  // 阶梯名称带序号，结构化字段让主页可显示当前值、目标与剩余量。
  return thresholds.map((v,i)=>({e:emoji,n:pool[i%pool.length]+' · '+String(i+1).padStart(2,'0'),d:fmt(v)+unit,tier:tierFor(i,thresholds.length),ok:value>=v,secret:!!secret,current:value,target:v,progress:v>0?Math.max(0,Math.min(1,value/v)):Number(value>=v),remaining:Math.max(0,v-value),direction:'at_least',thresholdIndex:i,thresholdCount:thresholds.length}));
}
const ACH_TRACKED=new Set(['累计 token','单日峰值','连续天数','累计活跃天','活跃小时数','模型种类','项目足迹','会话数量','调用次数','缓存读取量','单会话轮数','累计输入','累计输出','缓存写入']);
function generatedDate(){const raw=String(DATA.generated||'').slice(0,10),d=new Date(raw+'T12:00:00');return Number.isNaN(d.getTime())?new Date(0):d;}
function achievementSnapshots(){
  const daily=Object.fromEntries((DATA.achievement_daily||[]).map(x=>[x.day,x])),days=[...(DATA.day||[])].sort((a,b)=>a.period.localeCompare(b.period));
  let total=0,calls=0,cache=0,input=0,output=0,cacheWrite=0,activeDays=0,currentStreak=0,longestStreak=0,maxDay=0,maxTurns=0,previous=null;
  const hours=new Set(),models=new Set(),projects=new Set(),sessions=new Set(),sources={};
  return days.map(row=>{
    const day=row.period,detail=(DATA.day_details||{})[day]||{},extra=daily[day]||{};
    total+=row.total||0;calls+=row.calls||0;cache+=detail.cache_read||0;input+=extra.input||0;output+=extra.output||0;cacheWrite+=extra.cache_write||0;maxDay=Math.max(maxDay,row.total||0);maxTurns=Math.max(maxTurns,extra.max_turns||0);
    Object.keys(row.models||{}).forEach(m=>{if(row.models[m])models.add(m);});(detail.hourly||[]).forEach((v,h)=>{if(v)hours.add(h);});(detail.cwds||detail.top_cwds||[]).forEach(x=>projects.add(x[2]||x[0]));(detail.sessions||detail.top_sessions||[]).forEach(x=>sessions.add(x[2]||x[0]));Object.entries(extra.sources||{}).forEach(([source,value])=>sources[source]=(sources[source]||0)+value);
    if((row.total||0)>0){activeDays++;const expected=previous?new Date(previous+'T00:00:00'):null,actual=new Date(day+'T00:00:00');currentStreak=expected&&Math.round((actual-expected)/86400000)===1?currentStreak+1:1;longestStreak=Math.max(longestStreak,currentStreak);previous=day;}
    return {day,total,calls,cache,input,output,cacheWrite,activeDays,longestStreak,maxDay,maxTurns,hours:hours.size,models:models.size,projects:projects.size,sessions:sessions.size,sources:{...sources}};
  });
}
function achievementMetric(snapshot,category){
  if(!snapshot)return null;
  const map={'累计 token':'total','单日峰值':'maxDay','连续天数':'longestStreak','累计活跃天':'activeDays','活跃小时数':'hours','模型种类':'models','项目足迹':'projects','会话数量':'sessions','调用次数':'calls','缓存读取量':'cache','单会话轮数':'maxTurns','累计输入':'input','累计输出':'output','缓存写入':'cacheWrite'};
  if(map[category])return snapshot[map[category]];
  if(category.startsWith('来源 · '))return snapshot.sources[category.slice(5)]||0;
  return null;
}
function finalizeAchievements(cats){
  const snapshots=achievementSnapshots(),seen=new Set();
  cats.forEach(c=>c.items.forEach((b,index)=>{
    b.category=c.name;b.id=b.target!=null?achievementSlug(c.name)+':'+String(b.target):achievementSlug(c.name)+':'+achievementSlug(b.n)+':'+index;
    if(seen.has(b.id))b.id+=':'+index;seen.add(b.id);
    b.prestige='图鉴'+({bronze:'青铜',silver:'白银',gold:'黄金',prismatic:'彩钻'}[b.tier]||'青铜')+'阶位';
    b.thresholdRank=b.thresholdCount?Math.max(1,Math.round((b.thresholdCount-b.thresholdIndex)/b.thresholdCount*100)):null;
    b.nearEligible=!!(b.target!=null&&!b.secret&&(ACH_TRACKED.has(c.name)||c.name.startsWith('来源 · ')));
    if(b.ok&&b.target!=null&&(ACH_TRACKED.has(c.name)||c.name.startsWith('来源 · '))){const hit=snapshots.find(s=>achievementMetric(s,c.name)>=b.target);if(hit){b.unlockDay=hit.day;b.unlockPrecision=hit===snapshots[0]?'range-boundary':'range-day';}}
  }));
  return cats;
}
const POOL_BIG=['初窥门径','初出茅庐','渐入佳境','小试牛刀','初露锋芒','小有所成','炉火纯青','驾轻就熟','游刃有余','登堂入室','十万火急','名声大噪','百万富翁','声名鹊起','日进斗金','富甲一方','千万大咖','名震江湖','亿万身家','一方霸主','登峰造极','富可敌国','名扬四海','威震天下','通天代','权倾朝野','宇宙级','神话','超凡入圣','不可名状','超脱','永恒','无尽','太初','混沌','虚无','归零','重启','飞升','涅槃'];
const POOL_STREAK=['初心','坚持','小成','连胜','热身','入门','上进','勤奋','刻苦','钻研','精通','大成','宗师','泰斗','传奇','不朽','一鼓作气','再接再厉','持之以恒','锲而不舍','水滴石穿','铁杵磨针','日复一日','年复一年','春秋不辍','冬夏无休','雷打不动','风雨无阻','马不停蹄','日夜兼程'];
const POOL_DAYS=['启程','起步','摸鱼','上手','入坑','沉迷','习惯','日常','本能','呼吸','熔铸','刻入DNA','老用户','熟客','常客','元老','资深','骨灰','活化石','传说玩家'];
const POOL_RATIO=['入门','及格','顺手','熟练','老练','精通','大成','化境','登顶','极限','极致','圆满'];
const WD=['周一','周二','周三','周四','周五','周六','周日'];
const WD_PERSONA=['Monday Blue','周二综合征','周三墙','小周末','TGIF','周末战士','周日恐慌'];
function almanacTrendMetrics(days,data=DATA){
  const generatedDay=String(data.generated||'').slice(0,10),until=data.range?.until,anchor=until&&until<generatedDay?until:generatedDay,totalsByDay=new Map(days.filter(day=>day.period!==generatedDay||!(!until||until>=generatedDay)).map(day=>[day.period,day.total||0])),first=data.range?.since||[...totalsByDay.keys()].sort()[0],endDate=new Date(anchor+'T00:00:00');
  if(!until||until>=generatedDay)endDate.setDate(endDate.getDate()-1);
  const totals=[];if(first&&!Number.isNaN(endDate.getTime())){const cursor=new Date(first+'T00:00:00');while(cursor<=endDate){const period=cursor.getFullYear()+'-'+String(cursor.getMonth()+1).padStart(2,'0')+'-'+String(cursor.getDate()).padStart(2,'0');totals.push(totalsByDay.get(period)||0);cursor.setDate(cursor.getDate()+1);}}
  const sum=values=>values.reduce((total,value)=>total+value,0),average=values=>values.length?sum(values)/values.length:0,recent7=totals.slice(-7),prior7=totals.slice(-14,-7),avg7=average(recent7),avg30=average(totals.slice(-30)),momentum=recent7.length===7&&prior7.length===7&&average(prior7)>0?avg7/average(prior7)-1:0;
  let growthStreak=0,declineStreak=0;for(let index=totals.length-1;index>0;index--){if(totals[index]>totals[index-1]&&!declineStreak)growthStreak++;else if(totals[index]<totals[index-1]&&!growthStreak)declineStreak++;else break;}
  return {avg7,avg30,momentum,growthStreak,declineStreak,completeDays:totals.length};
}
function getBadgeData(){
  const h=DATA.hourly||[]; let peak=-1; for(let i=0;i<24;i++)if((h[i]||0)>(h[peak]||0))peak=i;
  const hoursActive=(h||[]).filter(x=>x>0).length;
  const days=DATA.day||[], total=days.reduce((a,d)=>a+(d.total||0),0), calls=days.reduce((a,d)=>a+(d.calls||0),0), cr=DATA.cache_read||0, cRatio=total?cr/total:0, models=DATA.models.length;
  const dayCount=days.length, maxDay=Math.max(0,...days.map(d=>d.total));
  const streak=longestActiveStreak(days);
  const nCwds=DATA.n_cwds||0, nSess=DATA.n_sessions||0, maxTurns=DATA.max_turns||0;
  const avgPerDay=dayCount?total/dayCount:0;
  const AS=DATA.achievement_stats||{}, inputTotal=AS.input||0, outputTotal=AS.output||0, cacheWrite=AS.cache_write||0;
  const sessTotals=AS.session_totals||[], cwdTotals=AS.cwd_totals||[], sourceTotals=AS.source_totals||{}, modelStats=AS.model_stats||{};
  const sortedDays=days.map(d=>d.total||0), sumA=a=>a.reduce((x,y)=>x+y,0), avgA=a=>a.length?sumA(a)/a.length:0;
  const median=a=>{if(!a.length)return 0;const s=[...a].sort((x,y)=>x-y),i=Math.floor(s.length/2);return s.length%2?s[i]:(s[i-1]+s[i])/2;};
  const variance=a=>{const av=avgA(a);return a.length?avgA(a.map(x=>(x-av)*(x-av))):0;};
  const avgSession=nSess?total/nSess:0, avgProject=nCwds?total/nCwds:0, maxSession=sessTotals[0]||0, medSession=median(sessTotals), maxProject=cwdTotals[0]||0;
  const tokensPerCall=calls?total/calls:0, callsPerDay=dayCount?calls/dayCount:0, sessionsPerDay=dayCount?nSess/dayCount:0;
  const dailyCV=avgPerDay?Math.sqrt(variance(sortedDays))/avgPerDay:0;
  const {avg7,avg30,momentum,growthStreak,declineStreak}=almanacTrendMetrics(days);
  const hTotal=sumA(h), hRatio=(a,b)=>hTotal?sumA(h.slice(a,b))/hTotal:0;
  const nightRatio=(sumA(h.slice(0,6))+sumA(h.slice(22)))/(hTotal||1), morningRatio=hRatio(6,11), workRatio=hRatio(9,18), eveningRatio=hRatio(18,22);
  const activeHours=h.filter(v=>v>0), hourlySpan=activeHours.length, maxHour=Math.max(0,...h), avgActiveHour=avgA(activeHours);
  const modelTotals={}; days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>modelTotals[m]=(modelTotals[m]||0)+v));
  const modelVals=Object.values(modelTotals), topModelShare=total&&modelVals.length?Math.max(...modelVals)/total:0;
  const modelHHI=total?modelVals.reduce((a,v)=>a+(v/total)*(v/total),0):0;
  const denseLog=(lo,hi,n)=>Array.from({length:n},(_,i)=>Math.round(lo*Math.pow(hi/lo,i/Math.max(1,n-1))));
  const denseLinear=(lo,hi,n)=>Array.from({length:n},(_,i)=>lo+(hi-lo)*i/Math.max(1,n-1));
  const pushLadder=(name,e,value,thresholds,unit,formatter,pool=POOL_BIG,secret=false)=>cats.push({name,e,items:mk(e,value,[...new Set(thresholds)],unit,formatter,pool,secret)});

  const wd=[0,0,0,0,0,0,0], mo=[0,0,0,0,0,0,0,0,0,0,0,0];
  days.forEach(d=>{ const p=d.period.split('-'); const dt=new Date(Date.UTC(+p[0],+p[1]-1,+p[2])); wd[(dt.getUTCDay()+6)%7]+=d.total; mo[(+p[1]-1)]+=d.total; });
  const fmtT=v=>human(v);
  const tok=denseLog(1e3,1e14,72);
  const dayTok=denseLog(1e3,1e12,48);
  const streaks=[...Array.from({length:30},(_,i)=>i+1),...Array.from({length:35},(_,i)=>(i+7)*5),365,400,500,600,666,730,888,1000];
  const daysList=[...Array.from({length:30},(_,i)=>i+1),...Array.from({length:40},(_,i)=>(i+7)*5),250,300,365,500,666,730,888,1000,1500,2000];
  const hours=Array.from({length:24},(_,i)=>i+1);
  const modelsList=[...Array.from({length:20},(_,i)=>i+1),25,30,40,50,60,75,100,150,200];
  const cwdsList=[...Array.from({length:20},(_,i)=>i+1),25,30,40,50,75,100,150,200,300,500];
  const sessList=denseLog(1,10000,48);
  const callList=denseLog(10,1e8,52);
  const ratioList=[...Array.from({length:20},(_,i)=>(i+1)*.025),...Array.from({length:19},(_,i)=>.5+(i+1)*.025),.98,.99,.995,.999];
  const turnsList=denseLog(5,50000,42);
  const cacheAbs=denseLog(1e3,1e14,52);
  const avgList=denseLog(1e3,1e11,44);

  let cats=[];
  cats.push({name:'累计 token',e:'📈',items:mk('📈',total,tok,' tk',fmtT,POOL_BIG)});
  cats.push({name:'单日峰值',e:'📅',items:mk('📅',maxDay,dayTok,' /日',fmtT,POOL_BIG)});
  cats.push({name:'连续天数',e:'⚡',items:mk('⚡',streak,streaks,' 天',v=>v,POOL_STREAK)});
  cats.push({name:'累计活跃天',e:'🗓️',items:mk('🗓️',dayCount,daysList,' 天',v=>v,POOL_DAYS)});
  cats.push({name:'活跃小时数',e:'🕐',items:mk('🕐',hoursActive,hours,' 小时',v=>v,POOL_RATIO)});
  cats.push({name:'模型种类',e:'🎲',items:mk('🎲',models,modelsList,' 模型',v=>v,POOL_RATIO)});
  cats.push({name:'项目足迹',e:'📁',items:mk('📁',nCwds,cwdsList,' 项目',v=>v,POOL_DAYS)});
  cats.push({name:'会话数量',e:'💬',items:mk('💬',nSess,sessList,' 会话',v=>v,POOL_DAYS)});
  cats.push({name:'调用次数',e:'🔔',items:mk('🔔',calls,callList,' 次',fmtT,POOL_BIG)});
  cats.push({name:'缓存命中',e:'💎',items:mk('💎',cRatio,ratioList,'% 量',v=>(v*100).toFixed(0),POOL_RATIO)});
  cats.push({name:'缓存读取量',e:'🧊',items:mk('🧊',cr,cacheAbs,' tk',fmtT,POOL_BIG)});
  cats.push({name:'单会话轮数',e:'🦠',items:mk('🦠',maxTurns,turnsList,' 轮',v=>v,POOL_STREAK)});
  cats.push({name:'日均 token',e:'⚖️',items:mk('⚖️',avgPerDay,avgList,' /日均',fmtT,POOL_BIG)});
  pushLadder('累计输入','📥',inputTotal,denseLog(1e3,1e14,54),' 输入',fmtT);
  pushLadder('累计输出','📤',outputTotal,denseLog(1e3,1e13,50),' 输出',fmtT);
  pushLadder('缓存写入','🧬',cacheWrite,denseLog(1e3,1e13,46),' 写缓存',fmtT);
  pushLadder('每次调用密度','🧱',tokensPerCall,denseLog(10,1e8,42),' tk/次',fmtT);
  pushLadder('每日调用密度','🔔',callsPerDay,denseLog(1,1e5,38),' 次/日',v=>Number(v).toFixed(v<10?1:0),POOL_STREAK);
  pushLadder('平均会话体量','💬',avgSession,denseLog(100,1e10,46),' tk/会话',fmtT);
  pushLadder('会话中位数','🪨',medSession,denseLog(100,1e10,42),' tk 中位',fmtT);
  pushLadder('最大会话','🐋',maxSession,denseLog(1e3,1e12,48),' tk/会话',fmtT);
  pushLadder('每日会话密度','🫧',sessionsPerDay,denseLog(.1,1e3,34),' 会话/日',v=>Number(v).toFixed(v<10?1:0),POOL_RATIO);
  pushLadder('平均项目体量','🏗️',avgProject,denseLog(1e3,1e12,42),' tk/项目',fmtT);
  pushLadder('最大项目','🏰',maxProject,denseLog(1e3,1e13,44),' tk/项目',fmtT);
  // 趋势、节奏与集中度阶梯
  pushLadder('夜猫指数','🌙',nightRatio,denseLinear(.025,1,40),' 夜间',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('晨光指数','🌅',morningRatio,denseLinear(.025,1,36),' 清晨',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('工时集中度','💼',workRatio,denseLinear(.025,1,36),' 日间',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('黄昏指数','🌆',eveningRatio,denseLinear(.025,1,34),' 晚间',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('波动指数','🌊',dailyCV,denseLinear(.05,3,36),' CV',v=>Number(v).toFixed(2),POOL_RATIO);
  pushLadder('增长连击','📶',growthStreak,Array.from({length:30},(_,i)=>i+1),' 天连涨',v=>v,POOL_STREAK);
  pushLadder('回落连击','📉',declineStreak,Array.from({length:30},(_,i)=>i+1),' 天连降',v=>v,POOL_STREAK);
  pushLadder('近期加速度','🚀',Math.max(0,momentum),denseLinear(.025,5,40),' 增速',v=>'+'+(v*100).toFixed(1)+'%',POOL_BIG);
  pushLadder('七日均值','7️⃣',avg7,denseLog(1e3,1e11,42),' /近7日',fmtT);
  pushLadder('三十日均值','🗓️',avg30,denseLog(1e3,1e11,42),' /近30日',fmtT);
  pushLadder('活跃小时跨度','🧭',hourlySpan,Array.from({length:24},(_,i)=>i+1),' 个时段',v=>v,POOL_DAYS);
  pushLadder('单小时峰值','⚡',maxHour,denseLog(100,1e11,44),' /小时',fmtT);
  pushLadder('活跃小时均值','⌛',avgActiveHour,denseLog(100,1e10,40),' /活跃小时',fmtT);
  pushLadder('主力模型占比','👑',topModelShare,denseLinear(.05,1,38),' 占比',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('模型专注指数','🎯',modelHHI,denseLinear(.05,1,38),' HHI',v=>Number(v).toFixed(2),POOL_RATIO);

  // 星期 × 小时：每一个星期时刻都是独立可收集坐标
  const wdHour=Array.from({length:7},()=>Array(24).fill(0));
  days.forEach(d=>{const x=DATA.day_details[d.period],p=d.period.split('-'),dt=new Date(Date.UTC(+p[0],+p[1]-1,+p[2])),w=(dt.getUTCDay()+6)%7;if(x)(x.hourly||[]).forEach((v,hour)=>wdHour[w][hour]+=v||0);});
  const wdHourItems=[]; const WHT=[1e2,1e3,1e4,1e5];
  WD.forEach((day,w)=>{for(let hour=0;hour<24;hour++)WHT.forEach((v,i)=>wdHourItems.push({e:['·','▪','◆','✦'][i],n:day+' '+String(hour).padStart(2,'0')+'点·'+['微光','点亮','炽热','恒星'][i],d:day+' '+String(hour).padStart(2,'0')+':00 累计 '+fmtT(v)+' tk',tier:tierFor(i,WHT.length),ok:wdHour[w][hour]>=v,secret:i>=3}));});
  cats.push({name:'星期时空坐标',e:'🧿',items:wdHourItems});

  // 月份 × 四时段
  const moBand=Array.from({length:12},()=>Array(4).fill(0)), bands=[[0,6,'深夜'],[6,12,'晨午'],[12,18,'午后'],[18,24,'晚间']];
  days.forEach(d=>{const x=DATA.day_details[d.period],mon=Number(d.period.slice(5,7))-1;if(x)bands.forEach(([a,b],bi)=>moBand[mon][bi]+=sumA((x.hourly||[]).slice(a,b)));});
  const moBandItems=[];for(let m=0;m<12;m++)bands.forEach((band,bi)=>[1e3,1e5,1e7,1e9].forEach((v,i)=>moBandItems.push({e:['🌑','🌓','🌕','☀️'][i],n:(m+1)+'月·'+band[2]+'·'+['初响','回声','盛放','传说'][i],d:(m+1)+'月 '+band[2]+'累计 '+fmtT(v)+' tk',tier:tierFor(i,4),ok:moBand[m][bi]>=v,secret:i===3})));
  cats.push({name:'月份四时',e:'🌗',items:moBandItems});

  // 模型 × 时段人格
  const modelBandItems=[];Object.entries(modelStats).forEach(([m,ms],mi)=>{const mh=Array(24).fill(0);Object.values(DATA.day_details||{}).forEach(x=>{const a=(x.hourly_models||{})[m]||[];a.forEach((v,i)=>mh[i]+=v||0);});bands.forEach(([a,b,nm],bi)=>{const v=sumA(mh.slice(a,b));[1e3,1e5,1e7].forEach((th,i)=>modelBandItems.push({e:'🤖',n:pretty(m)+'·'+nm+'·'+['邂逅','搭档','灵魂'][i],d:pretty(m)+' 在'+nm+'累计 '+fmtT(th)+' tk',tier:tierFor(i,3),ok:v>=th,secret:i===2}));});});
  cats.push({name:'模型时段羁绊',e:'🪢',items:modelBandItems});

  // 来源阶梯
  Object.entries(sourceTotals).forEach(([src,v])=>pushLadder('来源 · '+src,'📡',v,denseLog(1e3,1e13,36),' tk',fmtT,POOL_BIG));

  // 组合成就：总量、缓存、连续、模型、会话彼此交叉
  const combo=[];
  const totalBands=[1e5,1e6,1e7,1e8,1e9,1e10], cacheBands=[.1,.3,.5,.7,.9];
  totalBands.forEach((tv,ti)=>cacheBands.forEach((cv,ci)=>combo.push({e:'⚗️',n:'算力炼金·'+(ti+1)+'-'+(ci+1),d:'累计 '+fmtT(tv)+' 且缓存率 '+Math.round(cv*100)+'%',tier:tierFor(ti+ci,totalBands.length+cacheBands.length),ok:total>=tv&&cRatio>=cv,secret:ci>=3})));
  [3,7,14,30,60,100].forEach((sv,si)=>[1e5,1e6,1e7,1e8,1e9].forEach((tv,ti)=>combo.push({e:'🔥',n:'长燃引擎·'+sv+'×'+(ti+1),d:'连续 '+sv+' 天且累计 '+fmtT(tv),tier:tierFor(si+ti,10),ok:streak>=sv&&total>=tv,secret:si>=4})));
  [1,2,3,5,8,12].forEach((mv,mi)=>[10,50,100,500,1000].forEach((sv,si)=>combo.push({e:'🧩',n:'多元宇宙·'+mv+'×'+sv,d:'使用 '+mv+' 模型且拥有 '+sv+' 会话',tier:tierFor(mi+si,10),ok:models>=mv&&nSess>=sv,secret:mi>=4})));
  cats.push({name:'复合炼金术',e:'⚗️',items:combo});

  // 24 时刻 × 量级矩阵
  const hourItems=[]; const htok=[1e2,1e3,1e4,1e5,1e6];
  for(let hr=0;hr<24;hr++){ htok.forEach((v,i)=>{ const name=['夜巡','更夫','守夜','夜神','夜之王'][i]; hourItems.push({e:'🕒',n:String(hr).padStart(2,'0')+'点·'+name,d:String(hr).padStart(2,'0')+':00 烧 '+fmtT(v)+' tk',tier:tierFor(i,htok.length),ok:(h[hr]||0)>=v,secret:i>=3}); }); }
  cats.push({name:'时刻战士',e:'🕒',items:hourItems});
  // 星期矩阵
  const wdItems=[]; const wdt=[1e4,1e6,1e8,1e10]; WD.forEach((nm,w)=> wdt.forEach((v,i)=> wdItems.push({e:'▮',n:nm+['·学徒','·常客','·狂魔','·化身'][i],d:nm+'累计 '+fmtT(v)+' tk',tier:tierFor(i,wdt.length),ok:wd[w]>=v})) );
  cats.push({name:'星期人格',e:'📆',items:wdItems});
  // 月份矩阵
  const moItems=[]; const mot=[1e5,1e7,1e9]; for(let m=0;m<12;m++) mot.forEach((v,i)=> moItems.push({e:'🌙',n:(m+1)+'月'+['·起势','·丰收','·封神'][i],d:(m+1)+'月累计 '+fmtT(v)+' tk',tier:tierFor(i,mot.length),ok:mo[m]>=v}));
  cats.push({name:'月份里程碑',e:'🌙',items:moItems});
  // 每个用过模型一枚
  const modelItems=(DATA.models||[]).map((m,i)=>{const tot=days.reduce((a,d)=>a+((d.models[m])||0),0);return {e:'🤖',n:pretty(m)+'用户',d:'用过 '+pretty(m),tier:tierFor(i,Math.max(1,DATA.models.length)),ok:tot>0};});
  cats.push({name:'模型图鉴',e:'🤖',items:modelItems});

  // ---- 奇思妙想 / 隐藏彩蛋 ----
  const SE=[];
  const has=v=>total>=v;
  // 数字彩蛋
  const eggs=[
    [42,'宇宙答案'],[64,'六十四位'],[128,'半字节军团'],[256,'像素方阵'],[404,'成就未找到'],[418,'我是茶壶'],[451,'不可用'],[500,'服务器冒烟'],[520,'我爱你'],[666,'恶魔契约'],[777,'幸运七'],[888,'发发发'],[999,'长长久久'],[1024,'一千零二十四'],[1314,'一生一世'],[1337,'Leet'],[2048,'合成玩家'],[4096,'页大小'],[5200,'我爱你加长版'],[7777,'老虎机'],[8192,'八千字节'],[9000,'Over 9000'],[10000,'万事开头'],[16384,'十六K'],[23333,'笑出声'],[32768,'有符号边界'],[65535,'端口之王'],[65536,'无符号飞升'],[66666,'六六大顺'],[88888,'暴富预兆'],[99999,'九九归一'],[111111,'全一教'],[123456,'顺子'],[161803,'黄金比'],[271828,'自然底'],[314159,'圆周率'],[524288,'半兆'],[654321,'倒顺子'],[666666,'六道轮回'],[777777,'七星连珠'],[888888,'一路发'],[999999,'无限逼近'],[1048576,'一兆门槛'],[1234567,'连续升级'],[16777216,'真彩色'],[5201314,'真爱粉'],[10000000,'千万俱乐部'],[16777215,'RGB 白'],[33554432,'三十二兆'],[100000000,'亿万先生'],[1073741824,'一吉字节'],[2147483647,'整数之巅'],[4294967295,'无符号边界']
  ];
  eggs.forEach(([v,nm])=>SE.push({e:'🎰',n:nm,d:'token 含 / 达到 '+fmtT(v),tier:'gold',ok:has(v)||String(total).includes(String(v)),secret:true}));
  // 单日数字蛋
  [[666666,'单日六六六'],[888888,'单日发发发'],[50000000,'单日五千万'],[100000000,'单日破亿']].forEach(([v,nm])=>SE.push({e:'🥚',n:nm,d:'单日达到 '+fmtT(v),tier:'gold',ok:maxDay>=v,secret:true}));
  // 时段人格（按峰值）
  const persona=[['🌅','破晓行者',5,8],['☕','早C战士',8,11],['🍱','午间摸鱼',11,14],['🍵','下午茶王',14,18],['🌆','黄昏斗士',18,21],['🌙','夜行者',21,24],['🦉','修仙党',0,5]];
  persona.forEach(([e,nm,a,b])=>SE.push({e,n:nm,d:'峰值在 '+a+'-'+b+' 点',tier:'silver',ok:peak>=a&&peak<b}));
  SE.push({e:'🕛',n:'子夜战神',d:'峰值恰在 0 点',tier:'gold',ok:peak===0,secret:true});
  SE.push({e:'🐓',n:'晨型人',d:'峰值在 6 点',tier:'silver',ok:peak===6,secret:true});
  // 星期人格
  WD_PERSONA.forEach((nm,w)=>SE.push({e:'📆',n:nm,d:'用量最高的是 '+WD[w],tier:'silver',ok: wd[w]===Math.max(...wd)&&Math.max(...wd)>0,secret:w<5}));
  // 周末战士
  const wkend=wd[5]+wd[6], wkdayAvg=(wd[0]+wd[1]+wd[2]+wd[3]+wd[4])/(5||1);
  SE.push({e:'🏄',n:'周末战士',d:'周末日均 > 工作日',tier:'gold',ok:wkend/2>wkdayAvg,secret:true});
  SE.push({e:'💼',n:'打工人',d:'工作日 > 周末',tier:'silver',ok:wkdayAvg>wkend/2,secret:true});
  // 全天候 / 极端
  SE.push({e:'🌍',n:'全天候',d:'24 小时都有用量',tier:'gold',ok:hoursActive>=24});
  SE.push({e:'🎯',n:'专一',d:'只用 1 个模型',tier:'bronze',ok:models===1});
  SE.push({e:'🌈',n:'万花筒',d:'用过 ≥5 模型',tier:'gold',ok:models>=5});
  SE.push({e:'🦠',n:'话痨',d:'单会话 ≥500 轮',tier:'gold',ok:maxTurns>=500,secret:true});
  SE.push({e:'🗂️',n:'多面手',d:'≥5 个项目',tier:'silver',ok:nCwds>=5});
  SE.push({e:'🐢',n:'龟速',d:'日均 <1 万',tier:'bronze',ok:avgPerDay<1e4&&dayCount>5,secret:true});
  SE.push({e:'🚀',n:'爆发',d:'单日占总量 ≥40%',tier:'gold',ok:maxDay>=total*0.4&&total>0,secret:true});
  // 编程梗（接真实条件）
  const TR=[
    ['👋','Hello World', total>=1e4],['🐛','捉虫能手', calls>=1000],['🧹','洁癖', cRatio>=0.9],['💀','rm -rf 幸存者', total>=1e8],
    ['🌀','无限循环', streak>=30],['📦','囤积狂', nCwds>=30],['🤡','摸鱼王', streak<3 && dayCount>10],['🎲','随机种子', models>=4],
    ['🧊','冷启动', cRatio<0.1 && total>1e5],['🔥','热加载', cRatio>=0.99],['🪦','坟墓', nSess>=100],['⚙️','CRUD 战神', calls>=1e4],
    ['🧪','实验狂', nCwds>=10],['🪄','魔法师', maxTurns>=1000],['🦆','鸭子调试', peak>=0&&peak<4],['🎈','内存泄漏', nSess>=500],
    ['🧭','导航员', nCwds>=20],['🍄','蘑菇', peak>=0&&peak<4],['🛷','滑坡', streak<dayCount-5 && dayCount>20],['🎨','调色板', models>=6],
    ['🧩','拼图', nCwds>=15],['🔭','观星者', hoursActive>=20],['🦾','钢铁肝', total>=5e7],['🧠','脑力劳动者', calls>=5000],
    ['🍔','外卖续命', peak>=22||peak<2],['💤','失眠', hoursActive>=22],['🪞','照镜子', models===1],['🎵','单曲循环', models===1 && total>1e6],
    ['🧶','乱麻', nCwds>=40],['🏹','神射手', cRatio>=0.85],
    ['🌃','赛博夜行人',nightRatio>=.5],['🌄','朝九之前',morningRatio>=.5],['🏢','标准工时',workRatio>=.65],['🌆','下班才上班',eveningRatio>=.5],
    ['🎢','过山车',dailyCV>=1.5],['🧘','稳定发挥',dailyCV<=.15&&dayCount>=7],['📈','牛市',growthStreak>=7],['📉','熊市',declineStreak>=7],
    ['🚄','高速迭代',momentum>=1],['🪶','轻量会话',avgSession>0&&avgSession<1e4],['🐘','重量级会话',avgSession>=1e7],['🐋','利维坦会话',maxSession>=1e9],
    ['🏙️','项目都市',nCwds>=100],['🌌','项目星系',nCwds>=500],['💬','群聊现场',sessionsPerDay>=20],['🔕','静默少言',sessionsPerDay<1&&dayCount>=7],
    ['🥇','一枝独秀',topModelShare>=.9],['🤹','左右开弓',models>=2&&topModelShare<.65],['🌈','模型联合国',models>=8],['🎯','极致专注',modelHHI>=.95],
    ['🫧','均匀分布',modelHHI<=.3&&models>=4],['📥','海纳百川',inputTotal>=1e9],['📤','滔滔不绝',outputTotal>=1e8],['🧬','缓存播种者',cacheWrite>=1e8],
    ['🧱','上下文长城',tokensPerCall>=1e6],['⚡','闪电问答',tokensPerCall<1e3&&calls>=100],['🧺','批处理大师',callsPerDay>=1000],['🕰️','长线主义',dayCount>=365],
    ['🪄','Prompt 巫师',outputTotal>inputTotal],['📚','上下文图书馆',inputTotal>=outputTotal*20&&outputTotal>0],['♻️','循环利用',cr>inputTotal],['🧯','缓存灭火器',cRatio>=.95&&total>=1e7],
    ['🧑‍🚀','全栈宇航员',nCwds>=20&&models>=5&&hoursActive>=18],['🧑‍💻','真正的程序员',nightRatio>=.4&&calls>=10000],['☕','咖啡编译器',h[9]>0&&h[14]>0&&h[21]>0],['🍜','泡面时区',h[0]+h[1]+h[2]>=hTotal*.25],
    ['🧿','零点观测站',h[0]>=maxHour*.8&&maxHour>0],['🐓','早起提交',h[6]>=maxHour*.8&&maxHour>0],['🥪','午休提交',h[12]+h[13]>=hTotal*.2],['🌇','晚高峰提交',h[18]+h[19]>=hTotal*.25],
    ['📆','周一启动器',wd[0]===Math.max(...wd)],['🎉','周五释放',wd[4]===Math.max(...wd)],['🏖️','双休日构建',wd[5]+wd[6]>(sumA(wd.slice(0,5))/5)*2],['🛠️','工作日机器',sumA(wd.slice(0,5))>=sumA(wd.slice(5))*4],
    ['🔬','微服务人格',avgProject<1e6&&nCwds>=10],['🗿','单体巨石',maxProject>=total*.8&&nCwds>0],['🪐','多项目轨道',nCwds>=50&&maxProject<total*.3],['🧳','项目旅行家',nCwds>=dayCount&&dayCount>10],
    ['🎛️','参数调优师',models>=3&&cRatio>=.7],['🔋','满电运行',streak>=100&&hoursActive>=18],['🕳️','Token 黑洞',maxDay>=1e9],['🌋','单日喷发',maxDay>=avgPerDay*8&&dayCount>=7],
    ['🧊','绝对零度',total===0],['🌱','第一粒 Token',total>0],['🛤️','万里长征',dayCount>=1000],['🏛️','数字文明',total>=1e12]
  ];
  TR.forEach(([e,nm,ok])=>SE.push({e,n:nm,d:nm,tier:'silver',ok,secret:true}));
  // 星座/生肖（按生成日期，必解锁其一）
  const ZODIAC=[['♈','白羊'],['♉','金牛'],['♊','双子'],['♋','巨蟹'],['♌','狮子'],['♍','处女'],['♎','天秤'],['♏','天蝎'],['♐','射手'],['♑','摩羯'],['♒','水瓶'],['♓','双鱼']];
  const gd=generatedDate(), gm=gd.getMonth()+1, gday=gd.getDate();
  const zidx=(gm===12&&gday>=22)||gm<=1&&gday<20?9:gm<=2?10:gm<=3?11:gm<=4?0:gm<=5?1:gm<=6?2:gm<=7?3:gm<=8?4:gm<=9?5:gm<=10?6:gm<=11?7:8;
  ZODIAC.forEach((z,i)=>SE.push({e:z[0],n:'星座·'+z[1],d:'今日星座 '+z[1],tier:'bronze',ok:i===zidx}));
  const SX=['🐀鼠','🐂牛','🐅虎','🐇兔','🐉龙','🐍蛇','🐎马','🐐羊','🐒猴','🐓鸡','🐕狗','🐖猪'];
  const sxIdx=(gd.getFullYear()-4)%12;
  SX.forEach((s,i)=>SE.push({e:'🔮',n:'生肖·'+s,d:'今年生肖 '+s,tier:'bronze',ok:i===sxIdx}));
  // 节日（按 mm-dd）
  const fest=[['01-01','元旦'],['02-14','情人节'],['03-08','妇女节'],['03-14','圆周率日'],['04-01','愚人节'],['04-22','地球日'],['05-01','劳动节'],['05-04','青年节'],['05-17','电信日'],['06-01','儿童节'],['07-01','建党节'],['07-17','世界 Emoji 日'],['08-15','抗战胜利'],['09-10','教师节'],['09-13','程序员节'],['10-01','国庆'],['10-24','程序员节 1024'],['10-31','万圣节'],['11-11','双十一'],['12-24','平安夜'],['12-25','圣诞节']];
  const today=String(gm).padStart(2,'0')+'-'+String(gday).padStart(2,'0');
  fest.forEach(([d,nm])=>SE.push({e:'🎉',n:'节日·'+nm,d:'在 '+nm+' 跑了统计',tier:'silver',ok:d===today,secret:true}));
  const solar=['小寒','大寒','立春','雨水','惊蛰','春分','清明','谷雨','立夏','小满','芒种','夏至','小暑','大暑','立秋','处暑','白露','秋分','寒露','霜降','立冬','小雪','大雪','冬至'];
  const todayOrdinal=Math.floor(Date.UTC(gd.getFullYear(),gd.getMonth(),gd.getDate())/86400000);
  solar.forEach((nm,i)=>{const target=Math.round(i*365/24),now=todayOrdinal-Math.floor(Date.UTC(gd.getFullYear(),0,1)/86400000);SE.push({e:'🌿',n:'节气·'+nm,d:'在'+nm+'附近生成报告',tier:i%6===0?'gold':'bronze',ok:Math.abs(now-target)<=2,secret:true});});
  const dateEggs=[['镜像日期',today.split('-').join('')===today.split('-').join('').split('').reverse().join('')],['双数之日',/[02468]{4}/.test(today.replace('-',''))],['幸运七日',today.includes('07')],['六六之日',today.includes('06')],['八八之日',today.includes('08')],['连续日期',/123|234|345|456|567|678|789/.test(today.replace('-',''))],['月日相同',gm===gday],['月末守望',gday===new Date(gd.getFullYear(),gm,0).getDate()]];
  dateEggs.forEach(([nm,ok])=>SE.push({e:'📟',n:nm,d:'生成日期触发：'+nm,tier:'silver',ok,secret:true}));
  cats.push({name:'奇思妙想 · 隐藏',e:'✨',items:SE});

  const finalized=finalizeAchievements(cats),ALL=[].concat(...finalized.map(c=>c.items));
  const got=ALL.filter(b=>b.ok).length;
  return {cats:finalized, all:ALL, got, pct: ALL.length? got/ALL.length:0};
}
function achievementDateLabel(b){if(!b.unlockDay)return '解锁日期不可从当前聚合数据还原';return b.unlockPrecision==='range-boundary'?'报告范围开始时已达成':'本报告范围内首次达到 '+b.unlockDay;}
function achievementTimeline(all){
  const groups={};all.filter(b=>b.ok&&b.unlockDay).forEach(b=>{const key=b.category+'|'+b.unlockDay,current=groups[key];if(!current||({bronze:0,silver:1,gold:2,prismatic:3}[b.tier]||0)>({bronze:0,silver:1,gold:2,prismatic:3}[current.tier]||0)||(b.target||0)>(current.target||0))groups[key]=Object.assign({},b,{crossed:(current?.crossed||0)+1});else current.crossed=(current.crossed||1)+1;});
  return Object.values(groups).sort((a,b)=>b.unlockDay.localeCompare(a.unlockDay)||({prismatic:3,gold:2,silver:1,bronze:0}[b.tier]-{prismatic:3,gold:2,silver:1,bronze:0}[a.tier]));
}
function nextAchievementGoals(all){
  const byCategory={};all.filter(b=>!b.ok&&b.nearEligible).forEach(b=>{if(!byCategory[b.category]||(b.target||Infinity)<byCategory[b.category].target)byCategory[b.category]=b;});
  return Object.values(byCategory).sort((a,b)=>b.progress-a.progress||({prismatic:3,gold:2,silver:1,bronze:0}[b.tier]-{prismatic:3,gold:2,silver:1,bronze:0}[a.tier])||(a.target-b.target)).slice(0,3);
}
function achievementScopeKey(){return 'v2|'+(DATA.anonymized?'anon':'raw')+'|'+(DATA.source||[]).join(',')+'|'+(DATA.range?.since||'all');}
function compareAchievementSnapshot(all){
  const key='tk-achievements-v2',scope=achievementScopeKey(),generated=String(DATA.generated||''),ids=all.filter(b=>b.ok).map(b=>b.id),fresh=new Set();let store={};
  try{store=JSON.parse(localStorage.getItem(key)||'{}')||{};}catch(e){}
  const previous=store[scope];if(previous&&previous.generated!==generated){const known=new Set(previous.ids||[]);ids.forEach(id=>{if(!known.has(id))fresh.add(id);});}
  store[scope]={generated,ids};const entries=Object.entries(store).sort((a,b)=>String(b[1].generated).localeCompare(String(a[1].generated))).slice(0,8);try{localStorage.setItem(key,JSON.stringify(Object.fromEntries(entries)));}catch(e){}
  return fresh;
}
function badgeCell(b){
  const masked=b.secret&&!b.ok,cls='badge '+(b.ok?('on tier-'+b.tier):'off')+(b.secret?' secret':'')+(b.isNew?' is-new':''),status=b.ok?'已解锁':'未解锁',date=b.ok?'，'+achievementDateLabel(b):'',progress=b.target!=null?'，当前 '+fmt(Math.round(b.current||0))+'，目标 '+fmt(Math.round(b.target)):'',label=masked?'隐藏成就，达成自动揭晓':b.n+'，'+status+'，'+b.prestige+date+progress;
  return '<button type=button class="'+cls+'" data-ach-id="'+esc(b.id)+'" aria-label="'+esc(label)+'"'+(masked?' disabled':'')+'><span class=ring>'+(masked?'❓':(b.ok?b.e:'🔒'))+'</span><span class=nm>'+(masked?'???':esc(b.n))+'</span><span class=dc>'+(masked?'隐藏':esc(b.d))+'</span></button>';
}
let _ach=null,_newAchievements=new Set();
function renderBadges(){
  _ach=getBadgeData();const a=_ach;_newAchievements=compareAchievementSnapshot(a.all);a.all.forEach(b=>b.isNew=_newAchievements.has(b.id));
  const timeline=achievementTimeline(a.all),latest=timeline[0]||a.all.filter(b=>b.ok).sort((x,y)=>({prismatic:3,gold:2,silver:1,bronze:0}[y.tier]-{prismatic:3,gold:2,silver:1,bronze:0}[x.tier]))[0],goals=nextAchievementGoals(a.all);
  document.getElementById('ach-meta').innerHTML='已解锁 <b>'+fmt(a.got)+'</b> 枚 · '+(_newAchievements.size?'<b>'+_newAchievements.size+'</b> 枚本设备新观察':'本地快照收藏');
  document.getElementById('ach-scope').textContent=(DATA.range?.since||DATA.range?.until)?'范围 '+(DATA.range.since||'最早')+' → '+(DATA.range.until||'最新'):'当前报告全部数据';
  document.getElementById('ach-latest').innerHTML=latest?'<div class=ach-latest-card><div class="ach-latest-icon tier-'+latest.tier+'">'+latest.e+'</div><div class=ach-latest-copy><h3>'+esc(latest.n)+'</h3><p>'+esc(latest.d)+(latest.crossed>1?' · 同日跨越 '+latest.crossed+' 个门槛':'')+'</p></div><div class=ach-latest-meta><span class=ach-rank>'+esc(latest.prestige)+(latest.thresholdRank?' · 该阶梯前 '+latest.thresholdRank+'% 门槛':'')+'</span><span class=ach-date>'+esc(achievementDateLabel(latest))+'</span>'+(_newAchievements.has(latest.id)?'<span class=ach-new>本设备新观察到</span>':'')+'</div></div>':'<div class=ach-empty>还没有可展示的已解锁成就。</div>';
  document.getElementById('ach-timeline').innerHTML=timeline.slice(0,5).map(b=>'<li><span class=ati>'+b.e+'</span><span><b>'+esc(b.n)+'</b><small>'+esc(b.prestige)+(b.crossed>1?' · 同日跨越 '+b.crossed+' 个门槛':'')+'</small></span><time datetime="'+b.unlockDay+'">'+b.unlockDay+'</time></li>').join('')||'<li class=ach-empty>当前聚合快照无法还原精确达成日期。</li>';
  document.getElementById('ach-goals').innerHTML=goals.map(b=>'<article class=ach-goal><div class=ach-goal-head><b>'+b.e+' '+esc(b.n)+'</b><span>'+esc(b.prestige)+'</span></div><div class=ach-goal-track aria-label="'+esc(b.n)+' 进度 '+Math.round(b.progress*100)+'%"><i style="width:'+Math.max(2,b.progress*100).toFixed(1)+'%"></i></div><div class=ach-goal-foot><span>'+fmt(Math.round(b.current))+' / '+fmt(Math.round(b.target))+'</span><strong>还差 '+fmt(Math.ceil(b.remaining))+'</strong></div></article>').join('')||'<div class=ach-empty>当前没有适合推荐的单调目标。</div>';
  const TCOL={bronze:'#c08457',silver:'#b8c0cc',gold:'#f0b429',prismatic:'linear-gradient(90deg,#5b8def,#a78bfa,#f472b6,#14b8a6)'},TLB={bronze:'青铜',silver:'白银',gold:'黄金',prismatic:'彩钻'},TORD=['prismatic','gold','silver','bronze'],trows=TORD.map(t=>{const bs=a.all.filter(b=>b.tier===t),g=bs.filter(b=>b.ok).length;return {t,g,n:bs.length,pct:bs.length?g/bs.length:0};}),top=TORD.find(t=>trows.find(r=>r.t===t&&r.g>0))||'bronze';
  document.getElementById('ach-collection-summary').innerHTML='<div><b>'+fmt(a.got)+'</b>已解锁</div><div><b>'+TLB[top]+'</b>最高阶位</div><div><b>'+fmt(a.all.length)+'</b>图鉴总数</div>';
  document.getElementById('ach-tiers').innerHTML=trows.map(r=>'<div class=trow><span class=tl><i style="background:'+(r.t==='prismatic'?'#a78bfa':TCOL[r.t])+'"></i>'+TLB[r.t]+'</span><span class=tbar><j style="width:'+(r.pct*100).toFixed(1)+'%;background:'+TCOL[r.t]+'"></j></span><span class=tv>'+r.g+'/'+r.n+'</span></div>').join('');
  document.getElementById('ach-prestige-note').textContent='图鉴阶位与“该阶梯前 X% 门槛”只描述本地目录中的门槛位置，不是全球用户稀有度。';
  if(_newAchievements.size){const strongest=a.all.filter(b=>_newAchievements.has(b.id)).sort((x,y)=>({prismatic:3,gold:2,silver:1,bronze:0}[y.tier]-{prismatic:3,gold:2,silver:1,bronze:0}[x.tier]))[0],card=document.getElementById('section-achievements');card.classList.remove('ach-celebrate');void card.offsetWidth;card.classList.add('ach-celebrate');toast('🏆 本设备新观察到 '+_newAchievements.size+' 枚成就');if(strongest&&['gold','prismatic'].includes(strongest.tier)&&document.documentElement.dataset.motion==='full')confetti();}
}
function achievementDetail(b){const date=b.ok?achievementDateLabel(b):'尚未达成',progress=b.target!=null?'当前 <b>'+fmt(Math.round(b.current||0))+'</b> / 目标 <b>'+fmt(Math.round(b.target))+'</b>'+(b.ok?'':' · 还差 <b>'+fmt(Math.ceil(b.remaining))+'</b>'):'';document.getElementById('ach-detail').innerHTML='<b>'+esc(b.e+' '+b.n)+'</b> · '+esc(b.ok?'已解锁':'未解锁')+' · '+esc(b.prestige)+(b.thresholdRank?' · 该阶梯前 '+b.thresholdRank+'% 门槛':'')+'<br>'+esc(date)+(progress?' · '+progress:'')+'<br><span>'+esc(b.d)+'；范围语义：当前报告快照。阶位不是全球用户稀有度。</span>';}
function achievementCategory(c,items,open,index){
  const g=items.filter(b=>b.ok).length,collapsed=open?'':' collapsed',contentId='ach-cat-'+index;
  return '<div class="cat'+collapsed+'" data-ach-cat="'+esc(c.name)+'"><button type=button class=cat-h aria-expanded="'+(open?'true':'false')+'" aria-controls="'+contentId+'"><span class=ce>'+c.e+'</span><span>'+c.name+'</span><span class=cc><b>'+g+'</b> / '+items.length+'</span><span class=chev aria-hidden=true>▼</span></button><div class=cat-grid id="'+contentId+'">'+(open?items.map(badgeCell).join(''):'')+'</div></div>';
}
function renderAchievements(q){
  if(!_ach)_ach=getBadgeData();const a=_ach;q=(q||'').trim().toLowerCase();const filter=document.getElementById('ach-filter').value,okFilter=b=>filter==='all'||(filter==='on'&&b.ok)||(filter==='off'&&!b.ok)||(filter==='secret'&&b.secret)||b.tier===filter;
  document.getElementById('ach-modal-meta').innerHTML='已解锁 <b>'+a.got+'</b> / '+a.all.length+' · 图鉴阶位并非全球稀有度';let shown=0,visibleCats=0;const forceOpen=!!q||filter!=='all';
  const body=a.cats.map((c,index)=>{let items=c.items.filter(okFilter);if(q)items=items.filter(b=>(c.name+' '+b.n+' '+b.d).toLowerCase().includes(q));if(!items.length)return '';shown+=items.length;visibleCats++;return achievementCategory(c,items,forceOpen,index);}).join('');
  document.getElementById('ach-body').innerHTML='<div class=ach-stats><span>当前显示 <b>'+shown+'</b> 枚</span><span><b>'+visibleCats+'</b> 个分类</span><span>总图鉴 <b>'+a.all.length+'</b> 枚</span><span>展开分类时按需渲染</span></div>'+body;
  const bindBadges=root=>root.querySelectorAll('.badge[data-ach-id]').forEach(el=>{const b=a.all.find(x=>x.id===el.dataset.achId);if(b)el.addEventListener('click',()=>achievementDetail(b));});bindBadges(document.getElementById('ach-body'));
  document.querySelectorAll('#ach-body .cat-h').forEach(h=>h.addEventListener('click',()=>{const cat=h.parentElement,grid=cat.querySelector('.cat-grid');if(cat.classList.contains('collapsed')){const c=a.cats.find(x=>x.name===cat.dataset.achCat);if(!c)return;let items=c.items.filter(okFilter);if(q)items=items.filter(b=>(c.name+' '+b.n+' '+b.d).toLowerCase().includes(q));if(!grid.childElementCount){grid.innerHTML=items.map(badgeCell).join('');bindBadges(grid);}cat.classList.remove('collapsed');h.setAttribute('aria-expanded','true');}else{cat.classList.add('collapsed');h.setAttribute('aria-expanded','false');}}));
}
function openAchievements(){renderAchievements(document.getElementById('ach-search').value);openModal(document.getElementById('ach-modal'),document.getElementById('ach-search'));}
function closeAchievements(){closeModal(document.getElementById('ach-modal'));}
document.getElementById('ach-open').addEventListener('click',openAchievements);
document.getElementById('ach-x').addEventListener('click',closeAchievements);
document.getElementById('ach-modal').addEventListener('click',e=>{if(e.target.id==='ach-modal')closeAchievements();});document.getElementById('ach-modal').addEventListener('keydown',e=>trapModalFocus(e,e.currentTarget));
document.getElementById('ach-search').addEventListener('input',e=>renderAchievements(e.target.value));
document.getElementById('ach-filter').addEventListener('change',()=>renderAchievements(document.getElementById('ach-search').value));
document.getElementById('ach-confetti').addEventListener('click',()=>{ confetti(); toast('🎉 庆祝本地收藏：'+fmt(_ach?_ach.got:0)+' 枚已解锁成就'); });

/* ---- Token 星云：数据生成的彩色深空 ---- */
function renderDNA(){
  const svg=document.getElementById('dna'), h=filteredHourly(), days=selectedRows(), total=days.reduce((a,d)=>a+d.total,0), cr=focusDetail()?.cache_read??selectedCacheRead(), cache=total?cr/total:0;
  const mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const models=Object.entries(mt).sort((a,b)=>b[1]-a[1]),ht=h.reduce((a,b)=>a+b,0),hmax=Math.max(1,...h),cx=150,cy=150;
  let p=['<defs><radialGradient id="ng" cx="50%" cy="50%"><stop offset="0" stop-color="#ffffff"/><stop offset=".18" stop-color="#d8e7ff"/><stop offset=".52" stop-color="#8daeff" stop-opacity=".9"/><stop offset="1" stop-color="#5b8def" stop-opacity="0"/></radialGradient><filter id="nb"><feGaussianBlur stdDeviation="5"/></filter><filter id="nbl"><feGaussianBlur stdDeviation="11"/></filter></defs>'];
  // 背景恒星：确定性分布，避免每次渲染跳动
  for(let i=0;i<72;i++){const seed=(i*7919+(total%104729))%100003,a=seed*.017,r=35+(seed%110),x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.86,rr=.35+(seed%7)/10;p.push('<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+rr.toFixed(1)+'" fill="#dbe9ff" opacity="'+(.18+(seed%5)*.1)+'"/>');}
  // 每个模型形成一条独立旋臂，模型颜色清晰可辨
  const arms=models.length?models:[[null,total]];
  arms.slice(0,8).forEach(([m,mv],mi)=>{
    const color=m?DATA.colors[m]:'#7aa2f7',frac=total?mv/total:1,count=Math.max(18,Math.round(24+frac*74)),phase=mi/Math.max(1,arms.length)*Math.PI*2+(total%97)/31;
    let haze='';for(let j=0;j<count;j++){const t=(j+1)/count,a=phase+t*Math.PI*(3.2+arms.length*.12),hour=Math.floor(t*24)%24,energy=(h[hour]||0)/hmax,rad=18+t*112+(energy-.5)*16,wob=Math.sin(j*1.73+mi)*9*(1-t*.45),x=cx+Math.cos(a)*rad+Math.cos(a+Math.PI/2)*wob,y=cy+Math.sin(a)*rad*.72+Math.sin(a+Math.PI/2)*wob*.72,rr=1.1+energy*2.9+(j%9===0?1.5:0),op=.25+energy*.58;haze+='<circle class="nebula-particle" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+rr.toFixed(1)+'" fill="'+color+'" opacity="'+op.toFixed(2)+'"><title>'+esc(m?pretty(m):'Token')+' · '+String(hour).padStart(2,'0')+':00 · '+human(h[hour]||0)+' tk</title></circle>';if(j%4===0)haze+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(rr*3.4).toFixed(1)+'" fill="'+color+'" opacity="'+(.035+energy*.055).toFixed(3)+'" filter="url(#nb)"/>';}
    p.push('<g class="nebula-arm" style="animation-delay:-'+(mi*11)+'s">'+haze+'</g>');
  });
  // 24 个小时轨道信标
  for(let hour=0;hour<24;hour++){const v=h[hour]||0,energy=v/hmax,a=hour/24*Math.PI*2-Math.PI/2,r=126+energy*13,x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.72;if(v>0)p.push('<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(1.4+energy*3).toFixed(1)+'" fill="#fff" opacity="'+(.28+energy*.7).toFixed(2)+'"><title>'+String(hour).padStart(2,'0')+':00 · '+fmt(v)+' Token</title></circle>');}
  // 缓存率越高，中央星核越明亮并出现更多光环
  p.push('<circle cx="150" cy="150" r="'+(24+cache*19).toFixed(1)+'" fill="url(#ng)" opacity=".32" filter="url(#nbl)"/><g class="nebula-core"><circle cx="150" cy="150" r="'+(10+cache*6).toFixed(1)+'" fill="url(#ng)"/><circle cx="150" cy="150" r="3.2" fill="#fff"/></g>');
  if(models.length){const dom=models[0];p.push('<text x="150" y="282" text-anchor="middle" fill="#91a6c8" font-size="8.5" letter-spacing="1.5">DOMINANT · '+esc(pretty(dom[0]).toUpperCase())+'</text>');}
  svg.innerHTML=p.join('');
  let peak=0;for(let i=1;i<24;i++)if((h[i]||0)>(h[peak]||0))peak=i;
  document.getElementById('nebula-meta').innerHTML='<div><b>'+models.length+' 个星团</b>模型光谱</div><div><b>'+String(peak).padStart(2,'0')+':00</b>最亮轨道</div><div><b>'+Math.round(cache*100)+'%</b>星核亮度</div>';
}
document.getElementById('dna-dl').addEventListener('click',()=>{
  const svg=document.getElementById('dna').cloneNode(true); svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
  svg.setAttribute('style','background:#0b1120');
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob(['<?xml version="1.0"?>\n'+svg.outerHTML],{type:'image/svg+xml'})); a.download='token-nebula.svg'; a.click(); toast('Token 星云已收藏为 SVG');
});

/* ---- 会话时间轴回放 ---- */
let rp={series:[],i:0,timer:null,sid:null,label:''};
function renderReplaySeries(){
  const s=rp.series;
  document.getElementById('replay-title').textContent=rp.label||'会话回放';
  document.getElementById('replay-sub').textContent=s.length+' 轮'+(s.length>=200?'（最近 200 轮）':'')+' · 共 '+human(s.reduce((a,b)=>a+b,0))+' token · 横轴为轮次，不代表真实耗时';
  const scrub=document.getElementById('replay-scrub');scrub.max=String(s.length-1);scrub.value=String(rp.i);
  drawECG(rp.i);
}
function openReplay(sid,label){
  const s=DATA.session_series[sid]||[];
  if(!s.length){ toast('该会话无逐轮数据'); return; }
  rp.series=s;rp.i=0;rp.sid=sid;rp.label=label||'会话回放';
  const modal=document.getElementById('replay-modal');openModal(modal,document.getElementById('replay-x'));
  renderReplaySeries();
}
function closeReplay(){if(rp.timer){clearInterval(rp.timer);}rp={series:[],i:0,timer:null,sid:null,label:''};document.getElementById('replay-play').textContent='▶ 播放';closeModal(document.getElementById('replay-modal'));}
function refreshedReplayState(current,data){
  if(!current.sid)return current;
  const series=data.session_series?.[current.sid]||[];
  if(!series.length)return null;
  return {...current,series,i:Math.min(current.i,series.length-1),timer:null};
}
function drawECG(index){
  const s=rp.series, W=700,H=160, max=Math.max(1,...s), n=s.length;
  let line=''; s.forEach((v,i)=>{ const x=i/Math.max(1,n-1)*W, y=H-6-(v/max)*(H-12); line+=(i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)+' '; });
  const cur=Math.max(0,Math.min(n-1,Math.round(index))),cx=cur/Math.max(1,n-1)*W,cy=H-6-(s[cur]||0)/max*(H-12),total=s.reduce((a,b)=>a+b,0),cum=s.slice(0,cur+1).reduce((a,b)=>a+b,0);rp.i=cur;
  document.getElementById('replay-ecg').innerHTML='<path d="'+line+'L '+W+' '+H+' L 0 '+H+' Z" fill=var(--accent-soft)/><path d="'+line+'" fill=none stroke=var(--accent-2) stroke-width=1.5/>'
    +'<line x1="'+cx.toFixed(1)+'" y1=0 x2="'+cx.toFixed(1)+'" y2='+H+' stroke=var(--accent)/><circle cx="'+cx.toFixed(1)+'" cy="'+cy.toFixed(1)+'" r=3.5 fill=var(--accent)/>';
  document.getElementById('replay-pos').textContent=(cur+1)+'/'+n;
  const scrub=document.getElementById('replay-scrub');scrub.value=String(cur);scrub.setAttribute('aria-valuetext','第 '+(cur+1)+' 轮，'+fmt(s[cur]||0)+' Token，累计 '+(total?cum/total*100:0).toFixed(1)+'%');
  document.getElementById('replay-stats').innerHTML='<span>当前轮 '+fmt(s[cur]||0)+' tk</span><span>累计 '+fmt(cum)+' tk</span><span>累计占比 '+(total?cum/total*100:0).toFixed(1)+'%</span>';
}
document.getElementById('replay-x').addEventListener('click',closeReplay);
document.getElementById('replay-modal').addEventListener('keydown',e=>trapModalFocus(e,e.currentTarget));
document.getElementById('replay-modal').addEventListener('click',e=>{ if(e.target.id==='replay-modal') closeReplay(); });
function stopReplay(){if(rp.timer){clearInterval(rp.timer);rp.timer=null;document.getElementById('replay-play').textContent='▶ 播放';}}
document.getElementById('replay-scrub').addEventListener('input',e=>{stopReplay();drawECG(Number(e.target.value||0));});
document.getElementById('replay-ecg').addEventListener('pointerdown',e=>{stopReplay();const r=e.currentTarget.getBoundingClientRect(),index=(e.clientX-r.left)/Math.max(1,r.width)*Math.max(0,rp.series.length-1);drawECG(index);});
document.getElementById('replay-play').addEventListener('click',function(){
  if(rp.timer){ clearInterval(rp.timer); rp.timer=null; this.textContent='▶ 播放'; return; }
  if(rp.series.length<2) return; let index=rp.i;if(index>=rp.series.length-1)index=-1;this.textContent='⏸ 暂停';
  rp.timer=setInterval(()=>{ index++; if(index>=rp.series.length-1){index=rp.series.length-1;clearInterval(rp.timer);rp.timer=null;this.textContent='▶ 播放';}drawECG(index); },120);
});

/* ---- 今日 token 运势 ---- */
function daySeed(){ const d=new Date(); return d.getFullYear()*10000+(d.getMonth()+1)*100+d.getDate(); }
function uhash(n){ n=Math.imul(n^(n>>>15),0x27d4eb2d); n=n^(n>>>13); return (n>>>0)/4294967296; }
function renderFortune(){
  const seed=daySeed(), r=k=>uhash(seed*(k+7));
  const yi=['宜重构','宜写测试','宜删废代码','宜提交','宜读文档','宜改名','宜早睡','宜喝口水','宜拆函数','宜加注释'];
  const ji=['忌 rm -rf','忌深夜上线','忌动数据库','忌裸奔 main','忌盲信 AI','忌硬编码','忌跳过测试','忌复制粘贴','忌不留缓存'];
  const poem=['token 如流水，缓存尚可留。','一日肝到夜，bug 自然来。','代码千行，缓存一响，黄金万两。','commit 之前，三思而后行。','算力烧不尽，春风吹又生。','多喝热水，少写 any。','重构像减肥，明天再说。'];
  const total=lastTotal||0, cr=DATA.cache_read||0, cRatio=total?cr/total:0;
  const score=Math.max(12,Math.min(99,Math.round(45+cRatio*40+r(3)*20-10)));
  const grade=score>=88?'大吉':score>=72?'中吉':score>=58?'吉':score>=44?'末吉':'凶';
  const pick=(arr,k)=>arr[Math.floor(r(k)*arr.length)];
  document.getElementById('f-date').textContent=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
  document.getElementById('fortune').innerHTML=
    '<div class=f-head><div class=f-grade>'+grade+'</div><div class=f-score>运势 <b style="color:var(--ink);font-size:16px">'+score+'</b> / 100</div></div>'
    +'<div class=f-bar><i style="width:'+score+'%"></i></div>'
    +'<div class=f-yj><span class=f-yi><b>宜</b>'+pick(yi,1)+'</span><span class=f-ji><b>忌</b>'+pick(ji,2)+'</span></div>'
    +'<div class=f-poem>'+pick(poem,4)+'</div>';
}

/* ---- 3D 鼠标倾斜卡：仅处理指针所在卡片 ---- */
(function(){
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches||window.matchMedia('(pointer: coarse)').matches)return;
  let active=null,raf=0,mx=0,my=0;
  document.addEventListener('pointermove',e=>{if(document.documentElement.dataset.motion!=='full')return;mx=e.clientX;my=e.clientY;active=e.target.closest('.card');if(!raf)raf=requestAnimationFrame(()=>{raf=0;if(!active)return;const r=active.getBoundingClientRect(),dx=(mx-(r.left+r.width/2))/(r.width/2),dy=(my-(r.top+r.height/2))/(r.height/2);active.style.transform='rotateX('+Math.max(-1.6,Math.min(1.6,-dy*1.6)).toFixed(2)+'deg) rotateY('+Math.max(-1.6,Math.min(1.6,dx*1.6)).toFixed(2)+'deg)';});},{passive:true});
  document.addEventListener('pointerout',e=>{const card=e.target.closest('.card');if(card&&!card.contains(e.relatedTarget)){card.style.transform='';if(active===card)active=null;}},{passive:true});
  addEventListener('tk-motion-change',e=>{if(e.detail.effective!=='full'){if(active)active.style.transform='';document.querySelectorAll('.card[style*="transform"]').forEach(card=>card.style.transform='');active=null;}});
})();

// 双击页面空白：模型色数据尘埃
(function(){
  document.addEventListener('dblclick',e=>{
    if(e.target.closest('button,input,label,a,.card,svg'))return;
    const cs=Object.values(DATA.colors||{});for(let i=0;i<38;i++){const d=document.createElement('i');d.style.cssText='position:fixed;z-index:110;pointer-events:none;left:'+e.clientX+'px;top:'+e.clientY+'px;width:'+(3+i%4)+'px;height:'+(3+i%4)+'px;border-radius:50%;background:'+(cs[i%Math.max(1,cs.length)]||'#7aa2f7')+';transition:transform .85s cubic-bezier(.15,.7,.2,1),opacity .85s';document.body.appendChild(d);requestAnimationFrame(()=>{const a=i/38*Math.PI*2,r=40+(i%9)*9;d.style.transform='translate('+Math.cos(a)*r+'px,'+Math.sin(a)*r+'px) scale(.2)';d.style.opacity='0';});setTimeout(()=>d.remove(),900);}
  });
})();

// 光标彗星：单 Canvas + 固定粒子池，不持续创建 DOM
(function(){
  const canvas=document.getElementById('comet-canvas'),ctx=canvas.getContext('2d'),particles=Array.from({length:28},()=>({life:0})),colors=Object.values(DATA.colors||{});let cursor=0,raf=0,last=0,allocated=false;
  function release(){if(raf)cancelAnimationFrame(raf);raf=0;particles.forEach(p=>p.life=0);canvas.width=1;canvas.height=1;allocated=false;}
  function resize(){if(document.documentElement.dataset.motion!=='full'){release();return;}const dpr=Math.min(1.5,devicePixelRatio||1),maxPixels=8000000,scale=Math.min(dpr,Math.sqrt(maxPixels/Math.max(1,innerWidth*innerHeight)));canvas.width=Math.max(1,Math.round(innerWidth*scale));canvas.height=Math.max(1,Math.round(innerHeight*scale));canvas.style.width=innerWidth+'px';canvas.style.height=innerHeight+'px';ctx.setTransform(scale,0,0,scale,0,0);allocated=true;}
  function tick(){raf=0;ctx.clearRect(0,0,innerWidth,innerHeight);let alive=false;particles.forEach(p=>{if(p.life<=0)return;p.life-=.055;p.x+=p.vx;p.y+=p.vy;p.vy+=.015;const a=Math.max(0,p.life);ctx.globalAlpha=a;ctx.fillStyle=p.color;ctx.shadowColor=p.color;ctx.shadowBlur=8;ctx.beginPath();ctx.arc(p.x,p.y,p.size*a,0,Math.PI*2);ctx.fill();alive=true;});ctx.globalAlpha=1;ctx.shadowBlur=0;if(alive&&!document.hidden)raf=requestAnimationFrame(tick);}
  function spawn(e){if(document.documentElement.dataset.motion!=='full'||document.hidden)return;const now=performance.now();if(now-last<38)return;last=now;const p=particles[cursor++%particles.length];p.x=e.clientX;p.y=e.clientY;p.vx=-.6+(cursor%5)*.3;p.vy=.7+(cursor%7)*.18;p.size=2+(cursor%4)*.55;p.life=1;p.color=colors.length?colors[cursor%colors.length]:'#7aa2f7';if(!raf)raf=requestAnimationFrame(tick);}
  resize();addEventListener('resize',resize,{passive:true});addEventListener('tk-motion-change',e=>e.detail.effective==='full'?resize():release());document.addEventListener('pointermove',spawn,{passive:true});document.addEventListener('visibilitychange',()=>{if(document.hidden){release();}else if(document.documentElement.dataset.motion==='full')resize();});
})();
document.addEventListener('visibilitychange',()=>{if(document.hidden){if(raceTimer){clearInterval(raceTimer);raceTimer=null;document.getElementById('race-play').textContent='▶ 播放';}if(rp.timer){clearInterval(rp.timer);rp.timer=null;document.getElementById('replay-play').textContent='▶ 播放';}}});

// 滚到深处出现返航火箭
(function(){const r=document.getElementById('rocket');window.addEventListener('scroll',()=>r.classList.toggle('on',scrollY>innerHeight*.9),{passive:true});r.addEventListener('click',()=>{if(motionDisabled()){scrollTo({top:0,behavior:'auto'});return;}r.classList.remove('launch');void r.offsetWidth;r.classList.add('launch');setTimeout(()=>{scrollTo({top:0,behavior:scrollBehavior()});r.classList.remove('launch');},360);});})();

function reconcileLiveData(next){
  const oldModelSet=new Set(DATA.models||[]),allPreviouslySelected=state.models.size===oldModelSet.size&&[...oldModelSet].every(model=>state.models.has(model));
  DATA=next;
  const allowed=new Set(DATA.models||[]),selected=new Set([...state.models].filter(model=>allowed.has(model)));
  if(allPreviouslySelected)allowed.forEach(model=>selected.add(model));
  state.models=selected;
  if(state.focusPeriod&&!validFocus(state.focusPeriod,state.gran))state.focusPeriod=null;
  if(selectedProject&&!scopedEntities('project').some(item=>item[2]===selectedProject))selectedProject=null;
  if(trailState.model&&!allowed.has(trailState.model))trailState.model=null;
  if(raceTimer){clearInterval(raceTimer);raceTimer=null;document.getElementById('race-play').textContent='▶ 播放';}
  if(rp.timer){clearInterval(rp.timer);rp.timer=null;document.getElementById('replay-play').textContent='▶ 播放';}
  if(rp.sid){
    const refreshed=refreshedReplayState(rp,DATA);
    if(refreshed){rp=refreshed;renderReplaySeries();}
    else closeReplay();
  }
  _almanac=null;_ach=null;previousModels=null;discoveryIndex=0;
  Object.keys(lazyState).forEach(name=>lazyState[name]=Object.assign({},lazyState[name],{dirty:true,rendered:false}));
  invalidateDerived();reconcileTrailState();reconcileSignalState();renderSnapshotMeta();renderFilters();render();Object.keys(LAZY_RENDERERS).forEach(name=>{if(lazyState[name]?.visible)renderLazy(name,true);});applyLanguage(dashboardLanguage,false);
}
function liveStatus(kind,text,title=text){
  const beacon=document.getElementById('live-beacon');
  beacon.className='seg live-beacon '+kind;beacon.title=title;document.getElementById('live-text').textContent=text;
  if(dashboardLanguage==='en')applyLanguage('en',false);
}
function initLiveDashboard(){
  const refresh=document.getElementById('live-refresh');
  if(!LIVE?.enabled){refresh.hidden=true;liveStatus('static','静态快照','静态离线快照');return;}
  let timer=null,failures=0,controller=null,current=DATA.snapshot?.id||null,interval=Math.max(1000,Number(LIVE.interval||300)*1000);
  refresh.hidden=false;const seconds=Math.round(interval/1000),presets=[60,300,900,1800];if(!presets.includes(seconds)){const option=document.createElement('option');option.value=String(seconds);option.textContent='刷新 · '+seconds+' 秒（CLI）';option.dataset.i18nSkip='';refresh.prepend(option);}refresh.value=String(seconds);
  const schedule=delay=>{clearTimeout(timer);if(interval>0&&!document.hidden)timer=setTimeout(check,delay);};
  async function check(){
    if(document.hidden||interval===0)return;
    liveStatus('syncing','正在检查');controller?.abort();controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),Math.min(10000,interval));
    try{
      const response=await fetch('/api/snapshot',{cache:'no-store',headers:current?{'If-None-Match':'"'+current+'"'}:{},signal:controller.signal});
      if(response.status===304){failures=0;liveStatus('live','本地实时');schedule(interval);return;}
      if(!response.ok)throw new Error('status');
      const payload=await response.json();
      if(payload.error){failures++;liveStatus('error','同步错误',payload.error);schedule(Math.min(interval*Math.max(2,failures),30000));return;}
      if(payload.snapshot&&payload.snapshot!==current){current=payload.snapshot;reconcileLiveData(decodeWire(payload.wire));liveStatus('updated','刚刚更新');setTimeout(()=>{if(!document.hidden&&interval>0)liveStatus('live','本地实时');},1800);}
      else liveStatus('live','本地实时');
      failures=0;schedule(interval);
    }catch(error){if(error.name==='AbortError'&&(document.hidden||interval===0))return;failures++;liveStatus('offline','暂时断开');schedule(Math.min(interval*Math.max(2,failures),30000));}
    finally{clearTimeout(timeout);}
  }
  refresh.addEventListener('change',()=>{clearTimeout(timer);controller?.abort();const seconds=Number(refresh.value);interval=seconds>0?seconds*1000:0;failures=0;if(interval===0)liveStatus('paused','刷新已暂停');else check();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){clearTimeout(timer);controller?.abort();}else if(interval>0)check();});
  liveStatus('live','本地实时');schedule(interval);
}

/* URL 可恢复当前视图；旧版 #day/#week/#month 仍兼容 */
document.getElementById('lang-btn').addEventListener('click',toggleLanguage);
applyLanguage(dashboardLanguage,false);
bindSignalLens();
applyMods();
initLazyRendering();
restoringView=true;restoreViewFromURL();invalidateDerived();renderFilters();render();restoringView=false;syncViewURL();initLiveDashboard();
