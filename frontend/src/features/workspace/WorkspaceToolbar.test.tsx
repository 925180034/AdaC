import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WorkspaceToolbar } from './WorkspaceToolbar'

const copy = {
  language: 'Language',
  english: 'English',
  chinese: '中文',
  theme: 'Theme',
  light: 'Light',
  dark: 'Dark',
  modelRuntime: 'Model runtime',
  localModel: 'Local vLLM',
  apiModel: 'DeepSeek API',
  runtimeSwitching: 'Switching runtime…',
}

describe('WorkspaceToolbar', () => {
  it('renders language, theme, and runtime controls', () => {
    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend="local"
        isRuntimePending={false}
        isRunning={false}
        onLanguageChange={vi.fn()}
        onThemeChange={vi.fn()}
        onRuntimeBackendChange={vi.fn()}
      />,
    )

    expect(screen.getByRole('group', { name: 'Language' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Theme' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Model runtime' })).toBeInTheDocument()
  })

  it('calls handlers when controls change', () => {
    const onLanguageChange = vi.fn()
    const onThemeChange = vi.fn()
    const onRuntimeBackendChange = vi.fn()

    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend="local"
        isRuntimePending={false}
        isRunning={false}
        onLanguageChange={onLanguageChange}
        onThemeChange={onThemeChange}
        onRuntimeBackendChange={onRuntimeBackendChange}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '中文' }))
    fireEvent.click(screen.getByRole('button', { name: 'Dark' }))
    fireEvent.click(screen.getByRole('button', { name: 'DeepSeek API' }))

    expect(onLanguageChange).toHaveBeenCalledWith('zh')
    expect(onThemeChange).toHaveBeenCalledWith('dark')
    expect(onRuntimeBackendChange).toHaveBeenCalledWith('api')
  })

  it('disables runtime switch while task is running', () => {
    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend="local"
        isRuntimePending={false}
        isRunning={true}
        onLanguageChange={vi.fn()}
        onThemeChange={vi.fn()}
        onRuntimeBackendChange={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'DeepSeek API' })).toBeDisabled()
  })
})
