import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

/**
 * YouTube channel video list — v1.2 Strategy Lab watcher support.
 * POST { url } = channel link (@handle, /channel/UC..., /c/name, /user/name)
 * → resolve channel_id → YouTube RSS feed → latest 15 videos (title, id,
 * published, live flag). Phone engine isse poll karta hai: jab YouTuber naya
 * video ya live stream upload kare, engine foran usse AI se process karwata hai.
 */

const DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

async function resolveChannelId(url: string): Promise<string | null> {
  if (url.includes('/channel/')) {
    const m = url.match(/channel\/(UC[A-Za-z0-9_-]{20,})/)
    return m ? m[1] : null
  }
  const page = await fetch(url, { headers: { 'User-Agent': DESKTOP_UA, 'Accept-Language': 'en-US,en;q=0.9' } }).then((r) => r.text())
  const m =
    page.match(/"externalId":"(UC[A-Za-z0-9_-]{20,})"/) ||
    page.match(/channel\/(UC[A-Za-z0-9_-]{20,})/) ||
    page.match(/"channelId":"(UC[A-Za-z0-9_-]{20,})"/)
  return m ? m[1] : null
}

function decodeXml(s: string): string {
  return s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}))
    const url = String(body?.url || '').trim()
    if (!url.startsWith('http')) return NextResponse.json({ error: 'Channel ka poora link dein (https://youtube.com/@...)' }, { status: 400 })

    const cid = await resolveChannelId(url)
    if (!cid) return NextResponse.json({ error: 'Channel ID resolve nahi hui — link check karein' }, { status: 422 })

    const rss = await fetch(`https://www.youtube.com/feeds/videos.xml?channel_id=${cid}`, {
      headers: { 'User-Agent': DESKTOP_UA },
    }).then((r) => r.text())

    const entries: Array<{ id: string; title: string; published: string; live: boolean }> = []
    const blocks = rss.split('<entry>').slice(1)
    for (const b of blocks) {
      const id = b.match(/<yt:videoId>(.*?)<\/yt:videoId>/)?.[1]
      const title = b.match(/<title>(.*?)<\/title>/)?.[1]
      const pub = b.match(/<published>(.*?)<\/published>/)?.[1]
      const live = /liveBroadcastContent>(live|upcoming)</.test(b)
      if (id && title) entries.push({ id, title: decodeXml(title), published: pub || '', live })
    }

    const chName = decodeXml(rss.match(/<author>[\s\S]*?<name>(.*?)<\/name>/)?.[1] || '')
    return NextResponse.json({ ok: true, channel: { id: cid, name: chName }, videos: entries.slice(0, 15) })
  } catch (e) {
    console.error('ai/ytlist error', e)
    return NextResponse.json({ error: 'YouTube channel fetch error — thori dair baad try karein' }, { status: 500 })
  }
}
