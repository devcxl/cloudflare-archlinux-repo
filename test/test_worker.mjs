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

test('根路径包请求应回退到 packages 目录', async () => {
  const keys = []
  const env = {
    ARCH_REPO: {
      async get(key) {
        keys.push(key)

        if (key === 'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst') {
          return {
            body: 'pkg',
            size: 3,
            httpMetadata: { contentType: 'application/octet-stream' },
          }
        }

        return null
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/localsend-bin-1.0-1-x86_64.pkg.tar.zst'), env)

  assert.equal(response.status, 200)
  assert.deepEqual(keys, [
    'localsend-bin-1.0-1-x86_64.pkg.tar.zst',
    'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst',
  ])
  assert.equal(await response.text(), 'pkg')
})

test('根路径包签名请求应回退到 packages 目录', async () => {
  const keys = []
  const env = {
    ARCH_REPO: {
      async get(key) {
        keys.push(key)

        if (key === 'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst.sig') {
          return {
            body: 'sig',
            size: 3,
            httpMetadata: { contentType: 'application/octet-stream' },
          }
        }

        return null
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/localsend-bin-1.0-1-x86_64.pkg.tar.zst.sig'), env)

  assert.equal(response.status, 200)
  assert.deepEqual(keys, [
    'localsend-bin-1.0-1-x86_64.pkg.tar.zst.sig',
    'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst.sig',
  ])
  assert.equal(await response.text(), 'sig')
})

test('合法 Range 返回 206 与正确的 Content-Range / Content-Length', async () => {
  const env = {
    ARCH_REPO: {
      async get() {
        return {
          body: { slice: (s, e) => 'abcd'.slice(s, e) },
          size: 4,
          httpMetadata: { contentType: 'application/octet-stream' },
        }
      },
    },
  }

  const response = await worker.fetch(
    new Request('https://repo.dev/file', { headers: { Range: 'bytes=0-1' } }),
    env,
  )
  assert.equal(response.status, 206)
  assert.equal(response.headers.get('Content-Range'), 'bytes 0-1/4')
  assert.equal(response.headers.get('Content-Length'), '2')
  assert.equal(await response.text(), 'ab')
})

test('后缀 Range bytes=-N 返回最后 N 字节', async () => {
  const env = {
    ARCH_REPO: {
      async get() {
        return {
          body: { slice: (s, e) => 'abcd'.slice(s, e) },
          size: 4,
          httpMetadata: { contentType: 'application/octet-stream' },
        }
      },
    },
  }

  const response = await worker.fetch(
    new Request('https://repo.dev/file', { headers: { Range: 'bytes=-2' } }),
    env,
  )
  assert.equal(response.status, 206)
  assert.equal(response.headers.get('Content-Range'), 'bytes 2-3/4')
  assert.equal(await response.text(), 'cd')
})

test('开放结尾 Range bytes=N- 正确截断到对象末尾', async () => {
  const env = {
    ARCH_REPO: {
      async get() {
        return {
          body: { slice: (s, e) => 'abcd'.slice(s, e) },
          size: 4,
          httpMetadata: { contentType: 'application/octet-stream' },
        }
      },
    },
  }

  const response = await worker.fetch(
    new Request('https://repo.dev/file', { headers: { Range: 'bytes=2-' } }),
    env,
  )
  assert.equal(response.status, 206)
  assert.equal(response.headers.get('Content-Range'), 'bytes 2-3/4')
})

test('非法/不支持的 Range 返回 416', async () => {
  const env = {
    ARCH_REPO: {
      async get() {
        return {
          body: { slice: (s, e) => 'abcd'.slice(s, e) },
          size: 4,
          httpMetadata: { contentType: 'application/octet-stream' },
        }
      },
    },
  }

  for (const range of ['bytes=abc', 'bytes=0-1,2-3', 'bytes=10-20', 'bytes=-']) {
    const response = await worker.fetch(
      new Request('https://repo.dev/file', { headers: { Range: range } }),
      env,
    )
    assert.equal(response.status, 416, `期望 416 for Range=${range}`)
    assert.equal(response.headers.get('Content-Range'), 'bytes */4')
  }
})

test('畸形 percent-encoding 返回 400 而非 500', async () => {
  const env = {
    ARCH_REPO: {
      async get() {
        return { body: 'x', size: 1, httpMetadata: {} }
      },
    },
  }

  const response = await worker.fetch(
    new Request('https://repo.dev/%zz'),
    env,
  )
  assert.equal(response.status, 400)
})
