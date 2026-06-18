#!/usr/bin/env node
// sync-github.js — Exporta cron jobs e sincroniza com GitHub
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const repoDir = path.join(process.env.USERPROFILE, '.openclaw');
const exportFile = path.join(repoDir, 'workspace', 'config-export.md');

process.chdir(repoDir);
const now = new Date().toISOString().slice(0, 16).replace('T', ' ');

console.log('\x1b[36m🔍 A exportar cron jobs...\x1b[0m');

// Get cron jobs
let cronJobs = [];
try {
  const raw = execSync('openclaw cron list', { encoding: 'utf8', timeout: 15000 });
  const parsed = JSON.parse(raw);
  cronJobs = parsed.jobs || [];
} catch {
  console.log('\x1b[33m⚠️  Gateway offline ou sem cron jobs.\x1b[0m');
}

// Build markdown
const lines = [];
const add = (t) => lines.push(t);

add('# Config Export — Macking/OpenClaw');
add('');
add(`> Export automático via sync-github. Gerado a ${now}.`);
add('> Para restaurar: instalar OpenClaw, clonar repo, recriar cron jobs.');
add('> API keys **não estão versionadas** (só no .gitignore).');
add('');
add('---');
add('');
add('## Cron Jobs');
add('');

if (cronJobs.length === 0) {
  add('> (nenhum cron job configurado)');
} else {
  for (const job of cronJobs) {
    add(`### ${job.name}`);
    add('');
    add('| Campo | Valor |');
    add('|---|---|');
    add(`| ID | ${job.id} |`);
    add(`| Schedule | ${job.schedule.expr} |`);
    add(`| Timezone | ${job.schedule.tz} |`);
    add(`| Session | ${job.sessionTarget} |`);
    add(`| Timeout | ${job.payload.timeoutSeconds}s |`);
    add(`| Delivery | ${job.delivery.mode} → ${job.delivery.channel}:${job.delivery.to} |`);
    const st = job.state?.lastRunStatus === 'ok' ? '✅ OK' : '❌ Falhou';
    add(`| Último run | ${st} (${job.state?.lastDurationMs}ms) |`);
    add('');
    if (job.payload.message) {
      add('**Payload:**');
      add('```');
      add(job.payload.message);
      add('```');
    }
    add('');
    add('---');
    add('');
  }
}

add('');
add('## Estrutura do Workspace');
add('');
add('| Ficheiro | Propósito |');
add('|---|---|');
add('| AGENTS.md | Instruções de comportamento |');
add('| SOUL.md | Personalidade do assistente |');
add('| USER.md | Info do humano |');
add('| IDENTITY.md | Identidade (Macking) |');
add('| TOOLS.md | Notas de ferramentas locais |');
add('| HEARTBEAT.md | Template de heartbeat |');
add('| memory/ | Memórias diárias |');
add('| config-export.md | Export de config |');

fs.writeFileSync(exportFile, lines.join('\n'), 'utf8');
console.log('   \x1b[32m✅ config-export.md atualizado\x1b[0m');

// Git sync
try {
  const status = execSync('git status --porcelain', { encoding: 'utf8', timeout: 10000 }).trim();
  
  if (!status) {
    console.log('\x1b[32m✨ Nada novo para sincronizar — tudo em dia!\x1b[0m');
    process.exit(0);
  }

  console.log('\x1b[36m📦 A sincronizar com GitHub...\x1b[0m');
  for (const line of status.split('\n')) {
    console.log(`   ${line}`);
  }

  execSync('git add -A', { timeout: 10000 });
  execSync(`git commit -m "sync: ${now}"`, { timeout: 10000 });
  execSync('git push', { timeout: 30000 });

  console.log('');
  console.log('\x1b[32m✅ Sincronizado com sucesso! 🚀\x1b[0m');
} catch (e) {
  console.log('');
  console.log('\x1b[33m⚠️  Push falhou. Verifica SSH:\x1b[0m');
  console.log('   ssh -T git@github.com');
  if (e.stderr) console.log('   ' + e.stderr.trim().split('\n').pop());
}
