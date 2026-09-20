import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { OfflineStatus } from '../api/types'
import type { CMSDecisionReceipt, RightsGateDimension, RightsGateExecutionReceipt } from './types'

type Props = { onOpenPrivacy: () => void }

function useObjectUrl(file: File | null) {
  const url = useMemo(() => file ? URL.createObjectURL(file) : null, [file])
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])
  return url
}

async function sha256(file: File) {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('')
}

type MediaMetadata = {
  kind: 'IMAGE' | 'VIDEO' | 'AUDIO'
  mediaType: string
  width?: number
  height?: number
  durationSeconds?: number
}

function mediaType(file: File): Pick<MediaMetadata, 'kind' | 'mediaType'> {
  const lower = file.name.toLowerCase()
  if (lower.endsWith('.png')) return { kind: 'IMAGE', mediaType: 'image/png' }
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return { kind: 'IMAGE', mediaType: 'image/jpeg' }
  if (lower.endsWith('.mp4')) return { kind: 'VIDEO', mediaType: 'video/mp4' }
  if (lower.endsWith('.mov')) return { kind: 'VIDEO', mediaType: 'video/quicktime' }
  if (lower.endsWith('.wav')) return { kind: 'AUDIO', mediaType: 'audio/wav' }
  throw new Error('RightsGate accepts PNG, JPEG, MP4, MOV and bounded PCM/WAV assets.')
}

async function mediaMetadata(file: File): Promise<MediaMetadata> {
  const identity = mediaType(file)
  if (identity.kind === 'IMAGE') {
    const bitmap = await createImageBitmap(file)
    try {
      return { ...identity, width: bitmap.width, height: bitmap.height }
    } finally {
      bitmap.close()
    }
  }
  const url = URL.createObjectURL(file)
  try {
    if (identity.kind === 'VIDEO') {
      const video = document.createElement('video')
      video.preload = 'metadata'
      video.src = url
      await new Promise<void>((resolve, reject) => {
        video.onloadedmetadata = () => resolve()
        video.onerror = () => reject(new Error('The browser could not read video metadata.'))
      })
      if (!Number.isFinite(video.duration) || video.duration <= 0 || !video.videoWidth || !video.videoHeight) {
        throw new Error('The video has invalid duration or frame dimensions.')
      }
      return {
        ...identity,
        width: video.videoWidth,
        height: video.videoHeight,
        durationSeconds: video.duration,
      }
    }
    const audio = document.createElement('audio')
    audio.preload = 'metadata'
    audio.src = url
    await new Promise<void>((resolve, reject) => {
      audio.onloadedmetadata = () => resolve()
      audio.onerror = () => reject(new Error('The browser could not read WAV metadata.'))
    })
    if (!Number.isFinite(audio.duration) || audio.duration <= 0) {
      throw new Error('The audio has an invalid duration.')
    }
    return { ...identity, durationSeconds: audio.duration }
  } finally {
    URL.revokeObjectURL(url)
  }
}

function score(value: number) {
  return `${Math.round(value * 100)}%`
}

