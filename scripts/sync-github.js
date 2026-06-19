#!/usr/bin/env node
// sync-github.js — Exporta cron jobs, commit + push para GitHub.
// Corre automático todos os dias às 01:00 (cron).

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const repoDir = path.join(process.env.USERPROFILE, '.openclaw');
const exportFile = path.join(repoDir, 'workspace', 'config-export.md');
const now = new Date().toISOString().slice(0, 16).replace('T', ' ');

process.chdir(repoDir);

const log = (...a) => console.log(...a);
const ok  = (m) => log(`\x1b[32m✅ ${m}\x1b[0m`);
const warn = (m) => log(`\x1b[33m⚠️  ${m}\x1b[0m`);

log('\x1b[36m🔍 Exporting cron jobs...\x1b[0m');

let cronJobs = [];
try {
  const raw = execSync('openclaw cron list', { encoding: 'utf8', timeout: 15000 });
  cronJobs = (JSON.parse(raw).jobs) || [];
} catch { warn('Gateway offline — no cron jobs to export'); }

const md = [
  '# Config Export — Macking/OpenClaw',
  '',
  `> Export automático via sync-github. Gerado a ${now}.`,
  '> API keys **não versionadas** (`.gitignore` cobre-as).',
  '',
  '---',
  '',
  '## Cron Jobs',
  '',
];

if (cronJobs.length === 0) {
  md.push('> (nenhum cron job)');
} else {
  for (const j of cronJobs) {
    const st = j.state?.lastRunStatus === 'ok' ? '✅ OK' : '❌ Falhou';
    md.push(
      `### ${j.name}`,
      '',
      '| Campo | Valor |',
      '|---|---|',
      `| Schedule | \`${j.schedule.expr}\` |`,
      `| TZ | ${j.schedule.tz} |`,
      `| Session | ${j.sessionTarget} |`,
      `| Timeout | ${j.payload.timeoutSeconds}s |`,
      `| Delivery | ${j.delivery.mode} → ${j.delivery.channel}:${j.delivery.to} |`,
      `| Último | ${st} (${j.state?.lastDurationMs}ms) |`,
      '',
      j.payload.message ? `**Payload:**\n\`\`\`\n${j.payload.message}\n\`\`\`\n` : '',
      '---',
      '',
    );
  }
}

md.push(
  '## Workspace',
  '',
  '| Ficheiro | Propósito |',
  '|---|---|',
  '| AGENTS.md | Comportamento do assistente |',
  '| SOUL.md | Personalidade |',
  '| USER.md | Quem é o humano |',
  '| IDENTITY.md | Identidade (Mcking) |',
  '| TOOLS.md | Notas de ferramentas |',
  '| HEARTBEAT.md | Template heartbeat |',
  '| memory/ | Memórias diárias |',
  '| config-export.md | Este export |',
);

fs.writeFileSync(exportFile, md.filter(Boolean).join('\n'), 'utf8');
ok('config-export.md updated');

try {
  const status = execSync('git status --porcelain', { encoding: 'utf8', timeout: 10000 }).trim();
  if (!status) { ok('Nothing new to sync — all clean!'); process.exit(0); }

  log('\x1b[36m📦 Syncing to GitHub...\x1b[0m');
  status.split('\n').forEach(l => log(`   ${l}`));

  execSync('git add -A', { timeout: 10000 });
  execSync(`git commit -m "sync: ${now}"`, { timeout: 10000 });
  execSync('git push', { timeout: 30000 });

  log('');
  ok('Synced to GitHub! 🚀');
} catch (e) {
  log('');
  warn('Push failed. Check SSH:');
  log('   ssh -T git@github.com');
  if (e.stderr) log('   ' + e.stderr.trim().split('\n').pop());
}
