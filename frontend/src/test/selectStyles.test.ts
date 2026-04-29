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
