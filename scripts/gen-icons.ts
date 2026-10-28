// Generate PWA icons for AI Trading Lab (gold bolt on dark) using sharp
import sharp from 'sharp'

const bolt = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#fbbf24"/>
      <stop offset="1" stop-color="#d97706"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="96" fill="#09090b"/>
  <rect x="24" y="24" width="464" height="464" rx="80" fill="none" stroke="#27272a" stroke-width="8"/>
  <path d="M300 64 L150 280 L232 280 L212 448 L362 232 L280 232 Z" fill="url(#g)" stroke="#fde68a" stroke-width="6" stroke-linejoin="round"/>
</svg>`

async function main() {
  const base = '/home/z/my-project/public'
  await sharp(Buffer.from(bolt)).resize(512, 512).png().toFile(`${base}/icon-512.png`)
  await sharp(Buffer.from(bolt)).resize(192, 192).png().toFile(`${base}/icon-192.png`)
  // apple-touch-icon: solid background, no transparency, 180x180
  await sharp(Buffer.from(bolt)).resize(180, 180).png().toFile(`${base}/apple-touch-icon.png`)
  await sharp(Buffer.from(bolt)).resize(32, 32).png().toFile(`${base}/favicon.png`)
  // maskable icon with extra safe padding
  const padded = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
    <rect width="512" height="512" fill="#09090b"/>
    <path d="M300 104 L170 292 L240 292 L224 408 L354 220 L284 220 Z" fill="#fbbf24" stroke="#fde68a" stroke-width="6" stroke-linejoin="round"/>
  </svg>`
  await sharp(Buffer.from(padded)).resize(512, 512).png().toFile(`${base}/icon-maskable-512.png`)
  console.log('icons generated')
}

main()
