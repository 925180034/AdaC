import type { RuntimeBackend } from '../../api/runtime'
import type { Language, ThemeMode } from './uiPreferences'

export type WorkspaceToolbarCopy = {
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
}

type WorkspaceToolbarProps = {
  copy: WorkspaceToolbarCopy
  language: Language
  theme: ThemeMode
  runtimeBackend: RuntimeBackend
  isRuntimePending: boolean
  isRunning: boolean
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
  isRunning,
  onLanguageChange,
  onThemeChange,
  onRuntimeBackendChange,
}: WorkspaceToolbarProps) {
  const runtimeDisabled = isRunning || isRuntimePending

  return (
    <aside className="workspace-toolbar" aria-label="Workspace preferences">
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
        >
          {copy.light}
        </button>
        <button
          className={selectedClass(theme === 'dark')}
          type="button"
          aria-pressed={theme === 'dark'}
          onClick={() => onThemeChange('dark')}
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
          {copy.localModel}
        </button>
        <button
          className={selectedClass(runtimeBackend === 'api')}
          type="button"
          aria-pressed={runtimeBackend === 'api'}
          onClick={() => onRuntimeBackendChange('api')}
          disabled={runtimeDisabled}
        >
          {isRuntimePending ? copy.runtimeSwitching : copy.apiModel}
        </button>
      </div>
    </aside>
  )
}
