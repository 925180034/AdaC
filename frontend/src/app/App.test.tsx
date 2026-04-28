import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App', () => {
  it('renders the workbench title and local demo warning', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'AdaCascade Workbench' })).toBeInTheDocument()
    expect(screen.getByLabelText('Local demo security warning')).toHaveTextContent(
      'Local demo environment',
    )
  })
})
