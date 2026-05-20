/**
 * postmortemPdf.ts
 * Generates a premium, branded PDF from a PostMortem object.
 * Strategy: html2canvas → canvas slices → jsPDF addImage.
 * Smart page-break detection snaps cuts to whitespace rows so text is never split.
 * Direct browser download — no new tab.
 */
import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import type { PostMortem } from '../api/client'

// ── Inline markdown → HTML converter (handles PM content patterns) ──────────

function fmt(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/_([^_]+)_/g, '<em>$1</em>')
}

function mdToHtml(md: string): string {
  if (!md) return ''
  let html = ''
  let inOl = false
  let inUl = false
  let inTable = false
  let tableRows: string[][] = []

  const flushTable = () => {
    if (!inTable || tableRows.length === 0) return
    html += '<table>'
    tableRows.forEach((row, i) => {
      html += '<tr>' + row.map(c =>
        i === 0 ? `<th>${fmt(c)}</th>` : `<td>${fmt(c)}</td>`
      ).join('') + '</tr>'
    })
    html += '</table>'
    tableRows = []
    inTable = false
  }

  const closeList = () => {
    if (inOl) { html += '</ol>'; inOl = false }
    if (inUl) { html += '</ul>'; inUl = false }
  }

  for (const rawLine of md.split('\n')) {
    const line = rawLine.trim()

    // Table row
    if (line.startsWith('|')) {
      if (/^\|[-\s|:]+\|$/.test(line)) continue // separator row
      closeList()
      inTable = true
      tableRows.push(line.slice(1, -1).split('|').map(c => c.trim()))
      continue
    }
    if (inTable) flushTable()

    // Ordered list
    const olMatch = line.match(/^(\d+)\.\s+(.+)/)
    if (olMatch) {
      if (inUl) { html += '</ul>'; inUl = false }
      if (!inOl) { html += '<ol>'; inOl = true }
      html += `<li>${fmt(olMatch[2])}</li>`
      continue
    }

    // Unordered list
    const ulMatch = line.match(/^[-*]\s+(.+)/)
    if (ulMatch) {
      if (inOl) { html += '</ol>'; inOl = false }
      if (!inUl) { html += '<ul>'; inUl = true }
      html += `<li>${fmt(ulMatch[1])}</li>`
      continue
    }

    closeList()

    if (line.startsWith('### ')) { html += `<h3>${fmt(line.slice(4))}</h3>`; continue }
    if (line.startsWith('## '))  { html += `<h2>${fmt(line.slice(3))}</h2>`; continue }
    if (line.startsWith('# '))   { html += `<h1>${fmt(line.slice(2))}</h1>`; continue }
    if (line === '---')          { html += '<hr>'; continue }
    if (line === '')             continue
    if (line.startsWith('> '))   { html += `<blockquote>${fmt(line.slice(2))}</blockquote>`; continue }

    html += `<p>${fmt(line)}</p>`
  }

  flushTable()
  closeList()
  return html
}

// ── HTML template for the PDF print view ────────────────────────────────────

