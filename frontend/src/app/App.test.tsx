import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App', () => {
  it('renders the workbench title without the local demo warning', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'AdaCascade Workbench' })).toBeInTheDocument()
    expect(screen.queryByText(/Local demo environment/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/browser-visible API key/i)).not.toBeInTheDocument()
  })
})
