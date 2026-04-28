import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WorkspacePage } from '../features/workspace/WorkspacePage'

const queryClient = new QueryClient()

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WorkspacePage />
    </QueryClientProvider>
  )
}
