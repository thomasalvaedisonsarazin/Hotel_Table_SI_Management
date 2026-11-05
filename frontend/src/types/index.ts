export interface User {
  id: number
  email: string
  full_name: string | null
  is_staff_account: boolean
  must_change_password: boolean
}

export interface TokenPair {
  access_token: string
  refresh_token: string
}

export type RestaurantRole = 'owner' | 'manager' | 'staff'
export type StaffRole = 'manager' | 'staff'

export interface Restaurant {
  id: number
  name: string
  timezone: string
  is_demo: boolean
  simulator_enabled: boolean
  has_api_key: boolean
  my_role: RestaurantRole
  daily_message_limit: number
  waiter_alert_seconds: number
  cleaning_alert_seconds: number
  seat_confirm_seconds: number
  vacate_confirm_seconds: number
  service_confirm_seconds: number
  clean_confirm_seconds: number
  default_turn_minutes: number
  covers_per_waiter: number
}

export type RestaurantUpdate = Partial<Omit<Restaurant, 'id' | 'is_demo' | 'simulator_enabled' | 'has_api_key' | 'my_role'>>

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

export interface StaffMember {
  id: number
  user_id: number
  full_name: string | null
  email: string
  is_owner: boolean
  role: StaffRole
  is_active: boolean
  phone: string | null
  alerts_consented: boolean
  notify_sms: boolean
  notify_whatsapp: boolean
  notify_waiter_alerts: boolean
  notify_cleaning_alerts: boolean
  on_shift: boolean
  temporary_password?: string | null
}

export interface StaffInput {
  full_name: string
  email: string
  role: StaffRole
  phone: string
  alerts_consented: boolean
  notify_sms: boolean
  notify_whatsapp: boolean
}

export type StaffUpdate = Partial<
  Pick<
    StaffMember,
    | 'phone'
    | 'role'
    | 'alerts_consented'
    | 'notify_sms'
    | 'notify_whatsapp'
    | 'notify_waiter_alerts'
    | 'notify_cleaning_alerts'
    | 'on_shift'
    | 'is_active'
  >
>

export interface TestSendResult {
  channel: string
  status: string
  error: string | null
}

export interface Delivery {
  id: number
  created_at: string
  member_name: string
  table_label: string
  alert_type: AlertType
  channel: string
  status: string
  attempts: number
  error: string | null
}

export interface NotificationStatus {
  provider: string
  can_send_sms: boolean
  can_send_whatsapp: boolean
  is_demo: boolean
  sent_last_24h: number
  daily_limit: number
  recent: Delivery[]
}
