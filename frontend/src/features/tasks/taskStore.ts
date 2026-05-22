import { create } from 'zustand'
import { INITIAL_TIMELINE, buildTimelineFromEvents, sortTaskEvents, type TimelineState } from './timeline'
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

      const events = sortTaskEvents([...state.events, event])

      return {
        events,
        timeline: buildTimelineFromEvents(events),
      }
    }),
  resetLiveState: () => set({ events: [], timeline: INITIAL_TIMELINE }),
}))