function buildHtml(pm: PostMortem): string {
  const genDate = new Date(pm.generated_at).toLocaleString('en-US', {
    dateStyle: 'long', timeStyle: 'short', timeZone: 'UTC',
  }) + ' UTC'

  const section = (num: number, title: string, content: string, accent = '#0d9488') => `
    <div class="section">
      <div class="section-header">
        <div class="section-bar" style="background:${accent}"></div>
        <div class="section-title">${num}. ${title}</div>
      </div>
      <div class="sc">${content}</div>
    </div>`

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', -apple-system, Arial, sans-serif;
    background: #ffffff;
    color: #111827;
    width: 794px;
  }

  /* ── Cover ── */
  .cover {
    background: linear-gradient(135deg, #0d1020 0%, #161c35 60%, #1e2444 100%);
    padding: 52px 56px 44px;
    position: relative;
    overflow: hidden;
    page-break-after: always;
  }
  .cover-orb1 {
    position: absolute; top: -80px; right: -80px;
    width: 280px; height: 280px; border-radius: 50%;
    background: radial-gradient(circle, rgba(13,148,136,0.12) 0%, transparent 70%);
  }
  .cover-orb2 {
    position: absolute; bottom: -60px; left: 20%;
    width: 180px; height: 180px; border-radius: 50%;
    background: radial-gradient(circle, rgba(13,148,136,0.08) 0%, transparent 70%);
  }
  .brand-row {
    display: flex; align-items: center; gap: 14px; margin-bottom: 32px;
    position: relative; z-index: 1;
  }
  .brand-icon {
    width: 44px; height: 44px; border-radius: 11px; flex-shrink: 0;
    background: linear-gradient(135deg, #0f766e 0%, #0d9488 100%);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 4px 20px rgba(13,148,136,0.4);
    color: #fff; font-weight: 900; font-family: Arial, sans-serif;
  }
  .brand-label-top {
    font-size: 8.5px; letter-spacing: 0.22em; text-transform: uppercase;
    color: rgba(255,255,255,0.35); font-weight: 700;
  }
  .brand-label-btm {
    font-size: 10.5px; letter-spacing: 0.07em; text-transform: uppercase;
    color: rgba(255,255,255,0.55); font-weight: 500; margin-top: 2px;
  }
  .report-badge {
    display: inline-block; position: relative; z-index: 1;
    background: rgba(13,148,136,0.14); border: 1px solid rgba(13,148,136,0.45);
    border-radius: 5px; padding: 5px 14px;
    font-size: 9.5px; letter-spacing: 0.18em; text-transform: uppercase;
    color: #5eead4; font-weight: 800; margin-bottom: 18px;
  }
  .cover-service {
    font-size: 38px; font-weight: 800; color: #ffffff;
    letter-spacing: -0.03em; line-height: 1.05;
    position: relative; z-index: 1; margin-bottom: 6px;
  }
  .cover-env {
    font-size: 13px; color: rgba(255,255,255,0.35); font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.1em;
    position: relative; z-index: 1; margin-bottom: 32px;
  }
  .cover-meta {
    display: flex; gap: 36px; border-top: 1px solid rgba(255,255,255,0.1);
    padding-top: 22px; position: relative; z-index: 1;
  }
  .meta-lbl {
    font-size: 8px; text-transform: uppercase; letter-spacing: 0.12em;
    color: rgba(255,255,255,0.28); margin-bottom: 5px; font-weight: 700;
  }
  .meta-val {
    font-size: 11.5px; color: rgba(255,255,255,0.82); font-weight: 600;
  }
  .meta-val-mono {
    font-size: 9.5px; color: rgba(255,255,255,0.4);
    font-family: 'Cascadia Code', 'Consolas', monospace;
  }

  /* ── Body ── */
  .body { background: #ffffff; padding: 44px 56px 36px; }

  .section { margin-bottom: 38px; }
  .section-header {
    display: flex; align-items: center; gap: 12px; margin-bottom: 14px;
  }
  .section-bar { width: 4px; height: 22px; border-radius: 2px; flex-shrink: 0; }
  .section-title {
    font-size: 14.5px; font-weight: 800; color: #0f1117; letter-spacing: -0.01em;
  }

  /* ── Section content base ── */
  .sc p  { font-size: 11.5px; color: #374151; line-height: 1.75; margin-bottom: 9px; }
  .sc strong { font-weight: 700; color: #111827; }
  .sc em { font-style: italic; color: #4b5563; }
  .sc code {
    background: #f3f4f6; padding: 1px 5px; border-radius: 3px;
    font-size: 10px; font-family: 'Cascadia Code','Consolas',monospace; color: #1f2937;
  }
  .sc h1, .sc h2 {
    font-size: 12.5px; font-weight: 700; color: #111827;
    margin: 16px 0 6px; letter-spacing: -0.01em;
  }
  .sc h3 { font-size: 11.5px; font-weight: 700; color: #374151; margin: 12px 0 5px; }
  .sc hr { border: none; border-top: 1px solid #e5e7eb; margin: 14px 0; }
  .sc ul, .sc ol { padding-left: 22px; margin: 8px 0 12px; }
  .sc li  { font-size: 11.5px; color: #374151; line-height: 1.65; margin-bottom: 4px; }
  .sc table { width: 100%; border-collapse: collapse; margin: 10px 0 16px; font-size: 10.5px; table-layout: fixed; word-break: break-word; }
  .sc th  {
    background: #f8f9fa; font-weight: 700; text-align: left;
    padding: 8px 11px; border: 1px solid #e5e7eb; color: #374151;
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em;
    word-break: break-word; overflow-wrap: break-word;
  }
  .sc td  { padding: 7px 11px; border: 1px solid #e5e7eb; color: #4b5563; vertical-align: top; word-break: break-word; overflow-wrap: break-word; }
  .sc tr:nth-child(even) td { background: #fafafa; }
  .sc blockquote {
    padding: 10px 14px 10px 18px;
    border-left: 3px solid rgba(13,148,136,0.5);
    background: rgba(13,148,136,0.05);
    border-radius: 0 8px 8px 0;
    margin-bottom: 10px;
    font-style: italic;
    color: #92400e;
    font-size: 11px;
    line-height: 1.65;
  }

  /* ── Prevention callout ── */
  .prevention-box {
    background: linear-gradient(135deg, #f0fdfa 0%, #ccfbf1 100%);
    border: 1px solid #99f6e4; border-radius: 12px; padding: 26px 30px;
    margin-bottom: 36px;
  }
  .prevention-header {
    display: flex; align-items: center; gap: 10px; margin-bottom: 14px;
  }
  .prevention-icon { font-size: 20px; }
  .prevention-title { font-size: 14px; font-weight: 800; color: #115e59; }
  .prevention-box .sc li { color: #0f766e; }
  .prevention-box .sc ol { counter-reset: item; }
  .prevention-box .sc ol li {
    position: relative; padding-left: 4px;
  }

  /* ── Footer ── */
  .footer {
    border-top: 1px solid #e5e7eb; padding-top: 18px; margin-top: 4px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .footer-brand {
    display: flex; align-items: center; gap: 8px;
  }
  .footer-icon {
    width: 28px; height: 28px; border-radius: 8px;
    background: linear-gradient(135deg, #0f766e, #0d9488);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }
  .footer-name { font-size: 10px; color: #6b7280; font-weight: 600; }
  .footer-conf { font-size: 9.5px; color: #9ca3af; }
</style>
</head>
<body>

<!-- COVER -->
<div class="cover">
  <div class="cover-orb1"></div>
  <div class="cover-orb2"></div>

  <div class="brand-row">
    <div class="brand-icon">
      <svg width="28" height="28" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="32" height="32" rx="7.5" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.8)" stroke-width="1"/>
        <path d="M21.5 9A9 9 0 1 0 21.5 23" stroke="white" stroke-width="2.8" fill="none" stroke-linecap="round"/>
        <path d="M16 12L20 16L16 20L12 16Z" fill="white"/>
      </svg>
    </div>
    <div>
      <div class="brand-label-top">Corvin SRE Co-Pilot</div>
      <div class="brand-label-btm">Automated Investigation Platform</div>
    </div>
  </div>

  <div class="report-badge">BLAMELESS POST-MORTEM</div>

  <div class="cover-service">${pm.service_name}</div>
  <div class="cover-env">${(pm.environment || '').toUpperCase()}</div>

  <div class="cover-meta">
    <div>
      <div class="meta-lbl">Generated</div>
      <div class="meta-val">${genDate}</div>
    </div>
    <div>
      <div class="meta-lbl">Reviewed By</div>
      <div class="meta-val">${pm.approved_by || 'Pending Review'}</div>
    </div>
    <div>
      <div class="meta-lbl">Investigation ID</div>
      <div class="meta-val-mono">${pm.request_id}</div>
    </div>
  </div>
</div>

<!-- BODY -->
<div class="body">

  ${section(1, 'Incident Summary', mdToHtml(pm.incident_summary))}
  ${section(2, 'Detection &amp; Timeline', mdToHtml(pm.detection_timeline))}
  ${section(3, 'Investigation Findings', mdToHtml(pm.investigation_findings))}
  ${section(4, 'Actions Taken / Fix Strategy', mdToHtml(pm.actions_taken))}

  <!-- Prevention callout -->
  <div class="prevention-box">
    <div class="prevention-header">
      <div class="prevention-icon">&#x1F4A1;</div>
      <div class="prevention-title">5. Prevention &amp; Future Actions</div>
    </div>
    <div class="sc">${mdToHtml(pm.prevention_recommendations)}</div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <div class="footer-brand">
      <div class="footer-icon">
        <svg width="18" height="18" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="32" height="32" rx="7.5" fill="rgba(255,255,255,0.15)" stroke="white" stroke-width="1"/>
          <path d="M21.5 9A9 9 0 1 0 21.5 23" stroke="white" stroke-width="2.8" fill="none" stroke-linecap="round"/>
          <path d="M16 12L20 16L16 20L12 16Z" fill="white"/>
        </svg>
      </div>
      <span class="footer-name">Corvin SRE Co-Pilot</span>
    </div>
    <div class="footer-conf">CONFIDENTIAL &mdash; Internal use only</div>
  </div>

</div>
</body>
</html>`
}

// ── Public export ─────────────────────────────────────────────────────────

/**
 * Renders the post-mortem HTML in an invisible iframe, captures it as a single
 * hi-res canvas, then slices that canvas into A4 pages with whitespace-snapping
 * page breaks (never cuts mid-line). Triggers a direct browser download.
 */
export async function exportPostMortemPdf(pm: PostMortem): Promise<void> {
  // Position iframe visible but transparent so html2canvas can read its layout.
  const iframe = document.createElement('iframe')
  iframe.style.cssText =
    'position:fixed;top:0;left:0;width:794px;height:1200px;border:none;opacity:0;pointer-events:none;z-index:-9999;'
  document.body.appendChild(iframe)

  try {
    const iDoc = iframe.contentDocument!
    iDoc.open()
    iDoc.write(buildHtml(pm))
    iDoc.close()

    // Let fonts and layout settle
    await new Promise(r => setTimeout(r, 700))

    const body = iDoc.body
    const totalContentH = body.scrollHeight
    iframe.style.height = `${totalContentH + 40}px`
    await new Promise(r => setTimeout(r, 150))

    // ── Capture full document as one canvas ──────────────────────────────
    const SCALE = 2
    const canvas = await html2canvas(body, {
      scale: SCALE,
      useCORS: true,
      allowTaint: true,
      backgroundColor: '#ffffff',
      logging: false,
      width: 794,
      height: totalContentH,
      windowWidth: 794,
      windowHeight: totalContentH,
    })

    const ctx = canvas.getContext('2d')!
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
    const PAGE_W_MM = pdf.internal.pageSize.getWidth()   // 210 mm
    const PAGE_H_MM = pdf.internal.pageSize.getHeight()  // 297 mm

    // Pixels per mm at this scale
    const pxPerMm = canvas.width / PAGE_W_MM
    // Maximum page height in canvas pixels
    const maxPagePx = Math.floor(PAGE_H_MM * pxPerMm)

    /**
     * Scan rows near the ideal cut point, seeking a row that is mostly white.
     * Returns the best cut row index (relative to canvas top) to snap to.
     */
    function findCutRow(idealCutPx: number): number {
      // Search window: 80px above ideal cut, 20px below
      const searchFrom = Math.max(idealCutPx - 80, 0)
      const searchTo   = Math.min(idealCutPx + 20, canvas.height - 1)

      for (let row = idealCutPx; row >= searchFrom; row--) {
        const data = ctx.getImageData(0, row, canvas.width, 1).data
        let isBlank = true
        for (let i = 0; i < data.length; i += 4) {
          // Allow near-white (>235) to handle anti-aliasing
          if (data[i] < 235 || data[i + 1] < 235 || data[i + 2] < 235) {
            isBlank = false
            break
          }
        }
        if (isBlank) return row
      }
      // No blank row found — try scanning below ideal cut
      for (let row = idealCutPx + 1; row <= searchTo; row++) {
        const data = ctx.getImageData(0, row, canvas.width, 1).data
        let isBlank = true
        for (let i = 0; i < data.length; i += 4) {
          if (data[i] < 235 || data[i + 1] < 235 || data[i + 2] < 235) {
            isBlank = false
            break
          }
        }
        if (isBlank) return row
      }
      // Fall back to exact cut
      return idealCutPx
    }

    // ── Slice canvas into A4 pages ───────────────────────────────────────
    let yPx = 0
    let pageIndex = 0

    while (yPx < canvas.height) {
      const remaining = canvas.height - yPx
      let sliceH: number

      if (remaining <= maxPagePx) {
        // Last page — take whatever is left
        sliceH = remaining
      } else {
        // Snap cut to nearest whitespace row
        sliceH = findCutRow(yPx + maxPagePx) - yPx
        // Safety: never exceed page height
        if (sliceH <= 0 || sliceH > maxPagePx) sliceH = maxPagePx
      }

      // Draw this slice to a temp canvas
      const sliceCanvas = document.createElement('canvas')
      sliceCanvas.width  = canvas.width
      sliceCanvas.height = sliceH
      const sc = sliceCanvas.getContext('2d')!
      sc.fillStyle = '#ffffff'
      sc.fillRect(0, 0, sliceCanvas.width, sliceH)
      sc.drawImage(canvas, 0, yPx, canvas.width, sliceH, 0, 0, canvas.width, sliceH)

      const imgData  = sliceCanvas.toDataURL('image/jpeg', 0.95)
      const imgH_mm  = sliceH / pxPerMm  // actual mm height of this slice

      if (pageIndex > 0) pdf.addPage()
      pdf.addImage(imgData, 'JPEG', 0, 0, PAGE_W_MM, imgH_mm)

      yPx += sliceH
      pageIndex++
    }

    const fileName = `postmortem-${pm.service_name}-${pm.generated_at.slice(0, 10)}.pdf`
    pdf.save(fileName)

  } finally {
    if (document.body.contains(iframe)) document.body.removeChild(iframe)
  }
}

