import { create } from 'zustand'
import { INITIAL_TIMELINE, applyTaskEvent, type TimelineState } from './timeline'
import type { TaskEvent } from './taskTypes'

type TaskStore = {
  currentTaskId: string | null
  events: TaskEvent[]
  timeline: TimelineState
  setCurrentTaskId: (taskId: string | null) => void
  appendEvent: (event: TaskEvent) => void
  resetLiveState: () => void
}

export const useTaskStore = create<TaskStore>((set) => ({
  currentTaskId: null,
  events: [],
  timeline: INITIAL_TIMELINE,
  setCurrentTaskId: (taskId) => set({ currentTaskId: taskId }),
  appendEvent: (event) =>
    set((state) => {
      if (state.currentTaskId && event.task_id !== state.currentTaskId) {
        return state
      }

      return {
        events: [...state.events, event],
        timeline: applyTaskEvent(state.timeline, event),
      }
    }),
  resetLiveState: () => set({ events: [], timeline: INITIAL_TIMELINE }),
}))
