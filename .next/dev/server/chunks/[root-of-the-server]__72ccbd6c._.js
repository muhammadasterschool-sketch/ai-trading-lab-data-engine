module.exports = [
"[externals]/next/dist/compiled/next-server/app-route-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-route-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/@opentelemetry/api [external] (next/dist/compiled/@opentelemetry/api, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/@opentelemetry/api", () => require("next/dist/compiled/@opentelemetry/api"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/shared/lib/no-fallback-error.external.js [external] (next/dist/shared/lib/no-fallback-error.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/shared/lib/no-fallback-error.external.js", () => require("next/dist/shared/lib/no-fallback-error.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/after-task-async-storage.external.js [external] (next/dist/server/app-render/after-task-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/after-task-async-storage.external.js", () => require("next/dist/server/app-render/after-task-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/fs/promises [external] (fs/promises, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("fs/promises", () => require("fs/promises"));

module.exports = mod;
}),
"[externals]/path [external] (path, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("path", () => require("path"));

module.exports = mod;
}),
"[externals]/os [external] (os, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("os", () => require("os"));

module.exports = mod;
}),
"[project]/src/app/api/ai/youtube/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "POST",
    ()=>POST,
    "dynamic",
    ()=>dynamic
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/server.js [app-route] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$z$2d$ai$2d$web$2d$dev$2d$sdk$2f$dist$2f$index$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/z-ai-web-dev-sdk/dist/index.js [app-route] (ecmascript)");
;
;
const dynamic = 'force-dynamic';
/**
 * AI YouTube Strategy Watcher — v1.2 Strategy Lab
 * POST { url } = ek YouTube video link. Server video ka transcript (captions)
 * nikalta hai, LLM se strategy extract karwata hai, aur strategy-spec JSON
 * return karta hai. Phone engine isse StrategyLab mein backtest karta hai.
 */ const DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';
