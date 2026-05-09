// /**
//  * StreamingProgress â€” V3 Streaming AI Visualizer
//  *
//  * Renders the live investigation SSE stream with:
//  * - Stage progress tracker (evidence â†’ rca â†’ fix_strategy â†’ complete)
//  * - Live prose typewriter for RCA and fix_strategy token streams
//  * - Structured summary cards after each stage completes
//  * - Degraded/fallback banners when generation used a fallback path
//  */

// import { useEffect, useRef } from 'react'
// import { useNavigate } from 'react-router-dom'
// import type { StageEvent } from '../hooks/useInvestigationStream'

// // â”€â”€ Types â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// interface StreamingProgressProps {
//   stages: StageEvent[]
//   streamText: Record<string, string>
//   isStreaming: boolean
//   isComplete: boolean
//   error: string | null
//   requestId: string | null
//   onReset: () => void
// }

// // â”€â”€ Stage config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// const STAGES = ['evidence', 'rca', 'fix_strategy'] as const
// type StageName = typeof STAGES[number]

// const STAGE_LABELS: Record<StageName, string> = {
//   evidence:     'Evidence Collection',
//   rca:          'Root Cause Analysis',
//   fix_strategy: 'Fix Strategy',
// }

// // â”€â”€ Stage progress tracker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// function StageTracker({ stages }: { stages: StageEvent[] }) {
//   const stageMap = new Map<string, StageEvent['status']>()
//   stages.forEach(s => { stageMap.set(s.stage, s.status) })

//   return (
//     <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 28 }}>
//       {STAGES.map((key, i) => {
//         const status = stageMap.get(key)
//         const active = status === 'started'
//         const done   = status === 'complete'
//         return (
//           <div key={key} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
//             {/* Node */}
//             <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, flexShrink: 0 }}>
//               <div
//                 style={{
//                   width: 32,
//                   height: 32,
//                   borderRadius: '50%',
//                   display: 'flex',
//                   alignItems: 'center',
//                   justifyContent: 'center',
//                   fontSize: '0.8rem',
//                   fontWeight: 800,
//                   transition: 'all 0.3s ease',
//                   background: done
//                     ? 'var(--c-green)'
//                     : active
//                     ? 'rgba(56,189,248,0.2)'
//                     : 'rgba(255,255,255,0.04)',
//                   border: done
//                     ? '2px solid var(--c-green)'
//                     : active
//                     ? '2px solid var(--c-accent)'
//                     : '2px solid var(--c-border)',
//                   color: done ? '#0b0f1a' : active ? 'var(--c-accent)' : 'var(--c-text-faint)',
//                   boxShadow: active ? '0 0 12px rgba(56,189,248,0.35)' : 'none',
//                 }}
//                 className={active ? 'animate-pulse-glow' : ''}
//               >
//                 {done ? 'âœ“' : i + 1}
//               </div>
//               <span style={{
//                 fontSize: '0.65rem',
//                 fontWeight: 600,
//                 letterSpacing: '0.05em',
//                 textTransform: 'uppercase',
//                 color: done ? 'var(--c-green)' : active ? 'var(--c-accent)' : 'var(--c-text-faint)',
//                 whiteSpace: 'nowrap',
//               }}>
//                 {STAGE_LABELS[key]}
//               </span>
//             </div>
//             {/* Connector */}
//             {i < STAGES.length - 1 && (
//               <div style={{
//                 flex: 1,
//                 height: 2,
//                 marginTop: -20,
//                 background: done ? 'var(--c-green)' : 'var(--c-border)',
//                 transition: 'background 0.4s ease',
//               }} />
//             )}
//           </div>
//         )
//       })}
//     </div>
//   )
// }

// // â”€â”€ Live typewriter panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// function TypewriterPanel({ stage, text }: { stage: string; text: string }) {
//   const ref = useRef<HTMLDivElement>(null)

//   useEffect(() => {
//     if (ref.current) {
//       ref.current.scrollTop = ref.current.scrollHeight
//     }
//   }, [text])

//   const label = STAGE_LABELS[stage as StageName] ?? stage

//   return (
//     <div
//       style={{
//         marginTop: 16,
//         borderRadius: 8,
//         border: '1px solid var(--c-border-glow)',
//         background: 'rgba(56,189,248,0.03)',
//         overflow: 'hidden',
//       }}
//     >
//       {/* Header */}
//       <div style={{
//         padding: '8px 14px',
//         borderBottom: '1px solid var(--c-border)',
//         display: 'flex',
//         alignItems: 'center',
//         gap: 8,
//         background: 'rgba(56,189,248,0.04)',
//       }}>
//         <span className="animate-pulse-glow" style={{
//           width: 8, height: 8, borderRadius: '50%',
//           background: 'var(--c-accent)', flexShrink: 0,
//           display: 'inline-block',
//         }} />
//         <span style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-accent)' }}>
//           {label} Â· generating
//         </span>
//       </div>
//       {/* Token text */}
//       <div
//         ref={ref}
//         style={{
//           padding: '14px 16px',
//           maxHeight: 220,
//           overflowY: 'auto',
//           fontSize: '0.82rem',
//           lineHeight: 1.75,
//           color: 'var(--c-text-muted)',
//           whiteSpace: 'pre-wrap',
//           wordBreak: 'break-word',
//         }}
//       >
//         {text}
//         <span className="animate-cursor" style={{ color: 'var(--c-accent)', fontWeight: 700 }}>â–‹</span>
//       </div>
//     </div>
//   )
// }

