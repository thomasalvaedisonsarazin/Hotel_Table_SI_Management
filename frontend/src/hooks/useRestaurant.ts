import { useOutletContext } from 'react-router-dom'
import type { LiveFloor } from './useLiveFloor'

export interface RestaurantContext extends LiveFloor {
  restaurantId: number
}

export const useRestaurant = (): RestaurantContext => useOutletContext<RestaurantContext>()
