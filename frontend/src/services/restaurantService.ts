import type {
  Alert,
  Analytics,
  Floor,
  Restaurant,
  RestaurantUpdate,
  Table,
  TableActionName,
  WaitlistEntry,
} from '../types'
import api from './api'

const browserTimezone = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const root = (id: number): string => `/restaurants/${id}`

export const restaurantService = {
  list: () => api.get<Restaurant[]>('/restaurants').then((r) => r.data),
  create: (name: string) =>
    api.post<Restaurant>('/restaurants', { name, timezone: browserTimezone() }).then((r) => r.data),
  createDemo: () =>
    api.post<Restaurant>('/restaurants/demo', { timezone: browserTimezone() }).then((r) => r.data),
  update: (id: number, data: RestaurantUpdate) =>
    api.patch<Restaurant>(root(id), data).then((r) => r.data),
  remove: (id: number) => api.delete(root(id)),
  rotateKey: (id: number) =>
    api.post<{ api_key: string }>(`${root(id)}/api-key`).then((r) => r.data.api_key),
  setSimulator: (id: number, enabled: boolean) =>
    api.post<Restaurant>(`${root(id)}/simulator`, { enabled }).then((r) => r.data),

  floor: (id: number) => api.get<Floor>(`${root(id)}/floor`).then((r) => r.data),
  analytics: (id: number, days: number) =>
    api.get<Analytics>(`${root(id)}/analytics`, { params: { days } }).then((r) => r.data),

  addTable: (id: number, data: { label: string; seats: number; x: number; y: number }) =>
    api.post<Table>(`${root(id)}/tables`, data).then((r) => r.data),
  updateTable: (id: number, tableId: number, data: Partial<Pick<Table, 'label' | 'seats' | 'x' | 'y'>>) =>
    api.patch<Table>(`${root(id)}/tables/${tableId}`, data).then((r) => r.data),
  removeTable: (id: number, tableId: number) => api.delete(`${root(id)}/tables/${tableId}`),
  tableAction: (id: number, tableId: number, action: TableActionName, partySize?: number) =>
    api
      .post<Table>(`${root(id)}/tables/${tableId}/actions`, { action, party_size: partySize })
      .then((r) => r.data),

  alerts: (id: number) => api.get<Alert[]>(`${root(id)}/alerts`).then((r) => r.data),
  acknowledgeAlert: (id: number, alertId: number) =>
    api.post<Alert>(`${root(id)}/alerts/${alertId}/acknowledge`).then((r) => r.data),

  addToWaitlist: (id: number, name: string, partySize: number) =>
    api
      .post<WaitlistEntry>(`${root(id)}/waitlist`, { name, party_size: partySize })
      .then((r) => r.data),
  seatFromWaitlist: (id: number, entryId: number, tableId: number) =>
    api.post(`${root(id)}/waitlist/${entryId}/seat`, { table_id: tableId }),
  leaveWaitlist: (id: number, entryId: number) => api.post(`${root(id)}/waitlist/${entryId}/leave`),
}
