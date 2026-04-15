import test from 'node:test'
import assert from 'node:assert/strict'

import worker from '../index.js'

test('Worker 应直接读取根路径对象', async () => {
  const keys = []
  const env = {
    ARCH_REPO: {
      async get(key) {
        keys.push(key)
        return {
          body: 'ok',
          size: 2,
          httpMetadata: { contentType: 'text/plain' },
        }
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/devcxl.db'), env)

  assert.equal(response.status, 200)
  assert.deepEqual(keys, ['devcxl.db'])
  assert.equal(await response.text(), 'ok')
})

test('Worker 应正确解码路径', async () => {
  const keys = []
  const env = {
    ARCH_REPO: {
      async get(key) {
        keys.push(key)
        return {
          body: 'decoded',
          size: 7,
          httpMetadata: { contentType: 'text/plain' },
        }
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/%E4%B8%AD'), env)

  assert.equal(response.status, 200)
  assert.deepEqual(keys, ['中'])
})

test('对象不存在时返回 404', async () => {
  const env = {
    ARCH_REPO: {
      async get() {
        return null
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/devcxl.gpg'), env)

  assert.equal(response.status, 404)
  assert.equal(await response.text(), 'Not found')
})