// // â”€â”€ RCA summary card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// function RCASummary({ s }: { s: StageEvent }) {
//   const factors = Array.isArray(s.contributing_factors) ? (s.contributing_factors as string[]) : []
//   const degraded = s.degraded === true

//   return (
//     <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
//       {degraded && (
//         <div style={{
//           padding: '8px 14px',
//           borderRadius: 6,
//           background: 'rgba(251,191,36,0.08)',
//           border: '1px solid rgba(251,191,36,0.25)',
//           fontSize: '0.75rem',
//           color: 'var(--c-yellow)',
//         }}>
//           âš  RCA generated via fallback path ({s.generation_status}) â€” result may be lower quality.
//         </div>
//       )}

//       <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10 }}>
//         {/* Confidence */}
//         {typeof s.confidence === 'string' && (
//           <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
//             <span style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-text-faint)' }}>Confidence</span>
//             <span className={`badge ${s.confidence === 'high' ? 'badge-approved' : s.confidence === 'low' ? 'badge-rejected' : 'badge-pending'}`}>
//               {s.confidence}
//             </span>
//           </div>
//         )}

//         {/* Summary */}
//         {typeof s.summary === 'string' && (
//           <div style={{ padding: '12px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--c-border)' }}>
//             <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 6 }}>Summary</div>
//             <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.65 }}>{s.summary}</p>
//           </div>
//         )}

//         {/* Root cause */}
//         {typeof s.root_cause === 'string' && (
//           <div style={{ padding: '12px 14px', borderRadius: 8, background: 'rgba(248,113,113,0.04)', border: '1px solid rgba(248,113,113,0.15)' }}>
//             <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-red)', marginBottom: 6 }}>Root Cause</div>
//             <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.65 }}>{s.root_cause}</p>
//           </div>
//         )}

//         {/* Contributing factors */}
//         {factors.length > 0 && (
//           <div style={{ padding: '12px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--c-border)' }}>
//             <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-text-faint)', marginBottom: 8 }}>Contributing Factors</div>
//             <ul style={{ margin: 0, paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: 4 }}>
//               {factors.map((f, i) => (
//                 <li key={i} style={{ fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.5 }}>{f}</li>
//               ))}
//             </ul>
//           </div>
//         )}
//       </div>
//     </div>
//   )
// }

// // â”€â”€ Fix strategy summary card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// function FixStrategySummary({ s }: { s: StageEvent }) {
//   const actions = Array.isArray(s.action_summaries) ? (s.action_summaries as string[]) : []
//   const degraded = s.degraded === true

//   return (
//     <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
//       {degraded && (
//         <div style={{
//           padding: '8px 14px',
//           borderRadius: 6,
//           background: 'rgba(251,191,36,0.08)',
//           border: '1px solid rgba(251,191,36,0.25)',
//           fontSize: '0.75rem',
//           color: 'var(--c-yellow)',
//         }}>
//           âš  Fix strategy generated via fallback path ({s.generation_status}).
//         </div>
//       )}
//       {typeof s.summary === 'string' && (
//         <div style={{ padding: '12px 14px', borderRadius: 8, background: 'rgba(56,189,248,0.04)', border: '1px solid rgba(56,189,248,0.15)' }}>
//           <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--c-accent)', marginBottom: 6 }}>Strategy</div>
//           <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.65 }}>{s.summary}</p>
//         </div>
//       )}
//       {actions.length > 0 && (
//         <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
//           {actions.map((a, i) => (
//             <div key={i} style={{
//               display: 'flex',
//               alignItems: 'flex-start',
//               gap: 10,
//               padding: '10px 14px',
//               borderRadius: 8,
//               background: 'rgba(255,255,255,0.02)',
//               border: '1px solid var(--c-border)',
//             }}>
//               <span style={{
//                 flexShrink: 0,
//                 width: 22,
//                 height: 22,
//                 borderRadius: '50%',
//                 background: 'rgba(56,189,248,0.12)',
//                 border: '1px solid rgba(56,189,248,0.3)',
//                 color: 'var(--c-accent)',
//                 fontSize: '0.7rem',
//                 fontWeight: 800,
//                 display: 'flex',
//                 alignItems: 'center',
//                 justifyContent: 'center',
//               }}>
//                 {i + 1}
//               </span>
//               <span style={{ fontSize: '0.82rem', color: 'var(--c-text-muted)', lineHeight: 1.5, paddingTop: 2 }}>{a}</span>
//             </div>
//           ))}
//         </div>
//       )}
//     </div>
//   )
// }

