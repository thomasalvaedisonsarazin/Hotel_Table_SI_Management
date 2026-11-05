export interface User {
  id: number
  email: string
  full_name: string | null
}

export interface TokenPair {
  access_token: string
  refresh_token: string
}

export interface Restaurant {
  id: number
  name: string
  timezone: string
  is_demo: boolean
  simulator_enabled: boolean
  has_api_key: boolean
  waiter_alert_seconds: number
  cleaning_alert_seconds: number
  seat_confirm_seconds: number
  vacate_confirm_seconds: number
  service_confirm_seconds: number
  clean_confirm_seconds: number
  default_turn_minutes: number
  covers_per_waiter: number
}

export type RestaurantUpdate = Partial<Omit<Restaurant, 'id' | 'is_demo' | 'simulator_enabled' | 'has_api_key'>>

export type TableStatus = 'free' | 'occupied' | 'needs_cleaning'
export type TableActionName = 'seat' | 'served' | 'vacate' | 'cleaned'

export interface Table {
  id: number
  label: string
  seats: number
  x: number
  y: number
  status: TableStatus
  status_changed_at: string
}

export interface FloorTable extends Table {
  party_size: number | null
  seated_at: string | null
  first_served_at: string | null
  vacated_at: string | null
  session_source: string | null
}

export type AlertType = 'waiter' | 'cleaning'

export interface Alert {
  id: number
  table_id: number
  table_label: string
  type: AlertType
  status: 'open' | 'acknowledged' | 'resolved'
  created_at: string
  acknowledged_at: string | null
  resolved_at: string | null
}

export interface WaitlistEntry {
  id: number
  name: string
  party_size: number
  status: string
  joined_at: string
  seated_at: string | null
  table_id: number | null
  estimated_wait_minutes: number | null
  suggested_table_id: number | null
  suggested_table_label: string | null
}

export interface TablePrediction {
  table_id: number
  label: string
  seats: number
  status: TableStatus
  estimated_free_at: string
  minutes_until_free: number
  based_on_history: boolean
}

export interface Floor {
  server_time: string
  restaurant: Restaurant
  tables: FloorTable[]
  alerts: Alert[]
  waitlist: WaitlistEntry[]
  predictions: TablePrediction[]
}

export interface HeatmapCell {
  weekday: number
  hour: number
  avg_covers: number
  suggested_waiters: number
}

export interface HourlyPoint {
  hour: number
  avg_covers: number
}

export interface Analytics {
  days: number
  is_sample_data: boolean
  parties: number
  covers: number
  avg_turn_minutes: number | null
  avg_wait_for_service_seconds: number | null
  avg_cleaning_seconds: number | null
  waiter_alerts: number
  cleaning_alerts: number
  peak_hour: number | null
  peak_weekday: number | null
  covers_per_waiter: number
  hourly: HourlyPoint[]
  heatmap: HeatmapCell[]
}

export type LiveMessage =
  | { type: 'ready' }
  | { type: 'floor_changed' }
  | { type: 'alert'; alert_id: number; table_id: number; alert_type: AlertType }