function humanize(value: string) {
  return value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function DimensionCard({ title, assessment }: { title: string; assessment: RightsGateDimension }) {
  const outcome = assessment.verdict ?? assessment.decision ?? 'UNKNOWN'
  return (
    <article className={`rg-dimension rg-${outcome.toLowerCase().replaceAll('_', '-')}`}>
      <div className="rg-dimension-heading">
        <span>{title}</span>
        <b>{assessment.state}</b>
      </div>
      <strong>{humanize(outcome)}</strong>
      <div className="rg-confidence"><i style={{ width: score(assessment.confidence) }} /><span>{score(assessment.confidence)} confidence</span></div>
      <div className="rg-claims">
        {assessment.claims.slice(0, 3).map((claim) => (
          <div key={claim.claim_id}>
            <b className={`rg-claim-${claim.outcome.toLowerCase()}`}>{humanize(claim.outcome)}</b>
            <span>{claim.statement}</span>
          </div>
        ))}
      </div>
      {assessment.limitations.length > 0 && (
        <details><summary>Limitations · {assessment.limitations.length}</summary><ul>{assessment.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
      )}
    </article>
  )
}

export function RightsGateApp({ onOpenPrivacy }: Props) {
  const [asset, setAsset] = useState<File | null>(null)
  const [reference, setReference] = useState<File | null>(null)
  const [referenceKind, setReferenceKind] = useState<'COPYRIGHTED_WORK' | 'TRADEMARK'>('COPYRIGHTED_WORK')
  const [rightsHolder, setRightsHolder] = useState('Demo rights holder')
  const [licenceEnabled, setLicenceEnabled] = useState(true)
  const [territory, setTerritory] = useState('IN')
  const [channel, setChannel] = useState('web')
  const [audience, setAudience] = useState('general')
  const [intendedUse, setIntendedUse] = useState('Public advertising campaign')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<RightsGateExecutionReceipt | null>(null)
  const [cmsReceipt, setCmsReceipt] = useState<CMSDecisionReceipt | null>(null)
  const [boundary, setBoundary] = useState<OfflineStatus | null>(null)
  const [theme, setTheme] = useState<'light' | 'dark'>(() => (
    document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
  ))
  const assetUrl = useObjectUrl(asset)
  const referenceUrl = useObjectUrl(reference)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem('veilgraph-theme', theme)
  }, [theme])

  useEffect(() => {
    api.status().then(setBoundary).catch(() => setBoundary(null))
  }, [])

  const unavailable = result?.assessment.components.filter((item) => item.state !== 'AVAILABLE') ?? []

  async function assess() {
    if (!asset || !reference) {
      setError('Choose both a deployment asset and a governed reference image.')
      return
    }
    setBusy('Binding asset bytes and governed reference')
    setError(null)
    setResult(null)
    setCmsReceipt(null)
    try {
      const [assetSha, referenceSha, metadata] = await Promise.all([
        sha256(asset),
        sha256(reference),
        mediaMetadata(asset),
      ])
      const referenceId = `reference.${referenceKind === 'TRADEMARK' ? 'mark' : 'work'}-${referenceSha.slice(0, 16)}`
      const sourceRecordId = `rights-record.${referenceSha.slice(0, 20)}`
      const governedReference = await api.deriveRightsImageReference(reference, {
        referenceId,
        kind: referenceKind,
        title: reference.name,
        rightsHolder,
        sourceRecordId,
      })
      setBusy('Executing provenance, rights and deployment gates')
      const now = Date.now()
      const policyId = 'policy.techgium-demo'
      const policyVersion = '2026.09.1'
      const idempotencyKey = `request.${crypto.randomUUID()}`
      const context = {
        policy_id: policyId,
        policy_version: policyVersion,
        intended_use: intendedUse,
        channel,
        audience,
        territories: [territory.toUpperCase()],
        brand_profile: 'default',
      }
      const assessmentRequest = {
        schema: 'veilgraph.rightsgate.assessment-request.v1',
        idempotency_key: idempotencyKey,
        asset_ir: {
          schema: 'veilgraph.rightsgate.asset-ir.v1',
          asset: {
            asset_id: `asset.${assetSha.slice(0, 24)}`,
            sha256: assetSha,
            media_kind: metadata.kind,
            media_type: metadata.mediaType,
            size_bytes: asset.size,
            original_filename: asset.name,
            ...(metadata.width ? { width: metadata.width } : {}),
            ...(metadata.height ? { height: metadata.height } : {}),
            ...(metadata.durationSeconds ? { duration_seconds: metadata.durationSeconds } : {}),
          },
          representations: [{
            representation_id: `representation.original-${assetSha.slice(0, 16)}`,
            kind: 'ORIGINAL',
            sha256: assetSha,
            media_type: metadata.mediaType,
            size_bytes: asset.size,
            locator: { kind: 'WHOLE_ASSET' },
          }],
        },
        context,
        requested_dimensions: ['PROVENANCE', 'RIGHTS_EXPOSURE', 'DEPLOYMENT_READINESS'],
      }
      const rightsRegistry = {
        schema: 'veilgraph.rightsgate.rights-reference-registry.v1',
        registry_id: 'registry.techgium-demo-rights',
        version: '2026.09.1',
        references: [governedReference],
      }
      const licenceRegistry = {
        schema: 'veilgraph.rightsgate.licence-registry.v1',
        registry_id: 'registry.techgium-demo-licences',
        version: '2026.09.1',
        licences: licenceEnabled ? [{
          licence_id: `licence.${referenceSha.slice(0, 20)}`,
          source_record_id: `licence-record.${referenceSha.slice(0, 20)}`,
          reference_ids: [referenceId],
          licensor: rightsHolder,
          licensee: 'Demo content team',
          state: 'ACTIVE',
          valid_from: new Date(now - 24 * 60 * 60 * 1000).toISOString(),
          valid_until: new Date(now + 30 * 24 * 60 * 60 * 1000).toISOString(),
          territories: [territory.toUpperCase()],
          channels: [channel],
          intended_uses: [intendedUse],
        }] : [],
      }
      const publicationPolicy = {
        schema: 'veilgraph.rightsgate.publication-policy.v1',
        policy_id: policyId,
        version: policyVersion,
        allowed_channels: [channel],
        allowed_audiences: [audience],
        allowed_brand_profiles: ['default'],
        allowed_territories: [territory.toUpperCase()],
        required_component_ids: metadata.kind === 'AUDIO'
          ? [
              'provenance.c2pa',
              'ingestion.pcm-wav-parser',
              'rights.voice-consent',
              'rights.licence-evaluator',
            ]
          : [
              'provenance.c2pa',
              'provenance.independent-forensics',
              'rights.local-image-registry',
              'rights.licence-evaluator',
              'rights.trademark-localizer',
              ...(metadata.kind === 'VIDEO' ? ['ingestion.video-timeline-analyzer'] : []),
            ],
        require_known_provenance: true,
        require_rights_clearance: true,
        block_tampered_provenance: true,
        block_unlicensed_reference_match: true,
        regulatory_rules: [{
          rule_id: 'demo.synthetic-publication-review',
          description: 'Synthetic or unresolved public media requires documented human review.',
          effect: 'REVIEW',
          territories: [territory.toUpperCase()],
          channels: [channel],
          audiences: [audience],
          brand_profiles: ['default'],
          provenance_verdicts: ['AI_GENERATED', 'PARTIALLY_GENERATED', 'UNKNOWN'],
          rights_verdicts: [],
        }],
      }
      const receipt = await api.executeRightsGate(asset, {
        assessmentRequest,
        rightsRegistry,
        licenceRegistry,
        publicationPolicy,
      })
      setResult(receipt)
      setBusy('Creating signed CMS workflow receipt')
      const workflowReceipt = await api.createRightsGateCmsDecision({
        cmsSystemId: 'cms.techgium-demo',
        contentId: `content.${assetSha.slice(0, 24)}`,
        assessmentIdempotencyKey: receipt.idempotency_key,
        expectedAssetSha256: assetSha,
        expectedAssessmentSha256: receipt.assessment_sha256,
      })
      setCmsReceipt(workflowReceipt)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'RightsGate assessment failed closed.')
    } finally {
      setBusy(null)
    }
  }

  function reset() {
    setResult(null)
    setError(null)
    setAsset(null)
    setReference(null)
    setCmsReceipt(null)
  }

  const decision = result?.assessment.deployment.decision ?? null
  return (
    <div className="rg-root">
      <header className="rg-header">
        <div className="rg-brand">
          <img className="brand-wordmark brand-wordmark-light" src="/veilgraph-brand-light.png" alt="VeilGraph" />
          <img className="brand-wordmark brand-wordmark-dark" src="/veilgraph-brand-dark.png" alt="" aria-hidden="true" />
          <span>RightsGate</span>
        </div>
        <div className="rg-header-actions">
          <span className="rg-local"><i />{
            boundary === null
              ? 'Boundary status pending'
              : boundary.offline_mode
                ? 'Local execution'
                : 'Networked execution'
          }</span>
          <button className="rg-text-button" onClick={onOpenPrivacy}>Inherited privacy workspace</button>
          <button className="theme-toggle" onClick={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')} aria-label="Toggle appearance"><span>{theme === 'dark' ? '☼' : '◐'}</span></button>
        </div>
      </header>

      {error && <div className="rg-alert"><strong>Assessment stayed locked.</strong><span>{error}</span><button onClick={() => setError(null)}>Dismiss</button></div>}
      {busy && <div className="busy-float"><i /><span>{busy}</span></div>}

      <main className="rg-shell">
        <section className="rg-hero">
          <div>
            <span className="overline">PRE-PUBLICATION CONTENT RIGHTS</span>
            <h1>Know what the asset is.<br/><em>Know whether it can ship.</em></h1>
            <p>One evidence-bound gate for provenance, rights exposure and deployment readiness. Unknown evidence never becomes silent approval.</p>
          </div>
          <div className="rg-hero-proof">
            <span>EXECUTION BOUNDARY</span><strong>Fail closed</strong><small>C2PA · reference retrieval · licence policy</small>
          </div>
        </section>

        {!result ? (
          <section className="rg-intake">
            <div className="rg-intake-heading">
              <div><span className="overline">NEW ASSESSMENT</span><h2>Bind the media to its deployment context</h2></div>
              <p>The reference image is converted server-side into a content-addressed governed record. Raw assets are not persisted by this workflow.</p>
            </div>
            <div className="rg-intake-grid">
              <label className={`rg-drop ${asset ? 'ready' : ''}`}>
                <input type="file" accept="image/png,image/jpeg,video/mp4,video/quicktime,audio/wav" onChange={(event) => setAsset(event.target.files?.[0] ?? null)} />
                {assetUrl && asset && mediaType(asset).kind === 'VIDEO' ? <video src={assetUrl} muted /> : assetUrl && asset && mediaType(asset).kind === 'AUDIO' ? <audio src={assetUrl} controls /> : assetUrl ? <img src={assetUrl} alt="Deployment asset preview" /> : <i>01</i>}
                <span><strong>{asset?.name ?? 'Deployment asset'}</strong><small>Image, bounded video or PCM/WAV · exact bytes assessed</small></span>
              </label>
              <label className={`rg-drop ${reference ? 'ready' : ''}`}>
                <input type="file" accept="image/png,image/jpeg" onChange={(event) => setReference(event.target.files?.[0] ?? null)} />
                {referenceUrl ? <img src={referenceUrl} alt="Governed reference preview" /> : <i>02</i>}
                <span><strong>{reference?.name ?? 'Governed reference'}</strong><small>Copyrighted work or trademark reference</small></span>
              </label>
              <div className="rg-context-form">
                <label><span>Reference type</span><select value={referenceKind} onChange={(event) => setReferenceKind(event.target.value as typeof referenceKind)}><option value="COPYRIGHTED_WORK">Copyrighted work</option><option value="TRADEMARK">Trademark</option></select></label>
                <label><span>Rights holder</span><input value={rightsHolder} onChange={(event) => setRightsHolder(event.target.value)} /></label>
                <label className="rg-wide"><span>Intended use</span><input value={intendedUse} onChange={(event) => setIntendedUse(event.target.value)} /></label>
                <label><span>Territory</span><input value={territory} maxLength={2} onChange={(event) => setTerritory(event.target.value.toUpperCase())} /></label>
                <label><span>Channel</span><input value={channel} onChange={(event) => setChannel(event.target.value)} /></label>
                <label><span>Audience</span><input value={audience} onChange={(event) => setAudience(event.target.value)} /></label>
                <label className="rg-switch"><input type="checkbox" checked={licenceEnabled} onChange={(event) => setLicenceEnabled(event.target.checked)} /><span><i />Valid licence record supplied</span></label>
              </div>
            </div>
            <div className="rg-intake-footer">
              <div><strong>No unsupported clearance.</strong><span>A missing credential or no registry match remains `UNKNOWN`. Unimplemented detectors are returned explicitly.</span></div>
              <button className="rg-run" disabled={Boolean(busy) || !asset || !reference || !rightsHolder || territory.length !== 2} onClick={assess}>Run three-dimension assessment <span>→</span></button>
            </div>
          </section>
        ) : (
          <section className="rg-results">
            <div className={`rg-decision rg-decision-${decision?.toLowerCase()}`}>
              <div><span className="overline">DEPLOYMENT DECISION</span><h2>{decision}</h2><p>{decision === 'BLOCK' ? 'A deterministic policy conflict prevents deployment.' : decision === 'REVIEW' ? 'Mandatory evidence is unresolved. Human review is required.' : 'Configured controls passed; release authorization remains a separate signed boundary.'}</p></div>
              <div className="rg-decision-meta"><span>Assessment commitment</span><code>{result.assessment_sha256}</code><small>{result.release_authorization ? 'Release authorized' : 'Decision only · release authorization false'}</small></div>
            </div>

            <div className="rg-dimensions">
              <DimensionCard title="01 · Provenance" assessment={result.assessment.provenance} />
              <DimensionCard title="02 · Rights exposure" assessment={result.assessment.rights} />
              <DimensionCard title="03 · Deployment readiness" assessment={result.assessment.deployment} />
            </div>

            <div className="rg-evidence-layout">
              <section className="rg-evidence-panel">
                <div className="rg-panel-heading"><span className="overline">EVIDENCE PACK</span><h3>{result.assessment.evidence.length} byte-bound records</h3></div>
                <div className="rg-evidence-list">{result.assessment.evidence.map((item) => <article key={item.evidence_id}><i className={`rg-polarity-${item.polarity.toLowerCase()}`} /><div><strong>{humanize(item.kind)}</strong><p>{item.summary}</p><small>{item.source} · {score(item.confidence)}</small></div><code>{item.evidence_id}</code></article>)}</div>
              </section>
              <aside className="rg-components">
                <div className="rg-panel-heading"><span className="overline">COMPONENT HEALTH</span><h3>{unavailable.length ? `${unavailable.length} unresolved` : 'All available'}</h3></div>
                {result.assessment.components.map((item) => <div key={item.component_id} className={`rg-component-${item.state.toLowerCase()}`}><i /><span><strong>{item.component_id}</strong><small>{item.reason ?? `${item.component_type} · v${item.component_version}`}</small></span><b>{item.state}</b></div>)}
                <details><summary>Policy citations</summary><ul>{result.assessment.deployment.policy_citations?.map((item) => <li key={item}><code>{item}</code></li>)}</ul></details>
              </aside>
            </div>

            <div className="rg-result-footer">
              <div><span>Execution fingerprint</span><code>{result.execution_sha256}</code><small>{result.replayed ? 'Durable idempotent replay' : 'First durable execution'}</small></div>
              <div><span>CMS workflow receipt</span><code>{cmsReceipt?.receipt_sha256 ?? 'Signing unavailable'}</code><small>{cmsReceipt ? `${humanize(cmsReceipt.payload.workflow_status)} · Ed25519 ${cmsReceipt.signer_fingerprint.slice(0, 16)}…` : 'Assessment remains valid; no CMS receipt was issued.'}</small></div>
              <button onClick={reset}>Assess another asset</button>
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
