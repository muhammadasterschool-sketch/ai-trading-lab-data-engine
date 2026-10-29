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
"[project]/src/app/api/ai/ytlist/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "POST",
    ()=>POST,
    "dynamic",
    ()=>dynamic
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/server.js [app-route] (ecmascript)");
;
const dynamic = 'force-dynamic';
/**
 * YouTube channel video list — v1.2 Strategy Lab watcher support.
 * POST { url } = channel link (@handle, /channel/UC..., /c/name, /user/name)
 * → resolve channel_id → YouTube RSS feed → latest 15 videos (title, id,
 * published, live flag). Phone engine isse poll karta hai: jab YouTuber naya
 * video ya live stream upload kare, engine foran usse AI se process karwata hai.
 */ const DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';
async function resolveChannelId(url) {
    if (url.includes('/channel/')) {
        const m = url.match(/channel\/(UC[A-Za-z0-9_-]{20,})/);
        return m ? m[1] : null;
    }
    const page = await fetch(url, {
        headers: {
            'User-Agent': DESKTOP_UA,
            'Accept-Language': 'en-US,en;q=0.9'
        }
    }).then((r)=>r.text());
    const m = page.match(/"externalId":"(UC[A-Za-z0-9_-]{20,})"/) || page.match(/channel\/(UC[A-Za-z0-9_-]{20,})/) || page.match(/"channelId":"(UC[A-Za-z0-9_-]{20,})"/);
    return m ? m[1] : null;
}
function decodeXml(s) {
    return s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
}
async function POST(req) {
    try {
        const body = await req.json().catch(()=>({}));
        const url = String(body?.url || '').trim();
        if (!url.startsWith('http')) return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: 'Channel ka poora link dein (https://youtube.com/@...)'
        }, {
            status: 400
        });
        const cid = await resolveChannelId(url);
        if (!cid) return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: 'Channel ID resolve nahi hui — link check karein'
        }, {
            status: 422
        });
        const rss = await fetch(`https://www.youtube.com/feeds/videos.xml?channel_id=${cid}`, {
            headers: {
                'User-Agent': DESKTOP_UA
            }
        }).then((r)=>r.text());
        const entries = [];
        const blocks = rss.split('<entry>').slice(1);
        for (const b of blocks){
            const id = b.match(/<yt:videoId>(.*?)<\/yt:videoId>/)?.[1];
            const title = b.match(/<title>(.*?)<\/title>/)?.[1];
            const pub = b.match(/<published>(.*?)<\/published>/)?.[1];
            const live = /liveBroadcastContent>(live|upcoming)</.test(b);
            if (id && title) entries.push({
                id,
                title: decodeXml(title),
                published: pub || '',
                live
            });
        }
        const chName = decodeXml(rss.match(/<author>[\s\S]*?<name>(.*?)<\/name>/)?.[1] || '');
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            ok: true,
            channel: {
                id: cid,
                name: chName
            },
            videos: entries.slice(0, 15)
        });
    } catch (e) {
        console.error('ai/ytlist error', e);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: 'YouTube channel fetch error — thori dair baad try karein'
        }, {
            status: 500
        });
    }
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__2029daf9._.js.map