// // â”€â”€ Stage panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// function StagePanel({
//   stageKey,
//   stageEvents,
//   streamText,
//   isActiveStage,
// }: {
//   stageKey: string
//   stageEvents: StageEvent[]
//   streamText: Record<string, string>
//   isActiveStage: boolean
// }) {
//   const latest = stageEvents.at(-1)
//   if (!latest) return null

//   const done   = latest.status === 'complete'
//   const active = latest.status === 'started'
//   const text   = streamText[stageKey] ?? ''

//   return (
//     <div
//       className="glass animate-fade-up"
//       style={{
//         padding: '16px 20px',
//         borderColor: done ? 'rgba(52,211,153,0.2)' : active ? 'var(--c-border-glow)' : 'var(--c-border)',
//       }}
//     >
//       <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
//         <div style={{
//           width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
//           background: done ? 'var(--c-green)' : active ? 'var(--c-accent)' : 'var(--c-text-faint)',
//         }} className={active ? 'animate-pulse-glow' : ''} />
//         <span style={{ fontWeight: 700, fontSize: '0.82rem', color: done ? 'var(--c-text)' : active ? 'var(--c-accent)' : 'var(--c-text-muted)' }}>
//           {STAGE_LABELS[stageKey as StageName] ?? stageKey}
//         </span>
//         <span style={{ fontSize: '0.72rem', color: 'var(--c-text-faint)', marginLeft: 'auto' }}>
//           {latest.message}
//         </span>
//       </div>

//       {/* Live token stream */}
//       {active && text && isActiveStage && (
//         <TypewriterPanel stage={stageKey} text={text} />
//       )}

//       {/* Structured results after complete */}
//       {done && stageKey === 'rca' && <RCASummary s={latest} />}
//       {done && stageKey === 'fix_strategy' && <FixStrategySummary s={latest} />}
//     </div>
//   )
// }

// // â”€â”€ Main component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// export default function StreamingProgress({
//   stages,
//   streamText,
//   isStreaming,
//   isComplete,
//   error,
//   requestId,
//   onReset,
// }: StreamingProgressProps) {
//   const navigate = useNavigate()

//   if (!isStreaming && !isComplete && stages.length === 0) return null

//   // Group events by stage
//   const byStage = new Map<string, StageEvent[]>()
//   stages.forEach(s => {
//     if (!byStage.has(s.stage)) byStage.set(s.stage, [])
//     byStage.get(s.stage)!.push(s)
//   })

//   // Active stage is the last non-complete stage that has started
//   const activeStage = isStreaming
//     ? (stages.filter(s => s.stage !== 'complete' && s.stage !== 'error').at(-1)?.stage ?? null)
//     : null

//   return (
//     <section style={{ marginTop: 32, display: 'flex', flexDirection: 'column', gap: 16 }}>
//       {/* Header */}
//       <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
//         <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
//           {isStreaming && (
//             <span className="animate-pulse-glow" style={{
//               width: 8, height: 8, borderRadius: '50%',
//               background: 'var(--c-accent)',
//               display: 'inline-block',
//             }} />
//           )}
//           <h3 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 700, color: 'var(--c-text)' }}>
//             {isStreaming
//               ? 'Investigation in progressâ€¦'
//               : isComplete && !error
//               ? 'Investigation complete'
//               : 'Investigation failed'}
//           </h3>
//         </div>
//         <button onClick={onReset} className="btn-ghost" style={{ padding: '4px 12px', fontSize: '0.75rem' }}>
//           Clear
//         </button>
//       </div>

//       {/* Stage tracker */}
//       <StageTracker stages={stages} />

//       {/* Error */}
//       {error && (
//         <div style={{
//           padding: '14px 16px',
//           borderRadius: 8,
//           background: 'rgba(248,113,113,0.08)',
//           border: '1px solid rgba(248,113,113,0.25)',
//           color: 'var(--c-red)',
//           fontSize: '0.82rem',
//         }}>
//           {error}
//         </div>
//       )}

//       {/* Stage panels */}
//       {STAGES.map(key => {
//         const events = byStage.get(key)
//         if (!events || events.length === 0) return null
//         return (
//           <StagePanel
//             key={key}
//             stageKey={key}
//             stageEvents={events}
//             streamText={streamText}
//             isActiveStage={activeStage === key}
//           />
//         )
//       })}

//       {/* Complete CTA */}
//       {isComplete && !error && requestId && (
//         <div
//           className="glass glass-accent animate-fade-up"
//           style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
//         >
//           <div>
//             <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--c-green)' }}>
//               âœ“ Investigation complete
//             </div>
//             <div style={{ fontSize: '0.75rem', color: 'var(--c-text-faint)', marginTop: 2 }}>
//               ID: <code style={{ color: 'var(--c-accent)' }}>{requestId}</code>
//             </div>
//           </div>
//           <button
//             className="btn-primary"
//             onClick={() => navigate(`/investigations/${requestId}`)}
//           >
//             View Results â†’
//           </button>
//         </div>
//       )}
//     </section>
//   )
// }
