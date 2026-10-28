const { PrismaClient } = require('@prisma/client');
const crypto = require('crypto');

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(password, salt, 64).toString('hex');
  return `scrypt:${salt}:${hash}`;
}

const p = new PrismaClient();
(async () => {
  const email = 'muhammadasterschool@gmail.com';
  const user = await p.user.findUnique({ where: { email } });
  if (!user) { console.error('admin not found'); process.exit(1); }

  await p.user.update({
    where: { id: user.id },
    data: {
      passwordHash: hashPassword('M2991474'),
      totpEnabled: false,
      totpSecret: null,
      isActive: true,
    },
  });

  // kill stale sessions — force a clean fresh login
  const gone = await p.session.deleteMany({ where: { userId: user.id } });
  console.log('OK: admin password -> M2991474, TOTP reset (fresh QR at next login), sessions deleted:', gone.count);
  await p.$disconnect();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
