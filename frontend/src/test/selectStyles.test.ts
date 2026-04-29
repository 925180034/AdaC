import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

describe('select option styling', () => {
  it('sets explicit option colors for native dropdown visibility', () => {
    const css = readFileSync(resolve(__dirname, '../styles/globals.css'), 'utf8')

    expect(css).toMatch(/option\s*{[^}]*background:\s*#fffaf1;/s)
    expect(css).toMatch(/option\s*{[^}]*color:\s*#2d261f;/s)
    expect(css).toMatch(/:root\[data-theme='dark'\]\s+option\s*{[^}]*background:\s*#201b16;/s)
    expect(css).toMatch(/:root\[data-theme='dark'\]\s+option\s*{[^}]*color:\s*#efe5d5;/s)
  })
})

describe('theme contrast styling', () => {
  it('routes error status colors through semantic danger variables', () => {
    const css = readFileSync(resolve(__dirname, '../styles/globals.css'), 'utf8')

    expect(css).toMatch(/:root\s*{[^}]*--danger-text:\s*#7c211b;/s)
    expect(css).toMatch(/:root\s*{[^}]*--danger-surface:\s*rgba\(185, 74, 63, 0\.12\);/s)
    expect(css).toMatch(/:root\[data-theme='dark'\]\s*{[^}]*--danger-text:\s*#ffd8cf;/s)
    expect(css).toMatch(/\.workspace-status--error\s*{[^}]*color:\s*var\(--danger-text\);/s)
    expect(css).toMatch(/\.workspace-status--error\s*{[^}]*background:\s*var\(--danger-surface\);/s)
  })

  it('uses theme-specific primary run button colors instead of translucent pale text', () => {
    const css = readFileSync(resolve(__dirname, '../styles/globals.css'), 'utf8')

    expect(css).toMatch(/:root\s*{[^}]*--run-button-bg:\s*linear-gradient\(135deg, #a85c18, #875116\);/s)
    expect(css).toMatch(/:root\s*{[^}]*--run-button-fg:\s*#fffaf1;/s)
    expect(css).toMatch(/:root\[data-theme='dark'\]\s*{[^}]*--run-button-fg:\s*#17120d;/s)
    expect(css).toMatch(/\.run-button\s*{[^}]*background:\s*var\(--run-button-bg\);/s)
    expect(css).toMatch(/\.run-button\s*{[^}]*color:\s*var\(--run-button-fg\);/s)
  })
})
