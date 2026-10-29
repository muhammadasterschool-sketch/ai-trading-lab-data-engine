import { NextRequest, NextResponse } from 'next/server'
import ZAI from 'z-ai-web-dev-sdk'

export const dynamic = 'force-dynamic'

/**
 * AI transcript → strategy extractor — v1.2 Strategy Lab.
 * PHONE pehle YouTube page se captions/transcript nikalta hai (phone ka
 * residential IP YouTube se block nahi hota — datacenter IP hota hai), phir
 * sirf TEXT yahan aata hai aur LLM strategy-spec JSON banata hai.
 */

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
side: BUY|SELL|BOTH. logic: ALL|ANY. Rules: max 4 conditions, map the video's rules as faithfully as possible to the supported indicators. If the video teaches nothing strategy-like, still output your closest honest mapping. JSON only.`

function extractJson(raw: string): unknown {
  const t = raw.replace(/```json/gi, '```').split('```').join('\n')
  const s = t.indexOf('{')
  const e = t.lastIndexOf('}')
  if (s < 0 || e <= s) throw new Error('no json')
  return JSON.parse(t.slice(s, e + 1))
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}))
    const transcript = String(body?.transcript || '').trim()
    const title = String(body?.title || 'YouTube video').slice(0, 200)
    const channel = String(body?.channel || '').slice(0, 120)
    if (transcript.length < 200) return NextResponse.json({ error: 'Transcript bohat chhota hai' }, { status: 400 })

    const zai = await ZAI.create()
    const completion = await zai.chat.completions.create({
      messages: [
        { role: 'assistant', content: SYSTEM },
        { role: 'user', content: `Video title: ${title}\nChannel: ${channel}\n\nTranscript:\n${transcript.slice(0, 12000)}` },
      ],
      thinking: { type: 'disabled' },
    })
    const raw = completion.choices[0]?.message?.content || ''
    let spec: Record<string, unknown>
    try {
      spec = extractJson(raw) as Record<string, unknown>
    } catch {
      return NextResponse.json({ error: 'AI transcript se strategy nahi nikal saka — doosri video try karein' }, { status: 502 })
    }
    const conds = Array.isArray(spec.conditions) ? (spec.conditions as unknown[]).slice(0, 4) : []
    if (!conds.length) return NextResponse.json({ error: 'Video mein koi machine-readable strategy nahi mili' }, { status: 502 })

    return NextResponse.json({
      ok: true,
      spec: {
        name: String(spec.name || title).slice(0, 60),
        side: ['BUY', 'SELL', 'BOTH'].includes(String(spec.side)) ? String(spec.side) : 'BOTH',
        logic: String(spec.logic) === 'ANY' ? 'ANY' : 'ALL',
        conditions: conds,
        notes: String(spec.notes || '').slice(0, 200),
      },
    })
  } catch (e) {
    console.error('ai/transcript error', e)
    return NextResponse.json({ error: 'AI service error — thori dair baad try karein' }, { status: 500 })
  }
}
