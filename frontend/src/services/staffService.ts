import type { NotificationStatus, StaffInput, StaffMember, StaffUpdate, TestSendResult } from '../types'
import api from './api'

const root = (id: number): string => `/restaurants/${id}`

export const staffService = {
  list: (id: number) => api.get<StaffMember[]>(`${root(id)}/staff`).then((r) => r.data),
  add: (id: number, data: StaffInput) =>
    api.post<StaffMember>(`${root(id)}/staff`, { ...data, phone: data.phone.trim() || null }).then((r) => r.data),
  update: (id: number, memberId: number, data: StaffUpdate) =>
    api.patch<StaffMember>(`${root(id)}/staff/${memberId}`, data).then((r) => r.data),
  resetPassword: (id: number, memberId: number) =>
    api
      .post<{ temporary_password: string }>(`${root(id)}/staff/${memberId}/reset-password`)
      .then((r) => r.data.temporary_password),
  sendTest: (id: number, memberId: number) =>
    api.post<TestSendResult[]>(`${root(id)}/staff/${memberId}/test-alert`).then((r) => r.data),
  notifications: (id: number) =>
    api.get<NotificationStatus>(`${root(id)}/notifications`).then((r) => r.data),
  myAlerts: (id: number) => api.get<StaffMember | null>(`${root(id)}/me/alerts`).then((r) => r.data),
  updateMyAlerts: (id: number, data: Pick<StaffUpdate, 'on_shift' | 'notify_sms' | 'notify_whatsapp' | 'notify_push'>) =>
    api.patch<StaffMember>(`${root(id)}/me/alerts`, data).then((r) => r.data),
}
