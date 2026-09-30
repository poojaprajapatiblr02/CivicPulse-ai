export interface Summary {
  total_requests: number
  requests_by_category: Record<string, number>
  total_population: number
  infrastructure_records: number
  total_investment: string
}

export interface Hotspot {
  hotspot_id: string
  location_name: string
  district: string
  category: string
  latitude: number
  longitude: number
  request_count: number
  affected_population: number
  created_at: string
}

export interface Priority extends Hotspot {
  infrastructure_gap_score: number | null
  priority_score: number | null
  capacity_gap: number | null
  capacity_unit: string | null
  scoring_status: 'complete' | 'insufficient_data'
  data_issues: string | null
}

export interface Recommendation {
  recommendation_id: string
  hotspot_id: string
  recommended_intervention: string
  reasoning: string[]
  evidence: string[]
  expected_impact: string
  confidence: number
  limitations: string[]
  created_at: string
  evidence_snapshot: {
    hotspot_id: string
    hotspot_created_at: string
    category: string
    location_name: string
    district: string
    facts: Record<string, string>
    limitations: string[]
  }
}

export interface Analysis {
  request_id: string
  language: string
  category: string
  problem: string
  location_name: string | null
  district: string | null
  urgency: number
  created_at: string
}