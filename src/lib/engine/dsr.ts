// ============ Deflated Sharpe Ratio noise bar ============
// Bailey & López de Prado (2014): under a null where every trial has zero
// true skill, the expected maximum Sharpe across N trials is
//   E[max SR] ≈ ((1-γ)·Φ⁻¹(1-1/N) + γ·Φ⁻¹(1-1/(N·e))) · σ_trials
// where γ ≈ 0.5772 (Euler-Mascheroni) and σ_trials is the cross-trial std of
// Sharpe estimates. This reproduces the published table:
// N=4→1.05σ, N=8→1.46σ, N=16→1.80σ, N=25→2.00σ, N=50→2.28σ.

const GAMMA = 0.5772156649015329

/** Acklam's inverse normal CDF approximation */
function probit(p: number): number {
  if (p <= 0) return -Infinity
  if (p >= 1) return Infinity
  // Coefficients
  const a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.38357751867269e2, -3.066479806614716e1, 2.506628277459239]
  const b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1]
  const c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783]
  const d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416]
  const plow = 0.02425
  const phigh = 1 - plow
  let q: number
  let r: number
  if (p < plow) {
    q = Math.sqrt(-2 * Math.log(p))
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
  }
  if (p <= phigh) {
    q = p - 0.5
    r = q * q
    return ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
  }
  q = Math.sqrt(-2 * Math.log(1 - p))
  return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
}

/** Expected max Sharpe of N zero-skill trials, in cross-trial σ units. */
export function expectedMaxNoiseZ(n: number): number {
  if (n < 2) return 0
  const z1 = probit(1 - 1 / n)
  const z2 = probit(1 - 1 / (n * Math.E))
  return (1 - GAMMA) * z1 + GAMMA * z2
}

/** Published reference points (Bailey-LdP) for UI display */
export const DSR_REFERENCE: Array<{ n: number; sigma: number }> = [
  { n: 4, sigma: 1.05 },
  { n: 8, sigma: 1.46 },
  { n: 16, sigma: 1.8 },
  { n: 25, sigma: 2.0 },
  { n: 50, sigma: 2.28 },
]

/**
 * Full deflation for a scan: given the winning Sharpe, the number of trials,
 * the cross-trial Sharpe std and the sample length (bars), compute:
 *  - noiseBarZ: expected best Sharpe from pure noise (σ units)
 *  - noiseBarSharpe: same in Sharpe units (× σ_trials)
 *  - deflatedSharpe: winner's Sharpe deflated for selection & non-normality
 *  - clearsNoise: does the winner beat the noise bar?
 */
export function deflateSharpe(
  winnerSharpe: number,
  trials: number,
  sigmaTrials: number,
  sampleBars: number,
  skewness = 0,
  kurtosis = 3
): {
  noiseBarZ: number
  noiseBarSharpe: number
  deflatedSharpe: number
  clearsNoise: boolean
} {
  const noiseBarZ = expectedMaxNoiseZ(trials)
  const sigma = Math.max(1e-9, sigmaTrials)
  const noiseBarSharpe = noiseBarZ * sigma

  // standard error of a single Sharpe estimate (LdP): sqrt((1 - skewness*SR + (kurtosis-1)/4 * SR^2)/(n-1))
  const sr = winnerSharpe / Math.sqrt(Math.max(1, sampleBars)) // per-bar Sharpe
  const seBar = Math.sqrt(Math.max(1e-12, (1 - skewness * sr + ((kurtosis - 1) / 4) * sr * sr) / Math.max(1, sampleBars - 1)))
  const seSharpe = seBar * Math.sqrt(Math.max(1, sampleBars)) // back to annualized-ish units
  const deflated = (winnerSharpe - noiseBarSharpe) / Math.max(1e-9, seSharpe)
  return {
    noiseBarZ,
    noiseBarSharpe,
    deflatedSharpe: Math.round(deflated * 100) / 100,
    clearsNoise: winnerSharpe > noiseBarSharpe,
  }
}

/** Cross-trial σ of Sharpe estimates */
export function sharpeStd(sharpes: number[]): number {
  const vals = sharpes.filter((v) => isFinite(v))
  if (vals.length < 2) return 0
  const mean = vals.reduce((s, v) => s + v, 0) / vals.length
  const variance = vals.reduce((s, v) => s + (v - mean) ** 2, 0) / (vals.length - 1)
  return Math.sqrt(variance)
}
