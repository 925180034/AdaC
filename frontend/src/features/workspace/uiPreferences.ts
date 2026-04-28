export type Language = 'en' | 'zh'
export type ThemeMode = 'light' | 'dark'

const LANGUAGE_KEY = 'adacascade.language'
const THEME_KEY = 'adacascade.theme'

export function readLanguage(): Language {
  return window.localStorage.getItem(LANGUAGE_KEY) === 'zh' ? 'zh' : 'en'
}

export function writeLanguage(language: Language): void {
  window.localStorage.setItem(LANGUAGE_KEY, language)
}

export function readTheme(): ThemeMode {
  return window.localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
}

export function writeTheme(theme: ThemeMode): void {
  window.localStorage.setItem(THEME_KEY, theme)
}
