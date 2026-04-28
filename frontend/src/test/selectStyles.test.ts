import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

describe('select option styling', () => {
  it('sets explicit option colors for native dropdown visibility', () => {
    const css = readFileSync(resolve(__dirname, '../styles/globals.css'), 'utf8')

    expect(css).toMatch(/option\s*{[^}]*background:\s*#0a1320;/s)
    expect(css).toMatch(/option\s*{[^}]*color:\s*#e6f7ff;/s)
  })
})
