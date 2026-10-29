import { NextRequest, NextResponse } from 'next/server'
import ZAI from 'z-ai-web-dev-sdk'

export const dynamic = 'force-dynamic'

/**
 * AI Strategy Compiler — v1.2 Strategy Lab
 * Phone engine POSTs { text } (user ki likhi hui strategy, kisi bhi zubaan mein).
 * LLM usse strict strategy-spec JSON mein compile karta hai jo Android
 * StrategyLab evaluator backtest / paper / live kar sakta hai.
 */

const SYSTEM = `You are a trading-strategy compiler for a 1-minute-candle crypto paper trading engine.
Convert the user's strategy description into ONE strict JSON object. No markdown, no commentary — ONLY the JSON.

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
  {"ind":"stoch","p":14,"op":"<","v":20}                        stoch %K vs number
  {"ind":"cci","p":20,"op":"<","v":-100}
  {"ind":"mfi","p":14,"op":"<","v":20}
  {"ind":"adx","p":14,"op":">","v":25}                          trend-strength filter
  {"ind":"candle","op":"engulf_bull"}                           op: engulf_bull|engulf_bear|doji|hammer

Output schema:
{"name":"short English name","side":"BOTH","logic":"ALL","conditions":[...max 4...],"notes":"one-line summary"}
side: BUY|SELL|BOTH (BOTH = signal direction decides). logic: ALL|ANY.
Rules: max 4 conditions, translate user intent faithfully, if the user's idea cannot map to supported indicators pick the closest faithful mapping. Respond with JSON only.`

function extractJson(raw: string): unknown {
  const t = raw.replace(/```json/gi, '```').split('```').join('\n')
  const s = t.indexOf('{')
  const e = t.lastIndexOf('}')
  if (s < 0 || e <= s) throw new Error('no json object in model output')
  return JSON.parse(t.slice(s, e + 1))
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}))
    const text = String(body?.text || '').trim()
    if (text.length < 5) return NextResponse.json({ error: 'Strategy text bohat chhota hai' }, { status: 400 })
    if (text.length > 4000) return NextResponse.json({ error: 'Strategy text bohat lamba hai (max 4000 chars)' }, { status: 400 })

    const zai = await ZAI.create()
    const completion = await zai.chat.completions.create({
      messages: [
        { role: 'assistant', content: SYSTEM },
        { role: 'user', content: text.slice(0, 4000) },
      ],
      thinking: { type: 'disabled' },
    })
    const raw = completion.choices[0]?.message?.content || ''
    let spec: Record<string, unknown>
    try {
      spec = extractJson(raw) as Record<string, unknown>
    } catch {
      return NextResponse.json({ error: 'AI ne valid strategy JSON nahi banaya — thoda aur specific likh kar dobara try karein' }, { status: 502 })
    }
    const conds = Array.isArray(spec.conditions) ? (spec.conditions as unknown[]).slice(0, 4) : []
    if (!conds.length) return NextResponse.json({ error: 'Strategy mein koi valid condition nahi bani' }, { status: 502 })
    const clean = {
      name: String(spec.name || 'Custom Strategy').slice(0, 60),
      side: ['BUY', 'SELL', 'BOTH'].includes(String(spec.side)) ? String(spec.side) : 'BOTH',
      logic: String(spec.logic) === 'ANY' ? 'ANY' : 'ALL',
      conditions: conds,
      notes: String(spec.notes || '').slice(0, 200),
    }
    return NextResponse.json({ ok: true, spec: clean })
  } catch (e) {
    console.error('ai/strategy error', e)
    return NextResponse.json({ error: 'AI service error — thori dair baad try karein' }, { status: 500 })
  }
}
