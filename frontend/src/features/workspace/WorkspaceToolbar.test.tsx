import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WorkspaceToolbar } from './WorkspaceToolbar'

const copy = {
  preferencesLabel: 'Workspace preferences',
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
  runtimeLoadError: 'Runtime status is unavailable.',
  runtimeSwitchError: 'Runtime switch failed.',
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

    expect(screen.getByLabelText('Workspace preferences')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Language' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Theme' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Model runtime' })).toBeInTheDocument()
  })

  it('exposes selected state for each segmented control', () => {
    render(
      <WorkspaceToolbar
        copy={copy}
        language="zh"
        theme="dark"
        runtimeBackend="api"
        isRuntimePending={false}
        isRunning={false}
        onLanguageChange={vi.fn()}
        onThemeChange={vi.fn()}
        onRuntimeBackendChange={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'English', pressed: false })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '中文', pressed: true })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Light', pressed: false })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dark', pressed: true })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Local vLLM', pressed: false })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'DeepSeek API', pressed: true })).toBeInTheDocument()
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

  it('disables theme buttons when theme controls are disabled', () => {
    const onThemeChange = vi.fn()

    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend="local"
        isRuntimePending={false}
        isRunning={false}
        isThemeDisabled={true}
        onLanguageChange={vi.fn()}
        onThemeChange={onThemeChange}
        onRuntimeBackendChange={vi.fn()}
      />,
    )

    const lightButton = screen.getByRole('button', { name: 'Light', pressed: true })
    const darkButton = screen.getByRole('button', { name: 'Dark', pressed: false })

    expect(lightButton).toBeDisabled()
    expect(darkButton).toBeDisabled()

    fireEvent.click(lightButton)
    fireEvent.click(darkButton)

    expect(onThemeChange).not.toHaveBeenCalled()
  })

  it('shows no selected runtime button when backend is unknown', () => {
    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend={null}
        isRuntimePending={false}
        isRunning={false}
        onLanguageChange={vi.fn()}
        onThemeChange={vi.fn()}
        onRuntimeBackendChange={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Local vLLM', pressed: false })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'DeepSeek API', pressed: false })).toBeDisabled()
  })

  it('disables runtime buttons when runtime controls are disabled', () => {
    const onRuntimeBackendChange = vi.fn()

    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend="local"
        isRuntimePending={false}
        isRunning={false}
        isRuntimeDisabled={true}
        onLanguageChange={vi.fn()}
        onThemeChange={vi.fn()}
        onRuntimeBackendChange={onRuntimeBackendChange}
      />,
    )

    const localButton = screen.getByRole('button', { name: 'Local vLLM', pressed: true })
    const apiButton = screen.getByRole('button', { name: 'DeepSeek API', pressed: false })

    expect(localButton).toBeDisabled()
    expect(apiButton).toBeDisabled()

    fireEvent.click(localButton)
    fireEvent.click(apiButton)

    expect(onRuntimeBackendChange).not.toHaveBeenCalled()
  })

  it('disables both runtime switch buttons while a task is running', () => {
    const onRuntimeBackendChange = vi.fn()

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
        onRuntimeBackendChange={onRuntimeBackendChange}
      />,
    )

    const localButton = screen.getByRole('button', { name: 'Local vLLM', pressed: true })
    const apiButton = screen.getByRole('button', { name: 'DeepSeek API', pressed: false })

    expect(localButton).toBeDisabled()
    expect(apiButton).toBeDisabled()

    fireEvent.click(localButton)
    fireEvent.click(apiButton)

    expect(onRuntimeBackendChange).not.toHaveBeenCalled()
  })

  it('shows pending text on the targeted runtime while runtime change is pending', () => {
    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend="api"
        isRuntimePending={true}
        pendingRuntimeBackend="local"
        isRunning={false}
        onLanguageChange={vi.fn()}
        onThemeChange={vi.fn()}
        onRuntimeBackendChange={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Switching runtime…', pressed: false })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'DeepSeek API', pressed: true })).toBeDisabled()
  })

  it('disables both runtime switch buttons while runtime change is pending', () => {
    const onRuntimeBackendChange = vi.fn()

    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend="api"
        isRuntimePending={true}
        isRunning={false}
        onLanguageChange={vi.fn()}
        onThemeChange={vi.fn()}
        onRuntimeBackendChange={onRuntimeBackendChange}
      />,
    )

    const localButton = screen.getByRole('button', { name: 'Local vLLM', pressed: false })
    const apiButton = screen.getByRole('button', { name: 'DeepSeek API', pressed: true })

    expect(localButton).toBeDisabled()
    expect(apiButton).toBeDisabled()

    fireEvent.click(localButton)
    fireEvent.click(apiButton)

    expect(onRuntimeBackendChange).not.toHaveBeenCalled()
  })
})
