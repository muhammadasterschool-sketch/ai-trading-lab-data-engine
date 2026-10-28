// Generate Android mipmap icons from the PWA master icon
import sharp from 'sharp'

const base = '/home/z/my-project/public/icon-512.png'
const out = '/home/z/my-project/android-app/app/src/main/res'
const sizes = { 'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192 }

async function main() {
  for (const [dpi, px] of Object.entries(sizes)) {
    await sharp(base).resize(px, px).png().toFile(`${out}/mipmap-${dpi}/ic_launcher.png`)
  }
  console.log('mipmaps done')
}

main()
