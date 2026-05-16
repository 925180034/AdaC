import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

describe('vite dev server config', () => {
  it('allows the AutoDL public frontend host', () => {
    const config = readFileSync(resolve(__dirname, '../../vite.config.ts'), 'utf8')

    expect(config).toContain('server:')
    expect(config).toContain('allowedHosts:')
    expect(config).toContain('u307207-94cd-0c29b003.nmb1.seetacloud.com')
  })

  it('proxies backend API routes through the public frontend origin', () => {
    const config = readFileSync(resolve(__dirname, '../../vite.config.ts'), 'utf8')

    expect(config).toContain('proxy:')
    expect(config).toContain('/tables')
    expect(config).toContain('/datasets')
    expect(config).toContain('/runtime')
    expect(config).toContain('/tasks')
    expect(config).toContain('/discover')
    expect(config).toContain('/match')
    expect(config).toContain('/integrate')
    expect(config).toContain('http://localhost:6008')
  })
})