const SYSTEM = `You are a trading-strategy extractor. You get the transcript of a YouTube trading video.
Extract the MAIN trading strategy being taught/used and output ONE strict JSON object. No markdown — ONLY JSON.

Supported indicator conditions (use ONLY these):
  {"ind":"rsi","p":14,"op":"<","v":30}                          rsi(p) vs number; op: < <= > >=
  {"ind":"price_vs_ema","p":50,"op":"above"}                    close vs EMA(p); op: above|below
  {"ind":"ema_cross","f":9,"s":21,"op":"golden"}                EMA fast vs slow state; op: golden|death
  {"ind":"sma","p":20,"op":"price_above"}                       op: price_above|price_below|slope_up|slope_down
  {"ind":"macd","f":12,"s":26,"sig":9,"op":"bull"}              MACD line vs signal; op: bull|bear
  {"ind":"bb","p":20,"k":2,"op":"lower_touch"}                  Bollinger; op: lower_touch|upper_touch|squeeze
  {"ind":"atr","p":14,"op":">","v":0.3}                         ATR as % of price vs number
  {"ind":"supertrend","p":10,"m":3,"op":"bull"}                 op: bull|bear
  {"ind":"volume","p":20,"op":">","v":1.5}                      volume > v × avg(p)
  {"ind":"change","n":5,"op":">","v":1.0}                       % change over last n candles; op: < <= > >=
  {"ind":"stoch","p":14,"op":"<","v":20}
  {"ind":"cci","p":20,"op":"<","v":-100}
  {"ind":"mfi","p":14,"op":"<","v":20}
  {"ind":"adx","p":14,"op":">","v":25}
  {"ind":"candle","op":"engulf_bull"}                           op: engulf_bull|engulf_bear|doji|hammer

Output schema:
{"name":"short English name","side":"BOTH","logic":"ALL","conditions":[...max 4...],"notes":"one-line summary of what the video taught"}
side: BUY|SELL|BOTH. logic: ALL|ANY. Rules: max 4 conditions, map the video's rules as faithfully as possible to the supported indicators. If the video teaches nothing strategy-like, still output your closest honest mapping. JSON only.`;
function videoId(url) {
    const m = url.match(/(?:v=|youtu\.be\/|\/shorts\/|\/live\/|\/embed\/)([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
}
function extractJson(raw) {
    const t = raw.replace(/```json/gi, '```').split('```').join('\n');
    const s = t.indexOf('{');
    const e = t.lastIndexOf('}');
    if (s < 0 || e <= s) throw new Error('no json');
    return JSON.parse(t.slice(s, e + 1));
}
async function getTranscript(vid) {
    const page = await fetch(`https://www.youtube.com/watch?v=${vid}&hl=en`, {
        headers: {
            'User-Agent': DESKTOP_UA,
            'Accept-Language': 'en-US,en;q=0.9'
        }
    }).then((r)=>r.text());
    const m = page.match(/"captionTracks":(\[.*?\])(,"audioTracks"|,"translationLanguages"|\})/s);
    if (!m) throw new Error('captions not found');
    const tracks = JSON.parse(m[1].replace(/\\u0026/g, '&').replace(/\\\\/g, '\\'));
    const track = tracks.find((t)=>t.languageCode === 'en' && !t.kind) || tracks.find((t)=>String(t.languageCode).startsWith('en')) || tracks[0];
    if (!track?.baseUrl) throw new Error('no caption track');
    const cap = await fetch(track.baseUrl + '&fmt=json3', {
        headers: {
            'User-Agent': DESKTOP_UA
        }
    }).then((r)=>r.text());
    const j = JSON.parse(cap);
    let out = '';
    for (const ev of j.events || []){
        if (!ev.segs) continue;
        for (const s of ev.segs)if (s.utf8) out += s.utf8;
    }
    out = out.replace(/\s+/g, ' ').trim();
    if (out.length < 200) throw new Error('transcript too short');
    return out.slice(0, 12000);
}
function metaFromPage(page) {
    const t = page.match(/<title>(.*?)<\/title>/);
    const ch = page.match(/"ownerChannelName":"(.*?)"/) || page.match(/"author":"(.*?)"/);
    return {
        title: t ? t[1].replace(/ - YouTube$/, '').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"') : 'YouTube video',
        channel: ch ? ch[1].replace(/\\u0026/g, '&') : ''
    };
}
async function POST(req) {
    try {
        const body = await req.json().catch(()=>({}));
        const url = String(body?.url || '').trim();
        const vid = videoId(url);
        if (!vid) return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: 'Ye YouTube video link nahi lag raha'
        }, {
            status: 400
        });
        const page = await fetch(`https://www.youtube.com/watch?v=${vid}&hl=en`, {
            headers: {
                'User-Agent': DESKTOP_UA,
                'Accept-Language': 'en-US,en;q=0.9'
            }
        }).then((r)=>r.text());
        const meta = metaFromPage(page);
        let transcript;
        try {
            transcript = await getTranscript(vid);
        } catch  {
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                error: 'Is video ke captions available nahi hain — koi aur video try karein jo captions wali ho'
            }, {
                status: 422
            });
        }
        const zai = await __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$z$2d$ai$2d$web$2d$dev$2d$sdk$2f$dist$2f$index$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["default"].create();
        const completion = await zai.chat.completions.create({
            messages: [
                {
                    role: 'assistant',
                    content: SYSTEM
                },
                {
                    role: 'user',
                    content: `Video title: ${meta.title}\nChannel: ${meta.channel}\n\nTranscript:\n${transcript}`
                }
            ],
            thinking: {
                type: 'disabled'
            }
        });
        const raw = completion.choices[0]?.message?.content || '';
        let spec;
        try {
            spec = extractJson(raw);
        } catch  {
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                error: 'AI transcript se strategy nahi nikal saka — doosri video try karein'
            }, {
                status: 502
            });
        }
        const conds = Array.isArray(spec.conditions) ? spec.conditions.slice(0, 4) : [];
        if (!conds.length) return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: 'Video mein koi machine-readable strategy nahi mili'
        }, {
            status: 502
        });
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            ok: true,
            video: {
                id: vid,
                title: meta.title,
                channel: meta.channel,
                url: `https://www.youtube.com/watch?v=${vid}`
            },
            spec: {
                name: String(spec.name || meta.title).slice(0, 60),
                side: [
                    'BUY',
                    'SELL',
                    'BOTH'
                ].includes(String(spec.side)) ? String(spec.side) : 'BOTH',
                logic: String(spec.logic) === 'ANY' ? 'ANY' : 'ALL',
                conditions: conds,
                notes: String(spec.notes || '').slice(0, 200)
            }
        });
    } catch (e) {
        console.error('ai/youtube error', e);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: 'YouTube/AI service error — thori dair baad try karein'
        }, {
            status: 500
        });
    }
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__72ccbd6c._.js.map