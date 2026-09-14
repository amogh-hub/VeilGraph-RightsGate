export type RightsGateDecision = 'GO' | 'REVIEW' | 'BLOCK'

export type RegistryImage = {
  reference_id: string
  kind: 'COPYRIGHTED_WORK' | 'TRADEMARK'
  title: string
  rights_holder: string
  sha256: string
  dhash: string
  media_type: string
  source_record_id: string
}

export type RightsGateClaim = {
  claim_id: string
  statement: string
  outcome: 'SUPPORTED' | 'CONTRADICTED' | 'UNKNOWN' | 'NOT_ASSESSED'
  confidence: number
  limitations: string[]
}

export type RightsGateEvidence = {
  evidence_id: string
  kind: string
  source: string
  polarity: string
  confidence: number
  summary: string
  attributes: Record<string, string | number | boolean | null>
}

export type RightsGateComponent = {
  component_id: string
  component_version: string
  component_type: string
  state: 'AVAILABLE' | 'DEGRADED' | 'UNAVAILABLE'
  mandatory: boolean
  reason?: string | null
}

export type RightsGateDimension = {
  dimension: string
  state: 'COMPLETE' | 'PARTIAL' | 'UNAVAILABLE'
  verdict?: string
  decision?: RightsGateDecision
  confidence: number
  claims: RightsGateClaim[]
  limitations: string[]
  policy_citations?: string[]
}

export type RightsGateAssessment = {
  schema: string
  assessment_id: string
  created_at: string
  asset: {
    asset_id: string
    sha256: string
    media_kind: string
    media_type: string
    size_bytes: number
    original_filename: string
    width?: number
    height?: number
  }
  components: RightsGateComponent[]
  evidence: RightsGateEvidence[]
  provenance: RightsGateDimension
  rights: RightsGateDimension
  deployment: RightsGateDimension
}

export type RightsGateExecutionReceipt = {
  receipt_schema: string
  idempotency_key: string
  request_sha256: string
  execution_sha256: string
  assessment_sha256: string
  replayed: boolean
  release_authorization: false
  assessment: RightsGateAssessment
}
