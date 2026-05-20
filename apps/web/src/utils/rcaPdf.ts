/**
 * rcaPdf.ts
 * Generates a premium branded PDF for the Root Cause Analysis report.
 * Same canvas-slice pipeline as postmortemPdf.ts — no text extraction = no garbling.
 */
import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import type { InvestigationResult } from '../api/client'

// ── Helpers ──────────────────────────────────────────────────────────────────

function esc(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}

function fmtEnum(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function mdList(text: string): string {
  if (!text) return ''
  let html = ''
  let inOl = false, inUl = false
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    const ol = line.match(/^\d+\.\s+(.+)/)
    const ul = line.match(/^[-*]\s+(.+)/)
    if (ol) {
      if (inUl) { html += '</ul>'; inUl = false }
      if (!inOl) { html += '<ol>'; inOl = true }
      html += `<li>${esc(ol[1])}</li>`
    } else if (ul) {
      if (inOl) { html += '</ol>'; inOl = false }
      if (!inUl) { html += '<ul>'; inUl = true }
      html += `<li>${esc(ul[1])}</li>`
    } else {
      if (inOl) { html += '</ol>'; inOl = false }
      if (inUl) { html += '</ul>'; inUl = false }
      if (line.startsWith('> ')) { html += `<blockquote>${esc(line.slice(2))}</blockquote>` }
      else if (line) html += `<p>${esc(line)}</p>`
    }
  }
  if (inOl) html += '</ol>'
  if (inUl) html += '</ul>'
  return html
}

// ── Inline SVG icons (html2canvas renders SVG correctly) ─────────────────────

const CORVIN_SVG = (size: number, color = 'white') => `
  <svg width="${size}" height="${size}" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="32" height="32" rx="7.5" fill="rgba(255,255,255,0.15)" stroke="${color}" stroke-width="1"/>
    <path d="M21.5 9A9 9 0 1 0 21.5 23" stroke="${color}" stroke-width="2.8" fill="none" stroke-linecap="round"/>
    <path d="M16 12L20 16L16 20L12 16Z" fill="${color}"/>
  </svg>`

const confBadgeColor = (c: string) =>
  c === 'high' ? '#16a34a' : c === 'low' ? '#dc2626' : '#d97706'

// ── HTML template ─────────────────────────────────────────────────────────────

