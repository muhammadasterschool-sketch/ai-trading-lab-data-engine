const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
(async () => {
  const users = await p.user.findMany({
    select: { id: true, name: true, email: true, role: true, isActive: true, totpEnabled: true, totpSecret: true, passwordHash: true, createdAt: true },
  });
  console.log(JSON.stringify(users, null, 2));
  const sessions = await p.session.count();
  console.log('sessions:', sessions);
  await p.$disconnect();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
