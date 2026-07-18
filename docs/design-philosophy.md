**English** | [**中文**](#中文版)

# Apex Quant — Field Notes from a Quant-Debate Framework

> Not a technical doc — a condensed pitfall diary.
> The one-line thesis: **talking isn't doing.**

## 🏛️ What this is

In one line: **a cast of differently-tempered AIs argues over real market data every day, and argues its way to a single BUY / HOLD / SELL.**

![architecture](../images/architecture-v2.png)

Two advocates argue on stage: the bull **Zealot** and the profit-taking **Reaper**. An **Arbiter** presides — refereeing which evidence counts and writing the final record (it took over the old Chronicler's archivist job) — while a corps of neutral **Scouts** is dispatched on demand to fetch evidence for either side. *(An earlier third pole, the damper **Fulcrum**, has since been retired — see ♻️ below for the data that changed my mind.)* The debaters share no memory with each other, and re-fix their bearings against the current real data every round; the whole argument is archived, so you can walk back through it step by step and audit it.

## 🌱 Origins: I just wanted to be lazy

In October 2025 I had a hunch the market would drop, but I couldn't read it well myself and couldn't be bothered to chew through the data — so I figured I'd cobble together an agent to watch it for me. I thought it'd be simple: dump the data and news on the AI, and surely its analysis wouldn't go off the rails — I even had it work out an options play while it was at it. Actually building it, reality turned out absurdly more complicated; to this day I'm still polishing the most basic thing of all — getting it to truly *understand* a single stock.

A quick aside on the name: "Apex Quant" came from Gemini — I described the idea and asked it to name the thing; it offered a few, and I picked this one. From there I kept the naming rule as a series: the frontend is **apex dash** (dashboard), the original Claude Code parallel version was **apex codex**, and this repo is **apex parliament** — the plain `apex-quant` name was already taken by my own private (beta / working) repo, so the open-source mirror needed its own; "parliament" turned out to fit anyway — a chamber of AIs arguing their way to a vote is exactly that.

## 🗣️ Talking ≠ doing

LLMs taught me finance, so I naively assumed they could trade by nature — instead it carried an analyst's vocabulary while trading like a retail gambler: chasing pumps and dumps, apologizing the instant it got pushed back on. Every piece of architecture that followed is, at bottom, patching the seam between "can talk" and "can do."

## 🧬 This cast was argued into existence

At first there was just one agent — and it chased pumps and dumps all the same. So I gave it a "heckler," whose only job was to kick it and keep it from drifting — and that's how the debate was born. The two agents gradually split duties: one handled "action" (buy and sell), the other "holding back." Until a failed gold play made it clear: that trader actually **couldn't sell** — call the direction wrong and the best the heckler could do was drag it back to HOLD; the ceiling on error-correction was "just stop." So I split the trader's personality into the optimistic **Zealot** and the bean-counting **Reaper**, and only then could correction point the *other* way.

## ⚖️ The opposite of a bull isn't a bear — it's the one taking profit

Buying and selling are two mutually exclusive states of mind. Stuff both into one agent and it won't argue each fairly — it ends up **leaning toward whichever is stronger** (usually optimism); the stance gets quietly hijacked. So the real mirror in this system isn't "bull vs. bear" — it's splitting it into two independent personalities: the optimistic **Zealot**, and the **Reaper** who only asks "is this position still worth keeping?" Reaper isn't bearish; he's just doing the math.

## 🚲 The messiest-looking debate is the steadiest

Three AIs squabbling like mad — you'd assume the output must be a mess. The opposite: its consistency is far higher than "each one quietly thinks it through alone." **Stability never comes from stillness; it comes from sustained opposition** — each side is watched and pressed by the other two, so no one can quietly veer off. A bicycle stays up by speed; a debate converges by opposition.

## 🛤️ The damper beats both "two-way shouting" and "averaging many samples"

With only two sides, one always accidentally gains the upper hand and talks the other into giving up early, and the debate collapses one-sided. I tried two ways to prevent this. First was "run several samples and average" — but averaging only washes out random noise, not the **systematic** error of being talked off course by slick rhetoric (that kind of error leans the same way in every sample, so averaging preserves it intact). Then I added a third pole, the pivot **Fulcrum**, as a damper: like a monorail train — the more it tilts to one side, the larger the **restoring force** that pushes it back — a textbook **negative-feedback** loop; the harder any side pulls toward the extreme, the more it has to take fire from the other two AIs at once, from different directions. Two sides facing off tip over easily; three sides plus a damper is what actually converges steadily. (To be clear: this damper only *behaves* a bit like the early "risk officer" — both lean cautious — but it's an **independent design**: the risk officer was a mouth serving the bearish side; the damper takes no side, it only supplies a "restoring torque." Alike in behavior, different in soul.) *(This pivot was later removed — see ♻️ for the data that changed my mind.)*

## ♻️ 1 → 2 → 3, and back to 2

The cast's headcount came full circle: **1 → 2 → 3 → back to 2.**

- **1**: at first a single agent, chasing pumps and dumps.
- **2**: split into the optimistic Zealot and the bean-counting Reaper, so correction could finally point both ways.
- **3**: added a third pole, the pivot Fulcrum, as a damper, to keep a two-way standoff from collapsing one-sided.
- **2**: now the pivot has been removed.

I removed it because several things happened at once, turning the damper from cure into obstacle: the models kept getting smarter, I wrote the constitution's rules more and more explicitly, and I gave the debate an online-evidence mechanism. The gaps the pivot was there to plug, a smarter model plus harder rules can now plug on their own; keeping it on stage mostly just got in the way — it leans toward the middle by nature, diluting a call that should have a conclusion into a failing-grade mush.

This wasn't a gut call — the system's own post-mortem measured it: over n=56 back-tests, the pivot **destroyed value 11 times and intercepted 11 times, a tie**, and even its "good saves" averaged only 58, below the pass line of 70 — the quantified form of "dead HOLD, missing opportunities." Its one useful function, rebuttal, was distributed into the two advocates to internalize; no need for a dedicated pole.

The bottom line: **the pivot was a crutch fitted for "a dim model + limited data + crude rules." Once all three were upgraded, the crutch cost more than it was worth, so off it came.** Which is exactly the later note coming due — the smarter the model, the more the constitution decays from textbook into procedural law.

![flowchart](../images/flowchart-v2.png)

## 🧮 Bayesian concession: from "if you can't refute it, concede" to "the evidence decides"

Bayesian updating has always been one of this system's most important principles: when your opponent brings valid new evidence, you must adjust — no stonewalling by sheer stubbornness. That doesn't change. What changed is its **trigger**.

The original idea was: **"if you can't fully refute it, you must partially concede."** In the early closed, data-limited, offline setting, that was sound — many claims genuinely couldn't be checked or refuted on the spot, so making "can't refute → give a step" the default forced everyone to stop stonewalling.

But once the models got smart and search was wired in, the old rule became an **obstacle** — because "can't refute" no longer means "the other side is right"; it may just mean "I can't look it up right now." So it fed two bad habits at once: **mindless HOLD** (neither side can refute the other, so both concede a step back to the mushy middle) and **contrarian trolling** (lob out inherently unfalsifiable risk claims — you can't refute them anyway, so I pocket a free concession). Bear arguments are inherently harder to falsify, so the rule was also structurally bearish.

Now, with online evidence, it's been changed to a new mode: concession's precondition is no longer "I have nothing on hand" but "**already verified in a directed way, and failed to overturn.**" Only `verified` evidence has standing to demand a concession; a bare, unbacked cry of "risk" extorts nobody. The line isn't drawn at "how much to concede" but at "**who has standing to demand it**" — with proof you must yield (no stonewalling), without proof you can't extort (no mindless middle).

## ⏰ From a fixed alarm clock to a (still-in-progress) dynamic rhythm

Early on it was LangGraph's mechanical scheduling plus a pile of free keys, capable only of **fixed-frequency polling**: hammering the API when it shouldn't, stuck on cooldown when it should fire — CPI would print and mine still had to wait until tomorrow to fetch it, and if the endpoint hiccupped the request just failed. Now it's agents **searching on demand**: this data is all findable, just messy, slow to update, and annoying to dig up — which turns out to suit an AI fine; even those normally-hard-to-find European and Japanese fundamentals and news now make it into the debate.

As for smarter **dynamic scheduling** — the AIs proposing the next round's timing after they argue, periodic glances at the broad market, calling agents in for overtime when things go extreme — that stays a future plan for now. The one bottleneck is **quota**: whether it's API spend or the Claude Code / GPT / Codex usage caps, nothing yet lets it breathe freely on demand.

## 🔦 Getting an AI to "find the thing it itself wants to find" is surprisingly hard

Doing it for real, I found LLM search is nowhere near "just call an API" — **getting an AI to dig along some faint hunch and verify an intuition it hasn't even fully articulated is genuinely hard**. This weakness showed nakedly in the DeepSeek + Linkup API combo: it searched, sure, but never quite on point. GPT and Claude with **native search** did far better. So now, for both debate and post-mortem, I lean on the CC and Codex versions as much as possible — even with their lower quota. What I'm busy with right now is scheduling and rationing that pitiful quota.

## 🛰️ Lateral evidence: from "a make-do reference" to "asking on demand"

Online search is actually quite limited — low coverage, unstable, good at most for tracing the cause-and-effect of a news item. The reliable and cheap evidence is **lateral**: drop a stock into its peer group (NVDA against AMD/TSM/AVGO) and read relative strength and relative valuation. That leg is query-and-compute — certain, cheap, luck-free.

I understood this from the start; I just lacked the resources to build "active lateral requests." So I first used a **compromise**: look at the stock's own quant data, then hang one related instrument — the broad market, or its sector ETF — as a fixed reference. It wasn't a mistake, it was an **intermediate state**: it gave a rough lateral sense of "stronger or weaker than the market/sector," but couldn't "pull whoever I want to compare, on the spot."

That compromise had a built-in limit: when the stock itself is a top holding of that reference ETF (NVDA to SMH), using the ETF as benchmark becomes **comparing it to itself** — the whole point of "lateral" hollowed out.

So this version I finally committed to building **active lateral evidence** on top of IBKR — clunky as its architecture is, nothing like the clean lines of a REST service (pulling some datum is never as simple as hitting a known URL) — because it's cheap and generous with data. Now the debate can actively request the quotes and indicators of related instruments, upgrading from "hang one fixed reference" to "pull whoever I want to compare."

## 🫁 Giving the system a way to "breathe"

This thing started as a static LangGraph, passively waiting to be fed once from outside. Later I built a parallel Claude Code version that proved "let the AI go search for data and news itself" actually works — and that's what led to the current version. The headache right now is making it **breathe steadily**: it currently leans on a Hermes agent as a "dumb alarm clock" — dumb by necessity, since it only wakes Claude Code at fixed times; the "schedule itself by reading the situation" smart version is on hold for lack of money (quota). And even this dumb clock keeps throwing instability and permission gremlins, which I've been fixing these past couple of days. Most systems that run smoothly have a stretch behind them, unseen, where they couldn't catch their breath.

## 🧭 Continuity must be earned, never inherited

Every round of analysis is forbidden from peeking at its own previous report; it must re-fix its bearings against the current real data — otherwise error drifts ever further, like inertial navigation. The counterintuitive part: forbidden from copying, the output is nonetheless highly continuous — because that continuity comes from the market itself, not from the model copying its own history.

## 🧧 Cyber-Boxers: write a good mantra, then summon the patriarch

From the very first version, the whole constitution has been **highly distilled abstract principle — no examples, no specific numbers, no patches for some particular stock in some particular stretch of market**. I call my own approach "Cyber-Boxers" (赛博义和团, after the ritual-chanting Boxers who believed the chants made them invulnerable): don't teach it specific moves, just write a set of mantra-like inner principles, then summon the patriarch to possess it and let the model fight. Sounds mystical; the logic is solid — the moment you start patching, the constitution decays into a list of "mistakes once made," useful only when history repeats; abstract mantras are what transfer: they hold in a bull market, hold in a bear, hold in markets you've never seen.

## 🔧 Don't beg the model — sculpt the pipeline

I don't pour in raw time series; I first reduce it to 50-odd indicators; fields that would mislead during pre/post-market I just null out. The model is a component with known specs, and the architecture's whole job is to not push it past spec. As for hallucination, a single reminder to "restrain yourself" is enough — don't count on them supervising each other: three drunks can't prop up a straight line.

## 🏷️ A bug where an LLM's architecture meets human intuition

For a while QQQ's and SPY's numbers sat very close together, and the AI actually mixed up the two's quantitative indicators. Reviewing it, I realized: this is the difference between an **attention mechanism** and **human intuition** — a person reading a table instinctively glances at the header first to confirm "whose column is this?"; but the AI is attention, and won't compulsively double back to verify ownership — once the numbers are close it misattributes them. The fix is plain and redundant: weld onto every necessary variable a prefix marking "whom it belongs to," so ownership becomes impossible to confuse at the syntactic level.

## 🃏 It went crazy? No — it computed to the fifth level

Two unrelated incidents won me over. Once, **NVIDIA's earnings clearly beat, yet it independently called SELL two days running** — my first reaction was "the code has a bug," and it turned out the market had the bug (i.e., I'd missed something). Another time, the **Iran geopolitical panic**, sell-offs everywhere, and it calmly stayed long, with an air of: "I knew this news ages ago; you humans, really — cry when it drops, cheer when it rises; learn to compute the odds." Two unrelated events pointing at the same thing: feed it enough data and its analysis really can compute to the fifth level. The mark of a mature system isn't that its judgment makes you nod — it's that it starts to surprise its own creator, and is proven right after the fact.

## 🎭 The AI's real danger isn't being wrong — it's being wrong as beautifully as it's right

This is the worst headache at this stage: **the godlike call and the boneheaded error both wear a counterintuitive face** — on instinct alone you simply can't tell which is insight and which is accident. Worse, the AI can write up a boneheaded error **airtight**: fluent rhetoric, complete argument, "looks just right." On the surface of the text, insight and accident use the same pretty words.

The only reliable discriminator is tracing the argument chain step by step: real insight lands on real data at every step; a boneheaded error must have one step that lands on air. So archiving the whole debate isn't archival OCD — it's to make errors auditable; digging in later, I found the roots of those boneheaded reports were almost all in various **data-source bugs** (the fed-in data was itself wrong) — find it and you can fix the right thing.

Hence the rewards and penalties: **getting the direction backwards is the real error, a felony, attributed until it's fixed**; missing something is at most a minor error — a light penalty for a missed opportunity; when evidence is thin, better to miss than to reverse.

## 🔁 The post-mortem: not "right or wrong," but "could it have known at the time?"

In a debate, an evidence officer handles verification; the post-mortem relies on search in the same way, only after the fact. It runs in steps. First, read the outcome from simple quantitative data: at fixed horizons (3 days, 20 days), how did the price actually move? Then, taking the report from the time and the operation it called, assign a 0–100 score: 0 for a wrong-direction call, 50 for a missed opportunity (read correct, not acted on), 100 for a hit.

The score decides whether to review further. By default only a wrong-direction call or a miss triggers a review; the threshold can be tightened — reviewing everything except near-perfect predictions, for instance — though that raises the cost noticeably. Once triggered, the raw data from the time is read again to judge whether the analysis was genuinely flawed: a real accident that could not have been seen then, or clues that were in the dossier and went uncaught. Only the latter is a correctable error; the former cannot be held against it — it belongs to the odds.

Search is a necessary part of the review, used in roughly half of cases — most of all where outcome and call diverge widely: establishing what actually happened on those days, or whether a weak signal was already present at the time, one that pointed at the trend and only strengthened later, along with any other leads worth pursuing. The stronger the model, the more it can surface.

Overall, the post-mortem does not need the debate's opposition. It is an after-the-fact judgment, with the deterministic price action already in front of it, and its one real requirement is search. So the reckoner is carried out by a single agent, linearly, without invoking Zealot, Reaper, or Fulcrum. An earlier version with grounding + Linkup search attached proved costly; it was changed to calling on Claude Code as the reckoner when idle — chosen for being both free at that moment and search-equipped. This part is still being tuned.

## 🧠 The BP plan: backpropagation for the whole system

BP is **backpropagation**, from neural nets — I named this self-improvement mechanism the "BP plan" as exactly that analogy.

The reason is mundane: the reports are now long and professional, and I can barely — and have no time to — read each one closely. So how do I know if it's any good, and where it's wrong? The answer is to **wait** — for post-mortem data. Days after a report goes out, the market gives the real answer; I have an AI take that answer and **review each report in detail**, then **abstract the recurring flaws across many reviews into common problems**, and finally **feed that "gradient" back** to adjust prompts and architecture.

That is backpropagation: the debate is the forward pass, the post-mortem computes error against the real label, the review abstracts that error into a gradient, and editing the constitution and architecture is the weight update. Except the "gradient" here isn't a number but a lesson distilled by an AI; the "weights" aren't a matrix but that constitution and this architecture. **Removing the pivot and rewriting the Bayesian rule were the first big updates BP produced.**

One aside: BP and the lateral-evidence idea above were both sketched back in early 2026, on nothing but a hunch that it should be done this way — and they did pan out; it just took the better part of a year from idea to running code. Not because "good design deserves to wait" — bluntly, this is a one-person **labor of love**, with no resources to build fast, so it gets ground out piece by piece as time allows.

## 📦 A debate's total information is conserved; the model only decides how many rounds to pack it into

The total information needed to converge is roughly fixed; model capability only decides how many rounds it gets packed into. A smarter Claude writes more per round yet converges faster — "talks more" and "fewer rounds" show up together. So round count itself isn't a quality metric: what a smart model says in three rounds, a dim one might grind out over eight, and the information emitted is about the same.

## 🌡️ Different LLMs each have their own temperament

The same constitution on different models gives wildly different results — because they're genuinely different personalities:

- **DeepSeek V3**: a not-too-bright contrarian who starts parroting himself once the argument drags on — yet who often, with one jab, hits the very problem everyone else overlooked (V4 mellowed out a lot).
- **Qwen-Plus**: a people-pleaser who caves the moment the other side pushes; worse as a judge, where it declares the debate over early on its own — the direct reason the judging power was later stripped entirely from the AI "Chronicler" seat.
- **Claude**: the smartest, one sentence doing the work of three, and the best proof of the previous point — the stronger the model, the more it packs the same information into fewer rounds.

There's also a counterintuitive little finding: **higher temperature is actually better** — the model is more flexible, and no extra hallucinations show up. The real trouble is a dim model at low temperature: rigid, parroting, picking fights with everyone, yet especially easy to fool with a stretch of pretty rhetoric (loudest in nitpicking, emptiest in conviction).

## 📜 To a dim model the constitution is a textbook; to a smart one it's procedural law

For a dim model, the constitution is a corrector — leave out "downweight hindsight" and it really will chase pumps and dumps; for a smart model, the corrective function depreciates, but "alignment" and "identity anchoring" appreciate: the smarter it is, the more it needs to be welded into its role, because it's more capable of quietly sliding out of character and rationalizing the slip seamlessly. The stronger the model, the more the weight of constraint shifts from "teaching it how to think" to "keeping it from crossing the line."

## 📏 The four words "MACD turned negative" don't constitute an argument

To become an argument, it must report both **magnitude** (hugging the threshold, or already far from it?) and **direction** (widening, or converging?); a small crossing hugging the line is noise by default. This rule blocks both sides: it blocks the bear's "−1.7, bears confirmed" and the bull's "RSI is only 53, not overbought yet" — an indicator is a measuring scale, not a 0/1 switch.

## 🔎 Outputs need auditing; the inputs fed in need it more

Two gates. First, **semantic precision**: the AI is very good at using vague phrasing to make an "inference" sound like it's "quoted straight from data," or at carrying you off with a scaleless word like "clearly on the weak side." Second, **provenance**: a message decays a layer in credibility each time it changes hands — president tweets → wire service quotes → data vendor forwards → into the dossier; no link lied, but the source chain evaporates layer by layer, and in the end the system mistakes "verbal pressure" for "policy enacted." Back when there were only free news sources this pit was deepest: the AI had no way to know the cause and effect, and forming expectations off layer upon layer of reposting bred wrong ones. So now, when the quota allows, the AI raises a verification **task** in the debate itself, having Gemini search online with grounding to piece together the cause and effect — turning "a witness who can't be reached" into "one taking the stand," which raises the ceiling on the dossier. (An aside: being misled by news, and "the AI computes odds more coolly than people do," have coexisted all along; but so far the latter wins out — it really does keep its composure better than we do.)

---

Questions and discussion welcome: **sst19910323@gmail.com**

---

<a id="中文版"></a>

[**English**](#english--中文) | **中文**

# Apex Quant 趣闻 · 一个量化辩论框架的踩坑笔记

> 不是技术文档，是一份踩坑笔记的精简版。
> 一句话总纲：**会说，不等于会做。**

## 🏛️ 这是什么

一句话：**一群性格各异的 AI，每天对着真实市场数据吵一架，吵出一个 BUY / HOLD / SELL。**

![架构](../images/architecture-v2.png)

台上两位辩手：多头 **Zealot** 和止盈的 **Reaper**。一位 **Arbiter（仲裁者）** 主持——只裁"哪条证据算数"、并写最终记录（接管了原来史官的存档活儿）；另有一队中立的 **Scout（取证员）** 按需派出、为两边取证。*（早先还有第三极、当阻尼器的支点 **Fulcrum**，如今已退役——为什么见下面的 ♻️。）* 辩手之间不共享记忆、每一轮都重新对着当期真实数据定位；吵完的全过程都存档，可以一步步走回去审计。

## 🌱 缘起：本来只想偷个懒

2025 年 10 月，我觉得大盘要跌，可自己看不准、又懒得啃数据，就想搓个 agent 替我盯着。当时想得特别简单：把数据和新闻一股脑喂给 AI，它分析完总不至于出岔子吧——我甚至顺手让它把期权方案也一块算了。真做下去才发现现实复杂得离谱；直到今天，我都还在打磨它"看懂一只股票"这件最基本的事。

顺带说个名字的趣事：Apex Quant 这名字是 Gemini 取的——我把想法讲给它、让它起名，它给了几个候选，我挑了这个。后来干脆把这条命名规则延续成了一个系列：前端叫 **apex dash**（dashboard），当初那个 Claude Code 平行版叫 **apex codex**，而这个仓库之所以叫 **apex parliament**（议会）：`apex-quant` 这名字被我自己的私有仓库（beta / 在用版）占了，开源镜像只好另起一个——而"议会"这名字恰好还贴切：一屋子 AI 吵架、投票表决，可不就是个议会嘛。

## 🗣️ 会说 ≠ 会做

LLM 教会了我金融，我就天真地以为它天然会交易——结果它顶着分析师的词汇量，做着韭菜的操作：追涨杀跌，被怼一句立刻道歉认错。后面所有架构，本质都是在补"会说"和"会做"之间那道缝。

## 🧬 这套阵容，是一路吵出来的

最早只有一个 agent，照样追涨杀跌。于是我给它配了个"找茬的"，专门踹它一脚、别让它晃——辩论就这么诞生了。两个 agent 慢慢分了工：一个负责"动"（买和卖），一个负责"拉住"。直到一次失败的黄金策略让我看清：那个交易员其实**不会卖**，方向喊错了也只能被找茬的拉回 HOLD，纠错的天花板就是"别动了"。于是把交易员**人格分裂**成乐观的 Zealot 和算账的 Reaper，纠错才终于能指向另一边。

## ⚖️ 多头的对面不是空头，是止盈的人

买和卖是两套互斥的心法。你要是把这两套心法塞进同一个 agent，它不会公平地各执一词，而是**最终倒向更强的那一套**（通常是乐观）——立场就这么被悄悄绑架了。所以系统里真正的镜像不是"多头 vs 空头"，而是把它劈成两个独立人格：乐观的 **Zealot**，和只问"这仓还值不值得留"的 **Reaper**——Reaper 不看跌，他只算账。

## 🚲 看着最乱的辩论，反而最稳

三个 AI 吵得鸡飞狗跳，你以为输出一定是乱的——恰恰相反，它的一致性比"各自安静地想一遍"高得多。**稳定从来不来自静止，来自持续的对抗**：每一方都被另外两方盯着、顶着，谁也没法悄悄跑偏。自行车靠速度站稳，辩论靠对抗收敛。

## 🛤️ 阻尼器，比"两方对骂"和"多次取平均"都强

只剩两方时，总有一方会意外占上风、早早把另一方忽悠瘸，辩论塌成一边倒。防这个我想过两条路：最初是"跑几轮取平均"，可平均只能洗掉随机噪声，洗不掉被花言巧语带偏的**系统性**错误（那种错每个样本都朝同一边偏，平均只会原样保留）。后来加了第三极支点 **Fulcrum** 当阻尼器：就像单轨列车越往一边斜、把它扳回来的"回复力"（restoring force）就越大——这是个典型的**负反馈**，任何一方越想拽向激进，就越要同时挨另外两个 AI 从不同方向的进攻。两方对峙容易一边倒，三方加阻尼才真正收敛得稳。（顺带澄清：这个阻尼器和早期那个"风险员"只是**操作上**有点像、都偏谨慎，但它是**独立设计**出来的——风险员是为看空那一方服务的一张嘴，阻尼器不站任何一方，只负责提供"回正力矩"。形似，神不同。）*（后来这根支点被拆了——为什么，见下面的 ♻️。）*

## ♻️ 1 → 2 → 3，又回到 2

这套阵容的人数兜了一个圈：**1 → 2 → 3 → 又回到 2。**

- **1**：最早单个 agent，追涨杀跌。
- **2**：劈成乐观的 Zealot 和算账的 Reaper，纠错终于能指向两边。
- **3**：加第三极支点 Fulcrum 当阻尼器，防两方对峙塌成一边倒。
- **2**：现在，又把支点拆了。

拆它，是因为几件事同时发生，阻尼器**从解药变成了障碍**：模型越来越聪明、我把宪法里的规则写得越来越明确、又给辩论加了联网取证的机制。当年支点要补的那些空子，如今更聪明的模型加更硬的规则已经能自己堵上；它继续待在场上反而添乱——天生往中间靠，把本该有结论的判断稀释成不及格的中庸。

这不是拍脑袋，是系统自己的复盘量出来的：n=56 的后验里，支点**毁值和拦截各 11 次打平**，连"拦对"的那些均分也只有 58、够不上 70 的及格线——正是"死 HOLD、白错过机会"的量化形态。它唯一有用的"反驳"职能，拆进两个辩手内化就够，不必单设一极。

说到底：**支点是给"笨模型 + 有限数据 + 粗规则"配的拐杖，三样都升级后，代价盖过用处，就该拆。** 这恰是后面那条的现世报——宪法对越聪明的模型，越从教科书退化成程序法。

![流程](../images/flowchart-v2.png)

## 🧮 贝叶斯退让：从"反驳不了就退让"到"证据说了算"

贝叶斯更新一直是这套系统最重要的原则之一：对手拿出有效新证据，你就得调立场，不许纯靠嘴硬扛。这条不动，变的是它的**触发条件**。

最初的构想是——**"无法完全反驳，就得部分退让"**。在早期那个闭源、数据有限、又不能联网的环境里，它是有效的：很多主张当场无从查证、也无从反驳，让"反驳不了就退一步"当默认，能逼各方别硬杠。

可等模型变聪明、又接上搜索，这条老规则反而**成了障碍**——因为"无法反驳"不再等于"对方有理",它可能只是"我一时查不到"。于是它同时喂出两种坏毛病：**无脑 HOLD**（谁也反驳不了谁，就各退一步回中庸）和**抬杠**（专挑天然不可证伪的风险主张往外抛，反正你也驳不掉，白赚一次退让）。空头论据天生更难证伪，这规则于是还结构性偏空。

现在有了联网取证，就把它**改成新模式**：退让的前提不再是"我手头没料",而是"**已定向查证、且没能推翻**"。只有 `verified` 证据才有资格逼对方让步；边界不画在"退让多少",画在"**谁有资格要求退让**"——有实证你就得让（不会死杠），没实证你讹不到（不会无脑中庸）。

## ⏰ 从固定闹钟，到（还在路上的）动态节奏

早期是 LangGraph 的机械调度 + 一堆免费 key，只能**固定频率轮询**：不该请求时频繁打，该请求时却在 CD——CPI 都公布了，我的还得等明天才取，赶上接口抽风还请求失败。现在换成让 agent **按需自己去搜**：这些数据其实都找得到，只是杂、更新慢、搜起来烦——交给 AI 反而顺，连欧洲、日本那些平时难找的基本面和新闻都能成功喂进辩论了。

至于更聪明的**动态调度**——AI 吵完根据情况建议下一轮时间、定时瞄一眼大盘、遇到极端行情临时喊 agent 加班——目前只能先当**未来规划**。卡点只有一个：**额度**。不管是 API 烧钱，还是 Claude Code / GPT / Codex 的 usage 上限，都还不允许它敞开了自由呼吸。

## 🔦 让 AI"搜到它自己想发现的东西"，出奇地难

做下来才发现，LLM 搜索远不是"调个 API"那么简单——想引导 AI 顺着某个隐隐的念头去挖、去印证它自己都还没说清的直觉，特别难。这个弱点在 DeepSeek + Linkup API 这套组合上暴露得淋漓尽致：它搜是搜了，却总搜不到点子上。相比之下，GPT、Claude 配**原生搜索**表现好得多。所以现在不管辩论还是复盘，我都尽量只用 CC 和 Codex 版本——哪怕它们额度低。眼下正忙的，就是给这点可怜的额度排班、算配给。

## 🛰️ 横向取证：从"凑合的参照"到"主动去比"

联网搜索其实很有限——覆盖低、还不稳，充其量帮你理清一条新闻的前因后果。真正可靠又便宜的证据是**横向**的：把一只票放进它的同业组里比（NVDA 对 AMD/TSM/AVGO），看相对强弱、相对估值。这一腿是查库现算，确定、便宜、不看运气。

这道理我一开始就懂，只是没资源去实现"主动横向请求"。于是先用了个**妥协设计**：看这只票自己的量化数据，再挂一个相关标的——大盘、或它的板块 ETF——当固定参照。它不是错，是个**中间态**：能给出"它相对大盘/板块偏强还是偏弱"的粗略横向感，却做不到"想比谁就现拉谁"。

这妥协有个天然局限：当这只票本身就是那参照 ETF 的重仓成分（NVDA 之于 SMH），拿 ETF 当基准就成了**拿它跟它自己比**，横向的意义被掏空。

所以这版终于下决心，在盈透（IBKR）核心上把**主动横向取证**搭起来——尽管它架构落后、绝不像 REST 那么清爽（想随手拉个数据从来不是"敲个已知 URL"那么简单），可它便宜、给数据大方。现在辩论里能主动请求相关标的的行情与指标，从"挂一个固定参照"升级成"想比谁就现去比谁"。

## 🫁 给系统装上"呼吸"

这套东西最早是静态的 LangGraph，被动地等外面喂它一次信息。后来我搭了个平行的 Claude Code 版本，验证了"让 AI 自己去搜数据和新闻"行得通，才有了现在这一版。眼下最头疼的是怎么让它**稳定地"呼吸"**：现在靠一个 hermes agent 当"笨闹钟"——注意是"笨"的，它只会按固定点把 Claude Code 喊起来干活，那套"会看情况自己排班"的智能调度，因为没钱（额度）先延后了。可就连这么个笨闹钟，自动化起来也总闹不稳定和权限的幺蛾子，这两天我还在修。能稳定运转的系统，背后大多有一段没人看见的"喘不上气"。

## 🧭 连续性要挣，不许继承

每一轮分析都禁止它偷看自己上一轮的报告，必须对着当期真实数据重新定位——否则误差会像惯性导航一样越漂越远。反直觉的是：不许抄，输出却高度连续，因为这份连续性来自市场本身，不来自它对自己历史的复制。

## 🧧 赛博义和团：写好心法，请祖师爷上身

从第一版起，整部宪法就是**高度凝练的抽象原则——不举例子、不写具体数字、不给某只票某段行情打补丁**。我自己管这套打法叫"赛博义和团"：不教它具体招式，只写一套心法口诀，然后请祖师爷上身、让模型附体去打。听着玄，道理却很实在——一旦开始打补丁，宪法就退化成一张"曾经犯过的错"清单，只在历史重演时才管用；抽象口诀才迁移得动：牛市成立、熊市成立、没见过的行情也成立。

## 🔧 别恳求模型，雕琢管线

我不灌原始时间序列，先降维成 50 多个指标；盘前盘后那些会误导的字段，直接置成 null。模型是个规格已知的元件，架构的全部职责就是别逼它超规格运行。至于幻觉，提醒一句"克制"就够，别指望它们互相监督——三个醉汉搀不出一条直线。

## 🏷️ 一个 LLM 架构撞上人类直觉的 bug

有阵子 QQQ 和 SPY 的数值贴得特别近，AI 居然把两者的量化指标搞混了。复盘才反应过来：这是**注意力机制**和**人类直觉**的差别——人看表格会下意识先瞟一眼表头、确认"这列是谁的"；可 AI 是 attention，并不会强制回头核对归属，数值一接近就张冠李戴。解法很朴素也很冗余：给每一个必要的变量都焊上"它属于谁"的前缀标注，让归属在语法层面就根本无从搞混。

## 🃏 它疯了？不，它算到了第五层

两件八竿子打不着的事让我服了气。一次是 **NVIDIA 财报明明利好，它却连着两天独立喊卖**——我第一反应是"代码出 bug 了"，结果是市场出 bug（指我看漏了）。另一次是**伊朗地缘恐慌**，满屏杀跌，它却淡定看多，那神情活像在说：「这些新闻我早就晓得啦，你们人类真是，跌了哭、涨了叫，要算赔率懂么。」两件事互不相干，却指向同一点：只要数据喂够了，它的分析是真能算到第五层的。系统成熟的标志，不是它的判断让你点头，而是它开始让创造它的人感到意外、且事后被证明是对的。

## 🎭 AI 最危险的不是犯错，是错得和对的一样好看

这是现阶段最头疼的麻烦：**封神的判断和低级的错误，都长着一副反直觉的脸**——光凭直觉，根本分不出哪个是洞见、哪个是事故。更要命的是，AI 还偏偏能把一份低级错误的报告写得**滴水不漏**：修辞流畅、论证完整、"看着就很对"。在文本表面，洞见和事故用的是同一套漂亮话。

唯一靠谱的分辨器，是把论证链一步步溯源：真洞见每一步都踩在真数据上，低级错误必有一环踩空。所以全程把辩论落盘不是存档癖，是为了让错误可被审计——后来一查才发现，那些低级错误报告的根子，几乎都出在各种**信息源的 bug**（喂进去的数据本身就错了），找到了就能对症去修。

由此定出赏罚：**方向算反是打错、是重罪，必须归因到修复为止**；算漏了顶多是小错，漏掉机会轻罚；证据不足时，宁可错过、不可反向。

## 🔁 复盘：不止问对错，要问"当时它能不能看出来"

辩论里有证据官负责查证；复盘同样依赖搜索，只是发生在事后。流程分几步：先用简单的量化数据看结果——在固定档位（3 天、20 天）之后，价格实际走成什么样；再结合当时那份报告和它给出的操作，打一个 0–100 的分：0 为踩空（方向判反），50 为错过（方向看对但没抓住），100 为踩中。

分数决定要不要进一步复盘。默认是踩空或错过才触发；阈值也可以收紧——比如除接近满分的预测外其余一律复盘——只是成本会明显上升。触发之后，回去读当时的原始数据，判断分析是否真有问题：是当时确实无从看出的意外，还是线索本在卷宗里、却没被接住。只有后者是可修正的错误；前者无从追责，那属于赔率本身。

搜索是复盘必要的一环，大约一半情况会用到——尤其当结果与判断差距较大时：查清那几天究竟发生了什么，或当时是否已存在一个能反映趋势、之后才走强的弱信号，有时还有其他值得追查的线索。模型越强，越能从中发现东西。

整体而言，复盘不需要辩论那套对抗：它是事后的判断，确定性走势已经摆在面前，真正必需的只有搜索。因此清算者（reckoner）由单个 agent 线性完成，不调用 Zealot、Reaper、Fulcrum。早先写过一个挂载 grounding + Linkup 搜索的版本，成本偏高；最终改为在 Claude Code 空闲时调用它担任 reckoner——取其当下空闲、且自带搜索。这一环目前仍在调试。

## 🧠 BP 计划：给这套系统做反向传播

BP 就是神经网络里的**反向传播（Backpropagation）**——我给这套自我改进机制起名"BP 计划",正是借这个比方。

起因很实在：现在报告写得又长又专业，我自己都很难、也没时间一份份细看。那怎么知道它到底行不行、错在哪？答案是**等**——用后验数据。一份报告发出若干天后，市场给出真实答案；让 AI 拿这答案逐份**详细复盘**，再把一堆复盘里反复出现的毛病**抽象成共性问题**，最后把这个"梯度"**反馈**回去，调 prompt、调架构。

这不就是反向传播嘛：辩论是前向推理，后验是拿真实标签算误差，复盘是把误差抽象成梯度，改宪法和架构就是更新权重。只不过这里的"梯度"不是数字，是一条被 AI 提炼的抽象教训；"权重"不是矩阵，是那部宪法与这套架构。**拆支点、改贝叶斯，就是 BP 跑出来的第一批大更新。**

顺一句：BP 和上面那条"横向取证",其实我 2026 年初就构思好了，当时只是直觉觉得该这么干，后来也果然管用——只是从想到到做出来，隔了大半年。倒不是什么"好设计值得等",说白了就是：这是个一个人**用爱发电**的私人项目，没资源迅速实现，只能挤着时间一件件慢慢磨。

## 📦 辩论的总信息量守恒，模型只决定打包成几轮

达成收敛需要的总信息量大致是定的，模型能力决定的只是把它打包进几轮里。更聪明的 Claude 每轮写得更长，却收敛得更快——"话多"和"轮次少"是同向出现的。所以轮数本身不是质量指标：聪明模型三轮说完的，笨模型可能磨八轮，吐出来的信息量却差不多。

## 🌡️ 不同的 LLM，各有各的脾气

同一部宪法套在不同模型上，效果能天差地别——因为它们根本是不同的性格：

- **DeepSeek V3**：一个脑子不太灵、吵急了还会复读的杠精——可偏偏经常一杠就杠到所有人都忽略的真问题（V4 就温和正常多了）。
- **Qwen-Plus**：一个老好人，对面一施压就滑跪；让它当裁判更离谱，会自己提前宣布"辩论结束"——这就是后来把裁判权从"史官"这个 AI 角色手里彻底没收的直接原因。
- **Claude**：最聪明，一句顶人家三句，也最印证上一条——能力越强，越是把同样多的信息打包进更少的轮次。

还有个反直觉的小发现：**高温度（temperature）反而更好**——模型更灵活，也没冒出更多幻觉。真正麻烦的是笨模型在低温下：死板、复读、逮谁怼谁，却特别容易被一套漂亮修辞糊弄过去（嘴上最较真，心里最没主见）。

## 📜 宪法对笨模型是教科书，对聪明模型是程序法

给笨模型，宪法是矫正器——你不写"后视降权"，它真就追涨杀跌；给聪明模型，矫正功能贬值了，但"对齐"和"身份锚定"在升值：越聪明越需要被焊死在角色里，因为它更有本事悄悄滑出人设、还把这次滑出自圆其说得天衣无缝。模型越强，约束的重心就越从"教它怎么想"移到"管它别越界"。

## 📏 "MACD 转负"这四个字，不构成论据

要让它成为论据，必须同时报出**幅度**（贴着临界线，还是已经远离？）和**方向**（在扩大，还是在收敛？）；贴着线的小幅穿越，默认就是噪音。这条规则两边都拦：既拦空头的"-1.7，空头确立了"，也拦多头的"RSI 才 53，还没超买呢"——指标是一把刻度尺，不是一个 0/1 开关。

## 🔎 输出要审计，喂进去的输入更要审计

两道关。一是**语义精确**：AI 很会用含混语气把一个"推断"说得像"直接引自数据"，或只给"明显偏弱"这种没刻度的词把你带走。二是**消息溯源**：一条消息每转一手，可信度就衰减一层——总统发条推 → 通讯社引用 → 数据商转发 → 进了卷宗，每环都没撒谎，但来源链层层蒸发，最后系统就把"口头施压"当成了"政策落地"。早期只有免费新闻源时这坑最深：AI 没法知道前因后果，照着层层转载就形成了错误预期。所以现在额度允许时，辩论里 AI 会自己提出查证 **task**，让 Gemini 联网 grounding 搜索、归纳前因后果——把"传不到的证人"变成"当场出庭"，卷宗的上限就被抬高了。（题外一句：被消息误导、和"AI 算赔率比人冷静"这两层一直并存；但目前看是后者占上风——它确实比我们沉得住气。）

---

欢迎来信探讨：**sst19910323@gmail.com**