function buildHtml(data: InvestigationResult): string {
  const { rca, fix_strategy, request, request_id } = data
  if (!rca) return '<body>No RCA data.</body>'

  const genDate = new Date().toLocaleString('en-US', {
    dateStyle: 'long', timeStyle: 'short', timeZone: 'UTC',
  }) + ' UTC'

  const confColor = confBadgeColor(rca.confidence)
  const confPct   = rca.confidence === 'high' ? 85 : rca.confidence === 'medium' ? 52 : 20

  const factorRows = (rca.contributing_factors ?? []).map(f => {
    const fl = f.toLowerCase()
    const tag = (fl.includes('no ') || fl.includes('not ') || fl.includes('healthy'))
      ? { label: 'No Issue', color: '#6b7280' }
      : (fl.includes('pod') || fl.includes('aks') || fl.includes('cluster') || fl.includes('memory') || fl.includes('cpu'))
      ? { label: 'Infra', color: '#d97706' }
      : (fl.includes('deploy') || fl.includes('config') || fl.includes('change'))
      ? { label: 'Change', color: '#0d9488' }
      : { label: 'App', color: '#14b8a6' }
    return `
      <tr>
        <td style="width:80px">
          <span style="display:inline-block;padding:2px 8px;border-radius:4px;
            font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:0.06em;
            background:${tag.color}22;color:${tag.color};border:1px solid ${tag.color}44">
            ${tag.label}
          </span>
        </td>
        <td>${esc(f)}</td>
      </tr>`
  }).join('')

  const actionRows = (fix_strategy?.actions ?? []).map((a, i) => {
    const riskColor = a.risk_level?.toLowerCase() === 'high' ? '#dc2626'
      : a.risk_level?.toLowerCase() === 'medium' ? '#d97706' : '#16a34a'
    return `
      <tr>
        <td style="text-align:center;font-weight:700;color:#6b7280">${i + 1}</td>
        <td><strong>${esc(a.title)}</strong><br/><span style="font-size:9.5px;color:#6b7280">${esc(a.description ?? '')}</span></td>
        <td>
          <span style="display:inline-block;padding:2px 8px;border-radius:4px;
            font-size:9px;font-weight:800;color:${riskColor};
            background:${riskColor}18;border:1px solid ${riskColor}44">
            ${(a.risk_level ?? 'LOW').toUpperCase()}
          </span>
        </td>
        <td style="font-size:9.5px;color:#4b5563">${esc(a.estimated_impact ?? '')}</td>
      </tr>`
  }).join('')

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',-apple-system,Arial,sans-serif;background:#fff;color:#111827;width:794px}

  /* ── Cover ── */
  .cover{
    background:linear-gradient(135deg,#0a0f1e 0%,#111830 55%,#1a2240 100%);
    padding:52px 56px 44px;position:relative;overflow:hidden;
    page-break-after:always;
  }
  .orb1{position:absolute;top:-80px;right:-80px;width:260px;height:260px;border-radius:50%;
    background:radial-gradient(circle,rgba(13,148,136,0.15) 0%,transparent 70%)}
  .orb2{position:absolute;bottom:-60px;left:22%;width:200px;height:200px;border-radius:50%;
    background:radial-gradient(circle,rgba(13,148,136,0.08) 0%,transparent 70%)}
  .brand-row{display:flex;align-items:center;gap:14px;margin-bottom:32px;position:relative;z-index:1}
  .brand-icon{width:44px;height:44px;border-radius:11px;flex-shrink:0;
    background:linear-gradient(135deg,#0f766e 0%,#14b8a6 100%);
    display:flex;align-items:center;justify-content:center;
    box-shadow:0 4px 20px rgba(13,148,136,0.45)}
  .brand-label-top{font-size:8.5px;letter-spacing:0.22em;text-transform:uppercase;
    color:rgba(255,255,255,0.35);font-weight:700}
  .brand-label-btm{font-size:10.5px;letter-spacing:0.07em;text-transform:uppercase;
    color:rgba(255,255,255,0.55);font-weight:500;margin-top:2px}
  .report-badge{display:inline-block;position:relative;z-index:1;
    background:rgba(13,148,136,0.14);border:1px solid rgba(13,148,136,0.45);
    border-radius:5px;padding:5px 14px;
    font-size:9.5px;letter-spacing:0.18em;text-transform:uppercase;
    color:#5eead4;font-weight:800;margin-bottom:18px}
  .cover-service{font-size:38px;font-weight:800;color:#fff;
    letter-spacing:-0.03em;line-height:1.05;position:relative;z-index:1;margin-bottom:6px}
  .cover-env{font-size:13px;color:rgba(255,255,255,0.35);font-weight:500;
    text-transform:uppercase;letter-spacing:0.1em;position:relative;z-index:1;margin-bottom:32px}
  .cover-meta{display:flex;gap:36px;border-top:1px solid rgba(255,255,255,0.1);
    padding-top:22px;position:relative;z-index:1}
  .meta-lbl{font-size:8px;text-transform:uppercase;letter-spacing:0.12em;
    color:rgba(255,255,255,0.28);margin-bottom:5px;font-weight:700}
  .meta-val{font-size:11.5px;color:rgba(255,255,255,0.82);font-weight:600}
  .meta-val-mono{font-size:9px;color:rgba(255,255,255,0.4);font-family:'Consolas',monospace}

  /* ── Confidence bar (on cover) ── */
  .conf-bar-wrap{margin-top:24px;position:relative;z-index:1}
  .conf-bar-label{font-size:8px;text-transform:uppercase;letter-spacing:0.14em;
    color:rgba(255,255,255,0.3);margin-bottom:6px;font-weight:700}
  .conf-bar-track{height:4px;background:rgba(255,255,255,0.1);border-radius:2px;width:260px}
  .conf-bar-fill{height:4px;border-radius:2px}
  .conf-badge{display:inline-block;padding:4px 12px;border-radius:20px;
    font-size:10px;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;
    margin-top:8px}

  /* ── Body ── */
  .body{background:#fff;padding:44px 56px 36px}
  .section{margin-bottom:36px}
  .section-header{display:flex;align-items:center;gap:12px;margin-bottom:14px}
  .section-bar{width:4px;height:22px;border-radius:2px;flex-shrink:0}
  .section-title{font-size:14.5px;font-weight:800;color:#0f1117;letter-spacing:-0.01em}

  /* ── Root cause card ── */
  .rc-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px}
  .rc-card{padding:16px;border-radius:10px;border:1px solid}
  .rc-card .card-label{font-size:9px;font-weight:800;text-transform:uppercase;
    letter-spacing:0.1em;margin-bottom:8px}
  .rc-card .card-value{font-size:11.5px;font-weight:600;color:#111827;line-height:1.45}

  /* ── Reasoning blockquote ── */
  .rationale-box{
    padding:14px 16px 14px 20px;
    border-left:3px solid #0d9488;
    background:#f0fdfa;border-radius:0 8px 8px 0;
    margin-bottom:24px;font-style:italic;
  }
  .rationale-box p{font-size:11px;color:#92400e;line-height:1.65}

  .sc p{font-size:11.5px;color:#374151;line-height:1.75;margin-bottom:9px}
  .sc strong{font-weight:700;color:#111827}
  .sc code{background:#f3f4f6;padding:1px 5px;border-radius:3px;
    font-size:10px;font-family:'Consolas',monospace;color:#1f2937}
  .sc ul,.sc ol{padding-left:22px;margin:8px 0 12px}
  .sc li{font-size:11.5px;color:#374151;line-height:1.65;margin-bottom:4px}
  .sc table{width:100%;border-collapse:collapse;margin:10px 0 16px;font-size:10.5px;table-layout:fixed;word-break:break-word}
  .sc th{background:#f8f9fa;font-weight:700;text-align:left;
    padding:8px 11px;border:1px solid #e5e7eb;color:#374151;
    font-size:10px;text-transform:uppercase;letter-spacing:0.05em;word-break:break-word;overflow-wrap:break-word}
  .sc td{padding:7px 11px;border:1px solid #e5e7eb;color:#4b5563;vertical-align:top;word-break:break-word;overflow-wrap:break-word}
  .sc tr:nth-child(even) td{background:#fafafa}
  .sc blockquote{padding:10px 14px 10px 18px;border-left:3px solid rgba(13,148,136,0.5);
    background:rgba(13,148,136,0.05);border-radius:0 8px 8px 0;margin-bottom:10px;
    font-style:italic;color:#92400e;font-size:11px;line-height:1.65}

  /* ── Fix strategy ── */
  .fix-box{background:linear-gradient(135deg,#f0fdfa 0%,#ccfbf1 100%);
    border:1px solid #99f6e4;border-radius:12px;padding:26px 30px;margin-bottom:36px}
  .fix-header{display:flex;align-items:center;gap:10px;margin-bottom:14px}
  .fix-title{font-size:14px;font-weight:800;color:#115e59}
  .fix-summary{font-size:11.5px;color:#0f766e;line-height:1.65;margin-bottom:16px}

  /* ── Footer ── */
  .footer{border-top:1px solid #e5e7eb;padding-top:18px;margin-top:4px;
    display:flex;justify-content:space-between;align-items:center}
  .footer-brand{display:flex;align-items:center;gap:8px}
  .footer-icon{width:28px;height:28px;border-radius:8px;
    background:linear-gradient(135deg,#0f766e,#14b8a6);
    display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .footer-name{font-size:10px;color:#6b7280;font-weight:600}
  .footer-conf{font-size:9.5px;color:#9ca3af}
</style>
</head>
<body>

<!-- COVER -->
<div class="cover">
  <div class="orb1"></div>
  <div class="orb2"></div>

  <div class="brand-row">
    <div class="brand-icon">${CORVIN_SVG(28)}</div>
    <div>
      <div class="brand-label-top">Corvin SRE Co-Pilot</div>
      <div class="brand-label-btm">Automated Investigation Platform</div>
    </div>
  </div>

  <div class="report-badge">ROOT CAUSE ANALYSIS</div>

  <div class="cover-service">${esc(request.service_name)}</div>
  <div class="cover-env">${esc(request.environment || '')} · ${fmtEnum(request.trigger_source || 'Manual')}</div>

  <div class="conf-bar-wrap">
    <div class="conf-bar-label">RCA Confidence</div>
    <div class="conf-bar-track">
      <div class="conf-bar-fill" style="width:${confPct}%;background:${confColor}"></div>
    </div>
    <div class="conf-badge" style="background:${confColor}22;color:${confColor};border:1px solid ${confColor}55">
      ${rca.confidence.toUpperCase()} CONFIDENCE
    </div>
  </div>

  <div class="cover-meta" style="margin-top:24px">
    <div>
      <div class="meta-lbl">Generated</div>
      <div class="meta-val">${genDate}</div>
    </div>
    <div>
      <div class="meta-lbl">Trigger</div>
      <div class="meta-val">${esc(request.description?.slice(0, 60) || 'Manual')}</div>
    </div>
    <div>
      <div class="meta-lbl">Investigation ID</div>
      <div class="meta-val-mono">${request_id}</div>
    </div>
  </div>
</div>

<!-- BODY -->
<div class="body">

  <!-- 1. Root Cause -->
  <div class="section">
    <div class="section-header">
      <div class="section-bar" style="background:#dc2626"></div>
      <div class="section-title">1. Root Cause</div>
    </div>
    <div class="rc-grid">
      <div class="rc-card" style="background:rgba(239,68,68,0.05);border-color:rgba(239,68,68,0.25)">
        <div class="card-label" style="color:#dc2626">Primary Root Cause</div>
        <div class="card-value">${esc(rca.root_cause)}</div>
      </div>
      <div class="rc-card" style="background:rgba(13,148,136,0.05);border-color:rgba(13,148,136,0.25)">
        <div class="card-label" style="color:#0d9488">Service Context</div>
        <div class="card-value">${esc(request.service_name)} in ${esc(request.environment || '—')}</div>
        <div style="font-size:9.5px;color:#9ca3af;margin-top:4px">Trigger: ${fmtEnum(request.trigger_source)}</div>
      </div>
    </div>
  </div>

  <!-- 2. Corvin's Rationale -->
  ${rca.confidence_reasoning ? `
  <div class="section">
    <div class="section-header">
      <div class="section-bar" style="background:#0d9488"></div>
      <div class="section-title">2. Corvin's Rationale</div>
    </div>
    <div class="rationale-box">
      <p>${esc(rca.confidence_reasoning)}</p>
    </div>
  </div>` : ''}

  <!-- 3. Detailed Analysis -->
  <div class="section">
    <div class="section-header">
      <div class="section-bar" style="background:#14b8a6"></div>
      <div class="section-title">${rca.confidence_reasoning ? '3' : '2'}. Detailed Analysis</div>
    </div>
    <div class="sc">${mdList(rca.summary)}</div>
  </div>

  <!-- Contributing Factors -->
  ${factorRows ? `
  <div class="section">
    <div class="section-header">
      <div class="section-bar" style="background:#d97706"></div>
      <div class="section-title">${rca.confidence_reasoning ? '4' : '3'}. Contributing Factors</div>
    </div>
    <div class="sc">
      <table>
        <thead><tr><th style="width:90px">Category</th><th>Factor</th></tr></thead>
        <tbody>${factorRows}</tbody>
      </table>
    </div>
  </div>` : ''}

  <!-- Evidence References -->
  ${rca.evidence_references?.length ? `
  <div class="section">
    <div class="section-header">
      <div class="section-bar" style="background:#6b7280"></div>
      <div class="section-title">Evidence References</div>
    </div>
    <div class="sc">
      <ul>${rca.evidence_references.map(e => `<li><code>${esc(e)}</code></li>`).join('')}</ul>
    </div>
  </div>` : ''}

  <!-- Fix Strategy -->
  ${fix_strategy ? `
  <div class="fix-box">
    <div class="fix-header">
      <div class="section-bar" style="background:#f97316;height:20px"></div>
      <div class="fix-title">Proposed Fix Strategy</div>
    </div>
    <div class="fix-summary">${esc(fix_strategy.summary)}</div>
    ${actionRows ? `
    <div class="sc">
      <table>
        <thead>
          <tr>
            <th style="width:5%">#</th>
            <th style="width:44%">Action</th>
            <th style="width:12%">Risk</th>
            <th style="width:39%">Estimated Impact</th>
          </tr>
        </thead>
        <tbody>${actionRows}</tbody>
      </table>
    </div>` : ''}
  </div>` : ''}

  <!-- Footer -->
  <div class="footer">
    <div class="footer-brand">
      <div class="footer-icon">${CORVIN_SVG(18)}</div>
      <span class="footer-name">Corvin SRE Co-Pilot</span>
    </div>
    <div class="footer-conf">CONFIDENTIAL &mdash; Internal use only</div>
  </div>

</div>
</body>
</html>`
}

// ── Public export ─────────────────────────────────────────────────────────────

export async function exportRcaPdf(data: InvestigationResult): Promise<void> {
  const iframe = document.createElement('iframe')
  iframe.style.cssText =
    'position:fixed;top:0;left:0;width:794px;height:1200px;border:none;opacity:0;pointer-events:none;z-index:-9999;'
  document.body.appendChild(iframe)

  try {
    const iDoc = iframe.contentDocument!
    iDoc.open()
    iDoc.write(buildHtml(data))
    iDoc.close()

    await new Promise(r => setTimeout(r, 700))

    const body = iDoc.body
    const totalH = body.scrollHeight
    iframe.style.height = `${totalH + 40}px`
    await new Promise(r => setTimeout(r, 150))

    const SCALE = 2
    const canvas = await html2canvas(body, {
      scale: SCALE,
      useCORS: true,
      allowTaint: true,
      backgroundColor: '#ffffff',
      logging: false,
      width: 794,
      height: totalH,
      windowWidth: 794,
      windowHeight: totalH,
    })

    const ctx = canvas.getContext('2d')!
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
    const PAGE_W = pdf.internal.pageSize.getWidth()
    const PAGE_H = pdf.internal.pageSize.getHeight()
    const pxPerMm = canvas.width / PAGE_W
    const maxPagePx = Math.floor(PAGE_H * pxPerMm)

    function findCutRow(ideal: number): number {
      for (let row = ideal; row >= Math.max(ideal - 80, 0); row--) {
        const d = ctx.getImageData(0, row, canvas.width, 1).data
        let blank = true
        for (let i = 0; i < d.length; i += 4) {
          if (d[i] < 235 || d[i + 1] < 235 || d[i + 2] < 235) { blank = false; break }
        }
        if (blank) return row
      }
      for (let row = ideal + 1; row <= Math.min(ideal + 20, canvas.height - 1); row++) {
        const d = ctx.getImageData(0, row, canvas.width, 1).data
        let blank = true
        for (let i = 0; i < d.length; i += 4) {
          if (d[i] < 235 || d[i + 1] < 235 || d[i + 2] < 235) { blank = false; break }
        }
        if (blank) return row
      }
      return ideal
    }

    let yPx = 0, pageIdx = 0
    while (yPx < canvas.height) {
      const rem = canvas.height - yPx
      let sliceH = rem <= maxPagePx ? rem : findCutRow(yPx + maxPagePx) - yPx
      if (sliceH <= 0 || sliceH > maxPagePx) sliceH = maxPagePx

      const sc = document.createElement('canvas')
      sc.width = canvas.width; sc.height = sliceH
      const sctx = sc.getContext('2d')!
      sctx.fillStyle = '#ffffff'; sctx.fillRect(0, 0, sc.width, sliceH)
      sctx.drawImage(canvas, 0, yPx, canvas.width, sliceH, 0, 0, canvas.width, sliceH)

      if (pageIdx > 0) pdf.addPage()
      pdf.addImage(sc.toDataURL('image/jpeg', 0.95), 'JPEG', 0, 0, PAGE_W, sliceH / pxPerMm)
      yPx += sliceH; pageIdx++
    }

    const svc = data.request?.service_name ?? 'service'
    const date = new Date().toISOString().slice(0, 10)
    pdf.save(`rca-${svc}-${date}.pdf`)

  } finally {
    if (document.body.contains(iframe)) document.body.removeChild(iframe)
  }
}
