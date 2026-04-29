import type { RuntimeBackend } from '../../api/runtime'
import type { Language, ThemeMode } from './uiPreferences'

export type WorkspaceToolbarCopy = {
  preferencesLabel: string
  language: string
  english: string
  chinese: string
  theme: string
  light: string
  dark: string
  modelRuntime: string
  localModel: string
  apiModel: string
  runtimeSwitching: string
  runtimeLoadError: string
  runtimeSwitchError: string
}

type WorkspaceToolbarProps = {
  copy: WorkspaceToolbarCopy
  language: Language
  theme: ThemeMode
  runtimeBackend: RuntimeBackend | null
  isRuntimePending: boolean
  pendingRuntimeBackend?: RuntimeBackend | null
  isRunning: boolean
  isThemeDisabled?: boolean
  isRuntimeDisabled?: boolean
  onLanguageChange: (language: Language) => void
  onThemeChange: (theme: ThemeMode) => void
  onRuntimeBackendChange: (backend: RuntimeBackend) => void
}

function selectedClass(isSelected: boolean): string {
  return `segmented-control__button${isSelected ? ' segmented-control__button--selected' : ''}`
}

export function WorkspaceToolbar({
  copy,
  language,
  theme,
  runtimeBackend,
  isRuntimePending,
  pendingRuntimeBackend = null,
  isRunning,
  isThemeDisabled = false,
  isRuntimeDisabled = false,
  onLanguageChange,
  onThemeChange,
  onRuntimeBackendChange,
}: WorkspaceToolbarProps) {
  const runtimeDisabled = isRuntimeDisabled || isRunning || isRuntimePending || runtimeBackend === null

  return (
    <aside className="workspace-toolbar" aria-label={copy.preferencesLabel}>
      <div className="segmented-control" role="group" aria-label={copy.language}>
        <button
          className={selectedClass(language === 'en')}
          type="button"
          aria-pressed={language === 'en'}
          onClick={() => onLanguageChange('en')}
        >
          {copy.english}
        </button>
        <button
          className={selectedClass(language === 'zh')}
          type="button"
          aria-pressed={language === 'zh'}
          onClick={() => onLanguageChange('zh')}
        >
          {copy.chinese}
        </button>
      </div>

      <div className="segmented-control" role="group" aria-label={copy.theme}>
        <button
          className={selectedClass(theme === 'light')}
          type="button"
          aria-pressed={theme === 'light'}
          onClick={() => onThemeChange('light')}
          disabled={isThemeDisabled}
        >
          {copy.light}
        </button>
        <button
          className={selectedClass(theme === 'dark')}
          type="button"
          aria-pressed={theme === 'dark'}
          onClick={() => onThemeChange('dark')}
          disabled={isThemeDisabled}
        >
          {copy.dark}
        </button>
      </div>

      <div className="segmented-control" role="group" aria-label={copy.modelRuntime}>
        <button
          className={selectedClass(runtimeBackend === 'local')}
          type="button"
          aria-pressed={runtimeBackend === 'local'}
          onClick={() => onRuntimeBackendChange('local')}
          disabled={runtimeDisabled}
        >
          {isRuntimePending && pendingRuntimeBackend === 'local' ? copy.runtimeSwitching : copy.localModel}
        </button>
        <button
          className={selectedClass(runtimeBackend === 'api')}
          type="button"
          aria-pressed={runtimeBackend === 'api'}
          onClick={() => onRuntimeBackendChange('api')}
          disabled={runtimeDisabled}
        >
          {isRuntimePending && pendingRuntimeBackend === 'api' ? copy.runtimeSwitching : copy.apiModel}
        </button>
      </div>
    </aside>
  )
}
